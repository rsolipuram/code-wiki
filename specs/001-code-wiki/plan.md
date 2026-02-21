# Implementation Plan: AI-Powered Code Wiki Platform

**Branch**: `001-code-wiki` | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)
**Created**: 2026-02-15 | **Last Updated**: 2026-02-21

---

## Plan Overview

Code Wiki is an AI-powered platform that automatically generates and maintains Wikipedia-style documentation for code repositories. It uses a 3-layer analysis architecture (deterministic reconnaissance → parallel facet agents → module wiki synthesis) to produce structured, browsable wiki pages with hyperlinked code entities, architecture diagrams, search, and an AI chat assistant. The MVP covers public GitHub repositories with zero authentication, focusing on Python/JavaScript/TypeScript and delivering documentation within 15 minutes for 50k–100k LOC codebases.

### Implementation Phases

| Phase | Name | Scope | MVP? | Status |
|-------|------|-------|------|--------|
| 0 (Setup) | Project Foundation | Scaffold, Docker, DB connections, health check | ✅ Yes | Done |
| 1 (Foundation) | Core Infrastructure | SQLAlchemy models, Neo4j, Qdrant, Redis, LLM clients | ✅ Yes | Done |
| 2 (US1) | Wiki Generation Pipeline | Parsers, facet agents, wiki synthesis, API, frontend wiki UI | ✅ Yes | Done |
| 3 (US2) | Real-Time Synchronization | Webhook receiver, sync job, partial regeneration | ✅ Yes | Done |
| 4 (US3) | AI Chat Assistant | RAG context builder, chat response generator, chat UI | ✅ Yes | Done |
| 5 (US4) | Visual Diagrams | Architecture/dependency/module relationship diagrams UI | ✅ Yes | Done |
| 6 (Polish) | Quality + Completeness | Login page, link styles, OpenAPI cleanup, artifact fixes | ✅ Yes | Done |
| 7 (Post-MVP) | Production Hardening | Auth, webhooks, multi-tenant, performance, public deploy | ❌ No | Deferred |

**MVP Boundary**: Phases 0–6. All 109 implementation tasks complete as of 2026-02-21.

---

## Technology Stack

> Full rationale in [research.md](./research.md). This table summarizes decisions only.

| Component | Technology | Decision # |
|-----------|-----------|-----------|
| Backend framework | Python 3.11 + FastAPI | Decision 1 |
| Code parsing (JS/TS) | TypeScript Compiler API | Decision 2 |
| Code parsing (Python) | Jedi + Python AST | Decision 2 |
| LLM provider | LM Studio + qwen3-coder-30b (local, 262k ctx) | Decision 3 |
| LLM client | Raw OpenAI SDK (no LangChain wrappers) | Decision 4 |
| Agent orchestration | LangGraph StateGraph | Decision 4 |
| Iterative agents | LangGraph `create_react_agent` | Decision 4 |
| Graph database | Neo4j Community | Decision 6 |
| Vector database | Qdrant (self-hosted Docker) | Decision 5 |
| Embedding model | `all-MiniLM-L6-v2` via sentence-transformers (384-dim) | Decision 5 |
| RDBMS | PostgreSQL 15+ | Decision 7 |
| Job queue | Redis + RQ | Decision 12 |
| Git operations | GitPython | Decision 13 |
| Frontend | React + TypeScript + Next.js (App Router) | Decision 8 |
| Deployment (MVP) | Railway | Decision 11 |

---

## Architecture: 3-Layer System

### Layer Overview

```
LAYER 0 — Repo Reconnaissance   [< 2s, zero LLM]
  Input: repository path
  Output: RepoFingerprint (languages, system type, toolchain, config files)
  Agents: RepoRecon (heuristic-only)

LAYER 1 — Facet Intelligence   [parallel, mixed LLM/heuristic]
  Input: RepoFingerprint + repository source
  Output: Dossier (shared blackboard with all facet findings)
  Agents: TriageAgent + 7 Heuristic + 4 ReAct Iterative + 6 Single-Pass + ConflictSynthesizer

LAYER 2 — Module Wiki Synthesis   [per-module, RAG-assisted]
  Input: module source files + Dossier (RAG query subset)
  Output: structured wiki pages (module narrative, entities, cross-links)
  Agents: StructuralAnalyst + ImplementationExplainer + ModuleWeaver (per module)
```

### The Dossier Invariant

All agents communicate **exclusively** through the Dossier (LangGraph TypedDict state). No agent calls another agent directly. This is the core architectural invariant that keeps the system debuggable and extensible:

- Agents write findings as atomic entries (`DossierEntry`) with `related_files`, `related_modules`, `severity`, and embedded text
- For large repos (800k+ lines): Dossier is indexed into Qdrant after Layer 1; Module Weaver uses RAG to retrieve only the relevant subset
- Progressive writes: ReAct agents write findings mid-loop (not just at end) to enable cross-agent knowledge sharing during parallel execution

### TAG_TRIGGERS: Dynamic Routing

Routing is pure Python — no LLM routing calls. Tags emitted by agents trigger additional specialists via the `TAG_TRIGGERS` static registry:

```python
TAG_TRIGGERS = {
    "pattern:jwt-auth":      ["AuthFlowTracer"],
    "risk:sql-injection":    ["VulnerabilityChainTracer"],
    "has:terraform":         ["IaCAnalyzer"],
    "has:docker":            ["ContainerAnalyzer"],
    "risk:jwt-without-rotation": ["DependencyAuditor"],  # surface CVEs
}
```

### Determinism Foundation

Architecture is **deterministic extraction + AI summarization** (not pure AI generation):

- Layer 0: 100% deterministic (file scanning, regex detection)
- Layer 1 heuristic agents: 100% deterministic (lock file parsing, YAML parsing, etc.)
- Layer 1 single-pass agents: deterministic structure, AI fills human-readable summaries
- Layer 2 `StructuralAnalyst`: 100% deterministic (AST-based entity extraction with interestingness scoring)
- Layer 2 `ImplementationExplainer` + `ModuleWeaver`: AI, but with `evidence_lines` validation

### ConflictSynthesizer

Runs last in Layer 1. Detects contradictions between facets (e.g., SecuritySentinel flags JWT without rotation while AuthFlowTracer reports token refresh working correctly). Generates **questions, not answers** — exposed in the wiki as "Open Questions" for developers to resolve. No ConflictResolutionAgent: show conflicting findings side-by-side with source labels.

---

## Agent Catalog

### Layer 0 — Reconnaissance (1 agent, zero LLM)

| Agent | Type | Output |
|-------|------|--------|
| `RepoRecon` | Heuristic | `RepoFingerprint`: language list, system type, toolchain, config files detected |

### Layer 1 — Triage (1 agent)

| Agent | Type | Output |
|-------|------|--------|
| `TriageAgent` | Single-pass LLM | Execution plan: which agents run, budget, invocation order |

### Layer 1 — Heuristic Facet Agents (7 agents, zero LLM)

| Agent | Reads | Dossier Section |
|-------|-------|-----------------|
| `DependencyAuditor` | lock files → OSV.dev CVE lookup | `dependency_analysis` |
| `ContainerAnalyzer` | Dockerfile, docker-compose | `container_topology` |
| `IaCAnalyzer` | Terraform, K8s, Helm | `iac_resources` |
| `APIContractExtractor` | OpenAPI, .proto, .graphql | `api_contracts` |
| `CIPipelineAnalyzer` | GitHub Actions, Jenkinsfile | `ci_pipeline` |
| `OwnershipExtractor` | CODEOWNERS, git blame | `ownership` |
| `FeatureFlagMapper` | LaunchDarkly/Unleash patterns | `feature_flags` |

### Layer 1 — ReAct Iterative Agents (4 agents, LangGraph `create_react_agent`)

| Agent | Trigger Condition | Dossier Section |
|-------|-------------------|-----------------|
| `SecuritySentinel` | Always (security-relevant repos) | `security_findings` |
| `DataFlowTracer` | Always (data transformation code) | `data_flows` |
| `AuthFlowTracer` | Tag: `pattern:jwt-auth` | `security_findings` |
| `VulnerabilityChainTracer` | Tag: `risk:sql-injection` | `security_findings` |

**ReAct Termination Safeguards** (required for all iterative agents):
- Hard iteration cap: **30 steps** per agent
- Time limit: **5 minutes** per agent
- Visited-set tracking: no file re-reads within a single run
- Hierarchical guidance: TriageAgent provides file priority hints to bound search space
- Cost monitoring: abort if accumulated LLM tokens exceed per-agent budget

### Layer 1 — Single-Pass LLM Agents (6 agents)

| Agent | Output |
|-------|--------|
| `ArchitecturalClassifier` | System style, design patterns (CQRS, Event Sourcing, Layered, etc.) |
| `BusinessRuleExtractor` | Plain-English domain rules mapped to code locations |
| `ObservabilityAuditor` | Logging/metrics/tracing gaps and coverage |
| `ErrorResilienceAnalyzer` | Error handling strategy, retry patterns, failure modes |
| `TechnicalDebtAssessor` | Debt items, complexity hotspots, TODO/FIXME density |
| `PerformanceHotspotScanner` | N+1 queries, blocking I/O, caching gaps |

### Layer 1 — Synthesis (1 agent, runs last)

| Agent | Output |
|-------|--------|
| `ConflictSynthesizer` | Questions (not answers) where facet findings contradict each other |

### Layer 2 — Module Wiki Sub-Pipeline (3 agents, per module)

| Agent | Type | Output |
|-------|------|--------|
| `StructuralAnalyst` | AST-based, zero LLM | Entity list with interestingness scores + canonical hash |
| `ImplementationExplainer` | Parallel LLM calls (dynamic N) | Per-entity: purpose, how-it-works, gotchas with `evidence_lines` |
| `ModuleWeaver` | Single-pass LLM synthesis | Coherent module narrative from Dossier findings + entity explanations |

**Phase 7 expansion agents** (flagged in CLAUDE.md, not yet in directory structure):
- `TestCoverageAnalyzer` (heuristic)
- `DataLifecycleAnalyzer` (heuristic + LLM)
- `DesignPatternDetector` (LLM)

---

## Wiki Generation Pipeline

### 3-Agent Pipeline (per module)

**Agent 1 — StructuralAnalyst** (pure AST, no LLM):
- Parses all files in module using language-specific parsers
- Extracts all functions, classes, methods with signatures
- Scores each entity by **interestingness** (see below)
- Computes canonical hash (AST hash) for change detection
- Output: ranked entity list, module structure summary

**Interestingness Scoring** (rule-based, no LLM):
- High call-in-degree (many callers across codebase)
- Cyclomatic complexity above threshold
- Cross-module dependencies (imported by other modules)
- Public API surface area (exported, non-private)
- Unusual patterns (decorators, generators, context managers, async)
- Score threshold is **dynamic** — not a fixed top-15 cap

**Agent 2 — ImplementationExplainer** (parallel LLM calls):
- Selects top-N entities by interestingness score (dynamic threshold)
- Each call provides: function signature + docstring + body + **class body context** (methods need surrounding class)
- Prompt answers "why does this exist?" not just "what does it do?"
- **Evidence validation**: all `gotchas` entries must include `evidence_lines` pointing to real source lines
- Output: per-entity explanation dict with `purpose`, `how_it_works`, `gotchas`, `evidence_lines`

**Agent 3 — ModuleWeaver** (single synthesis call):
- Input: StructuralAnalyst report + ImplementationExplainer explanations + Dossier RAG results
- Produces: module narrative (purpose, design patterns, data flow, known gotchas)
- Optional additional pass: architectural patterns prompt for emergent cross-entity patterns

### Partial Regeneration (incremental sync)

On commit webhook:
1. Detect changed files via `UpdateEvent.changed_files`
2. Find affected modules (file overlap with `Module.file_paths`)
3. Re-run `StructuralAnalyst` on affected modules → compare canonical hash
4. Re-run `ImplementationExplainer` only for changed entities (not unchanged)
5. Always re-run `ModuleWeaver` (narrative must reflect full updated state)

Cost: ~20–40 LLM calls vs ~400–500 for full analysis.

### Blackboard-Based Triage (edge case handling)

For novel/complex modules beyond the fixed 3-agent pipeline:
- `TriageAgent` classifies module upfront, decides which specialist agents to invoke
- Specialist agents write findings to shared Dossier, never call each other directly
- Tags trigger additional specialists via `TAG_TRIGGERS` registry
- RFI Protocol: agents flag unknowns without spawning uncontrolled sub-agents
- Designed for ~10–20s local inference latency (qwen3-coder-30b)

---

## LLM Call Budget

| Stage | Calls (typical 20-module repo) |
|-------|-------------------------------|
| TriageAgent | 1 |
| Single-pass facet agents (6) | ~6 |
| ReAct iterative agents (4 × up to 30 steps) | ~60–120 |
| Module wiki per module: ImplementationExplainer + ModuleWeaver | ~17 × 20 modules = ~340 |
| **Total first run** | **~400–500** |
| **Subsequent syncs (only changed modules)** | **~20–40** |

Cache strategy: Redis caches LLM responses keyed by `(prompt_hash, model)` with 24h TTL. Repeat analysis of unchanged modules hits cache.

---

## Project Structure

```
code-wiki/
├── docker-compose.yml          # PostgreSQL, Neo4j, Qdrant, Redis
├── specs/001-code-wiki/        # Specification artifacts
│   ├── plan.md                 # This file
│   ├── spec.md                 # Feature requirements
│   ├── research.md             # Technology decisions
│   ├── data-model.md           # Entity schemas
│   ├── quickstart.md           # Dev setup guide
│   ├── tasks.md                # 109-task implementation list (all complete)
│   ├── contracts/openapi.yaml  # REST API specification
│   └── ux/docs-glassmorphism/  # 15-page mock set

backend/
└── src/
    ├── config.py               # Pydantic BaseSettings from .env
    ├── parsers/                # Language-specific code parsers
    │   ├── base.py             # CodeParser ABC
    │   ├── python_parser.py    # Jedi + AST
    │   └── typescript_parser.py # TypeScript Compiler API (via subprocess)
    │
    ├── recon/                  # Layer 0: Repo Reconnaissance
    │   ├── repo_recon.py       # File tree, language detection
    │   ├── fingerprint.py      # RepoFingerprint dataclass
    │   └── config_detector.py  # Docker, CI, IaC, package manifest detection
    │
    ├── dossier/                # Shared Blackboard (LangGraph State)
    │   ├── schema.py           # Dossier TypedDict + DossierEntry Pydantic
    │   └── manager.py          # DossierManager: write/query interface
    │
    ├── agents/                 # Layer 1: Facet Intelligence
    │   ├── triage/triage_agent.py
    │   ├── heuristic/          # Rule-based (no LLM)
    │   ├── iterative/          # ReAct via create_react_agent
    │   ├── single_pass/        # Single LLM call agents
    │   ├── conflict_synthesizer.py
    │   └── primitives/         # Shared tools: file_reader, ast_parser, etc.
    │
    ├── orchestrator/           # LangGraph StateGraph wiring
    │   ├── graph.py            # StateGraph definition + edges
    │   ├── routing.py          # Conditional edge functions (pure Python)
    │   └── tag_triggers.py     # TAG_TRIGGERS registry
    │
    ├── wiki/                   # Layer 2: Module Wiki Synthesis
    │   ├── orchestrator.py     # Per-module pipeline + partial_regenerate()
    │   ├── interestingness.py  # Entity scoring for Agent 2 selection
    │   └── page_builders/
    │       ├── module_page.py  # Module wiki page builder
    │       ├── home_page.py    # Repo wiki home builder
    │       ├── special_pages.py # Glossary, API reference, getting-started
    │       └── diagrams.py     # Architecture/dependency/module diagram data
    │
    ├── chat/                   # AI Chat
    │   ├── context_builder.py  # RAG retrieval from Qdrant
    │   └── assistant.py        # LLM response generation
    │
    ├── jobs/                   # Background Jobs (RQ)
    │   ├── analyze.py          # Full repository analysis job
    │   ├── sync.py             # Incremental sync job (webhook-triggered)
    │   └── worker.py           # RQ worker entrypoint
    │
    ├── api/                    # FastAPI REST API
    │   ├── main.py             # App setup, CORS, router registration
    │   ├── deps.py             # Shared dependencies (DB session, etc.)
    │   ├── routes/
    │   │   ├── repositories.py # CRUD + /refresh + /status
    │   │   ├── wikis.py        # Wiki pages, modules, entities, diagrams
    │   │   ├── chat.py         # Conversations + messages
    │   │   ├── search.py       # Semantic search
    │   │   └── webhooks.py     # GitHub/GitLab webhook receiver
    │   └── schemas/            # Pydantic response/request models
    │
    ├── storage/                # Database clients
    │   ├── graph_db.py         # Neo4j driver + relationship queries
    │   ├── vector_db.py        # Qdrant client + collection management
    │   ├── repo_cache.py       # GitPython: clone/pull/list_files
    │   └── cache.py            # Redis get/set/delete with TTL
    │
    ├── llm/                    # LLM utilities
    │   ├── client.py           # LM Studio OpenAI-compatible client + caching
    │   └── embeddings.py       # sentence-transformers all-MiniLM-L6-v2
    │
    └── models/                 # SQLAlchemy ORM models
        ├── repository.py       # Repository, RepositoryStatus
        ├── wiki.py             # Wiki, WikiPage, WikiPageType
        ├── code_entity.py      # Module, CodeEntity, EntityType
        └── events.py           # ChatConversation, UpdateEvent, UpdateEventStatus

frontend/
└── src/
    ├── app/                    # Next.js App Router
    │   ├── layout.tsx          # Root layout (Outfit font, globals.css)
    │   ├── page.tsx            # Landing / redirect
    │   ├── globals.css         # Glassmorphism design system
    │   ├── not-found.tsx       # 404 error state
    │   ├── error.tsx           # Generic error boundary
    │   ├── login/              # /login
    │   ├── submit/             # /submit
    │   ├── dashboard/          # /dashboard
    │   └── [owner]/[name]/     # /[owner]/[name] — wiki root
    │       ├── page.tsx        # Wiki home
    │       ├── progress/       # /progress — analysis pipeline status
    │       ├── modules/[slug]/ # /modules/[slug] — module page
    │       ├── getting-started/# /getting-started
    │       ├── search/         # /search
    │       ├── chat/           # /chat
    │       ├── diagrams/       # /diagrams
    │       ├── glossary/       # /glossary
    │       ├── api/            # /api — API reference
    │       └── entities/[name]/# /entities/[name] — function/class detail
    ├── components/
    │   ├── ui/                 # GradientBackground, GlassCard, Logo, etc.
    │   └── layout/             # WikiSidebar, TableOfContents
    └── services/api.ts         # Typed API client for all backend endpoints
```

---

## Phase Details

### Phase 0: Project Foundation

**Scope**: Scaffold, Docker Compose, database connections, health check
**Deliverables**:
- `docker-compose.yml` with PostgreSQL 15, Neo4j 5.16, Qdrant latest, Redis 7
- Backend project structure with `requirements.txt` (FastAPI, SQLAlchemy, etc.)
- Next.js frontend with TypeScript strict mode, Outfit + Fira Code fonts
- `backend/src/config.py` Pydantic BaseSettings loading from `.env`
- `GET /health` endpoint reporting service status for all 4 databases
- `.gitignore` covering all generated/secret files

**Test Criteria**: `docker-compose up -d` → all services healthy; `curl /health` → JSON with all services OK; `npm run dev` starts on port 3000.

---

### Phase 1: Core Infrastructure

**Scope**: SQLAlchemy models, Neo4j client, Qdrant client, Redis cache, LM Studio client, embedding utility, GitPython, CodeParser ABC, RQ worker, FastAPI skeleton, Pydantic schemas, frontend API client

**Deliverables** (all in `backend/src/`):
- 7 SQLAlchemy models matching data-model.md entity definitions
- Alembic migration for all 7 tables
- Neo4j connection manager with CALLS/IMPORTS/INHERITS_FROM relationship ops
- Qdrant wrapper with `code_entities` + `dossier_findings` collections (384-dim, Cosine)
- Redis cache with TTL support
- LM Studio client (`localhost:1234/v1`) with retry + Redis response caching
- Sentence-transformers embedding utility (384-dim, batch support)
- GitPython repo cache (clone/pull/list_files)
- `CodeParser` ABC with `parse_file()`, `resolve_imports()`, `get_call_graph()`
- RQ worker with 15-minute job timeout
- FastAPI app with CORS, error handlers, all 5 routers registered
- Pydantic schemas for all openapi.yaml components
- Frontend `api.ts` with typed methods for all endpoints

**Test Criteria**: All imports succeed; Qdrant upsert/search works; Neo4j node/relationship CRUD works; LM Studio client returns completion; health endpoint shows all services OK.

**Dependencies**: Phase 0 complete.

---

### Phase 2: User Story 1 — Automatic Wiki Generation (MVP Core)

**Scope**: Full code analysis pipeline, wiki generation, API endpoints, frontend wiki UI (9 pages)

**Deliverables**:

*Analysis pipeline*:
- Python parser (Jedi + AST): `parse_file`, `resolve_imports`, `get_call_graph`
- TypeScript parser (Compiler API via subprocess): same interface
- Repo Recon: file tree scan, language detection, `RepoFingerprint`
- Dossier schema + manager (LangGraph TypedDict state)
- Layer 1 heuristic agents: `ArchitectureAnalyzer`, `DependencyAuditor`, `CICDAnalyzer`
- Layer 2 `StructuralAnalyst`: AST entity extraction + interestingness scoring
- Layer 2 `ImplementationExplainer`: parallel LLM calls with evidence validation
- Layer 2 `ModuleWeaver`: narrative synthesis from Dossier + entity explanations
- `jobs/analyze.py`: full analysis job (recon → entities → dossier → wiki)
- Wiki page builders: `module_page.py`, `home_page.py`, `special_pages.py`

*API*:
- `POST /v1/repositories` — submit URL, enqueue analysis job
- `GET /v1/repositories` — list with status/pagination
- `GET /v1/repositories/{id}` — repo detail
- `GET /v1/wikis/{id}` — wiki metadata
- `GET /v1/wikis/{id}/pages` — list pages by type
- `GET /v1/wikis/{id}/pages/{slug}` — page content
- `GET /v1/wikis/{id}/modules` — module list
- `GET /v1/wikis/{id}/modules/{slug}` — module detail
- `GET /v1/search/{id}?q=...` — semantic search via Qdrant

*Frontend* (9 pages):
- `/submit` — URL input, provider detection, submit form
- `/[owner]/[name]/progress` — animated analysis pipeline with live status polling
- `/dashboard` — repository list with sync status, actions
- `/[owner]/[name]` — wiki home (stats, quick links, module cards)
- `/[owner]/[name]/modules/[slug]` — 3-column module wiki (sidebar, content, TOC)
- `/[owner]/[name]/getting-started` — step cards, prerequisites
- `/[owner]/[name]/glossary` — alphabetical term browser with live search
- `/[owner]/[name]/api` — API reference with alphabetical index
- `/[owner]/[name]/search` — search results with filter sidebar

**Test Criteria**: Submit a Python repo → analysis completes → wiki home shows modules → module page shows entities → search returns results.

**Dependencies**: Phase 1 complete.

---

### Phase 3: User Story 2 — Real-Time Synchronization

**Scope**: Webhook receiver, incremental sync job, repository status endpoint

**Deliverables**:
- `POST /v1/repositories/{id}/webhook` — GitHub/GitLab push event receiver
- Webhook signature verification (HMAC-SHA256)
- `UpdateEvent` creation on push, job enqueue via RQ
- `jobs/sync.py`: supersede older events → pull latest → find affected modules → partial_regenerate → update WikiPage content + commit_hash
- `GET /v1/repositories/{id}/status` — status + latest UpdateEvent summary
- Frontend progress page polls `/status` every 5s

**Test Criteria**: Simulate webhook push → `UpdateEvent` created → sync job runs → affected module wiki pages updated → `/status` shows completed event.

**Dependencies**: Phase 2 complete.

---

### Phase 4: User Story 3 — AI Chat Assistant

**Scope**: RAG context retrieval, chat response generation, chat UI

**Deliverables**:
- `chat/context_builder.py`: embed question → Qdrant search on `code_entities` + `dossier_findings` → format context + references
- `chat/assistant.py`: system prompt + context + history → LM Studio → response with references
- `POST /v1/chat/{repo_id}/conversations` — create conversation
- `GET /v1/chat/{repo_id}/conversations` — list conversations
- `POST /v1/chat/conversations/{id}/messages` — send message → RAG → generate response
- `/[owner]/[name]/chat` — full-height chat UI with suggestion chips, message bubbles, typing indicator, auto-scroll

**Test Criteria**: Ask "what does the auth module do?" → response references correct entities → follow-up question uses conversation history.

**Dependencies**: Phase 2 complete (needs entities indexed in Qdrant).

---

### Phase 5: User Story 4 — Visual Diagrams

**Scope**: Diagram data generation, diagrams UI page

**Deliverables**:
- `wiki/page_builders/diagrams.py`: `build_diagrams()` → architecture, dependency_graph, module_relationships data
- Architecture diagram: modules as tiered nodes (frontend/api/service/data), edges from `dependency_module_ids`
- Dependency graph: Neo4j `CALLS` relationships between modules, bubble node sizing by call_count
- Module relationships: compact card grid with dep count from adjacency map
- `GET /v1/wikis/{id}/diagrams` — returns `DiagramsResponse`
- `/[owner]/[name]/diagrams` — 3-tab diagram page with node legend, clickable nodes

**Test Criteria**: Diagrams endpoint returns non-empty data → architecture tab shows module nodes → clicking a node navigates to the module page.

**Dependencies**: Phase 2 complete (needs modules in DB).

---

### Phase 6: Polish + Completeness

**Scope**: Login page, content link styles, OpenAPI cleanup, data-model artifact fix

**Deliverables**:
- `/login` — OAuth buttons (GitHub/GitLab/Bitbucket stubs) + email/password form (MVP UI-only)
- `globals.css` `.content-body a` — `text-underline-offset: 3px` + cyan/purple link colors
- `openapi.yaml` — BearerAuth security scheme removed (MVP has no auth)
- `data-model.md` — pgvector section replaced with Qdrant (384-dim, 3 collections)

**Test Criteria**: `/login` matches `login.html` mock; inline links are cyan with purple hover; `/docs` Swagger UI shows no auth requirement; data-model.md references Qdrant not pgvector.

**Dependencies**: Phases 0–5 complete.

---

### Phase 7: Post-MVP Production Hardening (Deferred)

**Out of scope for MVP.** Planned capabilities:

| Feature | Why Deferred |
|---------|-------------|
| GitHub OAuth authentication | Adds complexity; MVP is public repos only |
| GitHub App webhook endpoint | Requires OAuth app registration |
| Private repository access | Requires token management + OAuth flow |
| Multi-tenant isolation | Not needed for single-operator MVP |
| Multi-dimensional wiki views (security, infra, domain) | Dossier built, views not wired to frontend |
| Production deployment (Railway → AWS) | Infrastructure work after MVP validation |
| Real-time WebSocket chat | SSE or polling sufficient for MVP |
| Phase 7 expansion agents (TestCoverage, DataLifecycle, DesignPattern) | Can be added incrementally |

---

## Artifact Gap Tracker

Tracks known inconsistencies across spec artifacts. Updated 2026-02-21.

| Artifact | Gap | Phase | Status |
|----------|-----|-------|--------|
| `data-model.md` | ~~pgvector reference~~ replaced with Qdrant | Phase 1 | ✅ Fixed (T109) |
| `openapi.yaml` | ~~BearerAuth~~ removed (MVP no auth) | Phase 5 | ✅ Fixed (T108) |
| `data-model.md` | ~~No Dossier schema~~ added `DossierEntry`, `RepoFingerprint` (entity 8) | Phase 1 | ✅ Fixed (2026-02-21) |
| `openapi.yaml` | ~~No webhook endpoint~~ added `POST /repositories/{id}/webhook` | Phase 7 | ✅ Fixed (2026-02-21) |
| `openapi.yaml` | ~~`GET /repositories/{id}/status` missing~~ — added with `RepositoryStatus` schema | Phase 3 | ✅ Fixed (2026-02-21) |
| `openapi.yaml` | ~~No diagrams endpoint~~ added `GET /wikis/{id}/diagrams` with `DiagramsResponse` schema | Phase 5 | ✅ Fixed (2026-02-21) |
| `openapi.yaml` | No multi-dimensional wiki view endpoints (security, infra, domain) | Phase 7 | ⚠ Open (post-MVP) |
| `plan.md` | Agent names: CLAUDE.md uses `ArchitectureAnalyzer`; plan uses `ArchitecturalClassifier` | — | ⚠ Standardize on `ArchitecturalClassifier` (matches directory) |

---

## MVP Scope Boundary

All scope decisions from spec.md and research.md, consolidated:

**Included in MVP**:
- Public GitHub repositories only (no auth required)
- Languages: Python, JavaScript, TypeScript
- Repository size: 1k–1M lines of code
- Wiki page types: home, module, getting-started, glossary, API reference, function detail
- AI chat with RAG (repository-scoped conversations)
- Visual diagrams (architecture, dependency graph, module relationships)
- Real-time sync via webhook (push events only)
- Zero external API costs (fully self-hosted: LM Studio + Qdrant + Neo4j)

**Excluded from MVP**:
- User authentication and accounts
- Private repositories and access tokens
- GitHub App integration (OAuth flow)
- Multi-tenant access control
- Multi-dimensional domain/security/infra wiki views (Dossier built, views deferred)
- Production deployment and scaling
- WebSockets for real-time chat
- Java, Go, Ruby, and other language parsers (architecture supports, not implemented)
- Git blame and commit attribution
- PR description generation

---

## Performance Targets

Derived from `spec.md` success criteria. All must be validated before production release.

| Metric | Target | Source |
|--------|--------|--------|
| Initial wiki generation (50k–100k LOC) | < 15 minutes | SC-001 |
| Wiki page update after commit | < 5 minutes | SC-011 |
| Search response time | < 2 seconds | SC-013 |
| Code entity link accuracy | 95%+ precision | SC-006 |
| Module detection accuracy | 85%+ | SC-008 |
| Wiki sync drift | < 1% | SC-012 |
| Concurrent repository analyses | 50+ | SC-017 |

ReAct iterative agents MUST enforce termination safeguards (30-step cap, 5-minute timeout, visited-set) — these directly enable the concurrent analysis target.

---

## UX Design System

### Glassmorphism Design Variables

```css
--primary: #8B5CF6;        /* Purple — primary brand, active states */
--primary-light: #A78BFA;  /* Light purple — hover links, active tab text */
--secondary: #06B6D4;      /* Cyan — inline content links (default) */
--accent: #EC4899;         /* Pink — accent highlights */
--bg-dark: #0A0A0F;
--bg-darker: #050508;
--glass-bg: rgba(15, 15, 25, 0.7);
--glass-border: rgba(255, 255, 255, 0.1);
--text-primary: #F9FAFB;
--text-secondary: #D1D5DB;
--text-tertiary: #9CA3AF;
```

**Glass Card** (`.glass-card`): `backdrop-filter: blur(20px)` + `border: 1px solid var(--glass-border)` + `border-radius: 20px` + `box-shadow: 0 8px 32px rgba(0,0,0,0.37)`

**Inline Content Links** (`.content-body a`): default `var(--secondary)` (#06B6D4), hover `var(--primary-light)` (#A78BFA). Scoped to avoid nav/sidebar/button links.

**Typography**: Outfit (body), Fira Code (code/monospace). Both loaded via `next/font/google`.

### 15-Page Mock Mapping

| Mock file | Route | Key Components | Status |
|-----------|-------|---------------|--------|
| `index.html` | `/` | Navigation hub | ✅ |
| `home.html` | `/[owner]/[name]` | RepoHeader, StatsGrid, ModuleCards, QuickLinks | ✅ |
| `module.html` | `/[owner]/[name]/modules/[slug]` | WikiSidebar, TableOfContents, 3-col layout | ✅ |
| `function.html` | `/[owner]/[name]/entities/[name]` | SignatureBlock, ParamsTable, CallGraph | ✅ |
| `search.html` | `/[owner]/[name]/search` | SearchBar, FilterSidebar, ResultCards | ✅ |
| `chat.html` | `/[owner]/[name]/chat` | MessageBubble, TypingIndicator, SuggestionChips | ✅ |
| `getting-started.html` | `/[owner]/[name]/getting-started` | StepCards, PrereqChecklist | ✅ |
| `glossary.html` | `/[owner]/[name]/glossary` | AlphaNav, TermCards, live search | ✅ |
| `api-reference.html` | `/[owner]/[name]/api` | AlphaIndex, EndpointCards | ✅ |
| `diagrams.html` | `/[owner]/[name]/diagrams` | ArchDiagram, DepGraph, RelGraph tabs | ✅ |
| `progress.html` | `/[owner]/[name]/progress` | PipelineSteps, LiveStats, CompletionState | ✅ |
| `dashboard.html` | `/dashboard` | RepoList, StatusBadge, ActionMenu | ✅ |
| `submit.html` | `/submit` | URLInput, ProviderDetector, SubmitForm | ✅ |
| `login.html` | `/login` | OAuthButtons, EmailForm, FormLinks | ✅ |
| `error.html` | `/not-found`, `/error` | ErrorState404, FailureState | ✅ |

### Mobile Breakpoints

| Breakpoint | Behavior |
|-----------|---------|
| `< 1400px` | Right TOC sidebar hidden |
| `< 900px` | Left sidebar becomes fixed slide-in drawer; hamburger topbar shown; `.wiki-layout` collapses to single column |
| `< 768px` | Orb sizes reduced; stats grid single-column |
| `< 480px` | Phone optimizations: stacked layouts, smaller fonts |

---

## Planning Status

| Milestone | Status | Date |
|-----------|--------|------|
| Requirements + spec | ✅ Complete | 2026-02-15 |
| Technology research | ✅ Complete | 2026-02-15 |
| Architecture + agent design | ✅ Complete | 2026-02-18 |
| 15-page glassmorphism mock set | ✅ Complete | 2026-02-16 |
| 3-agent wiki pipeline design (Gemini-reviewed) | ✅ Complete | 2026-02-18 |
| 109-task implementation list | ✅ Complete | 2026-02-19 |
| **All 109 tasks implemented** | ✅ Complete | 2026-02-21 |
| Phase 7 post-MVP planning | ⏳ Pending | — |
| Production deployment | ⏳ Pending | — |

**Next steps for Phase 7**:
1. Add GitHub App OAuth integration (auth, private repo access)
2. Implement multi-dimensional wiki views wired to Dossier findings
3. Add missing Phase 7 agents (TestCoverage, DataLifecycle, DesignPattern)
4. Add webhook endpoint to openapi.yaml + implement full GitHub App webhook
5. Deploy to Railway for MVP validation with real users
