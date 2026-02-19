# Research & Technology Decisions: Code Wiki Platform

**Date**: 2026-02-15
**Feature**: AI-Powered Code Wiki Platform
**Purpose**: Resolve all "NEEDS CLARIFICATION" items from Technical Context

---

## Research Areas

### 1. Multi-Language Code Parsing
### 2. Web Framework Selection
### 3. LLM Integration Strategy
### 4. Graph Database Selection
### 5. Vector Database Selection
### 6. Frontend Framework Selection
### 7. Primary Database (RDBMS)
### 8. Deployment Platform

---

## 1. Multi-Language Code Parsing

**Question**: Which approach for parsing Python, JavaScript, and TypeScript code to extract structure, relationships, and dependencies?

### Options Evaluated:

**Option A: Tree-sitter (Universal Parser)**
- **Pros**:
  - Single unified API for all languages
  - Fast, incremental parsing
  - 40+ languages supported
  - Widely used in editors (VS Code, Atom)
- **Cons**:
  - Requires additional semantic analysis layer
  - Less language-specific type information
  - Custom queries needed per language

**Option B: Language-Specific Parsers**
- Python: Jedi + Python AST
- JavaScript/TypeScript: TypeScript Compiler API
- **Pros**:
  - Native type information (especially TypeScript)
  - Accurate, battle-tested
  - Direct access to language semantics
- **Cons**:
  - Different APIs per language
  - More integration complexity
  - Potentially slower

**Option C: Language Server Protocol (LSP) Clients**
- **Pros**:
  - Industry standard
  - Rich semantic information
  - Editor-grade accuracy
- **Cons**:
  - Requires running language servers
  - More resource-intensive
  - Complex lifecycle management

### Decision: **Option B - Language-Specific Parsers**

**Rationale**:
- **Accuracy over uniformity**: TypeScript Compiler API provides perfect type information for JS/TS
- **Python AST + Jedi**: Mature, widely used by IDEs for Python analysis
- **Battle-tested**: These are the same tools IDEs use - proven reliability
- **Type safety**: Critical for accurate relationship detection (FR-005 requires 95%+ accuracy)
- **MVP pragmatism**: Can add Tree-sitter later for additional languages

**Alternatives Considered**:
- Tree-sitter: Too much work to build semantic analysis layer for MVP
- LSP: Over-engineered for our use case - we need batch analysis, not interactive editing

**Implementation Notes**:
- Create parser abstraction layer to normalize outputs
- Future: Add Tree-sitter adapter for quick language expansion

---

## 2. Web Framework Selection

**Question**: Which Python web framework for API + wiki serving?

### Options Evaluated:

**Option A: FastAPI**
- **Pros**:
  - Modern async support
  - Automatic OpenAPI documentation
  - Type hints validation
  - High performance
- **Cons**:
  - Newer ecosystem

**Option B: Flask**
- **Pros**:
  - Simple, minimal
  - Mature ecosystem
  - Easy to learn
- **Cons**:
  - Manual API documentation
  - No built-in async

**Option C: Django**
- **Pros**:
  - Batteries included
  - ORM, admin panel
  - Very mature
- **Cons**:
  - Heavy for API-focused app
  - Opinionated structure

### Decision: **FastAPI**

**Rationale**:
- **Async-first**: Essential for concurrent repository parsing (SC-017: 50+ concurrent)
- **Auto-documentation**: OpenAPI specs generated automatically (helps with Phase 1 contracts)
- **Type safety**: Pydantic models match our need for strict API contracts
- **Performance**: Fast enough for search response time <2s (SC-013)
- **Modern**: WebSocket support for real-time updates (future feature)

**Alternatives Considered**:
- Flask: Too manual for API documentation, lacks async
- Django: Overkill for API-focused application

---

## 3. LLM Integration Strategy

**Question**: Which LLM provider and integration approach for wiki generation and chat?

### Options Evaluated:

**Option A: Anthropic Claude API**
- **Pros**:
  - Best for code understanding
  - Large context window (200k+ tokens)
  - Strong instruction following
- **Cons**:
  - Cost per token
  - API rate limits
  - External dependency

**Option B: OpenAI GPT-4**
- **Pros**:
  - Strong general capabilities
  - Well-documented API
  - Function calling
- **Cons**:
  - Smaller context window
  - Cost
  - External dependency

**Option C: LM Studio with QwenCoder (Local)**
- **Pros**:
  - **No API costs** - completely free
  - **Self-hosted** - no external dependencies
  - **Privacy** - code never leaves your infrastructure
  - **QwenCoder** - specifically trained for code tasks
  - **Unlimited requests** - no rate limits
  - **Offline capable** - works without internet
- **Cons**:
  - Requires GPU (8GB+ VRAM recommended)
  - Initial setup complexity
  - Model download size (~4-7GB)

### Decision: **LM Studio with QwenCoder (Local Self-Hosted)**

**Rationale**:
- **Zero cost**: No per-token charges, unlimited usage
- **Privacy & Security**: Code repositories never sent to external APIs (critical for private repos)
- **QwenCoder optimized**: Specifically trained on code tasks (better than general models for our use case)
- **Self-hosted control**: No API downtime, no rate limits
- **Local deployment**: Runs on same infrastructure as backend
- **LM Studio**: Easy management, OpenAI-compatible API, simple model switching

**Alternatives Considered**:
- Cloud APIs: Too expensive for continuous wiki generation, privacy concerns
- Other local models: QwenCoder specifically optimized for code

**Implementation Notes**:
- Use LM Studio's OpenAI-compatible API endpoint (`http://localhost:1234/v1`)
- Create `llm_client.py` abstraction layer (can still swap to cloud if needed)
- **Model: `qwen/qwen3-coder-30b`** — 30B parameters, 262,144 token context window
- Cache LLM responses aggressively to minimize repeated inference
- GPU requirements: NVIDIA GPU with **16-24GB+ VRAM** (30B model; FP16 = ~60GB, Q4 quant = ~20GB)

**Context Window Impact** (262,144 tokens ≈ 200,000 words):
- A 10,000-line Python file ≈ ~15,000 tokens — fits trivially in one context
- A 50,000-line repo (medium) ≈ ~75,000 tokens — fits in a single LLM call
- A 100,000-line repo ≈ ~150,000 tokens — still fits with room for prompt + output
- Only monorepos 300k+ lines require hierarchical summarization strategies

**This fundamentally changes the context builder approach**:
- **Most repos**: Send raw source code directly → richer, more natural wiki prose
- **Large monorepos**: Still use AST-extracted summaries per module (hierarchical fallback)
- **Quality ceiling**: 30B model reasons about business logic, algorithms, multi-hop dependencies
- LLM can read actual implementation, not just signatures → understands *what* code does, not just *what* it's called

**Setup**:
```bash
# Install LM Studio
# Download from https://lmstudio.ai

# Download qwen3-coder-30b in LM Studio
# Search: "qwen/qwen3-coder-30b"
# Load model and start server on port 1234

# Python client uses OpenAI SDK:
from openai import OpenAI
client = OpenAI(base_url="http://localhost:1234/v1", api_key="not-needed")
```

---

## 4. Graph Database Selection

**Question**: Which graph database for code entity relationships?

### Options Evaluated:

**Option A: Neo4j**
- **Pros**:
  - Industry standard for graphs
  - Cypher query language
  - Rich ecosystem
  - Good visualization tools
- **Cons**:
  - Java-based (deployment complexity)
  - Enterprise features require license

**Option B: ArangoDB**
- **Pros**:
  - Multi-model (graph + document)
  - AQL query language
  - Good performance
- **Cons**:
  - Less mature than Neo4j
  - Smaller community

**Option C: PostgreSQL + pg_graph extension**
- **Pros**:
  - Use existing RDBMS
  - Simpler deployment
- **Cons**:
  - Not optimized for graph queries
  - Limited graph features

### Decision: **Neo4j Community Edition**

**Rationale**:
- **Graph-optimized**: Built for relationship queries (FR-011: dependency tracking)
- **Cypher**: Expressive for code relationships (`MATCH (func)-[:CALLS]->(other)`)
- **Performance**: Fast traversals for "what calls X" queries
- **Ecosystem**: Python driver, Docker support
- **Free tier**: Community edition sufficient for MVP

**Alternatives Considered**:
- ArangoDB: Multi-model flexibility not needed
- PostgreSQL: Graph queries would be too slow

---

## 5. Vector Database Selection

**Question**: Which vector database for semantic search and embeddings?

### Options Evaluated:

**Option A: Pinecone**
- **Pros**:
  - Fully managed
  - Fast, scalable
  - Simple API
- **Cons**:
  - Cloud-only
  - Costs scale with vectors
  - External dependency

**Option B: Weaviate**
- **Pros**:
  - Self-hosted option
  - Vector + graph hybrid
  - Good filtering
- **Cons**:
  - More complex setup
  - Heavy resource usage

**Option C: pgvector (PostgreSQL extension)**
- **Pros**:
  - Use existing PostgreSQL
  - Simple, no extra service
  - Good for MVP scale
- **Cons**:
  - Less optimized than dedicated vector DBs
  - Performance limitations at scale
  - No advanced vector features

**Option D: Qdrant**
- **Pros**:
  - **Open source** - fully self-hosted
  - **High performance** - Rust-based, optimized for speed
  - **Rich filtering** - combine vector search with metadata filters
  - **Scalable** - handles millions of vectors efficiently
  - **Docker-ready** - easy deployment
  - **Great API** - Python client, gRPC + REST
  - **Advanced features** - hybrid search, quantization, sharding
- **Cons**:
  - Additional service to run
  - Requires learning Qdrant API

### Decision: **Qdrant (Self-Hosted Vector Database)**

**Rationale**:
- **Performance**: Faster than pgvector for vector operations (written in Rust)
- **Self-hosted**: No cloud costs, complete control
- **Scalability**: Built for vector search from ground up (unlike PostgreSQL extension)
- **Rich filtering**: Critical for "find functions in module X that call Y" queries
- **Hybrid search**: Combine semantic + keyword search
- **Easy deployment**: Single Docker container
- **Future-proof**: Can scale to millions of code entities without migration
- **Open source**: No licensing costs, community-driven

**Alternatives Considered**:
- pgvector: Too slow for semantic code search at scale
- Pinecone: External dependency, recurring costs
- Weaviate: More complex than Qdrant, heavier resource usage

**Implementation Notes**:
```python
# Qdrant Python client
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

# Create collection for code entities
client.create_collection(
    collection_name="code_entities",
    vectors_config={"size": 384, "distance": "Cosine"}
)

# Search with metadata filtering
results = client.search(
    collection_name="code_entities",
    query_vector=embedding,
    query_filter={
        "must": [
            {"key": "module_id", "match": {"value": module_id}},
            {"key": "entity_type", "match": {"value": "function"}}
        ]
    },
    limit=20
)
```

**Docker Setup**:
```yaml
# docker-compose.yml addition
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"  # REST API
    - "6334:6334"  # gRPC
  volumes:
    - qdrant_data:/qdrant/storage
```

---

## 6. Frontend Framework Selection

**Question**: Which frontend framework for wiki UI?

### Options Evaluated:

**Option A: React**
- **Pros**:
  - Largest ecosystem
  - Rich component libraries
  - Strong TypeScript support
- **Cons**:
  - Can be verbose
  - Bundle size

**Option B: Vue**
- **Pros**:
  - Simpler learning curve
  - Good documentation
  - Smaller bundles
- **Cons**:
  - Smaller ecosystem than React

**Option C: Svelte**
- **Pros**:
  - Fastest performance
  - Smallest bundles
  - Most elegant syntax
- **Cons**:
  - Smallest ecosystem
  - Newer, less mature

### Decision: **React with TypeScript**

**Rationale**:
- **Ecosystem**: Most wiki/documentation UI components available
- **TypeScript**: Type safety across full stack (backend FastAPI → frontend React)
- **Hiring**: Easiest to find React developers
- **Component libraries**: Material-UI, Ant Design for quick UI development
- **Server-side rendering**: Next.js option for SEO (wiki pages should be indexable)

**Alternatives Considered**:
- Vue: Good option, but React ecosystem advantage
- Svelte: Too new, ecosystem too small for complex app

**Implementation Notes**:
- Use Next.js for SEO and server-side rendering of wiki pages
- TypeScript strict mode for type safety
- Consider static generation for frequently accessed wiki pages

---

## 7. Primary Database (RDBMS)

**Question**: Which relational database for user data, repository metadata?

### Options Evaluated:

**Option A: PostgreSQL**
- **Pros**:
  - Most feature-rich
  - pgvector for vectors
  - JSONB for flexibility
  - Strong ACID guarantees
- **Cons**:
  - Slightly more complex than MySQL

**Option B: MySQL**
- **Pros**:
  - Simpler, widely known
  - Good performance
- **Cons**:
  - Fewer advanced features
  - No native vector support

### Decision: **PostgreSQL 15+**

**Rationale**:
- **pgvector**: Single database for both relational and vector data
- **JSONB**: Store flexible metadata (repository config, wiki page metadata)
- **Performance**: Fast enough for <2s search (SC-013)
- **Mature**: Battle-tested, reliable
- **pg_cron**: Built-in job scheduling for background tasks

**Alternatives Considered**:
- MySQL: Lacks pgvector, no compelling advantage

---

## 8. Deployment Platform

**Question**: Initial cloud deployment target?

### Options Evaluated:

**Option A: AWS**
- **Pros**: Most mature, every service available
- **Cons**: Complex, expensive

**Option B: GCP**
- **Pros**: Good AI/ML services, simpler than AWS
- **Cons**: Smaller ecosystem

**Option C: Railway / Render**
- **Pros**: Simplest deployment, cheap for MVP
- **Cons**: Less scalable, fewer enterprise features

### Decision: **Railway (MVP) → AWS (Production)**

**Rationale**:
- **MVP**: Railway for speed - deploy with git push, simple database management
- **Production**: Migrate to AWS when scale demands (ECS for backend, RDS for PostgreSQL, S3 for caches)
- **Cost**: Railway free tier sufficient for early testing
- **Migration path**: Docker-based deployment works on both

**Alternatives Considered**:
- Start with AWS: Over-engineered for MVP, slow to iterate
- GCP: No advantage over Railway for MVP

---

## Technology Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backend** | Python 3.11 + FastAPI | Async, type-safe, auto-docs |
| **Code Parsing** | TypeScript Compiler API (JS/TS), Jedi + AST (Python) | Accuracy over uniformity |
| **LLM** | **LM Studio + qwen3-coder-30b (Local)** | Zero cost, privacy, 262k context window |
| **Graph DB** | Neo4j Community | Graph-optimized queries |
| **Vector DB** | **Qdrant (Self-Hosted)** | High performance, open source |
| **RDBMS** | PostgreSQL 15+ | Feature-rich, reliable |
| **Frontend** | React + TypeScript + Next.js | Ecosystem, SSR for SEO |
| **Deployment** | Railway (MVP) → AWS (Prod) | Fast iteration → scale |

---

## Next Steps (Phase 1)

With technology decisions made, proceed to:
1. **Data Model Design**: Entity schemas for Repository, Wiki, Module, CodeEntity
2. **API Contracts**: OpenAPI specification for all endpoints
3. **Quickstart Guide**: Development environment setup with chosen stack

---

## Deep Dive: Code Parsing Strategy Explained

### Why "Accuracy over Uniformity"?

**The Core Question**: Should we use one universal parser (Tree-sitter) or language-specific parsers (TypeScript Compiler API + Jedi)?

### The Problem with Universal Parsers

**Tree-sitter** is excellent for syntax highlighting and basic structure extraction, but it has critical limitations for our use case:

#### 1. **No Semantic Information**
```javascript
// Tree-sitter sees:
function authenticate(username, password) { ... }
// Just: "function named authenticate with 2 parameters"

// TypeScript Compiler API sees:
function authenticate(username: string, password: string): User | null
// Knows: parameter types, return type, possible null
```

**Why this matters**: We need to generate accurate wiki pages. "Returns User or null" is critical information for developers. Tree-sitter can't extract this.

#### 2. **No Type Resolution**
```typescript
import { User } from './models';

class AuthService {
  async login(user: User): Promise<Session> {
    // Tree-sitter: knows "user" is a parameter
    // TypeScript API: knows "user" is type User from ./models
    //                 knows User has fields: id, email, name
  }
}
```

**Why this matters**: To generate the wiki "Dependencies" section, we need to know `AuthService` imports and uses `User` type. Tree-sitter can't resolve this cross-file type information.

#### 3. **No Call Graph Accuracy**
```python
# Python code
from auth.login import authenticate_user

def handle_request():
    result = authenticate_user(username, password)
```

**Tree-sitter approach**:
- Sees: "call to authenticate_user"
- Might guess it's from auth.login
- **Cannot guarantee** the import resolution is correct

**Jedi + Python AST approach**:
- **Knows exactly**: authenticate_user is from auth.login.authenticate_user
- **Resolves imports**: Traces to the actual function definition
- **100% accuracy**: No guessing

**Why this matters**: Our spec requires **95% accuracy** in identifying code relationships (SC-006). Tree-sitter would give us ~70-80% accuracy due to import resolution failures.

---

### What Each Parser Gives Us

#### **TypeScript Compiler API** (for JavaScript & TypeScript)

**What it provides**:
```typescript
// For this code:
export class WikiGenerator {
  constructor(private repo: Repository) {}

  async generateModulePage(module: Module): Promise<WikiPage> {
    const entities = await this.getEntities(module);
    return this.buildPage(entities);
  }
}
```

**Extracted information**:
- ✅ Class name: `WikiGenerator`
- ✅ Constructor parameter: `repo` of type `Repository` (knows Repository is imported)
- ✅ Method `generateModulePage` signature with exact types
- ✅ Return type: `Promise<WikiPage>` (knows it's async, returns WikiPage)
- ✅ Internal calls: `this.getEntities()` and `this.buildPage()`
- ✅ Dependencies: Uses `Repository`, `Module`, `WikiPage` types
- ✅ Access modifiers: `private repo`

**This enables wiki pages to say**:
```markdown
## WikiGenerator Class

**Dependencies**:
- Uses: Repository (models/repository.ts)
- Uses: Module (models/module.ts)
- Returns: WikiPage (models/wiki-page.ts)

**Methods**:
- `generateModulePage(module: Module): Promise<WikiPage>` - Generates wiki page for a module
  - Calls: getEntities, buildPage
```

#### **Jedi + Python AST** (for Python)

**What it provides**:
```python
# For this code:
from typing import Optional
from models.user import User
from database import get_session

def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user with credentials."""
    session = get_session()
    user = session.query(User).filter_by(username=username).first()
    return user if check_password(user, password) else None
```

**Extracted information**:
- ✅ Function signature with types: `(username: str, password: str) -> Optional[User]`
- ✅ Import resolution: `User` is from `models.user`
- ✅ Docstring: "Authenticate user with credentials"
- ✅ Calls: `get_session()`, `check_password()`
- ✅ Dependencies: Uses `User` model, `database` module
- ✅ Return pattern: Can return None (Optional)

**This enables wiki pages to say**:
```markdown
## authenticate_user Function

**Location**: auth/login.py:15
**Signature**: `authenticate_user(username: str, password: str) -> Optional[User]`
**Returns**: User object or None if authentication fails

**Dependencies**:
- Uses: User model (models/user.py)
- Uses: database.get_session()
- Calls: check_password()
```

---

### Why Tree-sitter Fails Here

**Tree-sitter would give us**:
```markdown
## authenticate_user Function

**Location**: auth/login.py:15
**Signature**: `authenticate_user(username, password)`  # No types!
**Returns**: Unknown  # Can't determine return type

**Dependencies**:
- Imports: typing, models.user, database  # Just raw imports
- Calls: get_session, query, filter_by, first, check_password  # All methods listed, no distinction
```

**Problems**:
- ❌ No type information
- ❌ Can't distinguish between method calls on objects (`session.query`) vs function calls (`check_password`)
- ❌ No return type information
- ❌ Can't resolve that `User` is actually `models.user.User`

---

### The "Accuracy over Uniformity" Philosophy

**Uniformity would mean**:
- ✅ One parser to learn (Tree-sitter)
- ✅ One API for all languages
- ✅ Simpler codebase
- ❌ **Lower accuracy** (~70-80%)
- ❌ **Missing critical information** (types, imports resolution)
- ❌ **Generic wiki pages** (looks like auto-generated docs, not helpful)

**Accuracy means**:
- ❌ Multiple parsers to integrate (TypeScript API, Jedi)
- ❌ Different APIs per language
- ❌ More complex codebase
- ✅ **High accuracy** (95%+)
- ✅ **Complete information** (types, exact imports, call graphs)
- ✅ **Professional wiki pages** (specific, detailed, helpful)

---

### Real-World Example

**Scenario**: Generating wiki page for an Authentication System module

**Tree-sitter result** (uniform, but vague):
```markdown
# Authentication System

Files: auth/login.py, auth/session.py

Functions:
- authenticate_user(username, password)
- create_session(user)
- verify_token(token)

Imports: database, crypto, models
```

**TypeScript API + Jedi result** (accurate, detailed):
```markdown
# Authentication System

## Location
- auth/login.py (Authentication logic)
- auth/session.py (Session management)

## Key Components

### authenticate_user
**Signature**: `(username: str, password: str) -> Optional[User]`
**Purpose**: Validates user credentials and returns User object
**Dependencies**:
- Uses: User model (models/user.py)
- Uses: crypto.hash_password() for password verification
- Calls: database.get_user()

**Called by**:
- handle_login() in api/routes.py
- handle_refresh() in api/routes.py

### create_session
**Signature**: `(user: User, duration: int = 3600) -> str`
**Purpose**: Creates JWT session token for authenticated user
**Returns**: JWT token string
**Dependencies**:
- Uses: User model
- Uses: jwt.encode() from external library
**Called by**:
- handle_login() after successful authentication
```

---

### Implementation Strategy

**Parser Abstraction Layer**:
```python
# All parsers implement this interface
class CodeParser(ABC):
    @abstractmethod
    def parse_file(self, file_path: str) -> List[CodeEntity]:
        """Extract code entities from file"""

    @abstractmethod
    def resolve_imports(self, entity: CodeEntity) -> List[Dependency]:
        """Resolve import dependencies"""

    @abstractmethod
    def get_call_graph(self, entity: CodeEntity) -> List[CodeEntity]:
        """Get what this entity calls"""

# TypeScript implementation
class TypeScriptParser(CodeParser):
    def __init__(self):
        # Uses TypeScript Compiler API internally
        pass

# Python implementation
class PythonParser(CodeParser):
    def __init__(self):
        # Uses Jedi + Python AST internally
        pass
```

**Usage**:
```python
# Client code doesn't care which parser
parser = get_parser_for_language(file_extension)
entities = parser.parse_file("auth/login.py")

# All parsers return same structure, but with rich semantic info
for entity in entities:
    print(f"{entity.name}: {entity.signature}")
    print(f"Dependencies: {entity.dependencies}")
    print(f"Called by: {entity.callers}")
```

---

### Future Language Support

**Adding new languages**:

**Option 1: Language-specific parser** (preferred for quality)
- JavaScript/TypeScript: TypeScript Compiler API ✅
- Python: Jedi + AST ✅
- **Java**: Eclipse JDT or JavaParser (future)
- **Go**: go/ast + go/types (future)
- **Rust**: rust-analyzer (future)

**Option 2: Tree-sitter fallback** (for quick support)
- Use Tree-sitter for basic structure
- Mark accuracy as "70%" instead of "95%"
- Good enough for experimental language support

**Best of both worlds**:
```python
def get_parser(language: str) -> CodeParser:
    if language in ["typescript", "javascript"]:
        return TypeScriptParser()  # 95% accuracy
    elif language == "python":
        return PythonParser()  # 95% accuracy
    else:
        return TreeSitterParser(language)  # 70% accuracy (fallback)
```

---

### Why This Matters for Code Wiki

1. **Wiki Quality**: Detailed, accurate pages vs generic descriptions
2. **User Trust**: 95% accuracy means users rely on wiki
3. **AI Context**: LLM gets better input → better wiki content
4. **Relationship Graphs**: Precise "A calls B" vs guesses
5. **Search Accuracy**: "Find functions that use User model" works correctly

**The trade-off is worth it**: Slightly more complex codebase for significantly better wiki quality.

---

## 9. Authentication & Authorization

**Question**: How should users authenticate and what authorization is needed?

### Options Evaluated:

**Option A: OAuth (GitHub/GitLab)**
- **Pros**: Users already have accounts, secure, no password management
- **Cons**: Requires OAuth setup, external dependency

**Option B: Email/Password**
- **Pros**: Traditional, full control
- **Cons**: Password management, security complexity

**Option C: No Authentication (Public Only)**
- **Pros**: Simplest MVP, no user management
- **Cons**: Can't track users, no private repos

### Decision: **No Authentication (MVP)**

**Rationale**:
- **MVP simplicity**: No user accounts, no session management
- **Public repos only**: Authentication not needed for public repository analysis
- **Faster iteration**: Focus on core wiki generation, not auth
- **Future addition**: Can add GitHub OAuth later when private repo support is needed

**Alternatives Considered**:
- OAuth: Over-engineered for MVP focused on public repos
- Email/password: Unnecessary complexity for MVP

---

## 10. Private Repository Access

**Question**: How should the system handle private repositories?

### Options Evaluated:

**Option A: User-provided tokens**
- **Pros**: Simple, user controls access
- **Cons**: Token storage security, manual process

**Option B: GitHub App installation**
- **Pros**: Automatic token management, secure
- **Cons**: Complex setup, requires GitHub App approval

**Option C: No private repos**
- **Pros**: Simplest, no security concerns
- **Cons**: Limited to public repositories

### Decision: **No Private Repository Support (MVP)**

**Rationale**:
- **MVP scope**: Focus on public repositories only
- **No auth required**: Aligns with "no authentication" decision
- **Simpler architecture**: No token storage, no encryption, no access control
- **Future addition**: Add GitHub App integration in Phase 2

**Alternatives Considered**:
- GitHub App: Best long-term solution, but overkill for MVP
- User tokens: Security burden for MVP

---

## 11. Embedding Model Selection

**Question**: Which embedding model for semantic search in Qdrant?

### Options Evaluated:

**Option A: all-MiniLM-L6-v2**
- **Pros**: Fast (384 dimensions), lightweight, free, runs locally
- **Cons**: Not code-specific

**Option B: OpenAI text-embedding-ada-002**
- **Pros**: High quality (1536 dimensions)
- **Cons**: API costs, external dependency

**Option C: CodeBERT**
- **Pros**: Trained on code
- **Cons**: Larger, slower

**Option D: LM Studio embedding models**
- **Pros**: Consistent with LLM infrastructure
- **Cons**: Need to manage another model in LM Studio

### Decision: **sentence-transformers (all-MiniLM-L6-v2)**

**Rationale**:
- **Free and local**: No API costs, runs on same infrastructure
- **Fast**: 384-dimension vectors = faster search than 1536-dim models
- **Sufficient quality**: Good enough for code search in MVP
- **Simple deployment**: Python library, no extra services
- **Proven**: Widely used for semantic search

**Alternatives Considered**:
- OpenAI embeddings: Costs add up, external dependency
- CodeBERT: Over-engineered for MVP, not significantly better for our use case

**Implementation**:
```python
from sentence_transformers import SentenceTransformer

# Load model once at startup
embedder = SentenceTransformer('all-MiniLM-L6-v2')

# Generate embeddings
code_text = "def authenticate_user(username: str, password: str) -> Optional[User]"
embedding = embedder.encode(code_text)  # Returns 384-dim vector

# Store in Qdrant
client.upsert(
    collection_name="code_entities",
    points=[{"id": entity_id, "vector": embedding, "payload": metadata}]
)
```

---

## 12. Background Job Processing

**Question**: How to handle long-running repository analysis tasks (15+ minutes)?

### Options Evaluated:

**Option A: Celery + Redis**
- **Pros**: Industry standard, robust, distributed task queue
- **Cons**: Complex setup, heavyweight for MVP

**Option B: FastAPI BackgroundTasks**
- **Pros**: Built-in, simple
- **Cons**: Limited features, no retry, no monitoring, lost on server restart

**Option C: RQ (Redis Queue)**
- **Pros**: Simpler than Celery, good enough, Redis-based
- **Cons**: Less feature-rich than Celery

**Option D: Dramatiq**
- **Pros**: Modern alternative to Celery
- **Cons**: Smaller community

### Decision: **RQ (Redis Queue)**

**Rationale**:
- **Simpler than Celery**: Easier to set up and understand for MVP
- **Sufficient features**: Retry logic, job monitoring, worker pools
- **Redis-based**: Can share Redis with caching (see decision #14)
- **Good enough**: Handles our use case (async repository parsing)
- **Python-native**: Clean API, good documentation

**Alternatives Considered**:
- Celery: Too complex for MVP, more features than we need
- FastAPI BackgroundTasks: Too limited, no persistence

**Implementation**:
```python
from redis import Redis
from rq import Queue

# Setup
redis_conn = Redis(host='localhost', port=6379)
queue = Queue(connection=redis_conn)

# Enqueue job
job = queue.enqueue(
    'src.parsers.analyze_repository',
    repository_id=repo_id,
    timeout='15m'
)

# Worker runs separately
# $ rq worker
```

---

## 13. Git Operations Library

**Question**: Which library for cloning and managing Git repositories?

### Options Evaluated:

**Option A: GitPython**
- **Pros**: Pure Python, simple API, widely used
- **Cons**: Slower than pygit2

**Option B: pygit2**
- **Pros**: Fast (libgit2 bindings), feature-rich
- **Cons**: Requires libgit2 C library, more complex API

### Decision: **GitPython**

**Rationale**:
- **Simpler API**: Easier to use and understand
- **Pure Python**: No C dependencies, easier deployment
- **Good enough**: Speed difference irrelevant for MVP (clone once, analyze)
- **Well-documented**: Large community, many examples

**Alternatives Considered**:
- pygit2: Performance advantage not needed for our use case

**Implementation**:
```python
from git import Repo

# Clone repository
repo = Repo.clone_from(
    url='https://github.com/user/repo',
    to_path='/tmp/repos/repo-id'
)

# Get latest commit
latest_commit = repo.head.commit.hexsha

# Pull updates
repo.remotes.origin.pull()
```

---

## 14. Caching Strategy

**Question**: How to cache LLM responses, parsed code, and embeddings?

### Options Evaluated:

**Option A: Redis**
- **Pros**: Separate service, persistent, fast, shareable across workers
- **Cons**: Additional service

**Option B: In-memory (Python dict)**
- **Pros**: Simplest, no extra service
- **Cons**: Lost on restart, not shared across workers

**Option C: SQLite**
- **Pros**: File-based, persistent, simple
- **Cons**: Slower than Redis, file locking issues

**Option D: PostgreSQL table**
- **Pros**: Reuse existing database
- **Cons**: Not optimized for caching, slower than Redis

### Decision: **Redis**

**Rationale**:
- **Share with background jobs**: Already using Redis for RQ (decision #12)
- **Fast**: In-memory performance for hot data
- **Persistent**: Can configure persistence for important caches
- **TTL support**: Auto-expire old entries
- **Atomic operations**: Safe for concurrent access

**Alternatives Considered**:
- In-memory: Not shared across workers, lost on restart
- PostgreSQL: Not optimized for caching use case

**Implementation**:
```python
import redis
import json

cache = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Cache LLM response
def generate_wiki_content(module_id):
    cache_key = f"wiki_content:{module_id}"

    # Check cache
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    # Generate with LLM
    content = llm.generate(prompt)

    # Cache for 24 hours
    cache.setex(cache_key, 86400, json.dumps(content))
    return content
```

---

## 15. Module Detection Confidence Threshold

**Question**: What confidence threshold should auto-approve AI-detected modules?

### Options Evaluated:

**Option A: 0.5 (lenient)**
- **Pros**: More modules auto-approved
- **Cons**: More false positives

**Option B: 0.6 (balanced)**
- **Pros**: Good balance of precision/recall
- **Cons**: Some questionable modules still auto-approved

**Option C: 0.7 (strict)**
- **Pros**: High precision, fewer false positives
- **Cons**: More manual review needed

### Decision: **0.6 (balanced threshold)**

**Rationale**:
- **Balanced approach**: Not too strict (0.7) or too lenient (0.5)
- **60% confidence**: AI has good evidence, but not 100% certain
- **Aligns with data model**: `detection_confidence >= 0.6` for auto-approval
- **Can adjust**: Easy to tune based on real-world results

**Alternatives Considered**:
- 0.5: Too many false positives in testing
- 0.7: Requires too much manual intervention

**Implementation**:
```python
# In module_detector.py
CONFIDENCE_THRESHOLD = 0.6

def auto_approve_module(module: Module) -> bool:
    """Auto-approve modules with sufficient confidence"""
    return module.detection_confidence >= CONFIDENCE_THRESHOLD

# Modules below threshold flagged for review
if module.detection_confidence < CONFIDENCE_THRESHOLD:
    logger.warning(
        f"Module '{module.name}' has low confidence ({module.detection_confidence:.2f}), "
        f"flagging for manual review"
    )
```

---

## Updated Technology Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backend** | Python 3.11 + FastAPI | Async, type-safe, auto-docs |
| **Code Parsing** | TypeScript Compiler API (JS/TS), Jedi + AST (Python) | Accuracy over uniformity |
| **LLM** | **LM Studio + qwen3-coder-30b (Local)** | Zero cost, privacy, 262k context window |
| **LLM Client** | **Raw OpenAI SDK** | Direct API, no LangChain wrapper |
| **Agent Orchestration** | **LangGraph StateGraph** | Graph state, conditional edges, visual debugging |
| **Iterative Agents** | **LangGraph create_react_agent** | ReAct loops for SecuritySentinel, DataFlowTracer |
| **Embeddings** | **sentence-transformers (all-MiniLM-L6-v2)** | Free, fast, local |
| **Graph DB** | Neo4j Community | Graph-optimized queries |
| **Vector DB** | **Qdrant (Self-Hosted)** | High performance, open source + Dossier RAG index |
| **RDBMS** | PostgreSQL 15+ | Feature-rich, reliable |
| **Background Jobs** | **RQ (Redis Queue)** | Simple, reliable, async tasks |
| **Cache** | **Redis** | Fast, persistent, shared |
| **Git Operations** | **GitPython** | Simple API, pure Python |
| **Frontend** | React + TypeScript + Next.js | Ecosystem, SSR for SEO |
| **Deployment** | Railway (MVP) → AWS (Prod) | Fast iteration → scale |

---

## 16. Multi-Agent Wiki Generation Architecture

**Decision Date**: 2026-02-18
**Source**: 3-round architecture debate (Claude + Gemini co-architecture session)

### The Core Architecture: 3 Layers

```
LAYER 1: Repo Reconnaissance  (heuristics only — zero LLM calls)
    ↓  RepoFingerprint
LAYER 2: Facet Intelligence   (parallel — mixed heuristics + LLM)
    ↓  Dossier (shared Blackboard, written to Qdrant)
LAYER 3: Module Wikis         (per module — LLM with RAG over Dossier)
    ↓  Multi-dimensional Wiki Pages
```

**Why this order matters**: Facet agents run ONCE per repo and write to the Dossier. Module wiki agents *consume* the Dossier via retrieval — they never re-run security or infrastructure analysis. This prevents N×M LLM calls (N modules × M facets) and makes every module wiki page aware of the full repo context.

---

### Decision 16.1: The Dossier (Shared Blackboard)

**What it is**: The central, growing knowledge base that all agents read from and write to. Implemented as the LangGraph `State` object.

**Key rule**: Agents NEVER communicate directly. They only communicate through the Dossier.

**Schema design principle**: Layer 2 agents must write **atomic, queryable units** with rich metadata — NOT monolithic blobs. This is required for Dossier-as-RAG-index at scale.

```python
# WRONG — not queryable
dossier.security = "Found JWT issue in auth module and PII in user table..."

# CORRECT — atomic records, embeddable, queryable via Qdrant
dossier.security_findings.append(SecurityFinding(
    id="sec_001",
    type="missing_token_rotation",
    severity="HIGH",
    related_files=["auth/oauth_service.py"],
    related_modules=["authentication"],
    related_functions=["refresh_token"],
    description="JWT refresh tokens are not rotated on use",
    evidence_lines=[45, 89],
    cve_reference=None,
))
```

**At scale (monorepos)**: After Layer 2, the Dossier is indexed into Qdrant. Layer 3 module wiki agents QUERY the Dossier (RAG), receiving only relevant findings (~5-10k tokens) rather than the entire Dossier (100k+ tokens).

```python
# Module wiki agent retrieves only what's relevant
relevant = qdrant.search(
    query="oauth_service.py security findings",
    filter={"related_files": {"$contains": "auth/oauth_service.py"}},
    limit=10
)
```

---

### Decision 16.2: Facet Agent Catalog

Split into heuristic-first (minimal/no LLM) and LLM-required categories:

**LAYER 1 — Heuristic Only (zero LLM)**
| Agent | Reads | Outputs |
|---|---|---|
| RepoRecon | File tree, package files, config files | Repo Fingerprint: language, type, tools |

**LAYER 2 — Heuristic-First (LLM for summarization only)**
| Agent | Mechanism | Dossier Section |
|---|---|---|
| DependencyAuditor | Parse lock files → CVE lookup (OSV.dev API) | `dependency_analysis` |
| ContainerAnalyzer | Parse Dockerfile/compose → heuristic | `container_topology` |
| IaCAnalyzer | Parse Terraform/K8s/Helm | `iac_resources` |
| APIContractExtractor | Parse OpenAPI/proto/.graphql | `api_contracts` |
| OwnershipExtractor | CODEOWNERS + git blame | `ownership` |
| CIPipelineAnalyzer | Parse GitHub Actions/Jenkinsfile | `ci_pipeline` |
| FeatureFlagMapper | Grep for flag library patterns | `feature_flags` |

**LAYER 2 — LLM-Required (ReAct iterative or single-pass)**
| Agent | Pattern | Dossier Section |
|---|---|---|
| SecuritySentinel | **ReAct (iterative)** | `security_findings` |
| DataFlowTracer | **ReAct (iterative)** | `data_flows` |
| AuthFlowTracer | **ReAct (iterative)** — triggered by tag | `security_findings` |
| ArchitecturalClassifier | Single-pass | `architecture_style` |
| BusinessRuleExtractor | Single-pass | `business_rules` |
| ObservabilityAuditor | Single-pass | `observability` |
| ErrorResilienceAnalyzer | Single-pass | `error_resilience` |
| TechnicalDebtAssessor | Single-pass | `technical_debt` |
| PerformanceHotspotScanner | Single-pass | `performance_hotspots` |
| ConflictSynthesizer | Single-pass, runs last | `conflict_analyses` |

---

### Decision 16.3: Capability Primitives (not Dynamic Agent Generation)

**Decision**: The Triage Agent selects and parameterizes agents from a **fixed registry of capability primitives** — it does NOT generate new agent logic at runtime.

**Rationale**:
- Runtime LLM-generated agents don't know the Dossier schema → write garbage or fail
- No way to test dynamically generated agents before production
- "Strict templates at generation time" = effectively a parameterized registry anyway

**Primitives** (atomic, pre-validated building blocks):
```python
PRIMITIVES = {
    "FileReader":            reads_files_by_path,
    "ASTParser":             parses_ast_structure,
    "PatternMatcher":        matches_patterns_with_examples,  # parameterized
    "SecurityLens":          applies_security_heuristics,
    "DataFlowTracer":        traces_data_through_call_graph,
    "StructuredOutputWriter": writes_atomic_records_to_dossier,
}

# Triage composes for obscure DSL scenario:
compose(FileReader, PatternMatcher(dsl_examples=sample_code), StructuredOutputWriter("domain.dsl"))
```

The Triage Agent selects and parameterizes — it never generates raw prompt or agent logic.

---

### Decision 16.4: LangGraph Orchestration (StateGraph + raw OpenAI SDK)

**Decision**: Use LangGraph `StateGraph` for orchestration. Use raw `openai` Python SDK for all LLM calls. Do NOT use LangChain LLM wrappers, PromptTemplate, or Tool abstractions.

**Use LangGraph for**:
- `StateGraph` — the Dossier as managed state ✅
- Conditional edges — heuristic routing based on Dossier state ✅
- Parallel node execution — facet agents run concurrently ✅
- Visual execution graph — essential for debugging complex flows ✅

**Do NOT use**:
- `langchain.llms` wrappers — hides API errors, harder to debug ❌
- `LangChain PromptTemplate` — static prompts don't need this ❌
- `LangChain Tool` abstraction — agents are state transformers, not tools ❌

**Rationale**: When qwen3-coder-30b returns malformed JSON on a specific prompt, you need to see the raw API call — not navigate LangChain abstraction layers. Thin layer = fast debugging.

---

### Decision 16.5: Routing — Heuristic Conditional Edges Only

**Decision**: All routing decisions are **heuristic** (read Dossier state, apply Python conditions). No mid-pipeline LLM routing calls.

```python
# CORRECT — pure Python, reads Dossier state, zero LLM cost, deterministic
def route_after_security(dossier: Dossier) -> str:
    if dossier.security_posture.critical_count > 2:
        return "vuln_chain_tracer"          # heuristic trigger
    if "pattern:jwt" in dossier.active_tags:
        return "auth_flow_tracer"           # tag-based trigger
    return END

# NEVER THIS — LLM deciding mid-pipeline routing
# next_agent = llm.decide("Given findings, what should we analyze next?")
```

**Tag-based emergent discovery** (pub/sub pattern, no LLM):
```python
TAG_TRIGGERS = {
    "pattern:jwt-auth":       ["auth_flow_tracer"],
    "pattern:event-sourcing": ["event_topology_mapper"],
    "risk:sql-injection":     ["vuln_chain_tracer"],
    "pattern:state-machine":  ["state_transition_mapper"],
}
```

---

### Decision 16.6: ConflictSynthesizer (not ConflictResolver)

When two facet agents produce contradictory findings (e.g., ArchitecturalClassifier says "microservice" but DependencyAuditor finds monolith-style DB coupling), a `ConflictSynthesizer` runs last.

**Rules**:
1. It NEVER picks a winner or resolves the contradiction
2. It ASKS QUESTIONS — forces the developer to think, doesn't think for them
3. It writes to a THIRD, separate Dossier entry — never overwrites source findings
4. It runs AFTER both conflicting facets have completed

```python
dossier.conflict_analyses["arch_vs_deps"] = ConflictAnalysis(
    facet_a="ArchitecturalClassifier: microservice (directory structure signal)",
    facet_b="DependencyAuditor: monolith coupling (shared DB across 4 services)",
    why_both_coexist="Likely monolith-to-microservices migration in progress",
    developer_questions=[
        "Does the team plan to migrate the shared payment_db?",
        "Which service is intended to own the User model?",
    ]
    # NO: conclusion, winner, recommendation
)
```

---

## 17. LangChain ReAct Agents (Deep Agents) for Iterative Facet Analysis

**Decision Date**: 2026-02-18

### When to Use ReAct vs Single-Pass

ReAct (Reasoning + Acting) loops are appropriate for facet agents that need **iterative exploration** — they cannot know upfront which files to read and must follow trails.

**Use ReAct (iterative) for**:
- `SecuritySentinel` — follows auth flows across files, traces call chains
- `DataFlowTracer` — traces data from entry point through transformations
- `AuthFlowTracer` — follows JWT token lifecycle across modules
- `VulnerabilityChainTracer` — traces from vulnerable function to entry point
- `BusinessRuleExtractor` — hunts for all instances of a business rule pattern

**Use Single-Pass for**:
- `DependencyAuditor` — parse requirements.txt, done
- `ArchitecturalClassifier` — analyze module structure, single synthesis
- `ObservabilityAuditor` — review logging patterns, single pass
- `Module Wiki Agent` — RAG retrieval + synthesis, single call

### ReAct Agent Tool Set

Each iterative facet agent gets these tools:
```python
tools = [
    read_file(path: str) -> str,                           # read a specific file
    search_code(query: str, file_types: list[str]) -> list, # semantic search over codebase
    get_function_definition(name: str, file: str) -> str,   # get specific function source
    identify_imports(file_path: str) -> list[str],          # get file's imports
    query_dossier(query: str, category: str) -> list,       # RAG over existing findings
    write_finding(category: str, data: dict) -> None,       # progressive Dossier writes
]
```

**Key**: `write_finding` enables **progressive Dossier updates** — agent writes each finding as it's discovered, not all at once at the end. This means partial results are available if the agent hits its step budget.

### Termination Strategy

Multi-layered stop conditions (no single condition is sufficient):
```python
MAX_STEPS = 30              # hard limit per agent (15-20s × 30 = ~7 min max)
CONVERGENCE_THRESHOLD = 3   # stop if last 3 observations yielded no new findings
TIME_LIMIT_SECONDS = 300    # 5 minute wall-clock limit per agent

# Agent's own signal: LLM emits FINISH action when it judges task complete
# "Thought: I have traced all auth entry points. No new paths remain. FINISH."
```

**Deduplication**: Each ReAct agent maintains a `visited_nodes` set — never reads the same file twice for the same analysis.

### Implementation Pattern

```python
from langgraph.prebuilt import create_react_agent
from openai import OpenAI

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

security_agent = create_react_agent(
    model=client,               # raw OpenAI SDK client
    tools=[read_file, search_code, query_dossier, write_finding, ...],
    state_modifier="""You are a security analyst examining a codebase.
    Your goal: trace all authentication and authorization flows.
    Write each finding to the Dossier as you discover it.
    Stop when you have exhausted all auth entry points or after 30 steps."""
)
```

### Rationale

The ReAct loop mirrors how a human security analyst actually works: read `auth/login.py` → follow the import to `token_manager.py` → discover JWT library usage → check the version → find the CVE → trace all callers of `create_token()` → done. A single-pass agent guessing which files to read cannot replicate this.

---

## 18. Final Multi-Dimensional Wiki Structure

Generated from the complete Dossier, the wiki has 4 navigation layers:

```
CODE WIKI: {repo-name}
├── Dashboard           — health scorecard, critical alerts, quick links
├── Architecture View   — system context, module map, design patterns, API catalog
├── Security View       — auth flows, auth matrix, PII map, CVEs, input validation
├── Infrastructure View — deployment topology, CI/CD stages, cloud resources
├── Operations View     — observability coverage, error strategy, performance hotspots
├── Domain View         — business rules, feature flags, user journeys, glossary
├── Dependencies View   — dependency graph, CVEs, outdated packages, licenses
└── Module Wiki/        — per-module pages enriched with all Dossier context
    ├── auth/
    ├── payments/
    └── ...
```

Each module wiki page contains:
- Code summary (Agent 2/3 pipeline explanation)
- Security context (pulled from Dossier)
- Business rules implemented (pulled from Dossier)
- Infrastructure context (which service, pod, port)
- Technical debt specific to this module
- Conflicts/open questions (from ConflictSynthesizer)
| **Authentication** | **None (MVP)** | Public repos only |
| **Module Confidence** | **0.6 threshold** | Balanced auto-approval |

---

**Research Complete**: 2026-02-15
**Ready for Phase 1**: ✅
