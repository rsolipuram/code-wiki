# Implementation Plan: AI-Powered Code Wiki Platform

**Branch**: `001-code-wiki` | **Date**: 2026-02-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-code-wiki/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build an automatic code documentation platform that generates and maintains comprehensive, structured wikis for code repositories. The system analyzes codebases to automatically create Wikipedia-like documentation with organized pages for modules, systems, and components. Key capabilities include:

- **Automatic wiki generation**: Parse repositories and generate structured documentation pages (home, module pages, getting started, API reference, glossary)
- **AI-driven module detection**: Automatically identify logical modules, classify orphaned files, and group cross-cutting utilities
- **Hyperlinked navigation**: All code entities (functions, classes, modules) link to their definitions and related pages
- **Real-time synchronization**: Wiki updates automatically when code changes
- **AI chat interface**: Natural language Q&A over the codebase with links to wiki pages
- **Multi-language support**: Python, JavaScript, TypeScript initially (architecture supports expansion)

## Technical Context

**Language/Version**: Python 3.11+ (backend services and code parsing)
**Primary Dependencies**:
- Code parsing: TypeScript Compiler API (JS/TS), Jedi + Python AST (Python) - language-specific for accuracy
- Web framework: FastAPI (async Python web framework)
- LLM integration: **LM Studio + qwen3-coder-30b** (local self-hosted, 30B params, 262k context window, zero cost)
- LLM client: **Raw OpenAI SDK** (direct API, no LangChain wrappers)
- Agent orchestration: **LangGraph StateGraph** (Dossier as managed state, conditional edges, parallel execution)
- Iterative agents: **LangGraph create_react_agent** (ReAct loops for SecuritySentinel, DataFlowTracer)
- Graph storage: Neo4j Community (graph database for code relationships)
- Vector database: **Qdrant** (semantic search + Dossier RAG index for module wiki context retrieval)
- Frontend: React + TypeScript + Next.js (wiki UI with SSR)

**Storage**:
- Graph database for code entity relationships and module structure (Neo4j Community)
- Vector database for semantic search and embeddings (Qdrant self-hosted)
- Object storage or file system for repository cache (local filesystem MVP)
- RDBMS for repository metadata (PostgreSQL 15+)

**Testing**: pytest (unit, integration, contract tests)

**Target Platform**: Cloud-based web application (Linux containers), Railway (MVP) → AWS (Production)

**Project Type**: Web application (backend API + frontend wiki UI)

**Performance Goals**:
- Parse 50k-100k line repository in <15 minutes (SC-001)
- Wiki page generation: <5 minutes for updates (SC-002, SC-011)
- Search response time: <2 seconds (SC-013)
- Support 50+ concurrent repository analyses (SC-017)

**Constraints**:
- Multi-language parsing accuracy: 95%+ for code entity linking (SC-006)
- Automatic module detection: 85%+ accuracy (SC-008)
- Wiki synchronization drift: <1% (SC-012)
- Memory-efficient: Handle 1M+ line repositories

**Scale/Scope**:
- MVP: 3 languages (Python, JavaScript, TypeScript)
- Repository size: 1k to 1M lines of code
- Concurrent users: 100+ browsing wikis
- Concurrent parsing: 50+ repositories

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: ✅ **PASS** (No constitution defined - proceeding with standard best practices)

**Note**: Constitution file (`.specify/memory/constitution.md`) contains template only. Project will follow standard engineering principles:
- Modular architecture with clear separation of concerns
- Test-driven development where practical
- API-first design with documented contracts
- Observability and monitoring built-in
- MVP scope: Public repositories only (no authentication required)

**Post-Design Re-check**: Will validate after Phase 1 that design adheres to spec requirements and avoids unnecessary complexity.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── parsers/                    # Multi-language code parsing (Layer 1 + 2 input)
│   │   ├── base.py                 # CodeParser abstract base class
│   │   ├── python_parser.py        # Jedi + AST
│   │   ├── javascript_parser.py    # TypeScript Compiler API
│   │   └── typescript_parser.py
│   │
│   ├── recon/                      # LAYER 1: Repo Reconnaissance (no LLM)
│   │   ├── repo_recon.py           # File tree scan, language detection
│   │   ├── fingerprint.py          # RepoFingerprint dataclass
│   │   └── config_detector.py      # Detects Docker, CI, IaC, package files
│   │
│   ├── dossier/                    # Shared Blackboard (LangGraph State)
│   │   ├── schema.py               # Dossier + all nested Pydantic models
│   │   ├── manager.py              # DossierManager: write/query interface
│   │   └── rag_index.py            # Index Dossier findings into Qdrant for RAG
│   │
│   ├── agents/                     # LAYER 2: Facet Intelligence Agents
│   │   ├── triage/
│   │   │   └── triage_agent.py     # Reads fingerprint, produces execution plan
│   │   ├── heuristic/              # No LLM — pure parsing/heuristics
│   │   │   ├── dependency_auditor.py    # lock files + OSV.dev CVE lookup
│   │   │   ├── container_analyzer.py   # Dockerfile, docker-compose
│   │   │   ├── iac_analyzer.py         # Terraform, K8s, Helm
│   │   │   ├── api_contract_extractor.py # OpenAPI, proto, GraphQL
│   │   │   ├── ci_pipeline_analyzer.py  # GitHub Actions, Jenkinsfile
│   │   │   ├── ownership_extractor.py   # CODEOWNERS, git blame
│   │   │   └── feature_flag_mapper.py   # LaunchDarkly, Unleash patterns
│   │   ├── iterative/              # ReAct loop agents (LangGraph create_react_agent)
│   │   │   ├── security_sentinel.py     # Auth/authz flows, PII, input validation
│   │   │   ├── data_flow_tracer.py      # Data lineage through transformations
│   │   │   ├── auth_flow_tracer.py      # JWT lifecycle, token refresh chains
│   │   │   └── vuln_chain_tracer.py     # Call chain from vulnerable fn to entry
│   │   ├── single_pass/            # Single LLM call agents
│   │   │   ├── architectural_classifier.py
│   │   │   ├── business_rule_extractor.py
│   │   │   ├── observability_auditor.py
│   │   │   ├── error_resilience_analyzer.py
│   │   │   ├── technical_debt_assessor.py
│   │   │   └── performance_hotspot_scanner.py
│   │   ├── conflict_synthesizer.py # Runs last — generates questions, not answers
│   │   └── primitives/             # Capability primitives for Triage composition
│   │       ├── file_reader.py
│   │       ├── ast_parser_tool.py
│   │       ├── pattern_matcher.py
│   │       ├── security_lens.py
│   │       └── structured_output_writer.py
│   │
│   ├── orchestrator/               # LangGraph workflow
│   │   ├── graph.py                # StateGraph definition + all edges
│   │   ├── routing.py              # Heuristic conditional edge functions
│   │   └── tag_triggers.py         # TAG_TRIGGERS registry
│   │
│   ├── wiki/                       # LAYER 3: Module Wiki Generation
│   │   ├── orchestrator.py         # Per-module wiki generation workflow
│   │   ├── context_builder.py      # RAG over Dossier + direct source strategy
│   │   ├── page_builders/
│   │   │   ├── module_page.py      # Main module wiki page
│   │   │   ├── home_page.py        # Repo wiki home
│   │   │   ├── dashboard.py        # Health scorecard from Dossier
│   │   │   ├── security_view.py    # Security facet view
│   │   │   ├── infra_view.py       # Infrastructure facet view
│   │   │   └── domain_view.py      # Business rules + domain view
│   │   └── interestingness.py      # Entity scoring for Agent 2 selection
│   │
│   ├── graph/                      # Neo4j code relationship graph
│   │   ├── models.py
│   │   └── queries.py
│   ├── chat/                       # AI chat interface
│   │   ├── assistant.py
│   │   └── context_builder.py
│   ├── api/                        # REST API
│   │   ├── routes/
│   │   │   ├── repositories.py
│   │   │   ├── wiki.py
│   │   │   └── chat.py
│   │   └── schemas/
│   ├── storage/
│   │   ├── graph_db.py
│   │   ├── vector_db.py             # Qdrant: code embeddings + Dossier RAG index
│   │   └── repo_cache.py
│   └── models/
│       ├── repository.py
│       ├── wiki_page.py
│       └── code_entity.py
└── tests/
    ├── contract/
    ├── integration/
    └── unit/

frontend/
├── src/
│   ├── components/
│   │   ├── wiki/            # Wiki browsing components
│   │   │   ├── WikiPage.tsx
│   │   │   ├── Navigation.tsx
│   │   │   └── CodeLink.tsx
│   │   ├── search/          # Search interface
│   │   └── chat/            # Chat interface
│   ├── pages/
│   │   ├── home.tsx
│   │   ├── repository.tsx
│   │   └── wiki-page.tsx
│   └── services/
│       └── api.ts           # Backend API client
└── tests/

shared/
└── contracts/               # API contracts (OpenAPI/GraphQL schemas)
```

**Structure Decision**: Web application architecture selected based on requirements for:
- Backend API for repository analysis, wiki generation, and chat
- Frontend UI for browsing wiki, search, and chat interface
- Shared contracts to maintain API consistency between frontend and backend

## Multi-Agent Architecture

### The 3-Layer System

```
LAYER 1: Repo Reconnaissance  ← heuristics only, zero LLM, <2s
    Output: RepoFingerprint (language, system type, tools present)

LAYER 2: Facet Intelligence   ← parallel agents, each examines ONE dimension
    Heuristic agents: DependencyAuditor, ContainerAnalyzer, IaCAnalyzer,
                      APIContractExtractor, CIPipelineAnalyzer, OwnershipExtractor
    ReAct (iterative): SecuritySentinel, DataFlowTracer, AuthFlowTracer
    Single-pass LLM:   ArchitecturalClassifier, BusinessRuleExtractor,
                       ObservabilityAuditor, TechnicalDebtAssessor
    Runs last:         ConflictSynthesizer (generates questions, never resolves)
    Output: Dossier (shared blackboard) → indexed into Qdrant for RAG

LAYER 3: Module Wiki Generation  ← per module, RAG-assisted LLM
    Input: module source + Dossier RAG query results
    Output: multi-dimensional wiki pages (code + security + infra + domain context)
```

### Agent Communication: Only Through the Dossier

Agents never call each other directly. All communication is through the Dossier (LangGraph State). This is the core invariant that keeps the system debuggable and extensible.

### Routing: Heuristic Only

All routing decisions are pure Python reading Dossier state. No LLM routing calls mid-pipeline. Tag-based triggers (`TAG_TRIGGERS` registry) handle emergent discovery.

### LangChain Deep Agents (ReAct)

Iterative facet agents use `create_react_agent` from LangGraph. These agents have tools (`read_file`, `search_code`, `query_dossier`, `write_finding`) and loop via Thought → Action → Observation cycles. They write findings progressively to the Dossier as they discover them. Hard stop at 30 steps or 5 minutes.

### Dossier at Scale

For large repos (800k+ lines), the Dossier is indexed into Qdrant after Layer 2. Module wiki agents query the Dossier (RAG) for only the relevant subset — not the entire 100k+ token Dossier. Each Dossier entry is an **atomic queryable unit** with `related_files`, `related_modules`, `severity`, and embedded text.

### Full Agent Catalog (23 Agents)

**Layer 1 — Reconnaissance (1 agent, zero LLM)**

| Agent | Type | Output |
|---|---|---|
| `RepoRecon` | Heuristic | RepoFingerprint: language, system type, tools present |

**Layer 2 — Triage (1 agent)**

| Agent | Type | Output |
|---|---|---|
| `TriageAgent` | Single-pass LLM | Execution plan: which agents run, budget, order |

**Layer 2 — Heuristic Facet Agents (7 agents, zero LLM)**

| Agent | Reads | Dossier Section |
|---|---|---|
| `DependencyAuditor` | lock files → OSV.dev CVE lookup | `dependency_analysis` |
| `ContainerAnalyzer` | Dockerfile, docker-compose | `container_topology` |
| `IaCAnalyzer` | Terraform, K8s, Helm | `iac_resources` |
| `APIContractExtractor` | OpenAPI, .proto, .graphql | `api_contracts` |
| `CIPipelineAnalyzer` | GitHub Actions, Jenkinsfile | `ci_pipeline` |
| `OwnershipExtractor` | CODEOWNERS, git blame | `ownership` |
| `FeatureFlagMapper` | LaunchDarkly/Unleash patterns | `feature_flags` |

**Layer 2 — ReAct Iterative Agents (4 agents, LangGraph create_react_agent)**

| Agent | Trigger | Dossier Section |
|---|---|---|
| `SecuritySentinel` | Always (security-relevant repos) | `security_findings` |
| `DataFlowTracer` | Always (data transformation code) | `data_flows` |
| `AuthFlowTracer` | Tag: `pattern:jwt-auth` | `security_findings` |
| `VulnerabilityChainTracer` | Tag: `risk:sql-injection` | `security_findings` |

**Layer 2 — Single-Pass LLM Agents (6 agents)**

| Agent | Output |
|---|---|
| `ArchitecturalClassifier` | System style, design patterns (CQRS, Event Sourcing, etc.) |
| `BusinessRuleExtractor` | Plain-English domain rules mapped to code |
| `ObservabilityAuditor` | Logging/metrics/tracing gaps |
| `ErrorResilienceAnalyzer` | Error handling strategy, retry patterns, failure modes |
| `TechnicalDebtAssessor` | Debt items, complexity hotspots |
| `PerformanceHotspotScanner` | N+1 queries, blocking I/O, caching gaps |

**Layer 2 — Synthesis (1 agent, runs last)**

| Agent | Output |
|---|---|
| `ConflictSynthesizer` | Questions (not answers) where facets contradict each other |

**Layer 3 — Module Wiki Sub-Pipeline (3 agents, per module)**

| Agent | Type | Output |
|---|---|---|
| `StructuralAnalyst` | AST-based, no LLM | Entities with interestingness scores, canonical hash |
| `ImplementationExplainer` | Parallel LLM calls (up to 15) | Per-function: purpose, how-it-works, gotchas with evidence lines |
| `ModuleWeaver` | Single-pass LLM | Narrative wiki page synthesized from Dossier + explanations |

**LLM Call Budget per Repo (first run)**

| Stage | Calls |
|---|---|
| TriageAgent | 1 |
| Single-pass facet agents (6) | ~6 |
| ReAct iterative agents (4 × up to 30 steps) | ~60–120 |
| Module wiki per module (17 calls × N modules) | ~340 (20 modules) |
| **Total first run (typical 20-module repo)** | **~400–500 LLM calls** |
| **Subsequent syncs (only changed modules)** | **~20–40 calls** |

---

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

**Status**: No violations - architecture follows standard best practices

---

## Planning Complete ✅

**Phase 0 - Research**: ✅ Complete ([research.md](./research.md))
- Technology stack selected and justified
- 8 major decisions documented with alternatives

**Phase 1 - Design**: ✅ Complete
- Data model: [data-model.md](./data-model.md) - 9 entities with relationships
- API contracts: [contracts/openapi.yaml](./contracts/openapi.yaml) - REST API specification
- Quickstart: [quickstart.md](./quickstart.md) - Developer onboarding guide
- Agent context: Updated CLAUDE.md

**Next Steps**:
1. Run `/speckit.tasks` to generate task breakdown
2. Begin implementation with Phase 0 tasks (environment setup)
3. Implement parsers, wiki generation, and API according to plan

**Planning Completion Date**: 2026-02-15
