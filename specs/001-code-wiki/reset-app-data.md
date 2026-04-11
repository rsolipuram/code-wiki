# Reset App Data

This guide explains how to clear analysis data safely and predictably.

## When to use this

- Dashboard shows stale repositories
- You want a clean rerun for one repository
- You want a full local reset before testing

## 1) Repo-scoped reset (recommended)

Use this when you want to rerun one repository without wiping everything.

```bash
# 1. Find repository id
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -At -c \
  "SELECT id || '|' || url || '|' || status FROM repositories ORDER BY updated_at DESC;"

# 2. Clear generated data and reset repository state to pending
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -v ON_ERROR_STOP=1 -c "
BEGIN;
DELETE FROM update_events WHERE repository_id='<repo_id>';
DELETE FROM chat_conversations WHERE repository_id='<repo_id>';
DELETE FROM code_entities WHERE module_id IN (
  SELECT m.id FROM modules m JOIN wikis w ON m.wiki_id=w.id WHERE w.repository_id='<repo_id>'
);
DELETE FROM modules WHERE wiki_id IN (SELECT id FROM wikis WHERE repository_id='<repo_id>');
DELETE FROM wiki_pages WHERE wiki_id IN (SELECT id FROM wikis WHERE repository_id='<repo_id>');
DELETE FROM wikis WHERE repository_id='<repo_id>';
UPDATE repositories
SET status='pending', error_message=NULL, progress='{}'::jsonb,
    last_analyzed_commit=NULL, last_analyzed_at=NULL, updated_at=NOW()
WHERE id='<repo_id>';
COMMIT;"

# 3. Optional: remove repository row completely (empty dashboard)
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -c \
  "DELETE FROM repositories WHERE id='<repo_id>';"

# 4. Remove local clone cache for that repository
rm -rf backend/cache/repos/https___github_com_<owner>_<repo>
```

## 2) Full reset (all repositories + caches)

Use this when you want a completely clean local state.

```bash
# 0. Stop worker first (important: prevent writes during reset)
ps -ax | grep -E "rq worker --worker-class rq.SimpleWorker analysis" | grep -v grep
kill <worker_pid>

# 1. Truncate all PostgreSQL public tables except alembic version
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  stmt text;
BEGIN
  SELECT 'TRUNCATE TABLE ' || string_agg(format('%I.%I', schemaname, tablename), ', ') || ' RESTART IDENTITY CASCADE'
    INTO stmt
  FROM pg_tables
  WHERE schemaname='public' AND tablename <> 'alembic_version';

  IF stmt IS NOT NULL THEN
    EXECUTE stmt;
  END IF;
END $$;
SQL

# 2. Flush Redis (queues + pubsub data)
docker exec code-wiki-redis redis-cli -p 6379 FLUSHALL

# 3. Clear Ladybug graph data (optional but recommended)
cd backend && python3 -c "from pathlib import Path; from src.config import get_settings; p = Path(get_settings().resolved_graph_db_path); p.unlink(missing_ok=True); print(f'Cleared {p}')"
cd ..

# 4. Remove cached repository clones
rm -rf backend/cache/repos/*

# 5. Restart worker
cd backend
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
  DATABASE_URL="postgresql://codewiki:codewiki@localhost:5434/codewiki" \
  REDIS_URL="redis://localhost:6380" \
  rq worker --worker-class rq.SimpleWorker analysis --url redis://localhost:6380
```

## 3) Verify reset

```bash
# API should return empty repositories
curl -sS http://localhost:8000/v1/repositories

# DB should be empty
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -At -c \
  "SELECT COUNT(*) FROM repositories;"

# Redis should have no keys
docker exec code-wiki-redis redis-cli -p 6379 DBSIZE
```

Expected:
- `repositories.total = 0`
- SQL count is `0`
- Redis DB size is `0`
