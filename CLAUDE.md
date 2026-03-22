# code-wiki

AI-powered code documentation platform that generates wiki-style docs for repositories. Inspired by Google Code Wiki.

**Status**: Active — V2 wiki pipeline (7-agent LangGraph architecture with SSE progress)
**Feature Branch**: `001-code-wiki` | **Main Branch**: `main`

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11 + FastAPI |
| Frontend | Next.js + TypeScript |
| LLM | LM Studio (local, qwen3-coder-30b) |
| Graph DB | Neo4j Community |
| Vector DB | Qdrant (self-hosted) |
| RDBMS | PostgreSQL 15+ |
| Queue | Redis + RQ |

LM Studio runs on `localhost:1234` (OpenAI-compatible API). Model configured via `LLM_MODEL` in `backend/.env`.

## Project Structure

```
backend/src/
  agents/           # Facet intelligence (heuristic/, iterative/, single_pass/)
  api/              # FastAPI endpoints and routes
  dossier/          # LangGraph shared state blackboard
  llm/              # LM Studio client
  models/           # PostgreSQL models
  orchestrator/     # LangGraph StateGraph wiring
  parsers/          # Language-specific code parsers
  recon/            # Layer 0: Repo reconnaissance (no LLM)
  wiki/             # Wiki generation pipeline
    agents/         # 7-agent LangGraph pipeline (architect→planner→writer→annotator/diagrammer/tabulator→assembler)
    v2_pipeline.py  # V2 orchestrator
frontend/src/
  app/              # Next.js App Router pages
  components/       # UI + wiki rendering components
  services/api.ts   # Typed API client
specs/001-code-wiki/ # Spec, plan, research, data-model, quickstart, tasks, UX mocks
```

## Running the App

```bash
# 1. Docker services (requires Docker Desktop / Rancher Desktop)
docker-compose up -d && docker-compose ps

# 2. Verify LM Studio is running
curl http://localhost:1234/v1/models

# 3. Backend (from backend/, venv active)
DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  REDIS_URL="redis://localhost:6380" \
  uvicorn src.api.main:app --reload --port 8000

# 4. Frontend (from frontend/)
npm run dev

# 5. RQ worker (from backend/, venv active)
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  REDIS_URL="redis://localhost:6380" \
  rq worker --worker-class rq.SimpleWorker analysis --url redis://localhost:6380

# Verify
curl http://localhost:8000/health   # Backend health
open http://localhost:3000          # Frontend
```

## Critical Gotchas

- **LM Studio must be running** before backend/pipeline — verify with `curl http://localhost:1234/v1/models`
- **RQ must use SimpleWorker** on macOS — forking worker causes SIGABRT with Neo4j/Qdrant/embeddings
- **Restart RQ worker** after any backend code change — it caches imported modules
- **Port remapping**: PostgreSQL=5434, Redis=6380 (avoid local conflicts)
- **No local psql**: Use `docker exec -i code-wiki-postgres psql -U codewiki -d codewiki`
- **Data store reset**:
  - **Repo-scoped reset (recommended for reruns)**:
    1. Find repository id:
       `docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -At -c "SELECT id,url,status FROM repositories ORDER BY updated_at DESC;"`
    2. Delete repo analysis data and reset repository row to `pending`:
       `docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -v ON_ERROR_STOP=1 -c "BEGIN; DELETE FROM update_events WHERE repository_id='<repo_id>'; DELETE FROM chat_conversations WHERE repository_id='<repo_id>'; DELETE FROM code_entities WHERE module_id IN (SELECT m.id FROM modules m JOIN wikis w ON m.wiki_id=w.id WHERE w.repository_id='<repo_id>'); DELETE FROM modules WHERE wiki_id IN (SELECT id FROM wikis WHERE repository_id='<repo_id>'); DELETE FROM wiki_pages WHERE wiki_id IN (SELECT id FROM wikis WHERE repository_id='<repo_id>'); DELETE FROM wikis WHERE repository_id='<repo_id>'; UPDATE repositories SET status='pending', error_message=NULL, progress='{}'::jsonb, last_analyzed_commit=NULL, last_analyzed_at=NULL, updated_at=NOW() WHERE id='<repo_id>'; COMMIT;"`
    3. Optional: remove the repository row entirely (empty dashboard):
       `docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -c "DELETE FROM repositories WHERE id='<repo_id>';"`
    4. Clear cache clone for that repo:
       `rm -rf backend/cache/repos/https___github_com_<owner>_<repo>`
  - **Global reset**:
    - Redis: `docker exec code-wiki-redis redis-cli -p 6379 FLUSHALL`
    - Neo4j via container (works even without local python deps):
      `docker exec code-wiki-neo4j cypher-shell -u neo4j -p codewiki "MATCH (n) DETACH DELETE n;"`
    - Repo cache: `rm -rf backend/cache/repos/*`
- **Neo4j optional**: Backend degrades gracefully without it (graph queries disabled)
- **MermaidDiagram SVG cleaning**: The component replaces hardcoded pixel dimensions with `width="100%"` for inline layout. Pass the *original* (uncleaned) SVG to `DiagramExplorer` — the modal uses `position: absolute` with no intrinsic layout, so `width="100%"` resolves to nothing and the diagram becomes invisible.
- **Mermaid dark theme**: LLM-generated diagrams inject inline `fill`/`stroke` with `!important` that override CSS theme variables. Strip these post-render. Also set all 12 `cScale0`–`cScale11` variables explicitly — otherwise mermaid's auto palette assigns light colors to subgraphs/clusters, breaking the dark theme.
- **SVG foreignObject**: Rejects `height="auto"` — causes browser console errors. Use explicit pixel values or omit the attribute.

## Key Specs & Docs

- Setup guide: `specs/001-code-wiki/quickstart.md`
- Full spec: `specs/001-code-wiki/spec.md`
- Tech decisions: `specs/001-code-wiki/research.md`
- API contract: `specs/001-code-wiki/contracts/openapi.yaml`
- UX mocks: `specs/001-code-wiki/ux/docs-glassmorphism/`

## Architecture

See `.claude/rules/architecture.md` for facet intelligence, agent pipeline, and wiki generation details.
See `.claude/rules/wiki-content.md` for wiki page types, quality benchmarks, and content strategy.

## Code analysis pipeline setup (end-to-end)

The pipeline is asynchronous and runs as an RQ background job:

1. `POST /repositories` enqueues `analyze_repository(...)` (see `backend/src/api/routes/repositories.py`).
2. An RQ worker (`rq worker --worker-class rq.SimpleWorker analysis`) executes `backend/src/jobs/analyze.py::analyze_repository`.
3. `analyze_repository` runs the 9-step flow:
   - clone repo
   - run repo recon (`src/recon/repo_recon.py`)
   - parse entities (`src/parsers/extractor.py`)
   - persist/index entities (PostgreSQL + Qdrant)
   - run facet analysis (`src/orchestrator/graph.py::run_analysis`)
   - build relationship graph (Neo4j)
   - detect modules
   - generate wiki pages (`src/wiki/v2_pipeline.py` when V2 enabled)
   - finalize status/progress
4. Progress is dual-written to:
   - PostgreSQL (`repositories.progress` JSON)
   - Redis pub/sub for SSE (`src/api/progress_events.py`)

Facet analysis orchestration (`backend/src/orchestrator/graph.py`) is layered:

- Layer 0: Repo fingerprinting (or re-use precomputed fingerprint)
- Layer 1a: Heuristic agents
- Layer 1b: ReAct agents (+ tag-triggered follow-up agents)
- Layer 1c: Single-pass agents
- Conflict synthesis + dossier indexing for RAG

Wiki generation (V2) uses a LangGraph state pipeline in `backend/src/wiki/agents/graph.py`:

`architect -> planner -> writer -> critic -> (annotator + diagrammer + tabulator) -> assembler`

The critic can route back to writer for bounded retries before enrichment/assembly.
