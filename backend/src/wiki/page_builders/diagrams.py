"""Diagram data generator — T098.

Queries graph storage for module relationships, dependency graphs, and call chains,
outputting structured data for frontend rendering via the diagrams endpoint.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from src.models.code_entity import CodeEntity, Module
from src.models.wiki import Wiki
from src.storage import graph_db

logger = logging.getLogger(__name__)

# Node colours for consistent visual identity across diagram types
_MODULE_COLORS = ['purple', 'cyan', 'pink', 'green', 'amber']


def build_diagrams(session: Session, wiki: Wiki) -> dict[str, Any]:
    """Build all diagram data for a repository wiki.

    Returns:
        Dict with keys: architecture, dependency_graph, module_relationships.
        Each value contains nodes (list) and edges (list).
    """
    modules = session.query(Module).filter_by(wiki_id=wiki.id).all()
    module_ids = [m.id for m in modules]

    architecture = _build_architecture_diagram(session, wiki, modules)
    dependency_graph = _build_dependency_graph(session, wiki, modules)
    module_relationships = _build_module_relationships(modules, module_ids)

    return {
        "architecture": architecture,
        "dependency_graph": dependency_graph,
        "module_relationships": module_relationships,
    }


def _build_architecture_diagram(
    session: Session, wiki: Wiki, modules: list[Module]
) -> dict[str, Any]:
    """Architecture overview — groups modules into logical tiers.

    Nodes are coloured by tier (frontend, api, services, data).
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for i, module in enumerate(modules[:20]):  # cap at 20 for readability
        color = _MODULE_COLORS[i % len(_MODULE_COLORS)]
        icon = _module_icon(module.name)
        tier = _classify_tier(module.name, module.file_paths or [])

        nodes.append({
            "id": module.id,
            "label": module.name,
            "sublabel": (module.file_paths or [''])[0],
            "color": color,
            "icon": icon,
            "tier": tier,
            "file_count": module.file_count,
            "slug": module.slug,
        })

    # Add edges based on module dependency_module_ids (PostgreSQL-stored)
    node_ids = {n["id"] for n in nodes}
    for module in modules:
        for dep_id in (module.dependency_module_ids or []):
            if dep_id in node_ids and dep_id != module.id:
                edges.append({
                    "from": module.id,
                    "to": dep_id,
                    "label": "depends on",
                })

    return {"nodes": nodes, "edges": edges}


def _build_dependency_graph(
    session: Session, wiki: Wiki, modules: list[Module]
) -> dict[str, Any]:
    """Dependency graph — circular bubble nodes from graph inter-module calls."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    module_ids = [m.id for m in modules]
    id_to_module = {m.id: m for m in modules}

    # Query graph storage for inter-module relationships
    graph_edges: list[dict[str, Any]] = []
    try:
        graph_edges = graph_db.get_module_relationships(module_ids)
    except Exception as exc:
        logger.warning("Graph module relationship query failed: %s", exc)

    # Build node set from modules with call counts
    call_counts: dict[str, int] = {}
    for edge in graph_edges:
        from_id = edge.get("from_module", "")
        call_counts[from_id] = call_counts.get(from_id, 0) + int(edge.get("weight", 1))

    for i, module in enumerate(modules[:16]):
        color = _MODULE_COLORS[i % len(_MODULE_COLORS)]
        nodes.append({
            "id": module.id,
            "label": module.name,
            "color": color,
            "call_count": call_counts.get(module.id, 0),
            "slug": module.slug,
        })

    # Edges from graph storage
    node_ids = {n["id"] for n in nodes}
    for edge in graph_edges:
        from_id = edge.get("from_module", "")
        to_id = edge.get("to_module", "")
        if from_id in node_ids and to_id in node_ids and from_id != to_id:
            edges.append({
                "from": from_id,
                "to": to_id,
                "rel_type": edge.get("rel_type", "CALLS"),
                "weight": edge.get("weight", 1),
            })

    return {"nodes": nodes, "edges": edges}


def _build_module_relationships(
    modules: list[Module],
    module_ids: list[str],
) -> dict[str, Any]:
    """Module relationship grid — shows which modules depend on which others."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for i, module in enumerate(modules[:12]):
        color = _MODULE_COLORS[i % len(_MODULE_COLORS)]
        nodes.append({
            "id": module.id,
            "label": module.name,
            "sublabel": f"{module.file_count} files",
            "color": color,
            "slug": module.slug,
        })

    node_ids = {n["id"] for n in nodes}
    for module in modules:
        for dep_id in (module.dependency_module_ids or []):
            if dep_id in node_ids and dep_id != module.id:
                edges.append({
                    "from": module.id,
                    "to": dep_id,
                    "label": "uses",
                })

    return {"nodes": nodes, "edges": edges}


def _classify_tier(name: str, file_paths: list[str]) -> str:
    """Classify a module into a rough architectural tier."""
    name_lower = name.lower()
    paths = " ".join(file_paths).lower()

    if any(k in name_lower for k in ["ui", "frontend", "view", "component", "page", "web"]):
        return "frontend"
    if any(k in name_lower for k in ["api", "route", "endpoint", "handler", "controller"]):
        return "api"
    if any(k in name_lower for k in ["db", "database", "model", "repo", "store", "cache"]):
        return "data"
    if any(k in name_lower for k in ["test", "spec"]):
        return "test"
    return "service"


def _module_icon(name: str) -> str:
    """Return an emoji icon for a module based on its name."""
    name_lower = name.lower()
    if any(k in name_lower for k in ["auth", "login", "security", "jwt"]):
        return "🔐"
    if any(k in name_lower for k in ["api", "route", "endpoint"]):
        return "🔌"
    if any(k in name_lower for k in ["db", "database", "model", "store"]):
        return "🗄️"
    if any(k in name_lower for k in ["chat", "message", "ai", "llm"]):
        return "💬"
    if any(k in name_lower for k in ["search", "index", "query"]):
        return "🔍"
    if any(k in name_lower for k in ["wiki", "doc", "page"]):
        return "📄"
    if any(k in name_lower for k in ["test", "spec"]):
        return "🧪"
    if any(k in name_lower for k in ["util", "helper", "common"]):
        return "🔧"
    return "📦"
