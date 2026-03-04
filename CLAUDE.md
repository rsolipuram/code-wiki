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
- **No local psql**: Use `docker exec -i code-wiki-postgres-1 psql -U codewiki -d codewiki`
- **Data store reset**: Clear PostgreSQL, Neo4j (`backend/scripts/reset_neo4j.py`), Redis (`docker exec code-wiki-redis-1 redis-cli -p 6379 FLUSHALL`), repo cache (`backend/cache/repos/`)
- **Neo4j optional**: Backend degrades gracefully without it (graph queries disabled)

## Key Specs & Docs

- Setup guide: `specs/001-code-wiki/quickstart.md`
- Full spec: `specs/001-code-wiki/spec.md`
- Tech decisions: `specs/001-code-wiki/research.md`
- API contract: `specs/001-code-wiki/contracts/openapi.yaml`
- UX mocks: `specs/001-code-wiki/ux/docs-glassmorphism/`

## Architecture

See `.claude/rules/architecture.md` for facet intelligence, agent pipeline, and wiki generation details.
See `.claude/rules/wiki-content.md` for wiki page types, quality benchmarks, and content strategy.
