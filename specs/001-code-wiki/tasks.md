# Tasks: AI-Powered Code Wiki Platform

**Input**: Design documents from `/specs/001-code-wiki/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml, quickstart.md
**UX Reference**: `specs/001-code-wiki/ux/docs-glassmorphism/` (15 pages)

**Verification Policy**: Every task includes explicit exit criteria. UX tasks require side-by-side comparison against glassmorphism mock HTML at 1280px viewport, component-level visual checks (colors, shadows, blur, borders match mock), interactive state verification (hover, focus, active), zero console errors, and glassmorphism property verification (backdrop-filter, rgba backgrounds, border opacity).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)

## UX Mock → Frontend Page Reference

| Mock File | Route | Spec Req | Story |
|-----------|-------|----------|-------|
| `index.html` | `/` | FR-022 | US1 |
| `dashboard.html` | `/dashboard` | FR-022 | US1 |
| `submit.html` | `/submit` | FR-001 | US1 |
| `progress.html` | `/[repo]/progress` | FR-024 | US1 |
| `home.html` | `/[repo]` | FR-006 | US1 |
| `module.html` | `/[repo]/modules/[slug]` | FR-005, FR-010 | US1 |
| `function.html` | `/[repo]/entities/[name]` | FR-011, FR-014 | US1 |
| `getting-started.html` | `/[repo]/getting-started` | FR-007 | US1 |
| `search.html` | `/[repo]/search` | FR-023 | US1 |
| `glossary.html` | `/[repo]/glossary` | FR-009 | US1 |
| `api-reference.html` | `/[repo]/api` | FR-008 | US1 |
| `error.html` | (various) | FR-022 | US1 |
| `chat.html` | `/[repo]/chat` | FR-026, FR-027, FR-028 | US3 |
| `diagrams.html` | `/[repo]/diagrams` | FR-029 | US4 |
| `login.html` | `/login` | FR-025 | Post-MVP |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffold, Docker Compose, database connections

- [ ] T001 Create project root structure with `backend/`, `frontend/`, `shared/` directories per plan.md Project Structure section
  - **Verify**: `backend/src/`, `frontend/src/`, `shared/contracts/` directories exist; `backend/pyproject.toml` or `backend/requirements.txt` placeholder exists

- [ ] T002 Create Docker Compose file with PostgreSQL 15, Neo4j 5.16, Qdrant latest, and Redis 7 in `docker-compose.yml`
  - **Verify**: `docker-compose up -d` starts all 4 services; `docker-compose ps` shows all healthy; ports 5432, 7474/7687, 6333/6334, 6379 accessible

- [ ] T003 [P] Initialize Python backend project in `backend/` with FastAPI, SQLAlchemy, Alembic, openai, langgraph, qdrant-client, neo4j, redis, rq, gitpython, jedi, sentence-transformers in `backend/requirements.txt`
  - **Verify**: `pip install -r requirements.txt` succeeds; `python -c "import fastapi, sqlalchemy, openai, langgraph"` imports without error

- [ ] T004 [P] Initialize Next.js frontend project in `frontend/` with TypeScript strict mode, Outfit + Fira Code fonts
  - **Verify**: `npm run dev` starts on port 3000; TypeScript strict mode enabled in `tsconfig.json`; fonts load in browser

- [ ] T005 [P] Create backend environment configuration in `backend/src/config.py` with Pydantic BaseSettings loading from `.env` (DATABASE_URL, NEO4J_URI, QDRANT_URL, LLM_BASE_URL, REDIS_URL, REPO_CACHE_DIR)
  - **Verify**: Config loads from `.env` file; missing required vars raise ValidationError; `backend/.env.example` exists with all keys documented

- [ ] T006 [P] Create `backend/.env.example` and `frontend/.env.example` matching quickstart.md environment configuration section
  - **Verify**: All environment variables from quickstart.md present; no real secrets in example files

- [ ] T007 Create health check endpoint at `GET /health` in `backend/src/api/main.py` returning service connectivity status for PostgreSQL, Neo4j, Qdrant, Redis
  - **Verify**: `curl http://localhost:8000/health` returns JSON with status for each service; unhealthy services show error details

- [ ] T008 [P] Create `.gitignore` entries for `backend/venv/`, `backend/.env`, `frontend/.env.local`, `frontend/node_modules/`, `frontend/.next/`, `cache/`, `*.pyc`
  - **Verify**: `git status` does not show ignored files after setup

**Checkpoint**: Docker services running, backend serves health endpoint, frontend dev server starts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T009 Create Alembic migration framework in `backend/` with initial migration for `repositories`, `wikis`, `wiki_pages`, `modules`, `code_entities`, `chat_conversations`, `update_events` tables per data-model.md
  - **Verify**: `alembic upgrade head` creates all 7 tables; `alembic downgrade base` removes them cleanly; column types match data-model.md field definitions

- [ ] T010 [P] Create SQLAlchemy models for Repository in `backend/src/models/repository.py` with all fields from data-model.md Entity 1 including status enum (pending/analyzing/ready/error)
  - **Verify**: Model fields match data-model.md exactly; status enum validation works; `url` has unique constraint

- [ ] T011 [P] Create SQLAlchemy models for Wiki and WikiPage in `backend/src/models/wiki.py` with JSONB content field and page_type enum per data-model.md Entities 2-3
  - **Verify**: WikiPage content field accepts structured JSON per data-model.md Content Structure; page_type enum includes all 6 types; slug uniqueness per wiki enforced

- [ ] T012 [P] Create SQLAlchemy models for Module and CodeEntity in `backend/src/models/code_entity.py` per data-model.md Entities 4-5
  - **Verify**: Module.detection_confidence is Float 0.0-1.0; CodeEntity.entity_type enum includes all 6 types; qualified_name has unique constraint

- [ ] T013 [P] Create SQLAlchemy models for ChatConversation and UpdateEvent in `backend/src/models/events.py` per data-model.md Entities 6-7
  - **Verify**: ChatConversation.messages is JSONB array; UpdateEvent.status enum matches data-model.md state transitions

- [ ] T014 Create Neo4j connection manager in `backend/src/storage/graph_db.py` with connection pooling, health check, and CRUD operations for CodeEntity nodes and relationship types (CALLS, IMPORTS, INHERITS_FROM, DEFINES, USES, OVERRIDES)
  - **Verify**: Can create CodeEntity node, create CALLS relationship, query neighbors; connection pool handles concurrent requests; health check returns true when Neo4j is up

- [ ] T015 [P] Create Qdrant client wrapper in `backend/src/storage/vector_db.py` with collection management for `code_entities` (384-dim) and `dossier_findings` (384-dim) collections per research.md Section 5
  - **Verify**: Both collections created with Cosine distance; can upsert and search vectors; metadata filtering works (e.g., filter by module_id)

- [ ] T016 [P] Create Redis connection and cache utility in `backend/src/storage/cache.py` with get/set/delete operations and TTL support
  - **Verify**: Cache set with TTL expires correctly; concurrent access safe; connection failure returns None (not crash)

- [ ] T017 Create LM Studio client wrapper in `backend/src/llm/client.py` using raw OpenAI SDK pointing to `localhost:1234/v1` per research.md Decision 3, with retry logic and response caching via Redis
  - **Verify**: `client.chat.completions.create()` returns response when LM Studio running; retry on timeout (3 attempts); cached responses returned on repeat calls; graceful error when LM Studio is down

- [ ] T018 [P] Create sentence-transformers embedding utility in `backend/src/llm/embeddings.py` loading `all-MiniLM-L6-v2` model, with batch encoding support
  - **Verify**: `embed("test string")` returns 384-dim vector; batch encoding of 100 strings completes in <5s; model loads once at startup

- [ ] T019 Create Git operations utility in `backend/src/storage/repo_cache.py` using GitPython per research.md Decision 13 with clone, pull, get_commit_hash, list_files functions
  - **Verify**: Clones a public GitHub repo to `REPO_CACHE_DIR`; pull updates existing clone; `list_files()` returns all tracked files; invalid URL raises clear error

- [ ] T020 Create CodeParser abstract base class in `backend/src/parsers/base.py` with `parse_file()`, `resolve_imports()`, `get_call_graph()` methods per research.md Implementation Strategy section
  - **Verify**: ABC cannot be instantiated; all 3 methods are abstract; return types are typed (List[CodeEntity], List[Dependency])

- [ ] T021 Create RQ (Redis Queue) worker setup in `backend/src/jobs/worker.py` with task queue for long-running repository analysis jobs per research.md Decision 12
  - **Verify**: Can enqueue a test job; worker picks up and executes job; job status queryable (queued/started/finished/failed); timeout of 15 minutes configured

- [ ] T022 [P] Create FastAPI application skeleton in `backend/src/api/main.py` with CORS middleware, error handlers, and router registration for `/v1/repositories`, `/v1/wikis`, `/v1/chat`, `/v1/search` per openapi.yaml tags
  - **Verify**: App starts with `uvicorn`; `/docs` shows Swagger UI; CORS allows localhost:3000; 404 returns JSON error per openapi.yaml Error schema

- [ ] T023 [P] Create Pydantic request/response schemas in `backend/src/api/schemas/` matching ALL openapi.yaml component schemas (Repository, Wiki, WikiPage, Module, CodeEntity, ChatConversation, ChatMessage, UpdateEvent, SearchResults, Pagination, Error)
  - **Verify**: Each schema validates correctly against openapi.yaml field definitions; required fields enforced; enum values match; example data validates

- [ ] T024 Create frontend API client service in `frontend/src/services/api.ts` with typed methods for all openapi.yaml endpoints (createRepository, listRepositories, getRepository, getWiki, listWikiPages, getWikiPage, search, etc.)
  - **Verify**: TypeScript types match openapi.yaml schemas; API base URL configurable via env var; error handling returns typed error objects; all endpoints from openapi.yaml have corresponding methods

**Checkpoint**: Foundation ready - all databases connected, models migrated, parsers defined, API skeleton serving, frontend can call backend

---

## Phase 3: User Story 1 - Automatic Wiki Generation from Code (Priority: P1) -- MVP

**Goal**: Developer submits a repository URL and the system generates a complete, structured wiki with home page, module pages, API reference, getting started guide, glossary, and function index - all browsable via web UI matching glassmorphism design system.

**Independent Test**: Submit any public repository URL → verify wiki generated with multiple page types and browsable navigation within 15 minutes.

### 3A: Code Parsing (Backend)

- [ ] T025 [P] [US1] Implement PythonParser in `backend/src/parsers/python_parser.py` using Jedi + Python AST to extract functions, classes, methods, imports, signatures, docstrings, and call relationships per research.md Section 1
  - **Verify**: Parse a known Python file → extracts all functions with signatures including type hints; resolves cross-file imports (e.g., `from models.user import User` resolves to actual file); docstrings extracted; call graph shows caller/callee; 95%+ accuracy on test fixture

- [ ] T026 [P] [US1] Implement TypeScriptParser in `backend/src/parsers/typescript_parser.py` using TypeScript Compiler API via subprocess to extract functions, classes, interfaces, imports, type signatures per research.md Section 1
  - **Verify**: Parse a known TS file → extracts all exports with full type signatures; resolves import paths; return types captured; interface/type definitions extracted; 95%+ accuracy on test fixture

- [ ] T027 [US1] Create parser registry in `backend/src/parsers/__init__.py` mapping file extensions to parsers (.py→PythonParser, .ts/.tsx/.js/.jsx→TypeScriptParser) per research.md "Best of both worlds" section
  - **Verify**: `get_parser(".py")` returns PythonParser; `get_parser(".ts")` returns TypeScriptParser; unknown extensions raise `UnsupportedLanguageError`

- [ ] T028 [US1] Implement entity extraction pipeline in `backend/src/parsers/extractor.py` that walks a repo directory, parses each supported file, and produces CodeEntity records for PostgreSQL + Neo4j per data-model.md Entity 5
  - **Verify**: Given a repo path, extracts all code entities from all supported files; writes to PostgreSQL (CodeEntity rows) and Neo4j (nodes + relationships); handles 10k-line repo in <60s; skips `node_modules`, `.git`, `dist` directories

### 3B: Repo Reconnaissance (Layer 0)

- [ ] T029 [US1] Implement RepoRecon agent in `backend/src/recon/repo_recon.py` that scans file tree, detects languages, counts LOC, identifies config files (Docker, CI, IaC, package manifests) per plan.md Layer 1
  - **Verify**: Given repo path → produces RepoFingerprint with languages, file_count, loc, detected tools; zero LLM calls; completes in <2s for 50k LOC repo

- [ ] T030 [P] [US1] Create RepoFingerprint dataclass in `backend/src/recon/fingerprint.py` with fields: languages, primary_language, system_type, tools_present, file_count, loc, config_files
  - **Verify**: Dataclass instantiates with all fields; serializable to JSON; immutable after creation

- [ ] T031 [P] [US1] Create config detector in `backend/src/recon/config_detector.py` that identifies Dockerfiles, CI configs (GitHub Actions, Jenkins), IaC files (Terraform, K8s), package manifests (package.json, pyproject.toml, go.mod)
  - **Verify**: Detects each config type by filename pattern; returns dict of `{config_type: [file_paths]}`; handles repos with no configs gracefully

### 3C: Dossier (Shared Blackboard)

- [ ] T032 [US1] Create Dossier Pydantic schema in `backend/src/dossier/schema.py` with all nested models: SecurityFinding, DependencyAnalysis, ContainerTopology, CIPipeline, ArchitectureStyle, BusinessRule, TechnicalDebt, ConflictAnalysis per plan.md Architecture section and research.md Decision 16.1
  - **Verify**: All Dossier sections are typed Pydantic models; SecurityFinding has id, type, severity, related_files, related_modules, description, evidence_lines fields (atomic queryable units, not blobs); entire Dossier serializable to JSON

- [ ] T033 [US1] Create DossierManager in `backend/src/dossier/manager.py` with write_finding(), query_findings(), get_section(), clear() methods that operate on the Dossier state
  - **Verify**: write_finding appends to correct section; query_findings filters by module/severity; thread-safe for concurrent agent writes; empty Dossier returns empty results (not errors)

- [ ] T034 [US1] Create Dossier RAG index in `backend/src/dossier/rag_index.py` that embeds all Dossier findings into Qdrant `dossier_findings` collection with metadata filters (related_files, related_modules, severity)
  - **Verify**: After indexing 50 findings, semantic search for "authentication security" returns relevant SecurityFindings; metadata filter for specific module returns only that module's findings; re-indexing overwrites previous entries

### 3D: Facet Intelligence Agents (Layer 1)

- [ ] T035 [US1] Implement TriageAgent in `backend/src/agents/triage/triage_agent.py` that reads RepoFingerprint and produces an execution plan (which agents to run, budget, order) via single-pass LLM call per plan.md Layer 2 Triage
  - **Verify**: Given a RepoFingerprint → returns structured execution plan listing agents to invoke; respects LLM budget constraints; plan is deterministic for same fingerprint (cached)

- [ ] T036 [P] [US1] Implement DependencyAuditor in `backend/src/agents/heuristic/dependency_auditor.py` that parses lock files (requirements.txt, package-lock.json, go.sum) and optionally queries OSV.dev for CVEs per plan.md Heuristic Agents
  - **Verify**: Parses requirements.txt → extracts all packages with versions; writes DependencyAnalysis to Dossier; zero LLM calls; handles missing lock files gracefully

- [ ] T037 [P] [US1] Implement ContainerAnalyzer in `backend/src/agents/heuristic/container_analyzer.py` that parses Dockerfiles and docker-compose.yml to extract services, ports, volumes
  - **Verify**: Parses multi-stage Dockerfile → extracts base images, exposed ports; docker-compose → extracts service topology; writes to Dossier `container_topology`

- [ ] T038 [P] [US1] Implement CIPipelineAnalyzer in `backend/src/agents/heuristic/ci_pipeline_analyzer.py` that parses GitHub Actions workflows and Jenkinsfiles to extract pipeline stages
  - **Verify**: Parses `.github/workflows/*.yml` → extracts jobs, steps, triggers; writes to Dossier `ci_pipeline`; handles repos without CI gracefully

- [ ] T039 [P] [US1] Implement remaining heuristic agents: IaCAnalyzer, APIContractExtractor, OwnershipExtractor, FeatureFlagMapper in `backend/src/agents/heuristic/` (one file each per plan.md directory structure)
  - **Verify**: Each agent reads specific config files, writes to its Dossier section, uses zero LLM calls; repos without relevant configs produce empty sections (not errors)

- [ ] T040 [US1] Implement SecuritySentinel ReAct agent in `backend/src/agents/iterative/security_sentinel.py` using `create_react_agent` from LangGraph with tools (read_file, search_code, query_dossier, write_finding) per research.md Decision 17
  - **Verify**: Given a repo with auth code → traces auth flows across files; writes SecurityFindings progressively to Dossier; respects MAX_STEPS=30 and TIME_LIMIT=300s; maintains visited_nodes set (no re-reads); stops on convergence (3 consecutive no-new-findings)

- [ ] T041 [P] [US1] Implement DataFlowTracer ReAct agent in `backend/src/agents/iterative/data_flow_tracer.py` using same pattern as SecuritySentinel
  - **Verify**: Traces data transformations from entry points; writes to Dossier `data_flows`; respects same termination safeguards

- [ ] T042 [P] [US1] Implement AuthFlowTracer and VulnerabilityChainTracer in `backend/src/agents/iterative/auth_flow_tracer.py` and `vuln_chain_tracer.py` per plan.md ReAct agents table
  - **Verify**: AuthFlowTracer triggers only on tag `pattern:jwt-auth`; VulnChainTracer triggers on tag `risk:sql-injection`; both respect termination safeguards

- [ ] T043 [P] [US1] Implement all 6 single-pass LLM agents in `backend/src/agents/single_pass/`: ArchitecturalClassifier, BusinessRuleExtractor, ObservabilityAuditor, ErrorResilienceAnalyzer, TechnicalDebtAssessor, PerformanceHotspotScanner per plan.md Single-Pass table
  - **Verify**: Each agent makes exactly 1 LLM call; writes structured output to its Dossier section; handles LLM errors gracefully (retries, then writes error entry)

- [ ] T044 [US1] Implement ConflictSynthesizer in `backend/src/agents/conflict_synthesizer.py` that identifies contradictions between facet findings and generates questions (never resolves) per research.md Decision 16.6
  - **Verify**: Given contradictory findings (e.g., "microservice" vs "monolith coupling") → writes ConflictAnalysis with facet_a, facet_b, why_both_coexist, developer_questions; NEVER writes conclusion or winner

- [ ] T045 [US1] Create capability primitives in `backend/src/agents/primitives/` (file_reader.py, ast_parser_tool.py, pattern_matcher.py, security_lens.py, structured_output_writer.py) per research.md Decision 16.3
  - **Verify**: Each primitive is a callable tool usable by ReAct agents; file_reader returns file contents; structured_output_writer appends to Dossier; all have typed inputs/outputs

- [ ] T046 [US1] Implement TAG_TRIGGERS registry in `backend/src/orchestrator/tag_triggers.py` mapping agent-emitted tags to downstream agents per research.md Decision 16.5
  - **Verify**: `TAG_TRIGGERS["pattern:jwt-auth"]` returns `["auth_flow_tracer"]`; tags are strings; lookup for unknown tag returns empty list

- [ ] T047 [US1] Implement LangGraph StateGraph orchestration in `backend/src/orchestrator/graph.py` wiring Layer 0 → Triage → parallel facet agents → ConflictSynthesizer → Layer 2 wiki per plan.md Multi-Agent Architecture
  - **Verify**: Full pipeline executes end-to-end on a test repo; Dossier is populated after Layer 1; heuristic agents run in parallel; ReAct agents respect tag triggers; ConflictSynthesizer runs last; can visualize execution graph

- [ ] T048 [US1] Implement heuristic routing functions in `backend/src/orchestrator/routing.py` per research.md Decision 16.5 (pure Python conditional edges, no mid-pipeline LLM routing)
  - **Verify**: `route_after_security(dossier)` returns correct next agent based on Dossier state; all routing is deterministic; no LLM calls in routing functions

### 3E: Wiki Generation Pipeline (Layer 2)

- [ ] T049 [US1] Implement StructuralAnalyst in `backend/src/wiki/interestingness.py` with rule-based interestingness scoring (high call-in-degree, cyclomatic complexity, cross-module deps, public API surface, unusual patterns) per CLAUDE.md Wiki Generation Pipeline
  - **Verify**: Given module entities → scores each entity 0.0-1.0; high-callee functions score higher; dynamic threshold selects top-N% (not fixed cap); zero LLM calls; produces canonical hash for change detection

- [ ] T050 [US1] Implement ImplementationExplainer in `backend/src/wiki/orchestrator.py` that makes parallel LLM calls (up to 15) for top-scored entities, providing function signature + docstring + body + caller/callee + class body context per CLAUDE.md Wiki Generation Pipeline
  - **Verify**: Given top-N entities → makes parallel LLM calls; each prompt includes class body context (not just caller/callee); answers "why does this exist?" not just "what does it do?"; evidence_lines validated against actual source (hallucination mitigation)

- [ ] T051 [US1] Implement ModuleWeaver in `backend/src/wiki/orchestrator.py` that synthesizes StructuralAnalyst report + ImplementationExplainer explanations + Dossier RAG context into coherent module narrative
  - **Verify**: Output includes: module purpose, design patterns, data flow, gotchas, security context (from Dossier), business rules (from Dossier), technical debt; single LLM call; references actual file paths

- [ ] T052 [US1] Create wiki context builder in `backend/src/wiki/context_builder.py` that retrieves relevant Dossier findings via Qdrant RAG for a given module, merging with direct source code
  - **Verify**: For module "auth" → retrieves security findings mentioning auth files; combines RAG results with actual source; total context fits within LLM context window (262k tokens for qwen3-coder)

- [ ] T053 [US1] Implement page builders in `backend/src/wiki/page_builders/`: home_page.py, module_page.py, dashboard.py per plan.md wiki/ directory
  - **Verify**: home_page builds WikiPage with page_type=home, stats, module list, quick links; module_page builds with all 8 structured sections per spec FR-010 (overview, location, how-it-works, key-components, dependencies, configuration, related-pages, known-issues); all pages have valid JSONB content matching data-model.md WikiPage Content Structure

- [ ] T054 [US1] Implement getting_started, function_index, glossary, api_reference page builders in `backend/src/wiki/page_builders/`
  - **Verify**: getting_started extracts prerequisites + setup steps from README/config files (FR-007); function_index lists all public code entities with links (FR-008); glossary extracts domain terms from docstrings/comments (FR-009); api_reference creates alphabetical index (FR-008)

### 3F: API Endpoints

- [ ] T055 [US1] Implement POST /v1/repositories endpoint in `backend/src/api/routes/repositories.py` that validates URL, enqueues analysis job via RQ, returns 202 per openapi.yaml
  - **Verify**: Valid GitHub URL → returns 202 with Repository object (status=pending); invalid URL → returns 400; duplicate URL → returns 409; job enqueued in RQ

- [ ] T056 [US1] Implement GET /v1/repositories and GET /v1/repositories/{id} endpoints per openapi.yaml with pagination
  - **Verify**: List returns paginated results matching Pagination schema; GET by ID returns full Repository; 404 for unknown ID; status filter works

- [ ] T057 [US1] Implement DELETE /v1/repositories/{id} and POST /v1/repositories/{id}/refresh endpoints per openapi.yaml
  - **Verify**: Delete removes repo + wiki + all entities; refresh enqueues new analysis job, returns UpdateEvent; both return 404 for unknown ID

- [ ] T058 [US1] Implement GET /v1/wikis/{repositoryId} and GET /v1/wikis/{repositoryId}/pages endpoints per openapi.yaml
  - **Verify**: Returns Wiki with module_count, page_count; pages endpoint supports page_type filter; 404 when wiki not yet generated

- [ ] T059 [US1] Implement GET /v1/wikis/{repositoryId}/pages/{pageSlug} endpoint per openapi.yaml returning full WikiPage with structured JSONB content
  - **Verify**: Returns WikiPage with all sections; content matches data-model.md JSONB structure; hyperlinks to other pages/entities included; 404 for unknown slug

- [ ] T060 [US1] Implement GET /v1/wikis/{repositoryId}/modules and /modules/{moduleSlug} endpoints per openapi.yaml
  - **Verify**: Returns module list with detection_confidence, file_count, line_count; module detail includes dependencies_module_ids; 404 for unknown slug

- [ ] T061 [US1] Implement GET /v1/wikis/{repositoryId}/entities/{entityQualifiedName} endpoint per openapi.yaml returning CodeEntity with relationships (calls, imports, inherits_from)
  - **Verify**: Returns entity with signature, description, relationships from Neo4j; 404 for unknown qualified name

- [ ] T062 [US1] Implement GET /v1/search/{repositoryId} endpoint per openapi.yaml with hybrid search (keyword + semantic via Qdrant)
  - **Verify**: Search "authentication" returns relevant pages, entities, modules; type filter works (all/pages/entities/modules); results sorted by relevance score; response time <2s (SC-013)

- [ ] T063 [US1] Implement repository analysis background job in `backend/src/jobs/analyze.py` that orchestrates the full pipeline: clone repo → parse code → recon → facet agents → wiki generation → update status
  - **Verify**: End-to-end: submit repo URL → job completes → Repository status=ready → Wiki exists with pages; handles failures gracefully (status=error with error message); 50k LOC repo completes in <15 minutes (SC-001)

### 3G: Frontend - Design System & Shared Components

- [ ] T064 [US1] Create glassmorphism design system in `frontend/src/styles/globals.css` with all CSS variables from glassmorphism mocks: --primary (#8B5CF6), --primary-light (#A78BFA), --secondary (#06B6D4), --accent (#EC4899), --bg-dark (#0A0A0F), --bg-darker (#050508), --glass-bg, --glass-border, --text-primary/secondary/tertiary
  - **Verify**: Open browser at 1280px → CSS variables resolve correctly; compare color values against `home.html` mock `:root` block — every value must match exactly. Import Outfit + Fira Code fonts matching mock `<link>` tags.

- [ ] T065 [US1] Create GradientBackground component in `frontend/src/components/ui/GradientBackground.tsx` with 3 animated gradient orbs matching mock `.gradient-bg`, `.gradient-orb`, `.orb-1/2/3` styles exactly
  - **Verify**: Side-by-side with any glassmorphism mock at 1280px → orb sizes (700px/500px/400px), positions, gradient colors, blur(120px), opacity(0.35), animation timing (20s) all match. No visual deviation.

- [ ] T066 [US1] Create GlassCard component in `frontend/src/components/ui/GlassCard.tsx` matching mock `.glass-card` styles (background: rgba(15,15,25,0.7), backdrop-filter: blur(20px), border: 1px solid rgba(255,255,255,0.1), border-radius: 20px, box-shadow: 0 8px 32px rgba(0,0,0,0.37))
  - **Verify**: Render GlassCard → inspect computed styles → all 5 glassmorphism properties match mock values exactly. Hover state matches if mock has one.

- [ ] T067 [US1] Create Logo component in `frontend/src/components/ui/Logo.tsx` matching mock `.logo`, `.logo-icon`, `.logo-text` styles with gradient icon and gradient text
  - **Verify**: Side-by-side with mock logo → icon size, gradient, border-radius, box-shadow glow, text gradient all match.

- [ ] T068 [US1] Create ThreeColumnLayout component in `frontend/src/components/layout/ThreeColumnLayout.tsx` matching mock `.docs-layout` (300px | 1fr | 280px grid) with left sidebar (sticky, scrollable, nav sections), main content, and right TOC sidebar
  - **Verify**: At 1280px → 3 columns visible with correct widths. At 1400px → right sidebar hidden. At 900px → single column with hamburger. Compare against `module.html` mock at each breakpoint.

- [ ] T069 [US1] Create Sidebar navigation component in `frontend/src/components/layout/Sidebar.tsx` with nav sections, nav items (active state, hover translateX(4px), gradient background) matching mock sidebar patterns
  - **Verify**: Active item has gradient background + box-shadow matching mock `.nav-item.active`. Hover lifts 4px. Section titles match mock `.nav-section-title` uppercase style. Mobile menu slides in from left per mock mobile nav pattern.

- [ ] T070 [US1] Create TableOfContents component with scroll-spy in `frontend/src/components/layout/TableOfContents.tsx` matching mock `.toc-item` styles including animated left border on active
  - **Verify**: Scrolling content → TOC highlights correct section. Active item has gradient left border per mock `.toc-item.active::before`. Hover padding increase matches mock.

- [ ] T071 [US1] Create shared components: Breadcrumbs, InfoBox, CodeBlock (with copy button), TypeBadge, StatusIndicator in `frontend/src/components/ui/`
  - **Verify**: Each component rendered in isolation matches mock equivalent visually. CodeBlock has Fira Code font, dark background, copy button per mock `pre code` styles. TypeBadge colors match mock type badges. InfoBox has gradient background + left border per mock `.info-box`.

### 3H: Frontend - Pages (matching glassmorphism mocks)

- [ ] T072 [US1] Implement Landing page at `frontend/src/app/page.tsx` matching `index.html` mock — centered layout, logo, title "Complete UX Prototype", user flow diagram, page cards grid grouped by category (Onboarding/Wiki/Tools/States)
  - **Verify**: Side-by-side at 1280px with `index.html` mock → layout, card grid, flow diagram, group tags, card hover effects all match. At 900px → flow grid collapses to single column. At 600px → cards single column. Zero console errors.

- [ ] T073 [US1] Implement Dashboard page at `frontend/src/app/dashboard/page.tsx` matching `dashboard.html` mock — repository list with status badges, sync indicators, Add Repository CTA, empty state
  - **Verify**: Side-by-side at 1280px with `dashboard.html` mock → repo cards, status badges (green/yellow/red), sync indicators, empty state illustration all match. Glass card styling verified. Interactive states (hover on cards, CTA button) match mock.

- [ ] T074 [US1] Implement Submit page at `frontend/src/app/submit/page.tsx` matching `submit.html` mock — URL input with validation, provider detection (GitHub/GitLab/Bitbucket icon), visibility toggle, submit button calling POST /v1/repositories
  - **Verify**: Side-by-side at 1280px with `submit.html` mock → form layout, URL input styling, provider icon detection, validation states (error/success borders), submit button gradient all match. Form submission calls API and redirects to progress page.

- [ ] T075 [US1] Implement Progress page at `frontend/src/app/[repo]/progress/page.tsx` matching `progress.html` mock — animated 6-step pipeline stepper, progress bar, live stats, module discovery accordion, completion celebration animation
  - **Verify**: Side-by-side at 1280px with `progress.html` mock → stepper layout, step icons, progress bar gradient, stats cards, module list accordion all match. Polls GET /v1/repositories/{id} for status updates. Shows celebration on status=ready.

- [ ] T076 [US1] Implement Wiki Home page at `frontend/src/app/[repo]/page.tsx` matching `home.html` mock — repository header with stats grid (modules/functions/classes/LOC), quick links (Getting Started, API Reference, AI Assistant), module cards grid (4 columns), recent activity timeline
  - **Verify**: Side-by-side at 1280px with `home.html` mock → stats grid layout, stat card glassmorphism, quick link cards, module card grid (4 columns), activity timeline all match. Stats populated from GET /v1/wikis/{id}. Module cards link to /[repo]/modules/[slug]. At 768px → 2-column stats; at 480px → single column.

- [ ] T077 [US1] Implement Module page at `frontend/src/app/[repo]/modules/[slug]/page.tsx` matching `module.html` mock — 3-column layout with sidebar nav, main content (overview, location/file tree, key components grid, dependencies table, code samples, related pages), right TOC with scroll-spy
  - **Verify**: Side-by-side at 1280px with `module.html` mock → all 8 structured sections present per FR-010, sidebar nav with active state, TOC scroll-spy working, code blocks styled correctly, dependency table matches mock. Content populated from GET /v1/wikis/{id}/pages/{slug}.

- [ ] T078 [US1] Implement Function Detail page at `frontend/src/app/[repo]/entities/[name]/page.tsx` matching `function.html` mock — signature block with syntax highlighting, parameters table, return value, usage examples with copy buttons, call graph ("Called By" and "Calls" cards), source code preview
  - **Verify**: Side-by-side at 1280px with `function.html` mock → signature block colors, parameters table layout, example code blocks, call graph card grid all match. Content from GET /v1/wikis/{id}/entities/{name}. Hyperlinks to other entities work (FR-011).

- [ ] T079 [US1] Implement Getting Started page at `frontend/src/app/[repo]/getting-started/page.tsx` matching `getting-started.html` mock — prerequisites checklist, numbered step cards, code blocks, configuration examples, quick links grid
  - **Verify**: Side-by-side at 1280px with `getting-started.html` mock → step card layout, prerequisite icons, code block styling, info boxes, quick links grid all match.

- [ ] T080 [US1] Implement Search page at `frontend/src/app/[repo]/search/page.tsx` matching `search.html` mock — prominent search bar, tab filters (All/Functions/Classes/Modules/Documentation), left sidebar with type/module/visibility filters, result cards with type badges and code previews, sort options
  - **Verify**: Side-by-side at 1280px with `search.html` mock → search bar, tabs, filter sidebar, result card layout, type badges, sort dropdown all match. Calls GET /v1/search/{id}. At 900px → sidebar becomes overlay.

- [ ] T081 [US1] Implement Glossary page at `frontend/src/app/[repo]/glossary/page.tsx` matching `glossary.html` mock — alphabet navigation pills, live search, term cards with type badges and descriptions, scroll-spy for letter sections
  - **Verify**: Side-by-side at 1280px with `glossary.html` mock → alphabet nav, term cards, letter section headers, scroll-spy highlighting all match. Content from glossary WikiPage.

- [ ] T082 [US1] Implement API Reference page at `frontend/src/app/[repo]/api/page.tsx` matching `api-reference.html` mock — filter/sort bar, letter dividers, entry rows with method signatures, type badges, module chips, list/grid view toggle
  - **Verify**: Side-by-side at 1280px with `api-reference.html` mock → filter bar, letter dividers, entry row layout, view toggle all match. Content from function_index WikiPage.

- [ ] T083 [US1] Implement Error pages at `frontend/src/app/error.tsx` and `frontend/src/app/not-found.tsx` matching `error.html` mock — 404 state, analysis failure state with expandable stack trace, private repo auth fallback
  - **Verify**: Side-by-side at 1280px with `error.html` mock → error code display, title, description, suggested actions (back, search, chat links), expandable stack trace all match.

- [ ] T084 [US1] Implement mobile responsive navigation across all pages — hamburger menu at 900px, slide-in sidebar, overlay, close button, body scroll lock per CLAUDE.md Mobile Nav Fix Pattern
  - **Verify**: At 900px viewport → hamburger visible; tap opens sidebar from left; overlay covers content; X button closes; body scroll locked when open. Pattern consistent across module, function, getting-started, search, glossary, api-reference pages.

**Checkpoint**: Full US1 pipeline works end-to-end. Submit a public repo URL → analysis completes → wiki generated → all pages browsable via glassmorphism UI matching mocks.

---

## Phase 4: User Story 2 - Real-Time Documentation Synchronization (Priority: P2)

**Goal**: When code changes are committed, documentation automatically updates within 5 minutes.

**Independent Test**: Make a code change, commit, verify wiki updates automatically.

- [ ] T085 [US2] Implement webhook receiver endpoint at POST /v1/webhooks/github in `backend/src/api/routes/webhooks.py` that accepts GitHub push events, extracts commit hash and changed files, creates UpdateEvent
  - **Verify**: Send simulated GitHub webhook payload → UpdateEvent created with correct commit_hash and changed_files; invalid payloads return 400; signature verification (HMAC) works

- [ ] T086 [US2] Implement update detection logic in `backend/src/jobs/sync.py` that maps changed files to affected modules and enqueues partial wiki regeneration
  - **Verify**: Changed file `src/auth/login.py` → identifies "Authentication" module as affected; only affected modules queued for regeneration (not full repo re-analysis); UpdateEvent status transitions: pending → processing → completed

- [ ] T087 [US2] Implement partial wiki regeneration in `backend/src/wiki/orchestrator.py` that re-runs StructuralAnalyst + ImplementationExplainer only for changed entities, then full ModuleWeaver re-synthesis per CLAUDE.md partial regen strategy
  - **Verify**: Change one function → only that entity's explanation regenerated; ModuleWeaver re-synthesizes full module page; unchanged modules not touched; canonical hash used for change detection

- [ ] T088 [US2] Implement commit tracking in WikiPage model — update `commit_hash` field on regeneration per FR-020
  - **Verify**: After sync, WikiPage.commit_hash matches new commit; Repository.last_analyzed_commit updated; wiki version increments

- [ ] T089 [US2] Implement concurrent update handling per FR-021 — queue updates, process sequentially per repo, skip superseded commits
  - **Verify**: Two rapid commits → only latest processed; no race conditions on WikiPage writes; UpdateEvent for skipped commit marked as completed (superseded)

- [ ] T090 [US2] Add status polling endpoint GET /v1/repositories/{id}/status in `backend/src/api/routes/repositories.py` returning current analysis/sync progress
  - **Verify**: During analysis → returns progress percentage and current step; after completion → returns ready with timestamp; frontend Progress page can poll this

- [ ] T091 [US2] Wire frontend Progress page to poll status endpoint and show live updates during sync
  - **Verify**: Trigger a sync → Progress page shows updating stepper; completion shows success; error shows failure details

**Checkpoint**: Push a commit to a connected repo → wiki updates within 5 minutes → UI reflects changes

---

## Phase 5: User Story 3 - Interactive AI Chat Assistant (Priority: P3)

**Goal**: Developers ask natural language questions about the codebase and get accurate answers with code references.

**Independent Test**: Ask "How does authentication work?" → get accurate answer with links to relevant code.

- [ ] T092 [US3] Implement chat context builder in `backend/src/chat/context_builder.py` that retrieves relevant wiki pages, code entities, and Dossier findings via Qdrant RAG for a given user question
  - **Verify**: Question "How does auth work?" → retrieves auth module page, related functions, security findings; context fits within LLM context window; includes source code snippets

- [ ] T093 [US3] Implement chat assistant in `backend/src/chat/assistant.py` that generates responses using LLM with retrieved context, including links to wiki pages and code entities per FR-027, FR-028
  - **Verify**: Response explains auth flow accurately based on actual code; includes 2+ references to wiki pages/code entities; references are valid (pages/entities exist); 90% of responses include code references (SC-014)

- [ ] T094 [US3] Implement POST /v1/chat/{repositoryId}/conversations and POST /v1/chat/conversations/{id}/messages endpoints per openapi.yaml
  - **Verify**: Create conversation → returns ChatConversation with ID; send message → returns ChatMessage with references array; conversation history persisted in PostgreSQL

- [ ] T095 [US3] Implement GET /v1/chat/{repositoryId}/conversations endpoint per openapi.yaml
  - **Verify**: Returns list of conversations for repo; most recent first; empty list for new repos

- [ ] T096 [US3] Implement Chat page at `frontend/src/app/[repo]/chat/page.tsx` matching `chat.html` mock — full-height chat layout, message bubbles (user/AI), code blocks with syntax highlighting and copy buttons, linked page cards, suggested follow-up questions, auto-resizing textarea input
  - **Verify**: Side-by-side at 1280px with `chat.html` mock → message bubble styles, code block formatting, linked page cards, suggestion chips, input textarea all match. Send message → displays user bubble → shows typing indicator → shows AI response with code and links. At 768px → stacked header; at 480px → compact bubbles.

- [ ] T097 [US3] Add chat navigation entry to wiki sidebar and home page quick links pointing to /[repo]/chat
  - **Verify**: "AI Chat" link appears in sidebar nav under Tools section; home page quick links include Chat card; both navigate to chat page

**Checkpoint**: Navigate to chat → ask question → get accurate response with code references and wiki links

---

## Phase 6: User Story 4 - Visual Architecture and Relationship Diagrams (Priority: P4)

**Goal**: Auto-generated architecture diagrams, dependency graphs, and code relationship visualizations.

**Independent Test**: View generated diagrams → verify they accurately represent the codebase structure.

- [ ] T098 [US4] Implement diagram data generation in `backend/src/wiki/page_builders/diagrams.py` that queries Neo4j for module relationships, dependency graphs, and call chains, outputting structured data for frontend rendering
  - **Verify**: Module relationship query returns all inter-module dependencies; dependency graph includes external packages; call chain data traces from entry points through 3+ levels

- [ ] T099 [US4] Add GET /v1/wikis/{repositoryId}/diagrams endpoint returning diagram data (architecture, dependency-graph, module-relationships)
  - **Verify**: Returns 3 diagram types; each includes nodes and edges; node IDs map to existing modules/entities

- [ ] T100 [US4] Implement Diagrams page at `frontend/src/app/[repo]/diagrams/page.tsx` matching `diagrams.html` mock — 3-column layout with architecture overview tab, dependency graph tab, module relationships tab, clickable nodes, zoom capabilities
  - **Verify**: Side-by-side at 1280px with `diagrams.html` mock → tab navigation, diagram container, node styling, edge rendering all match. Clickable nodes navigate to module/entity pages. At 900px → single column.

- [ ] T101 [US4] Add diagrams navigation entry to wiki sidebar and home page
  - **Verify**: "Diagrams" link in sidebar under Features section; home page includes diagram quick link

**Checkpoint**: Navigate to diagrams → view architecture, dependency graph, module relationships → nodes clickable

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality, performance, and completeness improvements

- [ ] T102 [P] Implement login page at `frontend/src/app/login/page.tsx` matching `login.html` mock — OAuth buttons (GitHub/GitLab/Bitbucket), email/password form (UI only, no backend auth in MVP)
  - **Verify**: Side-by-side at 1280px with `login.html` mock → OAuth buttons, email form, layout all match. Buttons are non-functional stubs in MVP (show "Coming Soon" or redirect to dashboard).

- [ ] T103 [P] Add content link styles to all wiki pages per CLAUDE.md CSS Variables for Inline Content Links — default color var(--secondary) #06B6D4, hover color var(--primary-light) #A78BFA, scoped to avoid interfering with nav/sidebar/button links
  - **Verify**: Inline links in wiki content are cyan (#06B6D4); hover turns purple (#A78BFA); nav items, sidebar links, buttons not affected

- [ ] T104 [P] Validate all frontend pages against glassmorphism design system at 4 breakpoints (1400px, 900px, 768px, 480px) — verify gradient orbs, glass cards, typography, spacing, hover effects, mobile nav
  - **Verify**: Open each of 15 frontend pages at each breakpoint → no layout breaks; glass card properties (backdrop-filter, rgba bg, border) present; gradient orbs visible; fonts loaded (Outfit/Fira Code); all hover/focus/active states work; zero console errors

- [ ] T105 [P] Run OpenAPI contract validation — verify all implemented endpoints match openapi.yaml request/response schemas
  - **Verify**: For each endpoint in openapi.yaml → actual response matches schema; required fields present; enum values valid; error responses match Error schema

- [ ] T106 [P] Performance validation — verify SC-001 (50k LOC in <15min), SC-013 (search <2s), SC-006 (95% relationship accuracy)
  - **Verify**: Analyze a 50k LOC repo → completes in <15min; search query → response in <2s; sample 20 code relationships → 19+ correct (95%)

- [ ] T107 Run quickstart.md validation — follow all steps from scratch → verify working system
  - **Verify**: Fresh clone → docker-compose up → backend setup → frontend setup → health check passes → submit repo → wiki generated → all pages browsable

- [ ] T108 [P] Remove BearerAuth security scheme from API (MVP has no authentication per research.md Decision 9) — update openapi.yaml and remove `security: [BearerAuth: []]` global requirement
  - **Verify**: No endpoints require Authorization header; openapi.yaml `security` section removed; Swagger UI shows no auth requirement

- [ ] T109 [P] Fix data-model.md pgvector reference — replace pgvector mentions (Section "Database Schema Notes") with Qdrant per research.md Decision 5
  - **Verify**: data-model.md references Qdrant for embeddings, not pgvector; vector dimension is 384 (not 1536)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — contains all core functionality
- **US2 (Phase 4)**: Depends on Phase 3 (wiki must exist to update)
- **US3 (Phase 5)**: Depends on Phase 3 (wiki + code index must exist for chat context)
- **US4 (Phase 6)**: Depends on Phase 3 (Neo4j graph must be populated)
- **Polish (Phase 7)**: Can start after Phase 3; some tasks parallelizable with Phase 4-6

### Within Phase 3 (US1) — Execution Order

```
T025-T027 (Parsers) ─────────────────────────┐
T029-T031 (Recon) ───────────────────────────┤
T032-T034 (Dossier) ────────────────────────┤
                                              ├─→ T047 (LangGraph wiring)
T035 (Triage) ──────────────────────────────┤      │
T036-T039 (Heuristic agents) ──── parallel ──┤      │
T040-T042 (ReAct agents) ──────── parallel ──┤      │
T043 (Single-pass agents) ─────── parallel ──┤      │
T044 (ConflictSynthesizer) ─── after above ──┤      │
T045-T046 (Primitives + Tags) ── parallel ───┘      │
                                                     ▼
T049-T054 (Wiki generation pipeline) ────────────── after T047
                                                     │
T055-T063 (API endpoints) ──────────────────── after T054
                                                     │
T064-T071 (Frontend design system + shared) ── parallel with above
                                                     │
T072-T084 (Frontend pages) ───────────────── after T064-T071 + T055-T063
```

### Parallel Opportunities

**Phase 2** — All [P] tasks (T010-T013, T015-T016, T018, T022-T023) can run in parallel

**Phase 3 Backend** — Parser tasks (T025-T026), recon tasks (T029-T031), dossier tasks (T032-T034) can all start in parallel. All heuristic agents (T036-T039) can run in parallel. All single-pass agents (T043) can run in parallel.

**Phase 3 Frontend** — Design system (T064-T071) can start in parallel with backend API work. Pages (T072-T084) can start once design system AND API endpoints are ready.

**Phases 4, 5, 6** — Can run in parallel with each other (all depend only on Phase 3)

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3 = User Story 1)

1. Complete Phase 1: Setup (~8 tasks)
2. Complete Phase 2: Foundational (~16 tasks)
3. Complete Phase 3: US1 Wiki Generation (~60 tasks)
4. **STOP and VALIDATE**: Submit a public repo → verify complete wiki with all page types → verify glassmorphism UI matches mocks at all breakpoints
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready
2. Phase 3 → Wiki generation works end-to-end (MVP!)
3. Phase 4 → Wiki auto-updates on commits
4. Phase 5 → AI chat with code references
5. Phase 6 → Visual architecture diagrams
6. Phase 7 → Polish, fix artifacts, validate performance

---

## Summary

| Phase | Tasks | Story | MVP? |
|-------|-------|-------|------|
| 1: Setup | T001-T008 (8) | - | Yes |
| 2: Foundational | T009-T024 (16) | - | Yes |
| 3: US1 Wiki Gen | T025-T084 (60) | US1 | Yes |
| 4: US2 Sync | T085-T091 (7) | US2 | No |
| 5: US3 Chat | T092-T097 (6) | US3 | No |
| 6: US4 Diagrams | T098-T101 (4) | US4 | No |
| 7: Polish | T102-T109 (8) | - | No |
| **Total** | **109 tasks** | | |

**MVP scope**: Phases 1-3 (84 tasks) deliver full wiki generation with glassmorphism UI
**Full scope**: All 109 tasks across 7 phases cover all 4 user stories + polish
