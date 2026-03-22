# Worker Analysis Pipeline Deep Dive

This document explains exactly what happens after a repository URL is submitted for analysis, with a focus on the background worker path and where wiki quality can degrade.

---

## 1) What happens when a repository is submitted

### API request path (`POST /repositories`)

1. The API validates URL format against supported hosts (GitHub/GitLab/Bitbucket).
2. It checks if the URL already exists in `repositories`:
   - If yes, it returns the existing row (no duplicate job enqueue).
   - If no, it inserts a new `Repository` row with `status=pending`.
3. It enqueues an RQ job on queue `analysis`:
   - function: `src.jobs.analyze.analyze_repository`
   - args: `repo.id`, `repo.branch or "main"`
   - job id: `analyze-{repo.id}`
   - timeout: `-1` (no timeout at queue level)
4. API returns `202 Accepted` with repository metadata.

Source:
- `backend/src/api/routes/repositories.py`
- `backend/src/api/deps.py`

---

## 2) Worker execution model

An RQ worker process must be running on queue `analysis`. The worker imports and executes `analyze_repository(repository_id, branch)` from `backend/src/jobs/analyze.py`.

Inside `analyze_repository`:

1. Loads settings from env (`DATABASE_URL`, Redis URL, feature flags, etc.).
2. Opens a SQLAlchemy session.
3. Loads repository row by `repository_id`.
4. Sets repository status to `analyzing`.
5. Initializes progress payload with:
   - `current_step`, `step_label`, `step_detail`
   - shared `stats` dict
   - `started_at`, `elapsed_seconds`
6. Commits progress to DB immediately.

Progress update behavior:
- `_emit_progress(...)` always writes to DB (`repositories.progress`) and then *attempts* Redis publish for SSE.
- Redis publish failures are intentionally non-fatal.

Source:
- `backend/src/jobs/analyze.py` (`analyze_repository`, `_emit_progress`)
- `backend/src/api/progress_events.py`

---

## 3) Step-by-step breakdown of the 9 worker steps

## Step 1 — Clone/Pull repository cache

What runs:
- `clone(repo_url, branch)` in `src/storage/repo_cache.py`

Behavior:
1. URL is validated (HTTP(S) shape).
2. Cache path is derived from URL under `REPO_CACHE_DIR`.
3. If cache path exists: `pull(...)` is called.
4. If not: fresh clone is performed.
5. If `branch` is supplied, checkout is attempted.
6. Commit hash is read via `get_commit_hash(repo_url)` for traceability.

Failure modes:
- Git clone/pull exceptions raise `RuntimeError` and fail the job.
- Branch checkout warning may occur without failing clone itself.

Quality impact:
- Stale/incorrect branch checkout can produce wiki content for wrong code revision.

---

## Step 2 — Repo recon (fast structural fingerprint)

What runs:
- `repo_recon.run(local_path)`

Behavior:
1. Scans file tree while skipping known noise/build directories.
2. Detects languages and approximate LOC.
3. Detects config/tooling signals (CI, Docker, package managers, infra files).
4. Infers:
   - `system_type`
   - `source_roots`
   - `build_output_dirs`
   - project metadata (when manifest files are available)
5. Stores top-level stats in progress payload (`files_scanned`, `loc`, `languages`).

Why it matters:
- `source_roots` and `build_output_dirs` are reused by downstream parsing/module grouping.
- Bad recon signal quality can cascade into weak module boundaries and weaker page quality.

Source:
- `backend/src/recon/repo_recon.py`

---

## Step 3 — Parse code entities

What runs:
- `extract_entities(local_path, build_output_dirs=...)`

Behavior:
1. Language parsers walk source files and extract entities (`ParsedEntity`).
2. Parse excludes build output dirs discovered in recon.
3. Worker records `entities_found` in progress stats.

Entity data used later:
- names, qualified names, file paths
- signatures/docstrings
- call relations and metadata

Quality impact:
- Missing entities here directly means missing references/content in generated wiki pages.
- Overly broad parsing (if build outputs leak in) can dilute relevance and increase noise.

Source:
- `backend/src/jobs/analyze.py` (step 3 call)
- `backend/src/parsers/extractor.py`

---

## Step 4 — Persist/index entities (PostgreSQL + Qdrant)

What runs:
1. `_get_or_create_wiki(session, repository_id)` ensures a wiki row exists.
2. `index_entities(entities, str(repo.id))` indexes entities for RAG/vector retrieval.

Behavior:
- Worker reports progress as two phases in same step:
  - "Saving to database..."
  - "indexing vectors..."

Important nuance:
- Vector indexing errors can affect AI retrieval quality later even if parsing succeeded.

Source:
- `backend/src/jobs/analyze.py` step 4
- `src.dossier.rag_index.index_entities`

---

## Step 5 — Run facet analysis orchestrator

What runs:
- `run_analysis(repo_path, repository_id, fingerprint, progress_callback)`
- Implementation in `backend/src/orchestrator/graph.py`

Behavior (in order):
1. Layer 0:
   - Uses precomputed fingerprint from step 2 (avoids duplicate recon), or computes one if absent.
2. Triage:
   - Plans which heuristic/react/single-pass agents should run.
3. Layer 1a heuristic agents:
   - Executes selected heuristic agents.
4. Layer 1b ReAct agents:
   - Runs selected iterative agents.
   - Then evaluates emitted tags and can trigger additional ReAct agents.
5. Layer 1c single-pass agents:
   - Executes selected single-pass agents.
6. Conflict synthesis:
   - Combines/normalizes conflicting findings.
7. Index dossier findings for RAG.

Progress semantics:
- The callback reports `(completed, total, agent_name)` after each agent completion/failure.
- Worker stores these counters under step 5 stats.

Known implementation detail:
- Parallel helper currently uses `ThreadPoolExecutor(max_workers=1)`, so effective execution is single-worker even in “parallel” paths.

Quality impact:
- Weak agent outputs or failed agents reduce dossier richness and hurt planner/writer grounding.
- Triggered ReAct follow-ups are key for deeper security/auth/data-flow coverage.

Source:
- `backend/src/orchestrator/graph.py`
- `backend/src/jobs/analyze.py` step 5

---

## Step 6 — Build relationship graph (Neo4j)

What runs:
- `_write_neo4j(entities)`

Behavior:
1. Creates code entity nodes.
2. Builds `CALLS` edges with fuzzy resolution:
   - exact qualified name match first
   - fallback short-name lookup
3. Collects counts:
   - `neo4j_nodes`, `neo4j_edges`, `neo4j_unresolved`

Failure behavior:
- Per-node/edge write failures are logged as warnings (best-effort).
- Job continues unless broader failure bubbles up.

Quality impact:
- High unresolved edge counts usually indicate poor call graph connectivity and can reduce architecture clarity in docs.

Source:
- `backend/src/jobs/analyze.py` (`_write_neo4j`)

---

## Step 7 — Detect modules

What runs:
- `_detect_modules(local_path, entities, fingerprint)`

Behavior:
1. Groups entities using adaptive depth:
   - inside source roots: deeper grouping
   - outside source roots: shallower grouping
2. Skips known build/output dirs.
3. Post-processes:
   - splits mega-modules
   - merges tiny modules
   - humanizes module names
4. Stores `modules_detected` metric.

Quality impact:
- Module grouping is a major quality lever for readability.
- Poor grouping causes pages that are either too broad (shallow) or fragmented (over-split).

Source:
- `backend/src/jobs/analyze.py` (`_detect_modules`)

---

## Step 8 — Generate wiki pages (V2 or V1)

Branching:
- If `WIKI_V2_ENABLED=true`, worker runs V2 pipeline (`generate_wiki_v2`).
- Else it runs legacy V1 page generation.

### V2 path (`generate_wiki_v2`)

Phases:
1. **Prep**
   - Build entity index, call/reverse-call graphs, import graph.
   - Discover domain entities (agents/tools/guardrails hints).
2. **Phase 0: Compress**
   - `CodebaseCompressor` summarizes codebase context for token-efficient prompting.
3. **Agent graph orchestration**
   - `architect -> planner -> writer -> critic -> (annotator + diagrammer + tabulator) -> assembler`
   - `critic` may route back to writer up to `MAX_RETRIES=2`.
   - Heartbeat progress events are emitted while graph executes.
4. **Render**
   - Render final markdown pages from plan + enriched sections.
   - Inject runtime holistic sections and sanitize output.
   - Evaluate quality and collect generation warnings/metrics.
5. **Persist**
   - Replace existing wiki pages/modules with new ones.
   - Persist section/module mapping and metadata.
   - Export markdown artifacts.

Worker-facing outputs:
- `pages_created`
- optional `generation_warnings`
- optional `quality_metrics`

Progress semantics in step 8:
- page progress callback updates message such as:
  - `AI Analysis: ...` (initial)
  - `Page X/Y: ...` as pages/units advance

Quality impact hotspots:
- planner required entities vs writer coverage (critic loop)
- missing source links / unresolved paths
- section rendering and sanitization quality gates

Sources:
- `backend/src/wiki/v2_pipeline.py`
- `backend/src/wiki/agents/graph.py`
- `backend/src/wiki/agents/critic_agent.py`

### V1 fallback path

When V2 is disabled:
1. Persist modules/entities.
2. Generate module pages + special pages (home/getting-started/function-index/glossary/api-reference).
3. Continue with finalization.

Source:
- `backend/src/jobs/analyze.py` (`_generate_all_pages_v1`)

---

## Step 9 — Finalize status and publish terminal event

Behavior:
1. Marks repository status `ready`.
2. Stores:
   - `last_analyzed_commit`
   - `last_analyzed_at`
   - language and size metadata
3. If generation warnings exist:
   - computes degraded flags (critical warning reasons)
   - stores warning payload in `repositories.progress`
4. Commits DB transaction.
5. Publishes terminal SSE event:
   - `{"type":"done","status":"ready", ...optional warning flags}`
6. Returns summary dict to worker runtime.

Source:
- `backend/src/jobs/analyze.py` (finalization block)

---

## 4) Error path and partial-state behavior

If any step raises:

1. Worker sets repository status to `error`.
2. Stores `error_message`.
3. Preserves current progress step and updates `step_detail` with truncated error.
4. Publishes terminal event:
   - `{"type":"done","status":"error","error":"..."}`
5. Re-raises exception for worker logs.

Implication:
- You can inspect `repositories.progress` to see the last successful step and estimate blast radius.

Source:
- `backend/src/jobs/analyze.py` exception handler

---

## 5) How progress reaches the frontend

Dual channel:
1. Durable progress state in PostgreSQL (`repositories.progress`).
2. Real-time events via Redis pub/sub channel `progress:{repo_id}`.

SSE endpoint (`/repositories/{id}/progress/stream`) behavior:
1. Sends DB progress snapshot first (catch-up).
2. If already terminal (`ready` or `error`), sends done event and closes.
3. Otherwise subscribes to Redis stream.
4. Emits keepalive comments when idle (to keep proxies/connections alive).
5. Closes stream on `type=done`.

Source:
- `backend/src/api/routes/repositories.py`
- `backend/src/api/progress_events.py`

---

## 6) Practical debugging checklist for “wiki is missing details / not polished”

When quality is poor, inspect in this order:

1. **Step reached / status**
   - Check `/repositories/{id}/status`.
   - Confirm whether run ended `ready` vs `error`.

2. **Progress stats snapshot**
   - `entities_found`, `modules_detected`, agent completion counts, warnings.
   - Very low entities/modules often indicate parser/recon issues.

3. **Warnings + quality metrics (step 8/9)**
   - Look for `generation_warnings` and critical reasons such as unresolved references or placeholder leakage.

4. **Critic coverage behavior**
   - Verify whether writer retries occurred and if coverage remained low.
   - Persistent missing required entities usually maps to thin prose.

5. **Graph/index health**
   - Neo4j unresolved edge counts (`neo4j_unresolved`).
   - Qdrant indexing failures in worker logs.

6. **Module grouping quality**
   - Overly large/overly fragmented modules can make pages either vague or noisy.

7. **Source links fidelity**
   - Validate entity path normalization and rendered source links against repository files.

---

## 7) Important operational notes

- RQ worker should be started with `rq worker --worker-class rq.SimpleWorker analysis` in this project setup.
- Redis publish failures do not fail the analysis job, but UI may look “stuck” without SSE updates.
- Queue timeout is disabled (`job_timeout=-1`), so practical timeout enforcement for wiki graph happens inside V2 (`WIKI_AGENT_INVOKE_TIMEOUT_SECONDS`).

---

## 8) Key source files map

- API enqueue + status + SSE:
  - `backend/src/api/routes/repositories.py`
  - `backend/src/api/deps.py`
  - `backend/src/api/progress_events.py`
- Worker orchestration:
  - `backend/src/jobs/analyze.py`
- Repo cache + git operations:
  - `backend/src/storage/repo_cache.py`
- Recon:
  - `backend/src/recon/repo_recon.py`
- Facet analysis orchestrator:
  - `backend/src/orchestrator/graph.py`
- Wiki V2:
  - `backend/src/wiki/v2_pipeline.py`
  - `backend/src/wiki/agents/graph.py`
  - `backend/src/wiki/agents/critic_agent.py`
