# Proposed Plan (Opus)

**Migration: Neo4j → LadybugDB + AST Parsers → Tree-sitter**

Clean cutover — no rollback code, no feature flags, no dual-write compatibility layer.

---

## 0. Evidence Base

All file references verified against repository at `/Users/ranjit/Documents/Projects/code-wiki`.
External package data verified against PyPI and GitHub (April 2026).

### Current Neo4j touchpoints (7 files)

| File | Usage |
|------|-------|
| `backend/src/storage/graph_db.py` | Core: driver singleton, CRUD (4 Cypher queries), health check |
| `backend/src/jobs/analyze.py` | `_write_neo4j()` — writes nodes + CALLS edges from ParsedEntity |
| `backend/src/wiki/v3_tools/graph_tools.py` | 6 LangChain tools with raw Cypher (callers, callees, imports, inheritance, neighborhood, stats) |
| `backend/src/wiki/page_builders/diagrams.py` | `_build_dependency_graph()` calls `graph_db.get_module_relationships()` |
| `backend/src/api/routes/wikis.py` | Entity detail endpoint — inline Cypher for CALLS/IMPORTS/INHERITS_FROM |
| `backend/src/api/health.py` | `_check_neo4j_sync()` health check |
| `backend/src/config.py` | `neo4j_uri`, `neo4j_user`, `neo4j_password` settings |

### Current parser touchpoints (16 files)

| File | Usage |
|------|-------|
| `backend/src/parsers/base.py` | `ParsedEntity`, `Dependency`, `CallEdge`, `CodeParser` ABC |
| `backend/src/parsers/__init__.py` | Registry: `get_parser()`, `supported_extensions()`, extension→lang map |
| `backend/src/parsers/extractor.py` | `extract_entities()` — walks repo, dispatches to parsers |
| `backend/src/parsers/python_parser.py` | `PythonParser` — uses `ast` + `jedi` |
| `backend/src/parsers/typescript_parser.py` | `TypeScriptParser` — shells out to Node.js subprocess |
| `backend/src/parsers/rust_parser.py` | `RustParser` — regex + brace tracking |
| `backend/src/parsers/ts_extractor/` | Node.js package: `extractor.js` + `typescript` npm dep |
| `backend/src/agents/primitives/tools.py` | `parse_ast()` — on-demand file parsing for agents |
| `backend/src/jobs/analyze.py` | Step 3: calls `extract_entities()`, Step 4b: `_write_neo4j()` |
| `backend/src/wiki/compressor.py` | Consumes `ParsedEntity` for scoring/grouping |
| `backend/src/wiki/interestingness.py` | Consumes `ParsedEntity` for interestingness scoring |
| `backend/src/wiki/wiki_pipeline.py` | Persists `ParsedEntity` to PostgreSQL |
| `backend/src/wiki/pipeline_types.py` | Type references to `ParsedEntity` |
| `backend/src/wiki/page_builders/special_pages.py` | Builds API reference pages from entities |
| `backend/src/wiki/agents/reference_builder.py` | Generates entity documentation |
| `backend/src/wiki/agents/state.py` | Agent state includes `ParsedEntity` types |
| `backend/src/dossier/rag_index.py` | References `ParsedEntity` in vector indexing |

### Cypher queries to port (complete inventory)

1. **graph_db.py — MERGE node**: `MERGE (e:CodeEntity {id: $id}) SET e.qualified_name=..., e.entity_type=..., e.name=..., e.file_path=..., e.module_id=...`
2. **graph_db.py — MERGE relationship**: `MATCH (a:CodeEntity {id: $from_id}) MATCH (b:CodeEntity {id: $to_id}) MERGE (a)-[:REL_TYPE]->(b)`
3. **graph_db.py — get_neighbors**: `MATCH (a:CodeEntity {id: $id})-[r]-(b:CodeEntity) RETURN b`
4. **graph_db.py — get_module_relationships**: `MATCH (a:CodeEntity)-[r]->(b:CodeEntity) WHERE a.module_id IN $ids AND b.module_id IN $ids AND a.module_id <> b.module_id RETURN DISTINCT a.module_id, b.module_id, type(r), count(r)`
5. **graph_tools.py — get_callers**: `MATCH (caller:CodeEntity)-[:CALLS]->(target:CodeEntity) WHERE target.qualified_name CONTAINS $name OR target.name = $name ...`
6. **graph_tools.py — get_callees**: similar pattern reversed
7. **graph_tools.py — get_imports**: `MATCH (source:CodeEntity)-[:IMPORTS]->(imported:CodeEntity) WHERE ...`
8. **graph_tools.py — get_inheritance**: 2 queries (parents + children) via `INHERITS_FROM`
9. **graph_tools.py — get_entity_neighborhood**: `MATCH (a:CodeEntity)-[r]-(b:CodeEntity) WHERE ...` with `startNode(r)` direction check
10. **graph_tools.py — get_graph_stats**: `MATCH (n:CodeEntity) RETURN count(n)` + `MATCH ()-[r]->() RETURN type(r), count(r)`
11. **wikis.py — entity relationships**: `MATCH (n {qualified_name: $qname}) OPTIONAL MATCH (n)-[:CALLS]->(callee) OPTIONAL MATCH (n)-[:IMPORTS]->(imported) OPTIONAL MATCH (n)-[:INHERITS_FROM]->(parent) RETURN collect(DISTINCT ...)`

---

## 1. Architecture Decisions

### AD-1: Graph Storage — LadybugDB (embedded)

**Decision**: Replace Neo4j (server) with LadybugDB (embedded, file-based).

**Rationale**:
- LadybugDB uses Cypher (openCypher-compatible) — all 11 queries above port with minimal syntax changes
- Embedded = no Docker service, no network hop, no connection pool management
- On-disk mode with WAL for durability (`{data_dir}/graph/code_graph.lbug`)
- Python package: `real_ladybug` (v0.15.3 on PyPI, MIT license)
- Formerly known as Kuzu; 921 GitHub stars, active development

**Key API difference from Neo4j**:
```python
# Neo4j (current)
from neo4j import GraphDatabase
driver = GraphDatabase.driver(uri, auth=(user, pw))
with driver.session() as session:
    result = session.run("MATCH ... RETURN ...", param=value)
    records = [dict(r) for r in result]

# LadybugDB (target)
import real_ladybug as lb
db = lb.Database("path/to/code_graph.lbug")
conn = lb.Connection(db)
result = conn.execute("MATCH ... RETURN ...", parameters={"param": value})
records = [row for row in result.rows_as_dict()]
```

**Schema requirement** (LadybugDB needs explicit DDL, Neo4j did not):
```cypher
CREATE NODE TABLE CodeEntity(
    id STRING PRIMARY KEY,
    qualified_name STRING,
    entity_type STRING,
    name STRING,
    file_path STRING,
    module_id STRING
);
CREATE REL TABLE CALLS(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE IMPORTS(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE INHERITS_FROM(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE DEFINES(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE USES(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE OVERRIDES(FROM CodeEntity TO CodeEntity);
```

**Cypher compatibility notes** (confirmed from LadybugDB docs):
- `MERGE` is supported in LadybugDB
- `MATCH`, `WHERE`, `RETURN`, `OPTIONAL MATCH`, `collect`, `DISTINCT`, `count`, `type(r)` — all supported
- `startNode(r)` — **verify** if supported; may need workaround using explicit direction patterns
- `CONTAINS` string predicate — supported
- Parameterized queries — supported (syntax may differ: `$param` vs `{param}`)

**Open question OQ-1**: LadybugDB requires pre-defined schema. Current Neo4j usage is schema-free with implicit MERGE. Need to confirm `MERGE` behavior with pre-existing schema — specifically whether MERGE on CodeEntity works as upsert when the node table already exists. **Mitigation**: Test during Phase 1 spike.

### AD-2: Parser Architecture — Tree-sitter (unified)

**Decision**: Replace all three parser implementations + Node.js subprocess with a single Tree-sitter-based parser module.

**Rationale**:
- Single binary library handles all languages (no Node.js subprocess for TS)
- Eliminates `jedi` dependency (Python), `typescript` npm package, regex-based Rust parser
- Supports all target languages: Python, TypeScript/JS, Rust, C#, Java
- Tree-sitter is mature (7+ years, 1,392 stars for py-tree-sitter)
- Incremental parsing for fast re-analysis of changed files

**Python packages required**:
```
tree-sitter>=0.25.0          # Core parser library
tree-sitter-python>=0.23.0   # Python grammar
tree-sitter-typescript>=0.23.0  # TypeScript + TSX grammar
tree-sitter-rust>=0.23.0     # Rust grammar
tree-sitter-c-sharp>=0.23.0  # C# grammar
tree-sitter-java>=0.23.0     # Java grammar
```

**Architecture**:
```
parsers/
  base.py              # KEEP: ParsedEntity, Dependency, CallEdge, CodeParser ABC (unchanged)
  __init__.py           # REWRITE: registry maps extensions to TreeSitterParser instances
  extractor.py          # MINOR EDIT: no structural changes (calls get_parser → parse_file)
  tree_sitter_parser.py # NEW: single file, language-parameterized
  queries/              # NEW: directory of .scm query files per language
    python.scm
    typescript.scm
    rust.scm
    csharp.scm
    java.scm
```

**Design of `TreeSitterParser`**:
- Single class parameterized by language name
- Loads grammar via `tree_sitter_{lang}.language()`
- Uses S-expression query files (`.scm`) for entity extraction (functions, classes, imports, calls)
- Returns `list[ParsedEntity]` — identical output contract, no downstream changes needed
- Extraction approach: pattern-based queries (tree-sitter's query API) + AST walking for calls

**What stays unchanged**:
- `ParsedEntity` dataclass (base.py) — no changes
- `Dependency`, `CallEdge` dataclasses — no changes
- `CodeParser` ABC — no changes (TreeSitterParser implements it)
- `extractor.py` `extract_entities()` — unchanged (calls `get_parser().parse_file()`)
- All downstream consumers (compressor.py, interestingness.py, wiki_pipeline.py, etc.) — unchanged

### AD-3: No C# or Java Parser Exists Today

**Confirmed fact**: The current codebase only has parsers for Python, TypeScript/JS, and Rust. Adding C# and Java support is new functionality enabled by Tree-sitter.

**Approach**: Include C# and Java grammars and query files from Phase 2. The extension map in `__init__.py` adds `.cs`, `.java` entries.

---

## 2. Phases and Tasks

### Phase 1: LadybugDB Spike + Tree-sitter Proof of Concept (2-3 days)

Goal: Validate both technologies work for our use case before committing to full migration.

#### T1.1 — LadybugDB schema + query validation spike

**Description**: Install `real_ladybug`, create the CodeEntity schema, test all 11 Cypher queries from the inventory against it. Confirm MERGE, OPTIONAL MATCH, CONTAINS, collect(DISTINCT), type(r), startNode(r), count, parameterized queries.

**Acceptance criteria**:
- All 11 Cypher queries execute successfully or have documented rewrites
- MERGE works as upsert on existing node table
- Parameter binding syntax confirmed
- `startNode(r)` alternative confirmed if not supported
- Performance: 10K nodes + 50K edges loads in <10s

**Verification**: Standalone test script that creates schema, inserts sample data, runs each query, asserts results.

**Files touched**: None (standalone spike script in `backend/scripts/spike_ladybug.py`)

**Scope**: S (1 day)

#### T1.2 — Tree-sitter extraction spike

**Description**: Install tree-sitter + 5 grammars. Write a minimal extractor that parses a Python file and a TypeScript file, extracts functions/classes/imports/calls, and returns `ParsedEntity`-shaped data.

**Acceptance criteria**:
- Parse `backend/src/parsers/python_parser.py` (Python) → extract all functions/classes
- Parse `backend/src/parsers/ts_extractor/extractor.js` (JS) → extract functions/exports
- Extracted entities match current parser output (spot-check 5+ entities)
- Call extraction works (at least function-call-to-name resolution)

**Verification**: Standalone test script that parses known files, asserts entity count and names.

**Files touched**: None (standalone spike script in `backend/scripts/spike_treesitter.py`)

**Scope**: S (1 day)

#### T1.3 — Spike review checkpoint

**Description**: Review spike results. Decide go/no-go. Document any Cypher query rewrites needed, any tree-sitter extraction gaps.

**Acceptance criteria**: Written confirmation of all queries ported, extraction parity confirmed.

**Verification**: Review notes appended to this plan.

**Scope**: XS (<2 hours)

**Dependencies**: T1.1, T1.2

---

### Phase 2: Tree-sitter Parser Implementation (3-4 days)

Goal: Replace all three parser implementations with tree-sitter.

#### T2.1 — Create tree-sitter query files (.scm) for all 5 languages

**Description**: Write S-expression queries that capture:
- Function/method definitions (name, parameters, return type, docstring, line range)
- Class/struct/enum/trait/interface definitions
- Import/use/require statements
- Call expressions (caller context + callee name)

One `.scm` file per language under `backend/src/parsers/queries/`.

**Acceptance criteria**:
- `python.scm`: functions, classes, methods, imports, calls, decorators
- `typescript.scm`: functions, classes, interfaces, imports, calls (covers .ts/.tsx/.js/.jsx/.mjs/.cjs)
- `rust.scm`: fn, struct, enum, trait, impl methods, use, macro calls
- `csharp.scm`: methods, classes, interfaces, using, invocations
- `java.scm`: methods, classes, interfaces, imports, invocations

**Verification**: Each query file tested against sample source files with expected match counts.

**Files touched**:
- NEW: `backend/src/parsers/queries/python.scm`
- NEW: `backend/src/parsers/queries/typescript.scm`
- NEW: `backend/src/parsers/queries/rust.scm`
- NEW: `backend/src/parsers/queries/csharp.scm`
- NEW: `backend/src/parsers/queries/java.scm`

**Scope**: M (2 days)

#### T2.2 — Implement `TreeSitterParser` class

**Description**: Single class implementing `CodeParser` ABC, parameterized by language. Uses query files from T2.1. Handles:
- Grammar loading (lazy, cached per language)
- File parsing via `tree_sitter.Parser`
- Entity extraction via queries + AST walking
- Qualified name construction (module.class.method pattern)
- Signature extraction from AST nodes
- Docstring extraction
- Call extraction (walk `call_expression` nodes, resolve callee name)
- Import extraction

**Acceptance criteria**:
- Implements all 3 ABC methods: `parse_file()`, `resolve_imports()`, `get_call_graph()`
- Returns `list[ParsedEntity]` with all fields populated
- Handles encoding errors gracefully (skip unparseable files)
- No subprocess calls

**Verification**: Unit tests comparing output against current parsers on 5+ real files per language.

**Files touched**:
- NEW: `backend/src/parsers/tree_sitter_parser.py`

**Scope**: M (2 days)

**Dependencies**: T2.1

#### T2.3 — Rewrite parser registry

**Description**: Update `__init__.py` to:
- Remove imports of `PythonParser`, `TypeScriptParser`, `RustParser`
- Add `TreeSitterParser` imports
- Extend `_EXTENSION_MAP` with `.cs`, `.java` entries
- All parser singletons become `TreeSitterParser("python")`, `TreeSitterParser("typescript")`, etc.

**Acceptance criteria**:
- `get_parser(".py")` returns `TreeSitterParser("python")`
- `get_parser(".ts")` returns `TreeSitterParser("typescript")`
- `get_parser(".rs")` returns `TreeSitterParser("rust")`
- `get_parser(".cs")` returns `TreeSitterParser("csharp")`
- `get_parser(".java")` returns `TreeSitterParser("java")`
- `supported_extensions()` returns all expected extensions

**Verification**: Unit test calling `get_parser()` for each extension.

**Files touched**:
- EDIT: `backend/src/parsers/__init__.py`

**Scope**: XS (<1 hour)

**Dependencies**: T2.2

#### T2.4 — Delete old parsers

**Description**: Remove:
- `backend/src/parsers/python_parser.py`
- `backend/src/parsers/typescript_parser.py`
- `backend/src/parsers/rust_parser.py`
- `backend/src/parsers/ts_extractor/` (entire directory — extractor.js, package.json, node_modules)

**Acceptance criteria**:
- Files deleted
- No remaining imports of deleted modules anywhere in codebase
- `grep -r "python_parser\|typescript_parser\|rust_parser\|ts_extractor" backend/src/` returns nothing

**Verification**: grep confirmation + full test suite pass

**Files touched**:
- DELETE: `backend/src/parsers/python_parser.py`
- DELETE: `backend/src/parsers/typescript_parser.py`
- DELETE: `backend/src/parsers/rust_parser.py`
- DELETE: `backend/src/parsers/ts_extractor/` (entire directory)

**Scope**: XS (<30 min)

**Dependencies**: T2.3

#### T2.5 — Parity validation

**Description**: Run `extract_entities()` on a known test repository with both old and new parsers. Compare entity counts, qualified names, call lists. Document any acceptable differences (tree-sitter may find more/fewer entities in edge cases).

**Acceptance criteria**:
- Entity count within ±10% of old parsers for Python/TS/Rust files
- All function/class names match
- Call extraction captures at least 80% of previous calls
- No crashes on the full repository

**Verification**: Comparison script or test.

**Scope**: S (0.5 day)

**Dependencies**: T2.4

---

### Phase 3: LadybugDB Storage Implementation (2-3 days)

Goal: Replace Neo4j storage layer with LadybugDB.

#### T3.1 — Implement `graph_db.py` with LadybugDB

**Description**: Rewrite `backend/src/storage/graph_db.py` to use LadybugDB:
- Replace `get_driver()` with `get_db()` → returns `lb.Database` singleton
- Replace `get_connection()` → returns `lb.Connection` (per-request or pooled)
- Add `initialize_schema()` — creates node/rel tables if not exists
- Port all 4 functions: `create_code_entity_node()`, `create_relationship()`, `get_neighbors()`, `get_module_relationships()`
- Port `health_check()` — trivially true for embedded (file exists + can open)
- Port `close_driver()` → `close_db()`
- Database path: `{settings.resolved_data_dir}/graph/code_graph.lbug`

**Key Cypher changes**:
- `MERGE` should work as-is (LadybugDB supports MERGE)
- Dynamic relationship type in `create_relationship()`: Neo4j used f-string `f"MERGE (a)-[:{rel_type}]->(b)"`. LadybugDB may need one query per rel table. **Solution**: dispatch to the correct table name since rel types are fixed (CALLS, IMPORTS, etc.)
- Parameter syntax: confirm `$param` vs named parameter binding

**Acceptance criteria**:
- All 4 CRUD functions work against LadybugDB
- `health_check()` returns True when DB file exists
- Schema auto-creates on first use
- Existing callers (`analyze.py`, `diagrams.py`, `graph_tools.py`, `wikis.py`) work without change

**Verification**: Unit tests for each function. Integration test with sample data.

**Files touched**:
- REWRITE: `backend/src/storage/graph_db.py`

**Scope**: M (1.5 days)

#### T3.2 — Port `graph_tools.py` Cypher queries

**Description**: Update all 6 LangChain tools in `v3_tools/graph_tools.py`:
- Replace `from src.storage.graph_db import get_driver` with LadybugDB connection
- Port each Cypher query (likely minimal changes — LadybugDB speaks Cypher)
- Handle `startNode(r)` in `get_entity_neighborhood` — if not supported, split into two directional queries
- Update error handling (LadybugDB exceptions differ from `neo4j.exceptions`)

**Acceptance criteria**:
- All 6 tools return correct results
- Graceful fallback to empty results on error (preserve existing behavior)
- No Neo4j imports remain

**Verification**: Unit tests with sample graph data.

**Files touched**:
- EDIT: `backend/src/wiki/v3_tools/graph_tools.py`

**Scope**: S (0.5 day)

**Dependencies**: T3.1

#### T3.3 — Port `wikis.py` entity relationships query

**Description**: Update the inline Cypher in `api/routes/wikis.py` (lines 211-233) to use LadybugDB connection.

**Acceptance criteria**:
- Entity detail endpoint returns correct CALLS/IMPORTS/INHERITS_FROM lists
- Error handling preserved (empty relationships on failure)

**Verification**: Manual API test or integration test.

**Files touched**:
- EDIT: `backend/src/api/routes/wikis.py`

**Scope**: XS (<1 hour)

**Dependencies**: T3.1

#### T3.4 — Port `diagrams.py` dependency graph query

**Description**: Update `_build_dependency_graph()` to use new `graph_db.get_module_relationships()`.

**Acceptance criteria**:
- Diagram data includes correct inter-module edges
- Graceful empty result on error (existing behavior)

**Verification**: Unit test or integration test.

**Files touched**:
- EDIT: `backend/src/wiki/page_builders/diagrams.py` (likely zero code changes if `graph_db.get_module_relationships()` signature unchanged)

**Scope**: XS (verify only — function signature stays the same)

**Dependencies**: T3.1

#### T3.5 — Update `analyze.py` graph write step

**Description**: Update `_write_neo4j()` → rename to `_write_graph()`. Update imports, ensure it calls new `graph_db` functions. Update step 4b logging from "Neo4j" to "graph".

**Acceptance criteria**:
- Entities + call edges written to LadybugDB
- Stats dict still returns `{nodes, edges, unresolved}`
- Logging reflects new technology name

**Verification**: Integration test: parse + write + query cycle.

**Files touched**:
- EDIT: `backend/src/jobs/analyze.py`

**Scope**: S (0.5 day)

**Dependencies**: T3.1

---

### Phase 4: Infrastructure + Configuration Cleanup (1 day)

Goal: Remove all Neo4j infrastructure and update configuration.

#### T4.1 — Remove Neo4j from docker-compose.yml

**Description**:
- Delete the `neo4j` service block (lines 19-33)
- Delete `neo4j_data` from the `volumes` section
- No other services depend on neo4j (confirmed: no `depends_on` references)

**Acceptance criteria**:
- `docker compose config` validates successfully
- `docker compose up` starts without neo4j
- Only postgres, qdrant, redis remain

**Verification**: `docker compose config --quiet` exits 0.

**Files touched**:
- EDIT: `docker-compose.yml`

**Scope**: XS

#### T4.2 — Remove Neo4j from health check

**Description**: Update `api/health.py`:
- Delete `_check_neo4j_sync()` function
- Remove `neo4j` from the `services` dict
- Add `graph_db` health check (LadybugDB — just check file exists + connection opens)

**Acceptance criteria**:
- `/health` endpoint no longer reports neo4j
- New `graph_db` check reports "healthy"/"unhealthy"
- Overall status logic unchanged

**Verification**: Hit `/health` endpoint, confirm response schema.

**Files touched**:
- EDIT: `backend/src/api/health.py`

**Scope**: XS

#### T4.3 — Remove Neo4j from config + env

**Description**:
- Remove `neo4j_uri`, `neo4j_user`, `neo4j_password` from `Settings` class in `config.py`
- Add `graph_db_path` setting (default: empty → resolved to `{data_dir}/graph/code_graph.lbug`)
- Update `backend/.env.example`: remove `NEO4J_*` vars, add `GRAPH_DB_PATH` (optional)
- Update `backend/.env` if it exists: remove `NEO4J_*` vars

**Acceptance criteria**:
- No `neo4j` references in config.py
- New graph DB path setting works with defaults

**Verification**: `python -c "from src.config import get_settings; s = get_settings(); print(s)"` — no neo4j fields.

**Files touched**:
- EDIT: `backend/src/config.py`
- EDIT: `backend/.env.example`
- EDIT: `backend/.env` (if exists)

**Scope**: XS

#### T4.4 — Update requirements.txt

**Description**:
- Remove: `neo4j==5.24.0`, `jedi==0.19.1`
- Add: `real_ladybug>=0.15.0`, `tree-sitter>=0.25.0`, `tree-sitter-python>=0.23.0`, `tree-sitter-typescript>=0.23.0`, `tree-sitter-rust>=0.23.0`, `tree-sitter-c-sharp>=0.23.0`, `tree-sitter-java>=0.23.0`

**Net dependency change**:
- Removed: 2 packages (neo4j, jedi)
- Added: 7 packages (real_ladybug + tree-sitter + 5 grammars)
- Eliminated: Node.js/npm runtime dependency for TypeScript parsing (ts_extractor)

**Acceptance criteria**:
- `pip install -r requirements.txt` succeeds
- No import errors for new packages
- `import real_ladybug` works
- `import tree_sitter` works
- All 5 grammar imports work

**Verification**: Fresh venv install + import check.

**Files touched**:
- EDIT: `backend/requirements.txt`

**Scope**: XS

#### T4.5 — Update reset-app-data guide

**Description**: Update `specs/001-code-wiki/reset-app-data.md` to reflect new graph storage. Replace any Neo4j reset instructions with LadybugDB file deletion.

**Acceptance criteria**:
- Guide reflects correct reset procedure
- No Neo4j references remain

**Files touched**:
- EDIT: `specs/001-code-wiki/reset-app-data.md`

**Scope**: XS

---

### Phase 5: Integration Testing + Cleanup (1-2 days)

#### T5.1 — End-to-end pipeline test

**Description**: Run full analysis pipeline on a real repository:
1. `extract_entities()` with tree-sitter parsers
2. Write to PostgreSQL
3. Write to LadybugDB graph
4. Run wiki generation pipeline
5. Query graph via API endpoints
6. Verify diagram data

**Acceptance criteria**:
- Full pipeline completes without errors
- Entity counts reasonable (non-zero, within expected range)
- Graph queries return data
- Diagrams contain edges

**Verification**: Full job run + API smoke test.

**Scope**: M (1 day)

**Dependencies**: All Phase 2, 3, 4 tasks

#### T5.2 — Dead code sweep

**Description**: Final grep for any remaining references to:
- `neo4j` (package import, string literal, comment)
- `python_parser`, `typescript_parser`, `rust_parser`
- `ts_extractor`
- `jedi`
- `GraphDatabase` (neo4j class)

Remove any orphaned references.

**Acceptance criteria**: Zero results from sweep grep.

**Verification**: `grep -ri "neo4j\|python_parser\|typescript_parser\|rust_parser\|ts_extractor\|import jedi\|GraphDatabase" backend/src/`

**Files touched**: Any remaining stragglers.

**Scope**: XS

#### T5.3 — Update documentation

**Description**: Update `CLAUDE.md`, `AGENTS.md`, and any specs docs that reference Neo4j or the parser stack.

**Acceptance criteria**: No stale references to removed technologies.

**Scope**: XS

---

## 3. Migration Impact Map

### Neo4j Removal Impact

| Component | Current dependency | Migration action | Risk |
|-----------|-------------------|-----------------|------|
| `storage/graph_db.py` | Neo4j driver, Cypher queries | Full rewrite to LadybugDB | Medium — Cypher dialect differences |
| `jobs/analyze.py` | `graph_db.create_*` calls | Update import, rename function | Low — function signatures unchanged |
| `wiki/v3_tools/graph_tools.py` | Raw Cypher via `get_driver().session()` | Port to LadybugDB connection | Medium — 6 complex queries |
| `wiki/page_builders/diagrams.py` | `graph_db.get_module_relationships()` | No change if signature preserved | None |
| `api/routes/wikis.py` | Inline Neo4j session + Cypher | Port to LadybugDB connection | Low — single query |
| `api/health.py` | Neo4j connectivity check | Replace with file/DB check | None |
| `config.py` | 3 Neo4j settings | Remove, add graph_db_path | None |
| `docker-compose.yml` | neo4j service + volume | Delete service block | None |
| `.env.example` | NEO4J_* vars | Remove, add GRAPH_DB_PATH | None |

### Parser Replacement Impact

| Component | Current dependency | Migration action | Risk |
|-----------|-------------------|-----------------|------|
| `parsers/python_parser.py` | `ast` stdlib + `jedi` | Delete (replaced by TreeSitterParser) | None |
| `parsers/typescript_parser.py` | `subprocess` → Node.js | Delete (replaced by TreeSitterParser) | None |
| `parsers/rust_parser.py` | `re` (regex) | Delete (replaced by TreeSitterParser) | None |
| `parsers/ts_extractor/` | Node.js + `typescript` npm | Delete entire directory | None |
| `parsers/__init__.py` | Imports 3 parser classes | Rewrite registry for TreeSitterParser | Low |
| `parsers/base.py` | ABC + dataclasses | **No change** | None |
| `parsers/extractor.py` | `get_parser()` + `supported_extensions()` | **No change** (interface unchanged) | None |
| `agents/primitives/tools.py` | `get_parser()` + `parse_file()` | **No change** | None |
| `wiki/compressor.py` | `ParsedEntity` type | **No change** | None |
| `wiki/interestingness.py` | `ParsedEntity` type | **No change** | None |
| `wiki/wiki_pipeline.py` | `ParsedEntity` type | **No change** | None |
| `wiki/pipeline_types.py` | `ParsedEntity` type | **No change** | None |
| `wiki/page_builders/special_pages.py` | `ParsedEntity` type | **No change** | None |
| `wiki/agents/reference_builder.py` | `ParsedEntity` type | **No change** | None |
| `wiki/agents/state.py` | `ParsedEntity` type | **No change** | None |
| `dossier/rag_index.py` | `ParsedEntity` type | **No change** | None |

**Key insight**: Because `ParsedEntity` is the shared contract and it stays unchanged, all downstream consumers (12+ files) require zero modification.

---

## 4. Data Model Changes

### Graph Schema (NEW — LadybugDB requires explicit)

```cypher
-- Node table
CREATE NODE TABLE IF NOT EXISTS CodeEntity(
    id STRING PRIMARY KEY,
    qualified_name STRING,
    entity_type STRING,
    name STRING,
    file_path STRING,
    module_id STRING
);

-- Relationship tables (one per type — LadybugDB requirement)
CREATE REL TABLE IF NOT EXISTS CALLS(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE IF NOT EXISTS IMPORTS(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE IF NOT EXISTS INHERITS_FROM(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE IF NOT EXISTS DEFINES(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE IF NOT EXISTS USES(FROM CodeEntity TO CodeEntity);
CREATE REL TABLE IF NOT EXISTS OVERRIDES(FROM CodeEntity TO CodeEntity);
```

### PostgreSQL Schema

**No changes**. The `code_entities` and `modules` tables in PostgreSQL remain identical. The graph DB is a secondary index for relationship queries only.

### Query Migration Map

| # | Purpose | Neo4j Cypher (current) | LadybugDB Cypher (target) | Changes needed |
|---|---------|----------------------|--------------------------|----------------|
| 1 | Upsert node | `MERGE (e:CodeEntity {id: $id}) SET ...` | Same | Verify MERGE support with pre-defined schema |
| 2 | Create edge | `MATCH (a) MATCH (b) MERGE (a)-[:CALLS]->(b)` | Same (per rel table) | Must use correct rel table name |
| 3 | Get neighbors | `MATCH (a {id: $id})-[r]-(b) RETURN b` | `MATCH (a:CodeEntity {id: $id})-[r]-(b:CodeEntity) RETURN b` | Add explicit label (LadybugDB may require) |
| 4 | Module rels | `MATCH (a)-[r]->(b) WHERE ... RETURN type(r), count(r)` | Same | Verify `type(r)` works |
| 5-10 | Graph tools | Various MATCH+WHERE+RETURN | Same with minor label additions | Verify `CONTAINS`, `startNode(r)` |
| 11 | Entity rels | `OPTIONAL MATCH` chain | Same | Verify `collect(DISTINCT ...)` |

---

## 5. Dependency / Package Changes

### Python (requirements.txt)

| Action | Package | Version | Reason |
|--------|---------|---------|--------|
| REMOVE | `neo4j` | 5.24.0 | Replaced by LadybugDB |
| REMOVE | `jedi` | 0.19.1 | Only used by PythonParser (deleted) |
| ADD | `real_ladybug` | >=0.15.0 | Embedded graph DB |
| ADD | `tree-sitter` | >=0.25.0 | Core parser |
| ADD | `tree-sitter-python` | >=0.23.0 | Python grammar |
| ADD | `tree-sitter-typescript` | >=0.23.0 | TS/JS grammar |
| ADD | `tree-sitter-rust` | >=0.23.0 | Rust grammar |
| ADD | `tree-sitter-c-sharp` | >=0.23.0 | C# grammar |
| ADD | `tree-sitter-java` | >=0.23.0 | Java grammar |

### Node.js (eliminated)

| Action | Package | Reason |
|--------|---------|--------|
| DELETE | `backend/src/parsers/ts_extractor/package.json` | No longer needed |
| DELETE | `backend/src/parsers/ts_extractor/node_modules/` | No longer needed |
| KEEP | Root `package.json` | Playwright tests only — unrelated |

### Docker (docker-compose.yml)

| Action | Service | Reason |
|--------|---------|--------|
| REMOVE | `neo4j` service | Replaced by embedded LadybugDB |
| REMOVE | `neo4j_data` volume | No longer needed |
| KEEP | `postgres`, `qdrant`, `redis` | Unchanged |

### Environment Variables

| Action | Variable | Reason |
|--------|----------|--------|
| REMOVE | `NEO4J_URI` | No longer needed |
| REMOVE | `NEO4J_USER` | No longer needed |
| REMOVE | `NEO4J_PASSWORD` | No longer needed |
| ADD (optional) | `GRAPH_DB_PATH` | Override graph DB file location (default: `{data_dir}/graph/code_graph.lbug`) |

### Health Checks

| Check | Current | After migration |
|-------|---------|----------------|
| PostgreSQL | `pg_isready` via psycopg2 | Unchanged |
| Neo4j | HTTP GET to port 7474 | **Removed** |
| Graph DB | N/A | **New**: LadybugDB file exists + connection opens |
| Qdrant | HTTP GET /readyz | Unchanged |
| Redis | `redis-cli ping` | Unchanged |

---

## 6. Test Strategy

### Unit Tests (Phase 2-3)

| Test area | What to test | How |
|-----------|-------------|-----|
| Tree-sitter Python extraction | Functions, classes, imports, calls from known files | Assert entity names/types/line numbers |
| Tree-sitter TypeScript extraction | Functions, interfaces, imports, calls | Same approach |
| Tree-sitter Rust extraction | fn, struct, trait, impl, use | Same approach |
| Tree-sitter C# extraction | Methods, classes, interfaces, using | Same approach (new language) |
| Tree-sitter Java extraction | Methods, classes, interfaces, imports | Same approach (new language) |
| LadybugDB CRUD | Node create/read, edge create, neighbors query | In-memory DB for speed |
| LadybugDB schema init | Tables created idempotently | Assert no error on double-init |
| Graph tools queries | All 6 tools with sample data | Pre-populated in-memory DB |
| Parser registry | `get_parser()` for all extensions | Assert correct types returned |

### Integration Tests (Phase 5)

| Test | What | How |
|------|------|-----|
| Full pipeline | Clone → parse → persist → graph write → wiki gen | Run against small test repo |
| API smoke test | `/health`, `/wikis/{id}/entities/{qname}` | HTTP calls + assertions |
| Diagram generation | `build_diagrams()` with real wiki | Assert non-empty nodes/edges |

### Rollout Checkpoints (no rollback code)

| Checkpoint | Gate | Pass criteria |
|------------|------|---------------|
| CP-1: After Phase 1 | Spike review | All queries work, extraction parity proven |
| CP-2: After Phase 2 | Parser swap | `extract_entities()` produces comparable output to old parsers |
| CP-3: After Phase 3 | Graph swap | All graph queries work against LadybugDB |
| CP-4: After Phase 4 | Clean infra | `docker compose up` works, health checks pass |
| CP-5: After Phase 5 | Full E2E | Complete pipeline succeeds on real repository |

---

## 7. Task Dependency Graph

```
Phase 1 (Spike)
  T1.1 (LadybugDB spike) ──┐
  T1.2 (Tree-sitter spike) ─┼── T1.3 (Spike review) ── CP-1
                             │
Phase 2 (Parsers)            │
  T2.1 (Query files) ───── T2.2 (TreeSitterParser) ── T2.3 (Registry) ── T2.4 (Delete old) ── T2.5 (Parity) ── CP-2
                             │
Phase 3 (Graph DB)           │  (can start in parallel with Phase 2 after CP-1)
  T3.1 (graph_db.py) ──┬── T3.2 (graph_tools.py)
                        ├── T3.3 (wikis.py)
                        ├── T3.4 (diagrams.py)
                        └── T3.5 (analyze.py) ── CP-3

Phase 4 (Infra)         (after CP-2 + CP-3)
  T4.1 (docker-compose) ─┐
  T4.2 (health.py)       ├── CP-4
  T4.3 (config + env)    │
  T4.4 (requirements.txt)│
  T4.5 (reset guide)    ─┘

Phase 5 (Validation)     (after CP-4)
  T5.1 (E2E test) ── T5.2 (Dead code sweep) ── T5.3 (Docs update) ── CP-5
```

**Parallelism**: Phase 2 (parsers) and Phase 3 (graph DB) can proceed in parallel after Phase 1 passes. They are independent workstreams — parsers output `ParsedEntity`, graph DB consumes it; the interface (`ParsedEntity`) doesn't change.

---

## 8. Risks + Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| R1 | LadybugDB Cypher subset lacks `MERGE` upsert semantics | Low | High | Phase 1 spike validates this first. Fallback: use `CREATE ... ON CONFLICT` pattern or delete+create. |
| R2 | LadybugDB lacks `startNode(r)` function | Medium | Low | Only used in `get_entity_neighborhood`. Rewrite as two directional queries (outgoing + incoming). |
| R3 | LadybugDB lacks `type(r)` across heterogeneous relationships | Medium | Medium | Used in `get_module_relationships` and `get_graph_stats`. May need separate queries per rel table. Validate in spike. |
| R4 | Tree-sitter call extraction less accurate than Jedi/TypeScript Compiler API | Medium | Medium | Tree-sitter gives AST but no semantic resolution. Current Rust parser is already regex-based (worse). Accept that call extraction is syntactic, not semantic. Quality should be comparable or better than current Rust parser, and acceptable for Python/TS. |
| R5 | `real_ladybug` package name collision or instability | Low | High | Package is actively maintained (v0.15.3, April 2026 release). Pin to known good version. |
| R6 | Tree-sitter grammar packages have breaking API changes | Low | Medium | Pin all grammar versions. Use pre-built wheels (available for all 5 languages). |
| R7 | LadybugDB file corruption on crash | Low | Medium | LadybugDB uses WAL for durability. Graph is reconstructible from ParsedEntity data (re-run `_write_graph`). |
| R8 | Performance regression with LadybugDB for large repositories | Low | Medium | LadybugDB is designed for analytical workloads on large datasets. Should be faster than Neo4j network round-trips. Benchmark in spike. |
| R9 | `CREATE NODE TABLE IF NOT EXISTS` not supported | Low | Medium | Check in spike. If not supported, catch exception on duplicate table creation. |

---

## 9. Open Questions Requiring User Decision

| # | Question | Context | Default recommendation |
|---|----------|---------|----------------------|
| OQ-1 | **Graph DB path location**: Should the LadybugDB file live under `{data_dir}/graph/` or `{data_dir}/` directly? | Current `data_dir` resolves to `{project_root}/cache`. Suggest subdirectory for cleanliness. | `{data_dir}/graph/code_graph.lbug` |
| OQ-2 | **Per-repository graph isolation**: Should each analyzed repository get its own LadybugDB file, or one shared graph with `wiki_id` tagging? | Current Neo4j is a single shared instance. Single file is simpler. Separate files would allow independent cleanup. | Single file (matches current pattern) unless repo isolation is needed |
| OQ-3 | **C# and Java: immediate or deferred?** | Adding grammars is trivial, but writing quality `.scm` query files + testing takes effort. Should we ship C#/Java in the same PR or follow-up? | Include in same PR — incremental cost is low if Tree-sitter infrastructure is already built |
| OQ-4 | **Call extraction depth**: Tree-sitter gives syntactic calls only (no type resolution). Current Python parser uses Jedi for semantic resolution. Accept the quality regression for Python? | Jedi adds significant complexity and a heavy dependency. Most other languages were already syntactic-only. | Accept syntactic-only. Jedi's import resolution benefit is marginal for the call graph use case. |
| OQ-5 | **LadybugDB version pinning**: Pin to exact `0.15.3` or `>=0.15.0`? | LadybugDB is young and may have breaking changes. | Pin `>=0.15.0,<0.16.0` for minor version stability |
| OQ-6 | **Node.js removal scope**: The `ts_extractor/node_modules/` may be gitignored. Should we also remove any npm-related CI steps or dev scripts? | No CI config references ts_extractor currently. Just delete the directory. | Delete directory, no other action needed |

---

## 10. Estimated Total Effort

| Phase | Effort | Calendar days (1 engineer) |
|-------|--------|---------------------------|
| Phase 1: Spike | 2 days | 2-3 days |
| Phase 2: Tree-sitter parsers | 3-4 days | 3-4 days |
| Phase 3: LadybugDB storage | 2-3 days | 2-3 days (parallel with Phase 2) |
| Phase 4: Infrastructure cleanup | 1 day | 1 day |
| Phase 5: Integration + cleanup | 1-2 days | 1-2 days |
| **Total** | **9-12 days** | **7-10 calendar days** (with Phase 2/3 parallelism) |

---

## 11. Summary of Files Touched

### New files (7)
- `backend/src/parsers/tree_sitter_parser.py`
- `backend/src/parsers/queries/python.scm`
- `backend/src/parsers/queries/typescript.scm`
- `backend/src/parsers/queries/rust.scm`
- `backend/src/parsers/queries/csharp.scm`
- `backend/src/parsers/queries/java.scm`

### Rewritten files (2)
- `backend/src/storage/graph_db.py` (full rewrite)
- `backend/src/parsers/__init__.py` (near-full rewrite)

### Edited files (8)
- `backend/src/jobs/analyze.py`
- `backend/src/wiki/v3_tools/graph_tools.py`
- `backend/src/api/routes/wikis.py`
- `backend/src/api/health.py`
- `backend/src/config.py`
- `backend/.env.example`
- `backend/requirements.txt`
- `docker-compose.yml`

### Deleted files (4 + directory)
- `backend/src/parsers/python_parser.py`
- `backend/src/parsers/typescript_parser.py`
- `backend/src/parsers/rust_parser.py`
- `backend/src/parsers/ts_extractor/` (entire directory)

### Unchanged files (12+)
- `backend/src/parsers/base.py`
- `backend/src/parsers/extractor.py`
- `backend/src/agents/primitives/tools.py`
- `backend/src/wiki/compressor.py`
- `backend/src/wiki/interestingness.py`
- `backend/src/wiki/wiki_pipeline.py`
- `backend/src/wiki/pipeline_types.py`
- `backend/src/wiki/page_builders/special_pages.py`
- `backend/src/wiki/agents/reference_builder.py`
- `backend/src/wiki/agents/state.py`
- `backend/src/dossier/rag_index.py`
- All other files
