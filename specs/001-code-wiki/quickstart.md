# Quickstart Guide: Code Wiki Platform

**Date**: 2026-02-15
**Audience**: Developers setting up the Code Wiki platform
**Prerequisites**: Basic knowledge of Python, React, and Docker

---

## Prerequisites

### Required Software

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend services |
| Node.js | 18+ | Frontend build |
| Docker | 24+ | Database services |
| Git | 2.40+ | Version control |
| npm/yarn | Latest | Package management |

### Development Tools (Recommended)

- **IDE**: VS Code with Python + TypeScript extensions
- **API Testing**: Postman or Bruno
- **Database Client**: DBeaver or pgAdmin

---

## Quick Start (5 minutes)

### 1. Clone Repository

```bash
git clone https://github.com/your-org/code-wiki.git
cd code-wiki
```

### 2. Start Services with Docker Compose

```bash
# Start PostgreSQL + Neo4j + Qdrant
docker-compose up -d

# Verify services are running
docker-compose ps
```

Expected output:
```
NAME                SERVICE    STATUS
code-wiki-postgres  postgres   Up
code-wiki-neo4j     neo4j      Up
code-wiki-qdrant    qdrant     Up
```

### 2.5. Setup LM Studio (One-time)

```bash
# 1. Download LM Studio from https://lmstudio.ai
# 2. Install and open LM Studio
# 3. In LM Studio:
#    - Search for "Qwen2.5-Coder-7B-Instruct"
#    - Download the model (~7GB)
#    - Load the model
#    - Click "Start Server" (port 1234)

# 4. Verify LM Studio is running
curl http://localhost:1234/v1/models

# Expected: List of loaded models
```

### 3. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python -m src.cli.db init

# Run migrations
python -m src.cli.db migrate

# Start development server
uvicorn src.api.main:app --reload --port 8000
```

Backend should be running at `http://localhost:8000`

Swagger docs available at `http://localhost:8000/docs`

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend should be running at `http://localhost:3000`

### 5. Verify Setup

```bash
# Test backend health
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "version": "1.0.0"}
```

Open browser to `http://localhost:3000` - you should see the wiki homepage.

---

## Environment Configuration

### Backend Environment (`.env`)

Create `backend/.env`:

```env
# Application
APP_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key-change-in-production

# Database
DATABASE_URL=postgresql://codewiki:codewiki@localhost:5432/codewiki
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=codewiki

# Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # Optional, leave empty for local

# LLM (LM Studio with QwenCoder - Local)
LLM_PROVIDER=lmstudio
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=Qwen2.5-Coder-7B-Instruct
LLM_API_KEY=not-needed  # LM Studio doesn't require API key

# Optional: Cloud LLM fallback (if LM Studio not available)
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=your-key-here

# Repository Storage
REPO_CACHE_DIR=./cache/repos

# Feature Flags
ENABLE_CHAT=true
ENABLE_DIAGRAMS=false  # Diagrams feature not in MVP

# Performance
MAX_CONCURRENT_PARSES=5
PARSE_TIMEOUT_SECONDS=900  # 15 minutes
```

### Frontend Environment (`.env.local`)

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
NEXT_PUBLIC_ENABLE_CHAT=true
```

---

## Docker Compose Configuration

`docker-compose.yml` (create in project root):

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: code-wiki-postgres
    environment:
      POSTGRES_USER: codewiki
      POSTGRES_PASSWORD: codewiki
      POSTGRES_DB: codewiki
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  neo4j:
    image: neo4j:5.16
    container_name: code-wiki-neo4j
    environment:
      NEO4J_AUTH: neo4j/codewiki
      NEO4J_PLUGINS: '["graph-data-science"]'
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    volumes:
      - neo4j_data:/data

  qdrant:
    image: qdrant/qdrant:latest
    container_name: code-wiki-qdrant
    ports:
      - "6333:6333"  # REST API
      - "6334:6334"  # gRPC
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres_data:
  neo4j_data:
  qdrant_data:
```

---

## Project Structure

```
code-wiki/
├── backend/
│   ├── src/                  # Source code
│   │   ├── api/             # FastAPI routes
│   │   ├── parsers/         # Code parsers
│   │   ├── wiki/            # Wiki generation
│   │   ├── graph/           # Neo4j graph operations
│   │   ├── chat/            # AI chat
│   │   └── models/          # Data models
│   ├── tests/               # Tests
│   ├── requirements.txt     # Python dependencies
│   └── .env                 # Environment config
│
├── frontend/
│   ├── src/                 # React/Next.js source
│   │   ├── components/      # UI components
│   │   ├── pages/           # Next.js pages
│   │   └── services/        # API clients
│   ├── package.json
│   └── .env.local
│
├── specs/                   # Feature specs & design docs
├── docker-compose.yml
└── README.md
```

---

## Common Development Tasks

### Run Tests

```bash
# Backend tests
cd backend
pytest                    # All tests
pytest tests/unit         # Unit tests only
pytest tests/integration  # Integration tests only
pytest -k "test_parser"   # Specific test pattern

# Frontend tests
cd frontend
npm test                  # Run tests
npm run test:watch        # Watch mode
```

### Database Management

```bash
# Backend CLI commands
python -m src.cli.db status       # Check database status
python -m src.cli.db migrate      # Run migrations
python -m src.cli.db rollback     # Rollback last migration
python -m src.cli.db seed         # Seed test data
python -m src.cli.db reset        # Reset database (WARNING: deletes data)
```

### Add a Repository for Testing

```bash
# Via API
curl -X POST http://localhost:8000/v1/repositories \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://github.com/username/small-test-repo"
  }'

# Via CLI
python -m src.cli.repo add https://github.com/username/small-test-repo
```

### Monitor Processing

```bash
# Watch repository analysis
python -m src.cli.repo status <repository-id>

# Tail logs
tail -f backend/logs/app.log

# Check Neo4j graph
# Open http://localhost:7474 in browser
# Run query: MATCH (n:CodeEntity) RETURN count(n)
```

---

## Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/your-feature

# Make changes, write tests
# Run tests
pytest

# Commit with conventional commits
git commit -m "feat: add module detection for Python packages"
```

### 2. API Changes

When modifying API:
1. Update OpenAPI spec: `specs/001-code-wiki/contracts/openapi.yaml`
2. Update Pydantic models: `backend/src/api/schemas/`
3. Update FastAPI routes: `backend/src/api/routes/`
4. Update frontend API client: `frontend/src/services/api.ts`
5. Run contract tests: `pytest tests/contract/`

### 3. Database Changes

```bash
# Create migration
python -m src.cli.db migration create "add_wiki_pages_table"

# Edit migration file in backend/migrations/
# Run migration
python -m src.cli.db migrate

# Verify
python -m src.cli.db status
```

---

## Troubleshooting

### Backend won't start

```bash
# Check Python version
python --version  # Should be 3.11+

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Check database connection
python -m src.cli.db ping
```

### Frontend won't start

```bash
# Clear cache
rm -rf node_modules .next
npm install

# Check Node version
node --version  # Should be 18+
```

### Database connection errors

```bash
# Check containers are running
docker-compose ps

# Restart databases
docker-compose restart

# Check logs
docker-compose logs postgres
docker-compose logs neo4j
```

### Reset analysis data for rerun

Use this when you want to rerun analysis from a clean state.

```bash
# 1) Find repository id
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -At -c \
  "SELECT id || '|' || url || '|' || status FROM repositories ORDER BY updated_at DESC;"

# 2) Repo-scoped reset (keeps repository row, clears generated artifacts)
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

# 3) Optional: remove repository row completely (dashboard becomes empty)
docker exec -i code-wiki-postgres psql -U codewiki -d codewiki -c \
  "DELETE FROM repositories WHERE id='<repo_id>';"

# 4) Clear repo cache clone
rm -rf backend/cache/repos/https___github_com_<owner>_<repo>

# 5) Optional global store cleanup
docker exec code-wiki-redis redis-cli -p 6379 FLUSHALL
docker exec code-wiki-neo4j cypher-shell -u neo4j -p codewiki \
  "MATCH (n) DETACH DELETE n;"
```

### Parser errors

```bash
# Install language-specific dependencies
pip install jedi          # Python parsing
npm install -g typescript  # TypeScript parsing

# Test parser directly
python -m src.cli.parse test path/to/code/file.py
```

---

## Next Steps

1. **Read the spec**: `specs/001-code-wiki/spec.md` - understand requirements
2. **Review data model**: `specs/001-code-wiki/data-model.md` - understand entities
3. **Explore API**: `http://localhost:8000/docs` - Swagger documentation
4. **Try a repository**: Add a small public repository and watch it generate a wiki
5. **Join development**: Check `CONTRIBUTING.md` for contribution guidelines

---

## Additional Resources

- **API Documentation**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (login: neo4j/codewiki)
- **Feature Spec**: `specs/001-code-wiki/spec.md`
- **Architecture**: `specs/001-code-wiki/plan.md`
- **Data Model**: `specs/001-code-wiki/data-model.md`

---

## Getting Help

- **Issues**: GitHub Issues for bug reports
- **Discussions**: GitHub Discussions for questions
- **Slack**: #code-wiki-dev channel (if applicable)

---

**Quickstart Guide Complete**: 2026-02-15
**Happy Coding!** 🚀
