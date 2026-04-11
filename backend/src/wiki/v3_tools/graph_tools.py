"""Code graph query tools for V3 deep content agents.

Exposes graph call/import/inheritance queries as bounded, granular tools.
Falls back gracefully if graph storage is unavailable.
"""

import json
import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MAX_RESULTS = 30


def make_graph_tools() -> list:
    """Create graph query tools.

    Returns:
        List of LangChain tool functions. Safe to call even if graph storage is down.
    """

    def _query(cypher: str, params: dict) -> list[dict]:
        """Run a Cypher query, returning [] on failure."""
        try:
            from src.storage import graph_db

            return graph_db.query_records(cypher, params)
        except Exception as exc:
            logger.debug("Graph query failed: %s", exc)
            return []

    @tool
    def get_callers(entity_name: str) -> str:
        """Find what calls a given function/class/method.

        Returns entities that have a CALLS relationship to the target.

        Args:
            entity_name: Qualified name or short name (e.g. "analyze_repository",
                         "src.jobs.analyze.analyze_repository").
        """
        rows = _query(
            """
            MATCH (caller:CodeEntity)-[:CALLS]->(target:CodeEntity)
            WHERE target.qualified_name CONTAINS $name OR target.name = $name
            RETURN DISTINCT caller.name AS name, caller.qualified_name AS qualified_name,
                   caller.entity_type AS type, caller.file_path AS file
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        if not rows:
            return json.dumps({"entity": entity_name, "callers": [], "note": "No callers found (or graph unavailable)"})
        return json.dumps({"entity": entity_name, "callers": rows}, indent=2)

    @tool
    def get_callees(entity_name: str) -> str:
        """Find what a given function/class/method calls.

        Returns entities that the source has a CALLS relationship to.

        Args:
            entity_name: Qualified name or short name.
        """
        rows = _query(
            """
            MATCH (source:CodeEntity)-[:CALLS]->(callee:CodeEntity)
            WHERE source.qualified_name CONTAINS $name OR source.name = $name
            RETURN DISTINCT callee.name AS name, callee.qualified_name AS qualified_name,
                   callee.entity_type AS type, callee.file_path AS file
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        if not rows:
            return json.dumps({"entity": entity_name, "callees": [], "note": "No callees found (or graph unavailable)"})
        return json.dumps({"entity": entity_name, "callees": rows}, indent=2)

    @tool
    def get_imports(entity_name: str) -> str:
        """Find what a module/file imports.

        Args:
            entity_name: Module or file qualified name.
        """
        rows = _query(
            """
            MATCH (source:CodeEntity)-[:IMPORTS]->(imported:CodeEntity)
            WHERE source.qualified_name CONTAINS $name OR source.name = $name
            RETURN DISTINCT imported.name AS name, imported.qualified_name AS qualified_name,
                   imported.entity_type AS type, imported.file_path AS file
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        if not rows:
            return json.dumps({"entity": entity_name, "imports": [], "note": "No imports found (or graph unavailable)"})
        return json.dumps({"entity": entity_name, "imports": rows}, indent=2)

    @tool
    def get_inheritance(entity_name: str) -> str:
        """Find class inheritance — parents and children.

        Args:
            entity_name: Class name to look up.
        """
        parents = _query(
            """
            MATCH (child:CodeEntity)-[:INHERITS_FROM]->(parent:CodeEntity)
            WHERE child.qualified_name CONTAINS $name OR child.name = $name
            RETURN DISTINCT parent.name AS name, parent.qualified_name AS qualified_name,
                   parent.file_path AS file
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        children = _query(
            """
            MATCH (child:CodeEntity)-[:INHERITS_FROM]->(parent:CodeEntity)
            WHERE parent.qualified_name CONTAINS $name OR parent.name = $name
            RETURN DISTINCT child.name AS name, child.qualified_name AS qualified_name,
                   child.file_path AS file
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        return json.dumps({
            "entity": entity_name,
            "parents": parents,
            "children": children,
        }, indent=2)

    @tool
    def get_entity_neighborhood(entity_name: str) -> str:
        """Get all relationships around an entity (calls, imports, inheritance).

        Provides a complete picture of how one entity connects to others.

        Args:
            entity_name: Qualified name or short name.
        """
        outgoing = _query(
            """
            MATCH (a:CodeEntity)-[r]->(b:CodeEntity)
            WHERE a.qualified_name CONTAINS $name OR a.name = $name
            RETURN a.name AS source, type(r) AS relationship, '→' AS direction,
                   b.name AS target, b.qualified_name AS target_qualified, b.entity_type AS target_type
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        incoming = _query(
            """
            MATCH (a:CodeEntity)<-[r]-(b:CodeEntity)
            WHERE a.qualified_name CONTAINS $name OR a.name = $name
            RETURN a.name AS source, type(r) AS relationship, '←' AS direction,
                   b.name AS target, b.qualified_name AS target_qualified, b.entity_type AS target_type
            LIMIT $limit
            """,
            {"name": entity_name.strip(), "limit": MAX_RESULTS},
        )
        rows = outgoing + incoming
        if not rows:
            return json.dumps({"entity": entity_name, "relationships": [], "note": "No relationships found (or graph unavailable)"})
        return json.dumps({"entity": entity_name, "relationships": rows}, indent=2)

    @tool
    def get_graph_stats() -> str:
        """Get summary statistics of the code graph.

        Returns node count, edge count, and breakdown by relationship type.
        Use this first to understand what graph data is available.
        """
        nodes = _query("MATCH (n:CodeEntity) RETURN count(n) AS count", {})
        edges = _query(
            """
            MATCH ()-[r]->()
            RETURN type(r) AS rel_type, count(r) AS count
            ORDER BY count DESC
            """,
            {},
        )
        node_count = nodes[0]["count"] if nodes else 0
        if node_count == 0:
            return json.dumps({"status": "empty", "note": "No graph data available (graph storage may be empty or unavailable)"})
        return json.dumps({
            "nodes": node_count,
            "edges_by_type": {row["rel_type"]: row["count"] for row in edges},
        }, indent=2)

    return [get_callers, get_callees, get_imports, get_inheritance,
            get_entity_neighborhood, get_graph_stats]
