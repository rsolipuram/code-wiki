# Backend — code-wiki

Python 3.11 + FastAPI backend with LangGraph agent pipeline.

## Commands

```bash
# Start backend (venv must be active)
DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  uvicorn src.api.main:app --reload --port 8000

# Run migrations
DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" alembic upgrade head

# Start RQ worker (macOS — MUST use SimpleWorker)
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  REDIS_URL="redis://localhost:6380" \
  rq worker --worker-class rq.SimpleWorker analysis --url redis://localhost:6380

# Verify LM Studio
curl http://localhost:1234/v1/models

# PostgreSQL CLI (no local psql installed)
docker exec -i code-wiki-postgres-1 psql -U codewiki -d codewiki

# Health check
curl http://localhost:8000/health
```

## Service Ports

| Service | Port | Notes |
|---------|------|-------|
| Backend API | 8000 | Swagger at /docs |
| PostgreSQL | 5434 | Remapped from 5432 |
| Neo4j | 7474 (browser), 7687 (bolt) | Optional — backend degrades gracefully |
| Qdrant | 6333 (REST), 6334 (gRPC) | Docker volume `qdrant_data` |
| Redis | 6380 | Remapped from 6379 |
| LM Studio | 1234 | OpenAI-compatible API, must be running |

## Gotchas

- **LM Studio required**: Always verify before pipeline runs. V2 pipeline errors silently if down
- **macOS fork safety**: RQ's forking worker causes SIGABRT with Neo4j/Qdrant/embeddings. `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` alone is insufficient — must use `--worker-class rq.SimpleWorker`
- **RQ worker caches code**: Restart worker after any backend code change
- **RQ queue name**: Jobs use `analysis` queue — always start worker with `rq worker analysis`
- **FastAPI error envelope**: Errors wrapped in `{"detail": {...}}` — frontend must unwrap nested `detail`
- **Neo4j dangling edges**: Entity IDs use qualified names but relationship targets store raw names. `_write_neo4j` builds a lookup map to resolve. Without this, MATCH queries fail silently
- **Alembic migrations**: Run `alembic upgrade head` after pulling changes with new DB columns. Uses `batch_alter_table` for SQLite compatibility
- **Dossier Qdrant bug (known)**: `index_dossier()` creates correct vectors but payload fields (`repo_id`, `facet`, `agent`) are `None`. Filtered queries return 0 results. Root cause: DossierEntry→payload mapping needs investigation
- **Qdrant batch size**: `index_entities()` batches at 50. Reduce if payload overflow on large repos
- **Branch parameter**: Wired end-to-end: model → migration → schema → API → RQ job → `analyze_repository()` → frontend. Default: `main`

## Progress Tracking

- `Repository.progress` — JSONB column: `{step, label, detail, percent, started_at, stats{}}`
- Updated by `_emit_progress()` in `analyze.py` at 9 pipeline steps
- Orchestrator reports per-agent progress via callback
- Frontend polls `/repositories/{id}/status`
- Always restart RQ worker after modifying `_emit_progress()`

## SSE Progress for Wiki Agents

- Redis pub/sub channel: `wiki:progress:{repo_id}`
- Each agent calls `report_agent_progress(state, agent_name, status)`
- Frontend: `EventSource` → `/repositories/{id}/wiki-progress`
- Terminal events (`complete`/`error`) close the stream
- `progress_events.py` manages Redis publish + SSE endpoint
- `repo_id` must be in WikiState for progress reporting to work
