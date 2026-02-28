# code-wiki

AI-powered code documentation platform that automatically generates and maintains comprehensive, structured wiki-style documentation for code repositories.

## Project Overview

**Status**: Implementation phase (Active — Granular progress tracking wired end-to-end, pipeline logging + gap fixes applied)
**Feature Branch**: `001-code-wiki`
**Main Branch**: `main`

This platform addresses documentation drift by automatically analyzing repositories, generating hyperlinked documentation with architecture overviews and code relationships, and synchronizing updates within 5 minutes of commits. Inspired by Google Code Wiki.

**Core Value Proposition**: Reduce time to understand unfamiliar codebases by 40% through AI-powered automatic documentation that stays synchronized with code.

## Project Structure

```
code-wiki/
  backend/                       # FastAPI Python backend
    src/
      agents/                    # Facet intelligence agents (heuristic/, iterative/, single_pass/)
      api/                       # FastAPI endpoints and routes
      chat/                      # AI chat assistant module
      dossier/                   # LangGraph shared state blackboard
      llm/                       # LM Studio client interface
      models/                    # Database models (PostgreSQL)
      orchestrator/              # LangGraph StateGraph wiring
      parsers/                   # Language-specific code parsers
      recon/                     # Layer 0: Repo Reconnaissance
      storage/                   # Neo4j + Qdrant storage layer
      wiki/                      # Wiki page generation pipeline
        page_builders/           # Module, dashboard, special page builders
        context_builder.py       # RAG context assembly
    requirements.txt
  frontend/                      # Next.js + TypeScript frontend
    src/
      app/                       # Next.js App Router pages
        [owner]/[name]/          # Unified wiki reader (3-column: sidebar + content + TOC)
          [slug]/                # Wiki section pages (all rendered by unified reader)
          progress/              # Analysis progress page
        dashboard/               # Repository list management
        login/                   # OAuth + email auth
        submit/                  # Add repository form
      components/ui/             # Shared UI components
        Breadcrumbs.tsx          # Navigation breadcrumbs
        CodeBlock.tsx            # Syntax-highlighted code with copy
        GlassCard.tsx            # Glassmorphism card container
        GradientBackground.tsx   # Animated gradient background
        InfoBox.tsx              # Callout info boxes (4 variants)
        Logo.tsx                 # App logo component
        StatusIndicator.tsx      # Animated status dot
        TypeBadge.tsx            # Entity type badge (class/function/etc.)
      services/api.ts            # Typed API client with unified namespace
  docker-compose.yml             # PostgreSQL, Neo4j, Qdrant, Redis services
  specs/
    001-code-wiki/
      spec.md                    # Complete feature specification
      plan.md                    # Implementation plan with phases
      research.md                # Technology decisions and rationale
      data-model.md              # Entity schemas and relationships
      quickstart.md              # Development environment setup
      tasks.md                   # Implementation task list (all phases)
      contracts/
        openapi.yaml             # REST API specification
      ux/
        docs-glassmorphism/      # 9-page glassmorphism mock set (6 wiki-content pages absorbed into unified reader)
        docs-brutalist/          # Brutalist design variant
  .specify/
    templates/                   # Specify framework templates
    memory/                      # Temporary state (gitignored)
  .claude/
    observability/              # Session tracking
    *.local.md                  # Local plugin config (gitignored)
```

## Key Features (Prioritized)

### P1 - Automatic Documentation Generation
- Accept repository URLs and analyze entire codebase
- Generate structured wiki with architecture, components, relationships
- Create hyperlinked documentation (concepts → source code)
- Support multiple languages (Python, JavaScript, Java, Go, TypeScript)

### P2 - Real-Time Synchronization
- Webhook-based automatic updates on commits
- Documentation reflects current codebase state
- Track version/commit documentation represents

### P3 - AI Chat Assistant
- Natural language queries about codebase
- Contextual answers with code references
- Dependency and relationship analysis

### P4 - Visual Diagrams
- Auto-generated architecture diagrams
- Class relationships and sequence flows
- Updates automatically with code changes

## Specification Framework

This project uses **Specify** framework for requirements management:

**Templates Location**: `.specify/templates/`
- `spec-template.md` - Feature specification structure
- `checklist-template.md` - Quality validation
- `plan-template.md` - Implementation planning
- `tasks-template.md` - Task breakdown

**Current Specification**: `specs/001-code-wiki/spec.md`

**Key Specification Elements**:
- 4 prioritized user stories (P1-P4)
- 20 functional requirements (FR-001 to FR-020)
- 10 measurable success criteria
- 7 documented edge cases
- Clear scope boundaries (10 out-of-scope items)

## Success Metrics

- Documentation generation: 10 minutes for 50k-100k LOC repositories
- Auto-update latency: Within 5 minutes of commit
- Relationship detection accuracy: 95%
- Time-to-understand reduction: 40%
- AI response relevance: 90% include code references

## Technology Stack

**Finalized (2026-02-15)**: Complete architecture decisions documented in `specs/001-code-wiki/research.md`

| Component | Technology | Key Rationale |
|-----------|-----------|---------------|
| **Backend** | Python 3.11 + FastAPI | Async support, type safety, auto-generated OpenAPI docs |
| **Code Parsing** | TypeScript Compiler API (JS/TS)<br>Jedi + Python AST (Python) | 95%+ accuracy with full semantic analysis vs 70-80% with Tree-sitter |
| **LLM** | LM Studio + QwenCoder (local) | Zero cost, privacy-first, self-hosted, no API limits |
| **Graph DB** | Neo4j Community | Graph-optimized for code relationship queries |
| **Vector DB** | Qdrant (self-hosted) | High performance, open source, advanced filtering |
| **RDBMS** | PostgreSQL 15+ | JSONB flexibility, mature, reliable |
| **Frontend** | React + TypeScript + Next.js | Ecosystem depth, SSR for SEO |
| **Deployment** | Railway (MVP) → AWS (Production) | Fast iteration first, scale later |

### Key Architecture Decisions

**Self-Hosted Stack**: LM Studio + Qdrant eliminate external API costs and privacy concerns
- LLM runs locally via LM Studio (OpenAI-compatible API on localhost:1234)
- qwen3-coder-30b model optimized specifically for code tasks (configured via `LLM_MODEL` in `backend/.env`)
- Qdrant vector DB runs in Docker container (ports 6333/6334)

**Accuracy Over Uniformity**: Language-specific parsers prioritized over universal Tree-sitter
- TypeScript Compiler API: Full type resolution, import tracking, exact call graphs
- Jedi + Python AST: Cross-file imports, type annotations, 100% accurate dependency resolution
- Achieves spec requirement SC-006: 95% precision in code relationships
- See `specs/001-code-wiki/research.md` for detailed "Accuracy over Uniformity" philosophy

## Workflows

### Specification Validation with External AI
**Pattern**: Use `/ask-gemini` skill for collaborative spec review

**Process**:
1. Extract full specification from `specs/001-code-wiki/spec.md`
2. Create structured prompt with:
   - Mission statement (recreating Google Code Wiki magic)
   - Complete spec summary (user stories, requirements, success criteria)
   - 8 critical question categories (essential features, gaps, priorities, architecture, metrics, MVP, complexity, improvements)
3. Request specific deliverables (missing features, spec revisions, priority recommendations, architecture guidance, MVP clarity, risks, metrics)
4. Store prompt in `tmp/gemini-prompt.txt` for reuse
5. Collaborate with Gemini for brutally honest feedback

**Value**: External validation catches gaps, unrealistic metrics, and missing features before implementation

## MVP Scope Decisions

**Git Integration**: Excluded from MVP to reduce complexity
- MVP focuses on static code analysis and documentation generation only
- No commit tracking, PR descriptions, or expertise mapping in initial release
- Git blame attribution may be included for basic "last modified" info
- Full Context Layer (version control integration) deferred to post-MVP phases

**Repository Access**: Public repositories only
- Private repository access deferred from MVP (no GitHub App integration)
- No OAuth flows or access token management required
- Simplifies authentication infrastructure

**User Authentication**: Removed from MVP
- No login flows required for initial release
- Eliminates OAuth integration complexity
- Focus exclusively on public data access

**Embedding Model**: LMStudio selected as provider
- Local embedding generation for semantic search
- Avoids external API dependencies for embeddings

**Rationale**: Allow MVP to validate core value proposition (AI-powered documentation generation) without authentication flows, private access token management, and OAuth integration complexity.

## Wiki Architecture

**Design Decision**: Wiki-based documentation (structured, browsable pages) vs chatbot interface (Q&A only)

### Page Types (6 Categories)
1. **Home** - High-level project overview
2. **Module/System** - Logical component documentation
3. **Function/Class/API Reference** - Detailed API docs
4. **Architecture Overview** - System design with diagrams
5. **Dependency Graphs** - Inter-module relationships
6. **Glossary** - Auto-extracted from comments/docstrings

### Module Page Structure (8 Sections)
1. **Overview/Purpose** - Module's role in system
2. **Key Components** - Major classes/functions
3. **Dependencies** - What it uses / what uses it
4. **Public API** - Interaction patterns
5. **Configuration** - Relevant settings
6. **Code Examples** - Runnable snippets
7. **Related Documentation** - Cross-links
8. **Known Issues/Caveats** - Common pitfalls

### Auto-Generation Strategy (Multi-Strategy)
1. **Directory Structure** (Primary) - Maps folders to modules (e.g., `src/auth/` → Authentication module)
2. **Import/Call Graph Analysis** - Clusters frequently-interacting files
3. **Naming Conventions** - Detects consistent prefixes/suffixes
4. **Configuration File Analysis** - Identifies distinct services

### Quality Criteria
**Useful pages**: Accurate/fresh, clear/concise, contextual (why not just what), actionable with examples, well-navigated, include visual aids

**Avoid**: Outdated content, bloated/redundant info, lacks context, difficult navigation, too generic without project-specific tailoring

### Edge Case Handling Architecture

**Strategy**: Hybrid AI classification with rule-based pre-filtering

**Five Edge Case Categories**:
1. **Orphaned files** - Don't fit obvious modules
2. **Cross-cutting utilities** - Used everywhere
3. **Ambiguous module boundaries** - Unclear classification
4. **Micro-modules** - Too small for separate pages
5. **Mega-modules** - Too large to be useful

**Classification Approach**:
- **Rule-based pre-classification**: Identifies known patterns from spec.md (repository size, language diversity)
- **LLM anomaly detection**: Handles novel/ambiguous cases
- **Signals**: Import patterns, usage context, semantic clustering

**Architecture Pattern**: Independent supervisory module acting as quality gate
- Consumes Update Events
- Produces Documentation Pages or Edge Case Events
- Uses Langfuse observability for feedback loop

**Confidence Scoring**:
- Structural integrity metrics
- LLM self-assessment (generation model rates its own output clarity/completeness)
- User feedback via Langfuse traces

**MVP Validation**: Test against repositories with known edge cases, track detection rates and false positives via Langfuse dashboards

## Development Setup

**Quick Start**: See `specs/001-code-wiki/quickstart.md` for complete setup guide

### Initial Setup

```bash
# 1. Start database services
docker-compose up -d

# 2. Setup LM Studio (one-time)
# Download from https://lmstudio.ai
# Load "Qwen2.5-Coder-7B-Instruct" model
# Start server on port 1234

# 3. Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m src.cli.db init && python -m src.cli.db migrate

# 4. Frontend setup
cd frontend
npm install
```

### Running the App (Every Session)

```bash
# 1. Start Docker services (requires Rancher Desktop or Docker Desktop to be open)
docker-compose up -d
docker-compose ps   # verify all 4 services are Up

# 2. Run migrations (only needed after schema changes or first run)
cd backend
DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" alembic upgrade head

# 3. Start backend (from backend/, venv active)
source venv/bin/activate
DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  uvicorn src.api.main:app --reload --port 8000

# 4. Start frontend (separate terminal, from frontend/)
npm run dev

# 5. Optionally start RQ worker for background analysis jobs (separate terminal, from backend/)
source venv/bin/activate
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  rq worker analysis
```

**Verify everything is up:**
```bash
curl http://localhost:8000/health   # all services should show "healthy"
open http://localhost:3000          # frontend
open http://localhost:8000/docs     # Swagger API docs
```

### Development Commands

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start PostgreSQL, Neo4j, Qdrant, and Redis services |
| `docker-compose ps` | Check service status |
| `uvicorn src.api.main:app --reload --port 8000` | Start backend dev server (from backend/) |
| `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES rq worker analysis` | Start RQ worker on macOS (from backend/, requires `venv` active) |
| `npm run dev` | Start frontend dev server on port 3000 (from frontend/) |
| `curl http://localhost:8000/health` | Test backend health endpoint |
| `curl http://localhost:1234/v1/models` | Verify LM Studio is running |

### Service Ports

- Backend API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs` (auto-generated Swagger)
- Frontend: `http://localhost:3000`
- PostgreSQL: `localhost:5434` (host) → container 5432 (remapped to avoid local postgres conflict)
- Neo4j Browser: `http://localhost:7474`
- Qdrant: `http://localhost:6333` (REST), `localhost:6334` (gRPC)
- Redis: `localhost:6380` (host) → container 6379 (remapped to avoid local redis conflict)
- LM Studio: `http://localhost:1234` (OpenAI-compatible API)

## Gotchas

- **LM Studio required**: Backend depends on LM Studio running on localhost:1234 - start it before backend
- **GPU recommended**: qwen3-coder-30b model runs best with sufficient VRAM; configure model name in `backend/.env` via `LLM_MODEL`
- **Port conflicts**: PostgreSQL and Redis host ports are remapped (5434 and 6380) to avoid conflicts with local services — ensure `DATABASE_URL` and `REDIS_URL` in `backend/.env` match docker-compose port mappings
- **Qdrant in Docker**: Vector database runs in container, data persists in `qdrant_data` volume
- **macOS fork safety**: RQ worker crashes on macOS without `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`
- **RQ worker code changes**: RQ worker must be restarted after backend code changes — it caches imported Python modules in memory
- **RQ queue name**: Jobs are enqueued to the `analysis` queue — always start the worker with `rq worker analysis`, not the default queue
- **Neo4j optional**: Backend starts in degraded mode without Neo4j (graph queries disabled); safe to skip during local dev if disk space is limited — comment out the `neo4j` service in `docker-compose.yml`
- **psycopg2 on Python 3.13 + ARM**: Use `psycopg2-binary>=2.9.9`; older versions fail to build on Python 3.13 ARM (Apple Silicon)
- **FastAPI error envelope**: Backend wraps error responses in `{"detail": {...}}` — frontend `request()` must unwrap the nested `detail` object to extract meaningful error messages (e.g., 409 duplicate repository). Forgetting this causes silent error swallowing
- **Neo4j dangling edges**: Entity IDs use qualified names (`module.ClassName.method`) but relationship targets store raw call names (`method`). The `_write_neo4j` function builds a name→qualified_name lookup map to resolve targets before creating CALLS relationships. Without this, MATCH queries fail silently and the call graph has missing edges
- **Alembic migrations**: Run `alembic upgrade head` after pulling changes that add database columns (e.g., `branch` column on repositories). The migration uses `batch_alter_table` for SQLite compatibility
- **Branch parameter**: Wired end-to-end: `Repository.branch` model column → Alembic migration → `RepositoryCreate` schema → API route sets on create → passed to RQ job → `analyze_repository()` receives it → frontend `api.ts` sends in POST body. Default branch is `main`
- **Progress tracking**: `Repository.progress` is a JSONB column storing `{step, label, detail, percent, started_at, stats{}}`. Updated by `_emit_progress()` in `analyze.py` at each of 9 pipeline steps (clone → recon → parse → modules → Neo4j → Qdrant → dossier → orchestrator → wiki pages). The orchestrator also reports per-agent progress via a callback. Frontend polls `/repositories/{id}/status` and renders real steps — not cosmetic animation. The `_generate_all_pages()` function reports per-page progress (e.g., "page 3 of 12"). Always restart the RQ worker after modifying `_emit_progress()` or the progress callback chain
- `.specify/memory/` is gitignored - contains temporary framework state
- `.claude/*.local.md` files are gitignored - local plugin configuration
- Specification follows Specify framework patterns (business focus, no implementation details)
- All 20 functional requirements map to user scenarios for testability
- External AI collaboration prompts stored in `tmp/` directory for reuse

## Architecture Considerations

**Critical Insight from Gemini Feedback (2026-02-15)**:

The spec currently focuses on AI-powered generation but may be missing the **determinism foundation** that made Google Code Wiki trustworthy:

1. **Code Graph Layer**: Need static analysis foundation (AST parsing, call graphs, import analysis) as deterministic base
2. **Trust vs Magic**: Original Code Wiki's "magic" came from **deterministic accuracy**, not AI generation
3. **Hybrid Architecture**: Consider **deterministic extraction + AI summarization** rather than pure AI generation
4. **Three-Layer Model**:
   - Layer 1: Static analysis (deterministic, trustworthy)
   - Layer 2: AI enhancement (summaries, explanations)
   - Layer 3: User feedback loop

**Implication**: May need to revise architecture to prioritize static analysis/code graph as foundation, with AI as enhancement layer rather than primary mechanism.

### Parsing Strategy Decision (2026-02-15)

**Language-Specific Parsers vs Universal Parsers (LSP/Tree-sitter)**

**Decision**: Use language-specific parsers (TypeScript Compiler API for JS/TS, Jedi for Python) wrapped in unified CodeParser abstraction

**Rationale**:
- **Accuracy requirement**: SC-006 mandates 95% precision in code relationships
- **Language-specific parsers**: Achieve 95%+ accuracy with full semantic analysis
  - TypeScript Compiler API: Type signatures, return values, import resolution, precise dependencies
  - Jedi + Python AST: Cross-file imports, type annotations, accurate call graphs
- **Universal parsers (LSP/Tree-sitter)**: Only 70-80% accuracy
  - Syntax-only information without semantic understanding
  - Cannot resolve types, track imports across files, or provide accurate call graphs

**Architecture Pattern**:
- CodeParser abstraction interface: `parse_file()`, `resolve_imports()`, `get_call_graph()`
- Isolates implementation differences behind unified API
- Future expansion: Language-specific for high-quality support, Tree-sitter fallback for experimental languages

**Trade-off**: Prioritizes accuracy over uniformity - maintains separate parsers per language rather than single universal parser

## UX Design System

**Visual Identity**: Editorial design inspired by technical publications

**Typography**:
- **Monospace**: IBM Plex Mono (technical elements, code, signatures)
- **Serif**: Crimson Pro (body text, descriptions)
- **Sans-serif**: System fonts (UI controls, navigation)

**Color Palette**:
- Sky blue (#0ea5e9) - Parameters, links
- Emerald (#10b981) - Types, success states
- Purple (#a855f7) - Return values, keywords
- Amber (#f59e0b) - Highlights, active states
- Slate (#64748b) - Secondary text, borders

**CSS Variables for Inline Content Links** (glassmorphism design system):
- Default link color: `var(--secondary)` = `#06B6D4` (cyan)
- Hover link color: `var(--primary-light)` = `#A78BFA` (light purple)
- Scope carefully — avoid interfering with nav/sidebar/button links
- Apply ONLY to content pages (home.html, module.html, etc.) — NOT to navigation hub pages like `index.html`

**Interaction Patterns**:
- Gradient accent bars (sky-to-purple) reveal on hover
- Border color transitions (slate → amber/sky)
- Shadow elevation (subtle depth changes)
- Vertical lift animations (2-4px translate)
- Staggered fade-in sequences for content loading

**Navigation Hierarchy** (3 levels):
1. **Repository Home** → Overview, module list, quick links
2. **Module Page** → Components, dependencies, configuration
3. **Function/Class Detail** → Signature, parameters, call graph, source

**Design-First Workflow**:
- UX mockups created before implementation (`specs/001-code-wiki/ux/`)
- Module page establishes pattern for all page types
- Self-contained HTML files demonstrate full interactions
- Mockups serve as frontend implementation blueprints
- `documentation-layout.html` provides reusable three-column navigation pattern (collapsible sidebar, TOC, scroll-spy)
- Multiple design variants created in separate folders (`docs-glassmorphism/`, `docs-brutalist/`) for stakeholder comparison

## Implementation Planning

**Current Phase**: Planning complete, UX designed, ready for implementation

**Phase Structure** (from `specs/001-code-wiki/plan.md`):
1. **Phase 0: Foundation** - Project scaffold, Docker Compose, database schemas
2. **Phase 1: Code Analysis** - Language-specific parsers, entity extraction, relationship mapping
3. **Phase 2: Graph Storage** - Neo4j integration, code graph population, query optimization
4. **Phase 3: Vector Search** - Qdrant integration, embedding generation via LM Studio
5. **Phase 4: LLM Integration** - Wiki generation pipeline, prompt templates, caching
6. **Phase 5: API Layer** - FastAPI endpoints, OpenAPI contracts, authentication
7. **Phase 6: Frontend** - React UI, wiki pages, search interface

**Key Artifacts Created**:
- ✅ `plan.md` - Complete implementation roadmap with 7 phases
- ✅ `data-model.md` - Entity schemas and database relationships
- ✅ `contracts/openapi.yaml` - REST API specification
- ✅ `research.md` - Technology decisions with detailed rationale
- ✅ `quickstart.md` - Development environment setup guide
- ✅ `ux/*.html` - Frontend design mockups (5 complete pages + navigation template)
- ✅ `ux/docs-glassmorphism/` - **9-page glassmorphism mock set** (6 wiki-content pages absorbed into unified reader):
  - `module.html` - **Primary wiki reader template** (3-column: sidebar + content + TOC)
  - `function.html` - Entity drill-down detail page
  - `search.html`, `chat.html` - Interactive features
  - `login.html`, `dashboard.html`, `submit.html`, `progress.html`, `error.html` - App chrome pages
  - `README.md` - Mock set documentation
  - **Deleted** (absorbed into sidebar navigation): `home.html`, `getting-started.html`, `glossary.html`, `api-reference.html`, `diagrams.html`, `index.html`

## Mobile Nav Fix Pattern (Reference Implementation)

Applied to all wiki pages with sidebars (module.html, function.html, search.html, etc.). Four-step sequence:

1. **CSS**: Add slide-in sidebar styles (off-screen `left: -320px` + transition) + overlay + sticky topbar
2. **HTML topbar**: Inject sticky topbar as first `<body>` child (hamburger button + page title)
3. **HTML close button**: Inject `✕` button as first child inside sidebar nav
4. **JavaScript**: Add `toggleNav()` (open/close + body scroll lock) and `closeNav()` (overlay tap + X button)

**Gotcha**: function.html had a divergent legacy pattern (fixed circular button + `.active` toggle) — required removing old CSS/HTML before applying standard pattern.

## UX Mock Status (2026-02-24)

**Consolidated to 9 mocks** after unified wiki reader decision. 6 wiki-content pages (home, getting-started, glossary, api-reference, diagrams, index) absorbed into sidebar navigation within the unified reader.

| Page | Role | Status |
|---|---|---|
| `module.html` | **Primary wiki reader** (3-column layout template) | ✅ All wiki content rendered here |
| `function.html` | Entity drill-down detail | ✅ |
| `search.html` | Search interface | ✅ |
| `chat.html` | AI chat assistant | ✅ |
| `login.html` | OAuth + email auth | ✅ |
| `dashboard.html` | Repository list management | ✅ |
| `submit.html` | Add repository form | ✅ |
| `progress.html` | Analysis pipeline visualization | ✅ |
| `error.html` | Error states (404, failure) | ✅ |

## Facet Intelligence System Architecture (2026-02-18)

**Design Decision**: Repository analysis is not monolithic — it decomposes into independent "facets" (CI/CD, security, dependencies, architecture patterns, etc.) analyzed by specialist agents.

### 3-Layer Architecture

| Layer | Name | Purpose |
|-------|------|---------|
| **Layer 0** | Repo Reconnaissance | File tree, language detection, config fingerprinting (no LLM) |
| **Layer 1** | Facet Intelligence | Specialist agents analyze each facet (heuristic-first + LLM where needed) |
| **Layer 2** | Module Wikis | Per-module documentation synthesis from facet data |

### Facet Catalog

**Heuristic-First Facets** (extract with rules, LLM only for summarization):
- `ArchitectureAnalyzer` — module/layer structure from directories and imports
- `DependencyAuditor` — package manifests, CVE lookup, license check
- `CICDAnalyzer` — pipeline stages from YAML config files
- `InfrastructureMapper` — IaC files (Terraform, Helm, Dockerfile)
- `TestCoverageAnalyzer` — test framework, patterns, coverage gaps
- `DataLifecycleAnalyzer` — DB schema, migrations, data access patterns
- `OwnershipExtractor` — CODEOWNERS, git blame for module ownership

**LLM-Required Facets** (no heuristic shortcut):
- `SecurityPostureAnalyzer` — auth patterns, injection risks, secret exposure
- `APIContractExtractor` — REST/GraphQL/gRPC schema inference
- `DesignPatternDetector` — GoF patterns, architectural patterns
- `DomainModelExtractor` — business entities and relationships
- `TechnicalDebtScanner` — TODO/FIXME density, smell detection
- `ObservabilityAnalyzer` — logging/metrics/tracing patterns
- `FeatureFlagMapper` — flag inventory and usage patterns
- `ErrorHandlingAnalyzer` — error propagation patterns

### Agent Classification: ReAct vs Single-Pass (2026-02-18)

**Decision**: ReAct agent pattern (Thought → Action → Observation loop) applies ONLY to iterative facet agents that must explore an unknown codebase.

**Use ReAct for**: Agents that follow auth flows, trace data paths, chase call chains — where files to read cannot be predetermined.

**Use single-pass LLM calls for**: `DependencyAuditor`, `CICDAnalyzer`, `OwnershipExtractor` — inputs are known upfront, no iterative exploration needed.

**ReAct termination safeguards** (mitigate runaway loops on large codebases):
- Hard iteration caps per agent
- Visited-set tracking (no re-reading files)
- Hierarchical planning guidance from Triage Agent
- Cost monitoring

**Progressive Dossier updates**: ReAct agents should write findings mid-loop (not just at end) — preserves partial work and enables cross-agent knowledge sharing during parallel execution.

### Cross-Facet Communication

Agents NEVER communicate directly — all communication flows through the **Dossier** (shared LangGraph state):
- Tags emitted by agents trigger downstream specialists via static orchestrator rules
- Example: `SecurityPostureAnalyzer` emits tag `risk:jwt-without-rotation` → `DependencyAuditor` surfaces related CVEs
- **No ConflictResolutionAgent**: Show conflicting findings side-by-side with source labels, let developer judge

### LangGraph Wiring

```python
# Dossier IS the LangGraph TypedDict state
# Nodes read/mutate Dossier; conditional edges handle dynamic routing
# TAG_TRIGGERS catalog maps agent-emitted tags → downstream agents to invoke
```

### Implementation Directory Structure (from plan.md)

```
backend/src/
  recon/          # Layer 0: Repo Reconnaissance (no LLM)
  agents/
    heuristic/    # Rule-based facet agents (ArchitectureAnalyzer, CICDAnalyzer, etc.)
    iterative/    # ReAct facet agents (SecurityPostureAnalyzer, DesignPatternDetector, etc.)
    single_pass/  # Simple LLM call agents (DependencyAuditor, OwnershipExtractor, etc.)
  orchestrator/   # LangGraph StateGraph workflow wiring
  dossier/        # LangGraph State / shared blackboard
  wiki/           # Layer 2: Module Wiki synthesis agents
```

### Final Wiki Navigation

Dashboard → Unified wiki reader with sidebar navigation (all wiki content in single 3-column layout)

### Unified Wiki Reader Architecture (2026-02-24)

**Decision**: Consolidated all wiki content into a single 3-column reader (sidebar nav + main content + table of contents) matching `module.html` mockup pattern. Eliminates 6 separate page routes.

**Frontend route structure**:
- `/[owner]/[name]` — Wiki home (redirects or renders overview)
- `/[owner]/[name]/[slug]` — Wiki section page (module, getting-started, glossary, etc.)
- `/[owner]/[name]/progress` — Analysis progress page (separate route)

**Sidebar sections**: All wiki page types (modules, getting-started, glossary, api-reference, diagrams) become sidebar navigation items within the unified reader, not separate routes.

### Backend Integration Fixes Applied (2026-02-24)

Five integration seam repairs (not architectural changes):

1. **RepoFingerprint metadata** (`recon/repo_recon.py`): Now extracts `project_description`, `project_version`, `primary_language`, `build_output_dirs` from package.json/pyproject.toml/Cargo.toml/go.mod
2. **Build artifact filtering** (`jobs/analyze.py`): Skips minified `.cjs`/`.min.js`/`dist/`/`build/` files during entity extraction using `build_output_dirs` from fingerprint
3. **Semantic module detection** (`jobs/analyze.py`): Replaced directory-depth heuristic with functional grouping from package.json workspaces, src/ subdirectories, and manifest-defined entry points
4. **Entity path normalization** (`jobs/analyze.py`): Converts absolute clone paths to repo-relative paths before persistence
5. **Home page project identity** (`wiki/page_builders/home_page.py`): Populates `project_description` from RepoFingerprint instead of hardcoded fallback

## Wiki Generation Pipeline Architecture (2026-02-18)

**Design Decision**: Replace monolithic LLM call per module with a 3-agent multi-pass pipeline.

### The 3-Agent Pipeline

| Agent | Role | Method | Output |
|-------|------|--------|--------|
| **Agent 1** | Structural Analyst | Pure AST (no LLM) | Entity list with interestingness scores |
| **Agent 2** | Implementation Explainer | 15 parallel LLM calls | Focused entity-level explanations |
| **Agent 3** | Module Weaver | Single LLM synthesis call | Coherent module narrative |

**Agent 1 — Interestingness Scoring** (rule-based, no LLM):
- High call-in-degree (many callers)
- Cyclomatic complexity > threshold
- Cross-module dependencies
- Public API surface area
- Unusual patterns (decorators, generators, context managers)

**Agent 2 — Parallel Focused LLM Calls**:
- Top-N scored entities (dynamic, not fixed cap)
- Each call: function signature + docstring + body + caller/callee **with class body context**
- Answers "why does this exist?" not just "what does it do?"

**Agent 3 — Synthesis**:
- Receives: Agent 1 structural report + Agent 2 entity explanations
- Produces: Module narrative (purpose, design patterns, data flow, gotchas)
- Risk: May miss emergent architectural patterns not captured by per-entity analysis

### Gemini's Critical Feedback on This Design (2026-02-18)

1. **Fixed top-15 cap is arbitrary** → Use dynamic threshold (interestingness score > X, or top-N% of module)
2. **Agent 2 needs class body context** → Methods need surrounding class definition, not just caller/callee signatures
3. **Agent 3 risks missing emergent patterns** → Consider an explicit "architectural patterns" prompt pass
4. **LLM hallucination in gotchas** → Critical failure mode: fabricated `evidence_lines` — require evidence validation
5. **Partial regeneration strategy confirmed correct** → Re-run Agent 2 only for changed entities, then full Agent 3 re-synthesis

### Productionization Improvements (Gemini's suggestions)
- LSP integration for richer semantic context than pure AST
- CodeBERT-family models for entity importance scoring
- Human feedback loops via Langfuse traces

### Dynamic Extension: Blackboard-Based Triage Pattern (2026-02-18)

For handling novel/complex modules beyond the fixed 3-agent pipeline, Gemini proposed a **Blackboard-based Triage Architecture**:

- **Triage Agent**: Single upfront classification decides which specialist agents to invoke (avoids chatty back-and-forth)
- **Shared Dossier**: Agents communicate only through a shared context object, never directly — prevents coupling
- **Static orchestrator rules**: Tags emitted by agents trigger additional specialists (e.g., tag `has_async_patterns` → invoke AsyncSpecialist)
- **RFI Protocol**: Agents flag unknowns without spawning uncontrolled sub-agents
- **Key constraint**: Designed for ~10-20s local inference latency (qwen3-coder-30b at 262k context) — chatty frameworks (AutoGen, CrewAI) are too expensive at this latency

**When to use**: Apply this pattern for edge case modules (mega-modules, cross-cutting utilities) where the fixed 3-agent pipeline needs dynamic specialist augmentation.

## Next Steps

According to specification workflow:
1. ✅ Requirements gathered and documented
2. ✅ Specification created and validated
3. ✅ Technology decisions finalized
4. ✅ Planning phase complete
5. ✅ UX design system established
6. ✅ UX mock spec review completed (gaps resolved)
7. ✅ **Full glassmorphism mock set complete** (15 pages, all spec requirements covered)
8. ✅ **3-agent wiki generation pipeline designed** (Gemini-reviewed)
9. ✅ **Implementation task list generated** (`specs/001-code-wiki/tasks.md` — 112 tasks across 7 phases, MVP = Phases 1–3, mock references, API contracts)
10. ✅ **tasks.md exit criteria format decided and applied** — Option A: inline criteria on every task. UX tasks require explicit visual mock comparison (side-by-side against reference HTML, component-level checks, viewport anchors). Applied to T077–T082 as reference pattern; 14 UX tasks total have mock file references in tasks.md front matter.
11. ✅ **Phase 0: Foundation complete** — Docker Compose, PostgreSQL/Neo4j/Qdrant services, backend scaffold (`backend/src/` with agents/, api/, parsers/, recon/, wiki/, orchestrator/, dossier/ directories), requirements.txt
12. ✅ **Phase 0–1: Frontend scaffold complete** — Next.js + TypeScript, API client (`frontend/src/services/api.ts` with unified namespace), 8 UI components (Breadcrumbs, CodeBlock, GlassCard, GradientBackground, InfoBox, Logo, StatusIndicator, TypeBadge), font optimization (Next.js font API)
13. ✅ **Core pages implemented** — Landing hub (`/`), Dashboard (`/dashboard`), Submit (`/submit` with real-time URL validation + provider detection), Progress (`/[owner]/[name]/progress` with 5s polling + animated 6-step pipeline), Wiki Home (`/[owner]/[name]`), Module docs (`/[owner]/[name]/modules/[slug]` with 3-column layout)
14. ✅ **Backend wiki pipeline scaffold** — Context builder with RAG integration, module/dashboard page builders, special page builders (getting started, function index, glossary, API reference)
15. ✅ **All 109 tasks complete** — Frontend (login, chat, search, diagrams, glossary, API reference, error, getting-started pages), Backend (webhook handler, Phase 7 Polish tasks T102–T109)
16. ✅ **Spec artifacts updated** — `openapi.yaml`: added `/status`, `/webhook`, `/diagrams` endpoints + 5 new schemas; `data-model.md`: added Dossier entity (DossierEntry, RepoFingerprint), fixed Qdrant section; `plan.md`: full rewrite to 685 lines with all architecture decisions; Artifact Gap Tracker: 6 of 7 gaps resolved
17. ✅ **Integration fixes applied** — RepoFingerprint metadata extraction, build artifact filtering, semantic module detection, entity path normalization, home page project identity
18. ✅ **Unified wiki reader** — Consolidated 6+ wiki page routes into single 3-column reader with sidebar navigation; deleted 6 redundant glassmorphism mocks
19. ✅ **Pipeline logging + gap fixes** — Comprehensive structured logging across 8 backend modules; fixed 6 pipeline gaps (duplicate recon, Neo4j dangling edges, error_message persistence, API schema updates, frontend error state, branch field wired end-to-end with Alembic migration)
20. ✅ **Granular progress tracking** — `Repository.progress` JSONB column + Alembic migration, `_emit_progress()` helper in analyze.py reporting 9 pipeline steps with stats, orchestrator progress callback for per-agent reporting, API schema + route updates exposing `progress`, frontend progress page rewritten with 9 real steps + live telemetry (replacing cosmetic animation)
21. ⏳ **Next: Backend implementation** — Code parsers (Jedi/Python AST, TypeScript Compiler API), Facet Intelligence agents, Neo4j/Qdrant integration, FastAPI endpoints

---

## UX Task Exit Criteria Pattern

Established for all frontend page tasks. Each UX task must include:

1. **Side-by-side mock comparison** against reference glassmorphism HTML file
2. **Component-level visual checks** (specific colors, shadows, blur, borders — not "looks similar")
3. **Viewport anchor** where grid/layout is validated (typically 1280px)
4. **Interactive state verification** (hover, focus, active)
5. **Console error check** (no JS errors at runtime)
6. **Glassmorphism property verification** (backdrop-filter, rgba background, border opacity)

Applied to: T077 (design system), T078 (shared layout), T079 (home page), T080 (submit page), T081 (progress page), T082 (wiki dashboard).

*Last updated: 2026-02-28 (Granular progress tracking: JSONB column, 9-step pipeline telemetry, live frontend)*
*Managed by claude-md-manager skill. Quality target: 80+/100*
