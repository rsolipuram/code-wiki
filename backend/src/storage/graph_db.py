"""LadybugDB connection manager and code graph CRUD."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

from src.config import get_settings

logger = logging.getLogger(__name__)

_db: Optional[Any] = None
_conn: Optional[Any] = None
_schema_initialized = False
_lbug_module: Optional[Any] = None
_conn_lock = threading.Lock()

_REL_TYPES = {"CALLS", "IMPORTS", "INHERITS_FROM", "DEFINES", "USES", "OVERRIDES"}

_SCHEMA_STATEMENTS = [
    """
    CREATE NODE TABLE IF NOT EXISTS CodeEntity(
        id STRING PRIMARY KEY,
        qualified_name STRING,
        entity_type STRING,
        name STRING,
        file_path STRING,
        module_id STRING
    );
    """,
    "CREATE REL TABLE IF NOT EXISTS CALLS(FROM CodeEntity TO CodeEntity);",
    "CREATE REL TABLE IF NOT EXISTS IMPORTS(FROM CodeEntity TO CodeEntity);",
    "CREATE REL TABLE IF NOT EXISTS INHERITS_FROM(FROM CodeEntity TO CodeEntity);",
    "CREATE REL TABLE IF NOT EXISTS DEFINES(FROM CodeEntity TO CodeEntity);",
    "CREATE REL TABLE IF NOT EXISTS USES(FROM CodeEntity TO CodeEntity);",
    "CREATE REL TABLE IF NOT EXISTS OVERRIDES(FROM CodeEntity TO CodeEntity);",
]


def _get_lbug() -> Any:
    global _lbug_module
    if _lbug_module is not None:
        return _lbug_module
    try:
        import real_ladybug as lbug_module
    except ImportError:
        import lbug as lbug_module  # type: ignore[import-not-found]
    _lbug_module = lbug_module
    return lbug_module


def _result_to_records(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if hasattr(result, "rows_as_dict"):
        return [row for row in result.rows_as_dict()]
    if hasattr(result, "has_next") and hasattr(result, "get_next"):
        column_names: list[str] = []
        if hasattr(result, "column_names"):
            try:
                column_names = list(result.column_names)
            except Exception:
                column_names = []
        elif hasattr(result, "get_column_names"):
            try:
                column_names = list(result.get_column_names())
            except Exception:
                column_names = []
        rows: list[Any] = []
        while result.has_next():
            rows.append(result.get_next())
        if rows and isinstance(rows[0], dict):
            return rows  # type: ignore[return-value]
        if rows and isinstance(rows[0], (list, tuple)) and column_names and len(column_names) == len(rows[0]):
            return [dict(zip(column_names, row)) for row in rows]
        if rows:
            logger.warning("Unsupported LadybugDB row shape: %s", type(rows[0]).__name__)
        return []
    return []


def _ensure_schema(conn: Any) -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    for stmt in _SCHEMA_STATEMENTS:
        conn.execute(stmt)
    _schema_initialized = True


def get_connection() -> Any:
    global _db, _conn
    with _conn_lock:
        if _conn is None:
            lbug = _get_lbug()
            settings = get_settings()
            db_path = Path(settings.resolved_graph_db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _db = lbug.Database(str(db_path))
            _conn = lbug.Connection(_db)
            _ensure_schema(_conn)
    return _conn


def close_connection() -> None:
    global _db, _conn, _schema_initialized
    with _conn_lock:
        if _conn is not None and hasattr(_conn, "close"):
            try:
                _conn.close()
            except Exception as exc:
                logger.debug("Error closing graph connection: %s", exc)
        if _db is not None and hasattr(_db, "close"):
            try:
                _db.close()
            except Exception as exc:
                logger.debug("Error closing graph database: %s", exc)
        _conn = None
        _db = None
        _schema_initialized = False


def execute(query: str, parameters: Optional[dict[str, Any]] = None) -> Any:
    conn = get_connection()
    if parameters:
        return conn.execute(query, parameters=parameters)
    return conn.execute(query)


def query_records(query: str, parameters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    result = execute(query, parameters)
    return _result_to_records(result)


def health_check() -> bool:
    try:
        rows = query_records("RETURN 1 AS ok")
        return bool(rows and rows[0].get("ok") == 1)
    except Exception as exc:
        logger.warning("LadybugDB health check failed: %s", exc)
        return False


def create_code_entity_node(
    entity_id: str,
    qualified_name: str,
    entity_type: str,
    name: str,
    file_path: Optional[str] = None,
    module_id: Optional[str] = None,
) -> dict[str, Any]:
    rows = query_records(
        """
        MERGE (e:CodeEntity {id: $id})
        SET e.qualified_name = $qualified_name,
            e.entity_type = $entity_type,
            e.name = $name,
            e.file_path = $file_path,
            e.module_id = $module_id
        RETURN e.id AS id, e.qualified_name AS qualified_name, e.entity_type AS entity_type,
               e.name AS name, e.file_path AS file_path, e.module_id AS module_id
        """,
        {
            "id": entity_id,
            "qualified_name": qualified_name,
            "entity_type": entity_type,
            "name": name,
            "file_path": file_path,
            "module_id": module_id,
        },
    )
    return rows[0] if rows else {}


def create_relationship(from_id: str, to_id: str, rel_type: str) -> None:
    if rel_type not in _REL_TYPES:
        raise ValueError(f"Unknown relationship type: {rel_type!r}")
    execute(
        f"""
        MATCH (a:CodeEntity {{id: $from_id}})
        MATCH (b:CodeEntity {{id: $to_id}})
        MERGE (a)-[:{rel_type}]->(b)
        """,
        {"from_id": from_id, "to_id": to_id},
    )


def get_neighbors(entity_id: str, rel_type: Optional[str] = None, direction: str = "both") -> list[dict[str, Any]]:
    if rel_type is not None and rel_type not in _REL_TYPES:
        raise ValueError(f"Unknown relationship type: {rel_type!r}")

    rel_clause = f":{rel_type}" if rel_type else ""
    if direction == "outgoing":
        pattern = f"-[r{rel_clause}]->"
    elif direction == "incoming":
        pattern = f"<-[r{rel_clause}]-"
    else:
        pattern = f"-[r{rel_clause}]-"

    return query_records(
        f"""
        MATCH (a:CodeEntity {{id: $id}}){pattern}(b:CodeEntity)
        RETURN b.id AS id, b.qualified_name AS qualified_name, b.entity_type AS entity_type,
               b.name AS name, b.file_path AS file_path, b.module_id AS module_id
        """,
        {"id": entity_id},
    )


def get_module_relationships(module_ids: list[str]) -> list[dict[str, Any]]:
    return query_records(
        """
        MATCH (a:CodeEntity)-[r]->(b:CodeEntity)
        WHERE a.module_id IN $module_ids AND b.module_id IN $module_ids
          AND a.module_id <> b.module_id
        RETURN a.module_id AS from_module, b.module_id AS to_module,
               type(r) AS rel_type, count(*) AS weight
        ORDER BY weight DESC
        """,
        {"module_ids": module_ids},
    )


def get_entity_relationships(entity_qualified_name: str) -> dict[str, list[str]]:
    rows = query_records(
        """
        MATCH (n:CodeEntity {qualified_name: $qname})
        OPTIONAL MATCH (n)-[:CALLS]->(callee:CodeEntity)
        OPTIONAL MATCH (n)-[:IMPORTS]->(imported:CodeEntity)
        OPTIONAL MATCH (n)-[:INHERITS_FROM]->(parent:CodeEntity)
        RETURN
            collect(DISTINCT callee.qualified_name) AS calls,
            collect(DISTINCT imported.qualified_name) AS imports,
            collect(DISTINCT parent.qualified_name) AS inherits_from
        """,
        {"qname": entity_qualified_name},
    )
    if not rows:
        return {"calls": [], "imports": [], "inherits_from": []}
    row = rows[0]
    return {
        "calls": [x for x in row.get("calls", []) if x],
        "imports": [x for x in row.get("imports", []) if x],
        "inherits_from": [x for x in row.get("inherits_from", []) if x],
    }


def clear_graph() -> None:
    execute("MATCH (a:CodeEntity)-[r]->(b:CodeEntity) DELETE r")
    execute("MATCH (n:CodeEntity) DELETE n")
