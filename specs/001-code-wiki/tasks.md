# Tasks: AI-Powered Code Wiki Platform

**Feature Branch**: `001-code-wiki`
**Date**: 2026-02-18
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Data Model**: [data-model.md](./data-model.md)

---

## Design References

All frontend implementation tasks must match the glassmorphism mock designs:

| Mock Page | File | Implements |
|-----------|------|------------|
| Home (repo list) | `specs/001-code-wiki/ux/docs-glassmorphism/home.html` | Repository listing |
| Submit repo | `specs/001-code-wiki/ux/docs-glassmorphism/submit.html` | Add repository form |
| Analysis progress | `specs/001-code-wiki/ux/docs-glassmorphism/progress.html` | Real-time pipeline status |
| Wiki dashboard | `specs/001-code-wiki/ux/docs-glassmorphism/dashboard.html` | Health scorecard |
| Module wiki | `specs/001-code-wiki/ux/docs-glassmorphism/module.html` | Per-module documentation |
| Function detail | `specs/001-code-wiki/ux/docs-glassmorphism/function.html` | Entity deep-dive |
| Getting started | `specs/001-code-wiki/ux/docs-glassmorphism/getting-started.html` | Onboarding guide |
| Search results | `specs/001-code-wiki/ux/docs-glassmorphism/search.html` | Semantic search |
| Chat assistant | `specs/001-code-wiki/ux/docs-glassmorphism/chat.html` | AI Q&A interface |
| Diagrams | `specs/001-code-wiki/ux/docs-glassmorphism/diagrams.html` | Visual architecture |
| Glossary | `specs/001-code-wiki/ux/docs-glassmorphism/glossary.html` | Domain terms |
| API reference | `specs/001-code-wiki/ux/docs-glassmorphism/api-reference.html` | API docs view |
| Error state | `specs/001-code-wiki/ux/docs-glassmorphism/error.html` | Error pages |

**Architecture reference**: `specs/001-code-wiki/plan.md` — 3-layer, 23-agent system with LangGraph StateGraph + qwen/qwen3-coder-30b via LM Studio.
**API contracts**: `specs/001-code-wiki/contracts/openapi.yaml`

---

## Phase 1: Setup

**Goal**: Initialize project scaffolding, development infrastructure, and tooling. No functional code — just structure and configuration.

- [ ] T001 Create project directory structure per `specs/001-code-wiki/plan.md` at repo root: `backend/src/`, `frontend/`, `shared/contracts/`
  > `ls backend/src frontend/src shared/contracts` — all 3 directories exist without error

- [ ] T002 [P] Create `docker-compose.yml` at repo root with three services per `specs/001-code-wiki/quickstart.md`: PostgreSQL 15-alpine (port 5432), Neo4j 5.16 with graph-data-science plugin (ports 7474, 7687), Qdrant latest (ports 6333, 6334), with named volumes
  > `docker-compose up -d && docker-compose ps` — shows 3 services all with status "Up"

- [ ] T003 [P] Create `backend/requirements.txt` with all Python dependencies: fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, langgraph, langchain-core, openai, neo4j, qdrant-client, pydantic>=2, jedi, gitpython, httpx, pytest, pytest-asyncio
  > `pip install -r backend/requirements.txt` — exits 0 with no dependency conflicts

- [ ] T004 [P] Create `backend/pyproject.toml` with Python 3.11+ project config, pytest settings (asyncio_mode=auto, testpaths=tests)
  > `cd backend && python -m pytest --version` — runs and prints pytest version

- [ ] T005 [P] Create `backend/.env.example` from `specs/001-code-wiki/quickstart.md`: DATABASE_URL, NEO4J_URI, QDRANT_URL, LLM_BASE_URL=http://localhost:1234/v1, LLM_MODEL=qwen/qwen3-coder-30b, REPO_CACHE_DIR, MAX_CONCURRENT_PARSES=5
  > `grep LLM_MODEL backend/.env.example` — prints `LLM_MODEL=qwen/qwen3-coder-30b`

- [ ] T006 [P] Initialize Next.js 14 TypeScript project in `frontend/` with App Router, Tailwind CSS
  > `ls frontend/src/app frontend/tailwind.config.ts` — both exist

- [ ] T007 [P] Create `frontend/.env.local.example`: NEXT_PUBLIC_API_URL=http://localhost:8000/v1, NEXT_PUBLIC_ENABLE_CHAT=true
  > `cat frontend/.env.local.example` — shows both env vars

- [ ] T008 Create all `backend/src/__init__.py` files for the full directory tree from `specs/001-code-wiki/plan.md`: parsers/, recon/, dossier/, agents/triage/, agents/heuristic/, agents/iterative/, agents/single_pass/, agents/primitives/, orchestrator/, wiki/page_builders/, graph/, chat/, api/routes/, api/schemas/, storage/, models/
  > `find backend/src -name "__init__.py" | wc -l` — prints 15 or more

---

## Phase 2: Foundation

**Goal**: Core infrastructure that ALL user stories depend on. Must complete before Phases 3+.

### Database Models

- [ ] T009 Configure Alembic in `backend/`: `alembic.ini` and `backend/migrations/env.py` using async SQLAlchemy engine from `DATABASE_URL`
  > `cd backend && alembic current` — runs without ImportError or config error

- [ ] T010 Create `backend/src/models/repository.py`: SQLAlchemy async `Repository` model with all fields from `specs/001-code-wiki/data-model.md` §1 — id (UUID), url (unique), name, owner, primary_languages (ARRAY), status (Enum: pending/analyzing/ready/error), last_analyzed_commit, last_analyzed_at, created_at, updated_at
  > `python -c "from src.models.repository import Repository; print(Repository.__tablename__)"` — prints `repositories`

- [ ] T011 [P] Create `backend/src/models/wiki_page.py`: `Wiki` model (repository_id FK, structure_version, module_count, page_count, status Enum: generating/ready/updating) and `WikiPage` model (wiki_id FK, page_type Enum, title, slug, content JSONB, source_files ARRAY, commit_hash) per `specs/001-code-wiki/data-model.md` §2-3
  > `python -c "from src.models.wiki_page import Wiki, WikiPage; print(Wiki.__tablename__, WikiPage.__tablename__)"` — prints `wikis wiki_pages`

- [ ] T012 [P] Create `backend/src/models/module.py`: `Module` model (wiki_id FK, name, slug, file_paths ARRAY, line_count, description, detection_confidence Float, dependencies_module_ids ARRAY) per `specs/001-code-wiki/data-model.md` §4
  > `python -c "from src.models.module import Module; print(Module.__tablename__)"` — prints `modules`

- [ ] T013 [P] Create `backend/src/models/chat.py`: `ChatConversation` model (repository_id FK, messages JSONB array with role/content/timestamp/references structure) per `specs/001-code-wiki/data-model.md` §6
  > `python -c "from src.models.chat import ChatConversation; print(ChatConversation.__tablename__)"` — prints `chat_conversations`

- [ ] T014 [P] Create `backend/src/models/update_event.py`: `UpdateEvent` model (repository_id FK, commit_hash, changed_files ARRAY, affected_module_ids ARRAY, status Enum: pending/processing/completed/failed) per `specs/001-code-wiki/data-model.md` §7
  > `python -c "from src.models.update_event import UpdateEvent; print(UpdateEvent.__tablename__)"` — prints `update_events`

- [ ] T015 Create Alembic migration `backend/migrations/versions/001_initial_schema.py` for all MVP tables with all indexes from `specs/001-code-wiki/data-model.md` §Indexes
  > `alembic upgrade head && psql $DATABASE_URL -c "\dt"` — lists: repositories, wikis, wiki_pages, modules, chat_conversations, update_events

- [ ] T016 Create `backend/src/storage/db.py`: async SQLAlchemy engine and session factory with connection pooling (pool_size=10, max_overflow=20, pool_pre_ping=True)
  > `python -c "from src.storage.db import get_session; print('ok')"` — imports without error

- [ ] T017 [P] Create `backend/src/storage/graph_db.py`: Neo4j async driver wrapper with `connect()`, `run_query(cypher, params)`, `create_code_entity(entity)` helpers
  > `python -c "from src.storage.graph_db import GraphDB; print(GraphDB.__name__)"` — prints `GraphDB`

- [ ] T018 [P] Create `backend/src/storage/vector_db.py`: Qdrant client wrapper, create collections on startup: `code_entities`, `dossier_findings`, `wiki_pages` (all cosine, vector size 1536)
  > After app startup: `curl http://localhost:6333/collections` — response lists all 3 collection names

- [ ] T019 Create `backend/src/cli/db.py`: CLI with commands: `init`, `migrate`, `status`, `seed`, `reset` per `specs/001-code-wiki/quickstart.md`
  > `python -m src.cli.db --help` — lists all 5 commands without error

### Parser Layer

- [ ] T020 Create `backend/src/parsers/base.py`: `CodeParser` abstract base class with abstract methods `parse_file(path) -> ParsedFile` and `extract_entities(parsed) -> list[CodeEntity]`; `ParsedFile` dataclass
  > `python -c "from src.parsers.base import CodeParser, ParsedFile; print('ok')"` — imports cleanly

- [ ] T021 [P] Create `backend/src/parsers/python_parser.py`: `PythonParser(CodeParser)` using `ast` + `jedi`. Extracts functions (name, line_number, signature, docstring, is_exported, cyclomatic_complexity), classes, imports
  > `python -c "from src.parsers.python_parser import PythonParser; p=PythonParser(); r=p.parse_file('src/parsers/python_parser.py'); print(len(r.entities), 'entities')"` — prints a non-zero entity count

- [ ] T022 [P] Create `backend/src/parsers/javascript_parser.py` and `backend/src/parsers/typescript_parser.py`: subprocess call to `backend/scripts/ts-extract.js` using TypeScript Compiler API
  > `python -c "from src.parsers.typescript_parser import TypeScriptParser; p=TypeScriptParser(); r=p.parse_file('frontend/src/app/page.tsx'); print(len(r.entities), 'entities')"` — prints non-zero count

### Dossier Schema & Manager

- [ ] T023 Create `backend/src/dossier/schema.py`: `DossierEntry` (section, content, severity, related_files, related_modules, embedding_text, tags) and `Dossier` root model with all 15 section fields as `list[DossierEntry]` per `specs/001-code-wiki/plan.md` agent catalog
  > `python -c "from src.dossier.schema import Dossier, DossierEntry; d=Dossier(); print(len(d.model_fields), 'fields')"` — prints 15 or more

- [ ] T024 Create `backend/src/dossier/manager.py`: `DossierManager` with `write(section, entry)`, `query(section, **filters)`, `get_all()`, `emit_tag(tag)`, `get_tags()`
  > `python -c "from src.dossier.manager import DossierManager; dm=DossierManager(); dm.emit_tag('test'); print(dm.get_tags())"` — prints `['test']`

- [ ] T025 Create `backend/src/dossier/rag_index.py`: `DossierRAGIndex` — embeds DossierEntry objects into Qdrant `dossier_findings` collection; `query(text, module_filter, top_k) -> list[DossierEntry]`
  > `python -c "from src.dossier.rag_index import DossierRAGIndex; print(DossierRAGIndex.__name__)"` — imports without error

### LangGraph Orchestration Skeleton

- [ ] T026 Create `backend/src/orchestrator/graph.py`: LangGraph `StateGraph` with `Dossier` as typed state, all agent node stubs, parallel edges for Layer 2 heuristic agents, sequential ConflictSynthesizer edge (runs last in Layer 2)
  > `python -c "from src.orchestrator.graph import build_graph; g=build_graph(); print(type(g).__name__)"` — prints `CompiledGraph` or `CompiledStateGraph`

- [ ] T027 [P] Create `backend/src/orchestrator/routing.py`: pure Python conditional edge functions — `should_run_security_agent(state)`, `should_run_iac_agent(state)`, etc. Zero LLM calls
  > `python -c "from src.orchestrator.routing import should_run_security_agent; from src.dossier.schema import Dossier; print(should_run_security_agent({'fingerprint': {}}))"` — returns True or False without error

- [ ] T028 [P] Create `backend/src/orchestrator/tag_triggers.py`: `TAG_TRIGGERS: dict[str, list[str]]` registry
  > `python -c "from src.orchestrator.tag_triggers import TAG_TRIGGERS; print(TAG_TRIGGERS['pattern:jwt-auth'])"` — prints `['auth_flow_tracer']`

### Capability Primitives

- [ ] T029 Create `backend/src/agents/primitives/file_reader.py`: `FileReaderTool` — read file by path, return `{path, content, line_count}`
  > `python -c "from src.agents.primitives.file_reader import FileReaderTool; t=FileReaderTool(); r=t.invoke({'path':'README.md'}); print(r['line_count'])"` — prints a positive integer

- [ ] T030 [P] Create `backend/src/agents/primitives/ast_parser_tool.py`: `ASTParserTool` — detect language, invoke parser, return list of entities as JSON
  > `python -c "from src.agents.primitives.ast_parser_tool import ASTParserTool; t=ASTParserTool(); r=t.invoke({'path':'src/parsers/python_parser.py'}); print(type(r))"` — returns a list

- [ ] T031 [P] Create `backend/src/agents/primitives/pattern_matcher.py`: `PatternMatcherTool` — regex search across repo files, returns matches with file/line/context
  > `python -c "from src.agents.primitives.pattern_matcher import PatternMatcherTool; t=PatternMatcherTool(); r=t.invoke({'pattern':'def test_','root':'.'}); print(len(r), 'matches')"` — prints non-zero count if test files exist

- [ ] T032 [P] Create `backend/src/agents/primitives/security_lens.py`: `SecurityLensTool` — scan file for injection sinks, auth bypass, hardcoded secrets, PII field patterns
  > `python -c "from src.agents.primitives.security_lens import SecurityLensTool; t=SecurityLensTool(); r=t.invoke({'path':'src/api/routes/repositories.py'}); print(type(r))"` — returns a list without error

- [ ] T033 [P] Create `backend/src/agents/primitives/structured_output_writer.py`: `StructuredOutputWriterTool` — validate and write a DossierEntry to DossierManager
  > `python -c "from src.agents.primitives.structured_output_writer import StructuredOutputWriterTool; print(StructuredOutputWriterTool.__name__)"` — imports cleanly

### FastAPI Skeleton

- [ ] T034 Create `backend/src/api/main.py`: FastAPI app, CORS, lifespan handler (connect DBs on startup), `GET /health`
  > `curl http://localhost:8000/health` — returns `{"status":"healthy","version":"1.0.0"}`

- [ ] T035 [P] Create Pydantic schemas in `backend/src/api/schemas/`: `RepositoryCreate`, `RepositoryResponse`, `WikiPageResponse`, `ModuleResponse`, `ChatMessageCreate`, `ChatResponse` matching `specs/001-code-wiki/contracts/openapi.yaml`
  > `python -c "from src.api.schemas.repository import RepositoryCreate; r=RepositoryCreate(url='https://github.com/a/b'); print(r.url)"` — prints the URL

- [ ] T036 Create stub routers returning `501 Not Implemented`: `backend/src/api/routes/repositories.py`, `wiki.py`, `chat.py`, `webhooks.py` — all paths matching `specs/001-code-wiki/contracts/openapi.yaml`
  > `curl http://localhost:8000/v1/repositories` — returns HTTP 501 (not 404)

---

## Phase 3: US1 — Automatic Repository Documentation Generation

**User Story**: A developer adds a repository URL → system generates comprehensive, structured wiki automatically, without manual intervention.

**Success Criteria**: SC-001 (50k-100k line repo < 15 min), SC-005 (95% code relationship accuracy), SC-006 (85%+ module detection)

**References**:
- Architecture: `specs/001-code-wiki/plan.md` — 3-layer multi-agent system, 23-agent catalog, LLM call budget table
- UX Mocks: `specs/001-code-wiki/ux/docs-glassmorphism/submit.html`, `progress.html`, `home.html`, `dashboard.html`, `module.html`, `function.html`, `getting-started.html`, `glossary.html`, `api-reference.html`, `search.html`

### Layer 1 — Repository Reconnaissance (0 LLM calls)

- [ ] T037 Create `backend/src/recon/fingerprint.py`: `RepoFingerprint` Pydantic model — primary_languages (dict), file_count, total_lines, system_type (Enum: web-api/cli/library/monorepo), detected_tools (list), package_files (list)
  > `python -c "from src.recon.fingerprint import RepoFingerprint; f=RepoFingerprint(primary_languages={}, file_count=0, total_lines=0, system_type='cli', detected_tools=[], package_files=[]); print(f.model_dump())"` — prints dict without error

- [ ] T038 Create `backend/src/recon/config_detector.py`: `ConfigDetector` — file-existence checks for Dockerfile, docker-compose.yml, .github/workflows/, *.tf, K8s manifests, package.json, requirements.txt, pyproject.toml, go.mod, Cargo.toml
  > `python -c "from src.recon.config_detector import ConfigDetector; d=ConfigDetector(); r=d.detect('.'); print(r)"` — returns a list that includes 'docker' (since docker-compose.yml exists in the repo)

- [ ] T039 [US1] Create `backend/src/recon/repo_recon.py`: `RepoRecon` agent — walks file tree, counts lines by extension, calls `ConfigDetector`, produces `RepoFingerprint`. Zero LLM. Completes in <2 seconds
  > `time python -c "from src.recon.repo_recon import RepoRecon; r=RepoRecon(); fp=r.run('.'); print(fp.file_count, fp.total_lines)"` — prints non-zero counts; real time < 2s

### Layer 2 — Triage Agent (1 LLM call)

- [ ] T040 [US1] Create `backend/src/agents/triage/triage_agent.py`: `TriageAgent` — single raw OpenAI SDK call (model: `qwen/qwen3-coder-30b`, base_url from `LLM_BASE_URL`). Input: `RepoFingerprint`. Output: `{agents_to_run, agent_order, budget_per_agent}`
  > With LM Studio running: `python -c "from src.agents.triage.triage_agent import TriageAgent; import asyncio; t=TriageAgent(); r=asyncio.run(t.plan(open('/tmp/fp.json').read())); print(r['agents_to_run'])"` — returns a non-empty list

### Layer 2 — Heuristic Facet Agents (7 agents, 0 LLM calls)

- [ ] T041 [P] [US1] Create `backend/src/agents/heuristic/dependency_auditor.py`: `DependencyAuditor` — parse lock files, query OSV.dev for CVEs, write to `Dossier.dependency_analysis`
  > `python -c "from src.agents.heuristic.dependency_auditor import DependencyAuditor; import asyncio; d=DependencyAuditor(); asyncio.run(d.run('.',dm)); print(dm.query('dependency_analysis'))"` on a repo with requirements.txt — prints DossierEntry list

- [ ] T042 [P] [US1] Create `backend/src/agents/heuristic/container_analyzer.py`: `ContainerAnalyzer` — parse Dockerfile + docker-compose.yml, write service topology to `Dossier.container_topology`
  > Run on this repo: `python -c "..."` — `dm.query('container_topology')` returns at least 1 DossierEntry (docker-compose.yml exists)

- [ ] T043 [P] [US1] Create `backend/src/agents/heuristic/iac_analyzer.py`: `IaCAnalyzer` — parse .tf, K8s manifests, Helm charts, write to `Dossier.iac_resources`
  > `python -c "from src.agents.heuristic.iac_analyzer import IaCAnalyzer; print(IaCAnalyzer.__name__)"` — imports without error; running on a Terraform repo returns non-empty Dossier entries

- [ ] T044 [P] [US1] Create `backend/src/agents/heuristic/api_contract_extractor.py`: `APIContractExtractor` — parse OpenAPI yaml/json, .proto, .graphql, write to `Dossier.api_contracts`
  > Run pointed at `specs/001-code-wiki/contracts/` — `dm.query('api_contracts')` returns ≥1 entry with endpoint count > 0

- [ ] T045 [P] [US1] Create `backend/src/agents/heuristic/ci_pipeline_analyzer.py`: `CIPipelineAnalyzer` — parse .github/workflows/*.yml, Jenkinsfile, write pipeline jobs to `Dossier.ci_pipeline`
  > `python -c "from src.agents.heuristic.ci_pipeline_analyzer import CIPipelineAnalyzer; print(CIPipelineAnalyzer.__name__)"` — imports cleanly; run on a repo with GitHub Actions returns non-empty entries

- [ ] T046 [P] [US1] Create `backend/src/agents/heuristic/ownership_extractor.py`: `OwnershipExtractor` — parse CODEOWNERS, git blame, write file→owner mapping to `Dossier.ownership`
  > `python -c "from src.agents.heuristic.ownership_extractor import OwnershipExtractor; print(OwnershipExtractor.__name__)"` — imports cleanly

- [ ] T047 [P] [US1] Create `backend/src/agents/heuristic/feature_flag_mapper.py`: `FeatureFlagMapper` — scan source for LaunchDarkly/Unleash/homegrown flag patterns, write to `Dossier.feature_flags`
  > `python -c "from src.agents.heuristic.feature_flag_mapper import FeatureFlagMapper; print(FeatureFlagMapper.__name__)"` — imports cleanly; running on a repo with feature flags returns non-empty entries

### Layer 2 — ReAct Iterative Agents (LangGraph create_react_agent)

- [ ] T048 [US1] Create `backend/src/agents/iterative/security_sentinel.py`: `SecuritySentinel` using `langgraph.prebuilt.create_react_agent`. Tools: FileReaderTool, PatternMatcherTool, SecurityLensTool, StructuredOutputWriterTool. Hard stop: `recursion_limit=30`. Writes atomic entries to `Dossier.security_findings`
  > `python -c "from src.agents.iterative.security_sentinel import SecuritySentinel; print(SecuritySentinel.__name__)"` — imports without error; running on a repo with auth code populates `dm.query('security_findings')` with ≥1 entry

- [ ] T049 [P] [US1] Create `backend/src/agents/iterative/data_flow_tracer.py`: `DataFlowTracer` using `create_react_agent`. Traces data from API entry points through transformations. Writes to `Dossier.data_flows`
  > `python -c "from src.agents.iterative.data_flow_tracer import DataFlowTracer; print(DataFlowTracer.__name__)"` — imports cleanly

- [ ] T050 [P] [US1] Create `backend/src/agents/iterative/auth_flow_tracer.py`: `AuthFlowTracer` using `create_react_agent`. Triggered only when Dossier tag `pattern:jwt-auth` is present. Writes to `Dossier.security_findings`
  > `python -c "from src.agents.iterative.auth_flow_tracer import AuthFlowTracer; print(AuthFlowTracer.__name__)"` — imports cleanly; agent does NOT run if tag absent (verify by checking `dm.get_tags()` before and after routing)

- [ ] T051 [P] [US1] Create `backend/src/agents/iterative/vuln_chain_tracer.py`: `VulnerabilityChainTracer` using `create_react_agent`. Triggered by `risk:sql-injection` tag. Traces call chain from vulnerable function to entry points. Writes to `Dossier.security_findings`
  > `python -c "from src.agents.iterative.vuln_chain_tracer import VulnerabilityChainTracer; print(VulnerabilityChainTracer.__name__)"` — imports cleanly

### Layer 2 — Single-Pass LLM Agents (1 LLM call each)

- [ ] T052 [P] [US1] Create `backend/src/agents/single_pass/architectural_classifier.py`: `ArchitecturalClassifier` — single raw OpenAI SDK call. Output: system_style, design_patterns list, architectural_concerns. Writes to `Dossier.architectural_classification`
  > With LM Studio running: agent returns a valid `system_style` string (e.g., "web-api/REST") and non-empty `design_patterns` list; `dm.query('architectural_classification')` returns ≥1 entry

- [ ] T053 [P] [US1] Create `backend/src/agents/single_pass/business_rule_extractor.py`: `BusinessRuleExtractor` — output: list of `{rule, code_location, confidence}`. Writes to `Dossier.business_rules`
  > With LM Studio running: `dm.query('business_rules')` returns ≥1 entry where each entry has a non-empty `code_location` field

- [ ] T054 [P] [US1] Create `backend/src/agents/single_pass/observability_auditor.py`: `ObservabilityAuditor` — output: logging gaps, missing metrics, absent trace IDs. Writes to `Dossier.observability_audit`
  > `python -c "from src.agents.single_pass.observability_auditor import ObservabilityAuditor; print(ObservabilityAuditor.__name__)"` — imports cleanly; running returns non-empty entries

- [ ] T055 [P] [US1] Create `backend/src/agents/single_pass/error_resilience_analyzer.py`: `ErrorResilienceAnalyzer` — output: error handling strategy, retry patterns, failure modes. Writes to `Dossier.error_resilience`
  > `python -c "from src.agents.single_pass.error_resilience_analyzer import ErrorResilienceAnalyzer; print(ErrorResilienceAnalyzer.__name__)"` — imports cleanly

- [ ] T056 [P] [US1] Create `backend/src/agents/single_pass/technical_debt_assessor.py`: `TechnicalDebtAssessor` — output: debt items with file locations, complexity hotspots, TODO/FIXME inventory. Writes to `Dossier.technical_debt`
  > `python -c "from src.agents.single_pass.technical_debt_assessor import TechnicalDebtAssessor; print(TechnicalDebtAssessor.__name__)"` — imports cleanly

- [ ] T057 [P] [US1] Create `backend/src/agents/single_pass/performance_hotspot_scanner.py`: `PerformanceHotspotScanner` — output: N+1 queries, blocking I/O in async code, missing caching. Writes to `Dossier.performance_hotspots`
  > `python -c "from src.agents.single_pass.performance_hotspot_scanner import PerformanceHotspotScanner; print(PerformanceHotspotScanner.__name__)"` — imports cleanly

### Layer 2 — Conflict Synthesis (runs last)

- [ ] T058 [US1] Create `backend/src/agents/conflict_synthesizer.py`: `ConflictSynthesizer` — reads all Dossier sections after other agents complete, identifies contradictions, writes QUESTIONS (never hypotheses) to `Dossier.conflict_questions`. Must run last (enforced by LangGraph edge ordering in T026)
  > After full Layer 2 run: `dm.query('conflict_questions')` returns entries whose `content` field contains question marks ("?") and references at least 2 different Dossier sections per contradiction

### Layer 3 — Module Wiki Sub-Pipeline

- [ ] T059 [US1] Create `backend/src/wiki/interestingness.py`: `InterestingnessScorer` with formula: `complexity*0.3 + fan_in*0.25 + fan_out*0.2 + is_exported*0.1 + has_side_effects*0.1 + is_entry_point*0.05`. `top_k(entities, k=15) -> list`
  > `python -c "from src.wiki.interestingness import InterestingnessScorer; s=InterestingnessScorer(); r=s.top_k([...], k=3); print(len(r))"` — returns exactly 3 items sorted descending by score

- [ ] T060 [US1] Create `backend/src/wiki/context_builder.py`: `WikiContextBuilder` — if repo ≤ 200k tokens: direct source; if larger: Qdrant RAG query capped at 10k tokens
  > `python -c "from src.wiki.context_builder import WikiContextBuilder; c=WikiContextBuilder(); r=c.build_context(module_id='x', repo_token_count=50000); print(type(r))"` — returns a string; `len(r.split())` is non-zero

- [ ] T061 [US1] Create `backend/src/wiki/page_builders/module_page.py`: `ModulePageBuilder` coordinating 3-agent sub-pipeline: StructuralAnalyst (AST, no LLM) → ImplementationExplainer (parallel per-entity LLM calls, max 15) → ModuleWeaver (single synthesis LLM call)
  > After running on a real module: returned WikiPage has `content.sections` with at least 3 sections (Overview, Key Components, How It Works); each entity explanation has `evidence_lines` referencing actual line numbers in source

- [ ] T062 [P] [US1] Create `backend/src/wiki/page_builders/home_page.py`: `HomePageBuilder` — generates wiki home page from Dossier: repo overview, module index, health summary, tech stack
  > `HomePageBuilder().build(wiki_id, dossier)` — returns WikiPage with `page_type='home'`, title non-empty, at least 3 sections, module count matches `Dossier.architectural_classification` module list

- [ ] T063 [P] [US1] Create `backend/src/wiki/page_builders/dashboard.py`: `DashboardBuilder` — health scorecard from all Dossier sections: CVE count, security severity breakdown, tech debt score, observability gaps
  > `DashboardBuilder().build(wiki_id, dossier)` — returns WikiPage with `page_type='home'` (or dedicated type); sections include a numeric CVE count that matches `len(dm.query('dependency_analysis'))`

- [ ] T064 [P] [US1] Create `backend/src/wiki/page_builders/security_view.py`: `SecurityViewBuilder` — aggregates `Dossier.security_findings` into ranked security wiki page
  > `SecurityViewBuilder().build(wiki_id, dossier)` — returned page sections contain all findings from `dm.query('security_findings')`; no findings are dropped

- [ ] T065 [P] [US1] Create `backend/src/wiki/page_builders/infra_view.py`: `InfraViewBuilder` — aggregates `container_topology`, `iac_resources`, `ci_pipeline` into infrastructure wiki page
  > `InfraViewBuilder().build(wiki_id, dossier)` — returns WikiPage with content sections referencing Docker/CI data present in the Dossier

- [ ] T066 [P] [US1] Create `backend/src/wiki/page_builders/domain_view.py`: `DomainViewBuilder` — aggregates `business_rules` and `feature_flags` into domain wiki page
  > `DomainViewBuilder().build(wiki_id, dossier)` — returns WikiPage; if `dm.query('business_rules')` is non-empty, page sections contain rule text with code locations

- [ ] T067 [US1] Create `backend/src/wiki/orchestrator.py`: `WikiOrchestrator` — coordinates full wiki generation across all modules (parallel asyncio.gather), skips unchanged modules via semantic hash, persists all WikiPage records to PostgreSQL
  > After run on a test repo: `SELECT count(*) FROM wiki_pages WHERE wiki_id='{id}'` — count equals number of detected modules plus number of special pages (home, dashboard, security, infra, domain)

### Code Entity Graph

- [ ] T068 [US1] Create `backend/src/graph/models.py` and `backend/src/graph/queries.py`: Neo4j CodeEntity node upsert, all 6 relationship types from `specs/001-code-wiki/data-model.md` §5
  > After parsing a Python file: `MATCH (n:CodeEntity) RETURN count(n)` in Neo4j Browser (localhost:7474) — returns non-zero count; `MATCH ()-[r:CALLS]->() RETURN count(r)` returns non-zero if any function calls exist

### Repository Clone & Cache

- [ ] T069 [US1] Create `backend/src/storage/repo_cache.py`: `RepoCacheManager` using gitpython — `clone(url)`, `fetch_updates(path)`, `get_changed_files(path, from_commit, to_commit)`, `get_all_files(path)`
  > `python -c "from src.storage.repo_cache import RepoCacheManager; m=RepoCacheManager('/tmp/test-cache'); path=m.clone('https://github.com/tiangolo/fastapi'); print(path)"` — prints a valid local path where repo exists

### Analysis Pipeline Glue

- [ ] T070 [US1] Create `backend/src/analysis_pipeline.py`: `AnalysisPipeline.run(repo_id)` — clone → Layer 1 → Triage → Layer 2 parallel facets via LangGraph → DossierRAGIndex → Layer 3 wiki → update Repository.status throughout
  > `SELECT status FROM repositories WHERE id='{id}'` starts as `analyzing` during run, ends as `ready`; `SELECT count(*) FROM wiki_pages WHERE wiki_id=(SELECT id FROM wikis WHERE repository_id='{id}')` is > 0 after completion

### REST API — US1 Endpoints

- [ ] T071 [US1] Implement `POST /v1/repositories`: validate URL, create Repository (status=pending), enqueue `AnalysisPipeline.run()` as background task, return 202
  > `curl -X POST localhost:8000/v1/repositories -H "Content-Type: application/json" -d '{"url":"https://github.com/tiangolo/fastapi"}'` — returns HTTP 202 with `{"id": "<uuid>", "status": "pending"}`

- [ ] T072 [P] [US1] Implement `GET /v1/repositories/{id}` and `GET /v1/repositories/{id}/status`
  > `curl localhost:8000/v1/repositories/{id}/status` — returns `{"status":"analyzing","progress":0.45,"active_agent":"dependency_auditor"}` (not 404, not 501)

- [ ] T073 [P] [US1] Implement `GET /v1/repositories/{id}/wiki`
  > After analysis completes: `curl localhost:8000/v1/repositories/{id}/wiki` — returns JSON with `page_count > 0` and `module_count > 0`

- [ ] T074 [P] [US1] Implement `GET /v1/repositories/{id}/wiki/pages` and `GET /v1/repositories/{id}/wiki/pages/{page_id}`
  > `curl localhost:8000/v1/repositories/{id}/wiki/pages` — returns array with at least 1 page; each page has `content.sections` array with at least 1 section

- [ ] T075 [P] [US1] Implement `GET /v1/repositories/{id}/modules` and `GET /v1/repositories/{id}/modules/{module_id}`
  > `curl localhost:8000/v1/repositories/{id}/modules` — returns array with `detection_confidence` ≥ 0.0 for every module

- [ ] T076 [P] [US1] Implement `GET /v1/search?q={query}&repo_id={id}`
  > `curl "localhost:8000/v1/search?q=authentication&repo_id={id}"` — returns JSON array with at least 1 result when the repo has auth-related code; each result has `page_slug` and `excerpt` fields

### Frontend — US1 Pages

- [ ] T077 [US1] Create glassmorphism design system in `frontend/src/styles/globals.css`: CSS variables extracted from `specs/001-code-wiki/ux/docs-glassmorphism/home.html` — backdrop-filter, glass backgrounds, gradients, font imports, accent colors
  > Open any page side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/home.html`: (1) DevTools computed styles show `backdrop-filter: blur(...)` on glass panels — not absent or `none`; (2) `font-family` in computed styles matches the distinctive typeface visible in mock — not system-ui, Arial, or Inter; (3) accent color CSS variable matches the hex/rgba value used in mock (verify with DevTools color picker); (4) glass panel backgrounds are translucent rgba — not solid; (5) `--glass-bg` or equivalent variable is referenced by all panel components

- [ ] T078 [P] [US1] Create shared layout components: `frontend/src/components/layout/Sidebar.tsx`, `Header.tsx`, `Navigation.tsx` matching structure from `specs/001-code-wiki/ux/docs-glassmorphism/home.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/home.html`: (1) sidebar nav labels and hierarchy match mock exactly; (2) header height, logo position, and right-side controls match mock; (3) sidebar glassmorphism panel (blur, border, background opacity) matches mock visually; (4) active nav item highlight color and style match mock; (5) hover states on nav items match mock; (6) no console errors

- [ ] T079 [US1] Implement `frontend/src/app/page.tsx` (home / repository list): match `specs/001-code-wiki/ux/docs-glassmorphism/home.html`
  > `curl localhost:3000` returns HTML 200; open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/home.html`: (1) hero section heading, subtext, and CTA button layout match mock; (2) repository cards use glassmorphism styling — blur, translucent background, and border matching mock exactly; (3) card grid column count matches mock at same viewport width (1280px); (4) empty state (no repos yet) renders a placeholder matching mock's empty state if shown; (5) clicking "Add Repository" navigates to `/submit`

- [ ] T080 [US1] Implement `frontend/src/app/submit/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/submit.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/submit.html`: (1) form container glassmorphism style (blur, border, background) matches mock; (2) URL input border, focus ring color, and placeholder text match mock; (3) submit button color, size, and hover state match mock; (4) validation error message position and typography match mock; (5) entering an invalid URL shows inline error; (6) submitting a valid URL calls `POST /v1/repositories` and redirects to `/repositories/{id}/progress`

- [ ] T081 [US1] Implement `frontend/src/app/repositories/[id]/progress/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/progress.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/progress.html`: (1) progress indicator (bar or ring) style and color match mock; (2) agent activity feed layout (agent name, status icon, timestamp) matches mock item styling; (3) glassmorphism container card for progress section matches mock; (4) overall page background and typography match mock; (5) Network DevTools shows status polling every 3s; (6) agent names appear in feed as they activate; (7) when status becomes `ready`, page automatically redirects to `/repositories/{id}/wiki`

- [ ] T082 [US1] Implement `frontend/src/app/repositories/[id]/wiki/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/dashboard.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/dashboard.html`: (1) health scorecard widget positions, colors, and icon styles match mock; (2) CVE count and security finding count display correct API data values; (3) module card grid columns and card proportions match mock at 1280px viewport; (4) each glassmorphism card (blur, border, shadow, background opacity) matches mock styling for all card types present; (5) module card links navigate to correct module URLs; (6) severity color coding (red/yellow/green) matches mock

- [ ] T083 [US1] Implement `frontend/src/app/repositories/[id]/wiki/modules/[module_id]/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/module.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/module.html`: (1) prose narrative section typography (font size, line height, paragraph spacing) matches mock; (2) entity list item layout (entity name, type badge color/shape, line number chip) matches mock; (3) glassmorphism section containers match mock (blur, border, background); (4) dependency section layout and link styling match mock; (5) entity list shows all CodeEntities with line numbers from API; (6) clicking an entity navigates to the correct entity detail URL

- [ ] T084 [US1] Implement `frontend/src/app/repositories/[id]/wiki/modules/[module_id]/entities/[entity_id]/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/function.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/function.html`: (1) three-section layout (Purpose / How It Works / Gotchas) positions and proportions match mock; (2) section heading typography and divider styling match mock; (3) evidence line number citations use same visual treatment as mock (e.g., inline code chip, line badge, or highlighted reference); (4) "View source" button/link style, position, and icon match mock; (5) glassmorphism card containing all sections matches mock blur, border, and background; (6) function signature display (if shown) matches mock styling

- [ ] T085 [P] [US1] Implement `frontend/src/app/repositories/[id]/wiki/getting-started/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/getting-started.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/getting-started.html`: (1) page layout (content width, sidebar if present, padding) matches mock; (2) heading hierarchy (h1, h2, h3) typography matches mock font size and weight; (3) code block styling (background, font, padding, border-radius) matches mock; (4) glassmorphism content container matches mock styling; (5) all text content is AI-generated — no hardcoded placeholders like "Lorem ipsum" or "Coming soon"; (6) page renders at `/repositories/{id}/wiki/getting-started` without 404

- [ ] T086 [P] [US1] Implement `frontend/src/app/search/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/search.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/search.html`: (1) search input bar width, border, focus ring, and icon match mock; (2) search result card layout (title, excerpt snippet, breadcrumb path) matches mock proportions and spacing; (3) result card glassmorphism styling (blur, border, hover state lift effect) matches mock; (4) searching "authentication" returns ≥1 result with a wiki page link; (5) clicking a result navigates to the correct wiki page; (6) nonsense query shows empty state panel matching mock empty state design — not a crash, blank page, or unstyled "no results" text

- [ ] T087 [US1] Create `frontend/src/services/api.ts`: typed fetch client for all endpoints in `specs/001-code-wiki/contracts/openapi.yaml`
  > `npx tsc --noEmit` in frontend/ — compiles without type errors; all response types used in page components match the TypeScript interfaces in api.ts

---

## Phase 4: US2 — Real-Time Documentation Synchronization

**User Story**: Code commits trigger automatic wiki updates. Documentation never drifts from code.

**Success Criteria**: SC-002 (updates within 5 min of commits), SC-011 (sync with code), SC-012 (<1% drift)

**References**:
- Data Model: `specs/001-code-wiki/data-model.md` §7 — UpdateEvent entity and status transitions
- Plan: `specs/001-code-wiki/plan.md` — semantic hash caching, incremental analysis

- [ ] T088 [US2] Create `backend/src/sync/semantic_hasher.py`: `SemanticHasher` — canonical AST hash of function/class body ignoring comments, whitespace, docstrings using `ast.dump()` after stripping docstring nodes
  > `python -c "from src.sync.semantic_hasher import SemanticHasher; h=SemanticHasher(); h1=h.hash_function('def f():\n  # comment\n  return 1'); h2=h.hash_function('def f():\n  return 1'); print(h1==h2)"` — prints `True` (comments stripped)

- [ ] T089 [US2] Create `backend/src/sync/incremental_analyzer.py`: `IncrementalAnalyzer` — re-runs pipeline for only affected modules; skips unchanged functions via semantic hash
  > Submit a commit that changes 1 file in 1 module → UpdateEvent shows `affected_module_ids` contains only that 1 module's ID; unchanged modules' WikiPage.updated_at is NOT changed

- [ ] T090 [US2] Create `backend/src/sync/drift_detector.py`: `DriftDetector` — compare repo HEAD commit with WikiPage.commit_hash, compute drift percentage
  > After pipeline completes: `DriftDetector().check_drift(repo_id).drift_percent` == 0.0; after artificially advancing the repo HEAD without running sync: drift_percent > 0

- [ ] T091 [US2] Implement `POST /v1/webhooks/github`: verify HMAC-SHA256 signature from `X-Hub-Signature-256`, parse push event, create UpdateEvent, enqueue IncrementalAnalyzer
  > Send request with correct signature: returns HTTP 200; send with wrong signature: returns HTTP 403 (not 200 or 500); `SELECT count(*) FROM update_events` increases by 1 per webhook call

- [ ] T092 [P] [US2] Implement `PUT /v1/repositories/{id}/sync`, `GET /v1/repositories/{id}/updates`, `GET /v1/repositories/{id}/updates/{update_id}`
  > `curl -X PUT localhost:8000/v1/repositories/{id}/sync` — returns 202 and creates UpdateEvent; `curl localhost:8000/v1/repositories/{id}/updates` — returns array including the new event with `status` field

---

## Phase 5: US3 — Interactive AI-Powered Chat Assistant

**User Story**: Developers ask natural language questions about the codebase, receive accurate answers with direct code links.

**Success Criteria**: SC-003 (90% of responses include code references), SC-004 (40% reduction in time to understand unfamiliar codebases)

**References**:
- UX Mock: `specs/001-code-wiki/ux/docs-glassmorphism/chat.html`

- [ ] T093 [US3] Create `backend/src/chat/context_builder.py`: `ChatContextBuilder` — retrieve top-5 WikiPages via Qdrant, top-10 DossierEntries via RAG index, matching CodeEntities from Neo4j. Cap at 50k tokens
  > `python -c "from src.chat.context_builder import ChatContextBuilder; c=ChatContextBuilder(); r=c.build(question='How does auth work?', repo_id='x'); print(len(r.split()))"` — returns >100 words of context; does not exceed 50k tokens

- [ ] T094 [US3] Create `backend/src/chat/assistant.py`: `ChatAssistant` — LLM call with system prompt requiring `[[WikiPage:slug]]` and `[[CodeEntity:qualified_name]]` reference markers; resolves markers to URLs post-response
  > With LM Studio running: assistant response to "How does authentication work?" contains at least one `[[WikiPage:...]]` marker in raw output; resolved response contains actual `/wiki/pages/...` URLs

- [ ] T095 [US3] Implement `POST /v1/repositories/{id}/chat`
  > `curl -X POST localhost:8000/v1/repositories/{id}/chat -d '{"message":"How does authentication work?"}' -H "Content-Type: application/json"` — returns JSON with `content` (non-empty string) and `references` (array, may be empty but field must exist); HTTP 200

- [ ] T096 [P] [US3] Implement `GET /v1/repositories/{id}/chat/conversations` and `GET /v1/repositories/{id}/chat/conversations/{conv_id}`
  > After sending 2 messages: `GET /conversations/{conv_id}` returns conversation with `messages` array containing exactly 2 user messages and 2 assistant messages in chronological order

- [ ] T097 [US3] Implement `frontend/src/app/repositories/[id]/chat/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/chat.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/chat.html`: (1) user message bubble alignment, background color, and border-radius match mock; (2) assistant message bubble styling (color, border, avatar if present) matches mock; (3) wiki page reference chip/badge visual style (color, shape, icon) matches mock; (4) chat input area (textarea sizing, send button style) position at bottom matches mock; (5) message thread scroll container height matches mock; (6) typing and pressing Enter sends message; (7) no layout shift or scroll jump on response arrival

---

## Phase 6: US4 — Visual Architecture and Relationship Diagrams

**User Story**: Auto-generated visual diagrams that update automatically when code changes.

**Success Criteria**: SC-005 (95% accuracy in code relationships), SC-014 (diagrams auto-update on commits)

**References**:
- UX Mock: `specs/001-code-wiki/ux/docs-glassmorphism/diagrams.html`
- Data Model: `specs/001-code-wiki/data-model.md` §5 — CodeEntity relationships

- [ ] T098 [US4] Create `backend/src/wiki/diagrams/graph_exporter.py`: `GraphExporter` — queries Neo4j for module-level CALLS/IMPORTS, exports D3-compatible `{nodes, links}` JSON
  > `python -c "from src.wiki.diagrams.graph_exporter import GraphExporter; r=GraphExporter().export(repo_id='x'); print(len(r['nodes']), 'nodes,', len(r['links']), 'links')"` — both counts non-zero for a repo with multiple modules

- [ ] T099 [P] [US4] Create `backend/src/wiki/diagrams/sequence_generator.py`: `SequenceGenerator` — traces call chain up to depth 5, generates Mermaid `sequenceDiagram` markup
  > Output string starts with `sequenceDiagram` and contains `->>`  arrows; chain depth does not exceed 5 hops from entry point

- [ ] T100 [P] [US4] Create `backend/src/wiki/diagrams/class_diagram_generator.py`: `ClassDiagramGenerator` — queries INHERITS_FROM and DEFINES, generates Mermaid `classDiagram`
  > Output string starts with `classDiagram`; each class with inheritance shows `ParentClass <|-- ChildClass` arrow

- [ ] T101 [P] [US4] Implement `GET /v1/repositories/{id}/diagrams/architecture`
  > `curl localhost:8000/v1/repositories/{id}/diagrams/architecture` — returns `{"nodes":[...],"links":[...]}` with at least 2 nodes; node count matches module count from `GET /v1/repositories/{id}/modules`

- [ ] T102 [P] [US4] Implement `GET /v1/repositories/{id}/wiki/modules/{module_id}/diagrams/sequence` and `/class`
  > Both endpoints return HTTP 200 with a non-empty string starting with `sequenceDiagram` or `classDiagram` respectively; return HTTP 404 if module has no entry points or no classes

- [ ] T103 [US4] Implement `frontend/src/app/repositories/[id]/wiki/diagrams/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/diagrams.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/diagrams.html`: (1) diagram canvas area dimensions and position on page match mock; (2) tab switcher (Architecture / Sequence / Class) shape, color, and active-tab indicator style match mock; (3) D3 node color, size, and link color match mock; (4) glassmorphism panel surrounding the diagram canvas matches mock blur and border; (5) clicking a node shows highlight and tooltip with same visual treatment as mock; (6) switching to Sequence tab renders Mermaid diagram without overflow or clipping; (7) no console errors on page load

---

## Phase 7: Polish & Cross-Cutting Concerns

**Goal**: Complete remaining UI pages, production hardening, observability.

**References**: `specs/001-code-wiki/ux/docs-glassmorphism/glossary.html`, `api-reference.html`, `error.html`

- [ ] T104 [P] Implement `frontend/src/app/repositories/[id]/wiki/glossary/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/glossary.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/glossary.html`: (1) alphabetical group header (A, B, C...) styling matches mock; (2) term entry layout (term name, definition text, code location link) matches mock spacing and typography; (3) glassmorphism section or card container matches mock styling; (4) each term's code location link is clickable and navigates correctly; (5) empty state (no business rules extracted) renders a styled placeholder matching mock empty state — not a blank section or unstyled text

- [ ] T105 [P] Implement `frontend/src/app/repositories/[id]/wiki/api/page.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/api-reference.html`
  > Open side-by-side with `specs/001-code-wiki/ux/docs-glassmorphism/api-reference.html`: (1) HTTP method badge colors match mock (GET=blue, POST=green, PUT=amber, DELETE=red or equivalent); (2) endpoint row layout (method badge, path, description) matches mock proportions; (3) collapsible schema section expand/collapse animation and styling match mock; (4) glassmorphism endpoint card (border, blur, background) matches mock; (5) all content is from `Dossier.api_contracts` — no hardcoded placeholder endpoint data; (6) page renders empty state gracefully if no contracts were extracted

- [ ] T106 [P] Implement `frontend/src/app/error.tsx` and `frontend/src/app/not-found.tsx`: match `specs/001-code-wiki/ux/docs-glassmorphism/error.html`
  > Navigating to `/nonexistent-path` shows the 404 page with glassmorphism styling matching the mock; throwing an error in a page component shows the error boundary page, not a blank screen

- [ ] T107 Add structured error handling in `backend/src/api/main.py`: global exception handler returning RFC 7807 problem+json with correlation ID
  > Triggering a 500 error: response body is `{"type":"about:blank","title":"Internal Server Error","status":500,"correlation_id":"<uuid>"}` not raw Python traceback; `Content-Type` header is `application/problem+json`

- [ ] T108 [P] Implement `GET /v1/repositories/{id}/status/stream` (Server-Sent Events): emits agent start/complete events; update progress page to consume SSE
  > `curl -N -H "Accept: text/event-stream" localhost:8000/v1/repositories/{id}/status/stream` — outputs `data: {...}` lines as agents complete; browser EventSource on progress page receives events without polling

- [ ] T109 [P] Index WikiPage content into Qdrant `wiki_pages` collection after wiki generation
  > After pipeline completes: `curl localhost:6333/collections/wiki_pages` — response shows `vectors_count > 0`; `GET /v1/search?q=authentication&repo_id={id}` returns results (was empty before this task)

- [ ] T110 [P] Create `backend/Dockerfile`: multi-stage Python 3.11 build
  > `docker build -t code-wiki-backend backend/` — exits 0; `docker run -p 8000:8000 code-wiki-backend` starts and `curl localhost:8000/health` returns 200

- [ ] T111 [P] Create `frontend/Dockerfile`: Node 18 build
  > `docker build -t code-wiki-frontend frontend/` — exits 0; `docker run -p 3000:3000 code-wiki-frontend` starts and `curl localhost:3000` returns HTML

- [ ] T112 Update `docker-compose.yml`: add `backend` and `frontend` services with health checks and service dependencies
  > `docker-compose up -d && docker-compose ps` — shows 5 services all "Up" (postgres, neo4j, qdrant, backend, frontend); backend service waits for postgres health check before starting

---

## Dependency Graph

```
Phase 1: Setup
    ↓
Phase 2: Foundation  ← blocks ALL subsequent phases
    ↓
Phase 3: US1 (Auto Wiki)  ← primary product value, P1
    ↓
Phase 4: US2 (Sync)       ← depends on Phase 3 pipeline
    ↓
Phase 5: US3 (Chat)       ─┐ can run in parallel with each other
Phase 6: US4 (Diagrams)   ─┘ both depend on Phase 3 completion
    ↓
Phase 7: Polish
```

---

## Summary

| Phase | Story | Task Range | Count | Parallelizable |
|-------|-------|-----------|-------|----------------|
| Phase 1: Setup | — | T001-T008 | 8 | 6 |
| Phase 2: Foundation | — | T009-T036 | 28 | 20 |
| Phase 3: US1 Auto Wiki | P1 | T037-T087 | 51 | 33 |
| Phase 4: US2 Sync | P2 | T088-T092 | 5 | 1 |
| Phase 5: US3 Chat | P3 | T093-T097 | 5 | 1 |
| Phase 6: US4 Diagrams | P4 | T098-T103 | 6 | 4 |
| Phase 7: Polish | — | T104-T112 | 9 | 5 |
| **Total** | | | **112** | **70 parallelizable** |

**Suggested MVP scope**: Complete Phases 1-3. Phase 3 (US1) alone delivers the core product value — automatic wiki generation from a repository URL.
