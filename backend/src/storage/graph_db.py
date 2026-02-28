"""Neo4j connection manager with pooling, health check, and code graph CRUD."""

import logging
from typing import Any, Optional

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable

from src.config import get_settings

logger = logging.getLogger(__name__)

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=50,
        )
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def health_check() -> bool:
    try:
        get_driver().verify_connectivity()
        return True
    except ServiceUnavailable:
        logger.warning("Neo4j health check failed: service unavailable")
        return False


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------


def create_code_entity_node(
    entity_id: str,
    qualified_name: str,
    entity_type: str,
    name: str,
    file_path: Optional[str] = None,
    module_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create or merge a CodeEntity node in Neo4j."""
    logger.debug("Creating node: %s (%s)", entity_id, entity_type)
    with get_driver().session() as session:
        result = session.run(
            """
            MERGE (e:CodeEntity {id: $id})
            SET e.qualified_name = $qualified_name,
                e.entity_type = $entity_type,
                e.name = $name,
                e.file_path = $file_path,
                e.module_id = $module_id
            RETURN e
            """,
            id=entity_id,
            qualified_name=qualified_name,
            entity_type=entity_type,
            name=name,
            file_path=file_path,
            module_id=module_id,
        )
        record = result.single()
        return dict(record["e"]) if record else {}


def create_relationship(
    from_id: str,
    to_id: str,
    rel_type: str,
) -> None:
    """Create a directed relationship between two CodeEntity nodes.

    Supported rel_type values: CALLS, IMPORTS, INHERITS_FROM, DEFINES, USES, OVERRIDES
    """
    allowed = {"CALLS", "IMPORTS", "INHERITS_FROM", "DEFINES", "USES", "OVERRIDES"}
    if rel_type not in allowed:
        raise ValueError(f"Unknown relationship type: {rel_type!r}")

    logger.debug("Creating relationship: %s -[%s]-> %s", from_id, rel_type, to_id)
    with get_driver().session() as session:
        # Verify both nodes exist before creating relationship
        result = session.run(
            f"""
            MATCH (a:CodeEntity {{id: $from_id}})
            MATCH (b:CodeEntity {{id: $to_id}})
            MERGE (a)-[:{rel_type}]->(b)
            RETURN count(*) AS cnt
            """,
            from_id=from_id,
            to_id=to_id,
        )
        record = result.single()
        if record and record["cnt"] == 0:
            logger.warning("Relationship MATCH failed: %s -[%s]-> %s (target node not found)", from_id, rel_type, to_id)


def get_neighbors(
    entity_id: str,
    rel_type: Optional[str] = None,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """Return neighboring CodeEntity nodes.

    Args:
        entity_id: ID of the source node.
        rel_type: Optional relationship type filter.
        direction: 'outgoing', 'incoming', or 'both'.
    """
    rel_clause = f"[:{rel_type}]" if rel_type else ""
    if direction == "outgoing":
        pattern = f"-{rel_clause}->"
    elif direction == "incoming":
        pattern = f"<-{rel_clause}-"
    else:
        pattern = f"-{rel_clause}-"

    with get_driver().session() as session:
        result = session.run(
            f"""
            MATCH (a:CodeEntity {{id: $id}}){pattern}(b:CodeEntity)
            RETURN b
            """,
            id=entity_id,
        )
        return [dict(record["b"]) for record in result]


def get_module_relationships(
    module_ids: list[str],
) -> list[dict[str, Any]]:
    """Return inter-module relationships for diagram generation."""
    with get_driver().session() as session:
        result = session.run(
            """
            MATCH (a:CodeEntity)-[r]->(b:CodeEntity)
            WHERE a.module_id IN $module_ids AND b.module_id IN $module_ids
              AND a.module_id <> b.module_id
            RETURN DISTINCT a.module_id AS from_module, b.module_id AS to_module,
                   type(r) AS rel_type, count(r) AS weight
            """,
            module_ids=module_ids,
        )
        return [dict(record) for record in result]
