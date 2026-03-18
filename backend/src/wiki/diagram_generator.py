"""Mermaid diagram generation — file-based entity lookup.

Decoupled from narrator-produced entities_referenced. Instead uses
section_plan.all_relevant_files to deterministically find entities
and their call-graph edges.
"""

import logging
import re

logger = logging.getLogger(__name__)


def generate_diagram(
    section_files: list[str],
    entity_index: dict[str, dict],
    call_graph: dict[str, list[str]],
    reverse_call_graph: dict[str, list[str]],
    diagram_type: str,
    section_title: str,
    max_nodes: int = 30,
) -> list[dict]:
    """Generate Mermaid diagram using file-based entity lookup.

    Returns list of [{mermaid_source, caption}].
    """
    section_entities = _collect_section_entities(section_files, entity_index)
    if not section_entities:
        return []

    # Dispatch to specialized generators for new diagram types
    if diagram_type == "class_hierarchy":
        return _generate_class_hierarchy(
            section_entities, entity_index, section_title, max_nodes,
        )
    if diagram_type == "data_flow":
        return _generate_data_flow(
            section_files, section_entities, entity_index,
            call_graph, section_title, max_nodes,
        )

    edges = _find_edges(section_entities, call_graph, reverse_call_graph)
    if not edges:
        return []

    nodes = set()
    for a, b in edges:
        nodes.add(a)
        nodes.add(b)

    # Cap at max_nodes — keep highest-degree nodes
    if len(nodes) > max_nodes:
        degree: dict[str, int] = {}
        for a, b in edges:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        top_nodes = set(
            sorted(degree, key=lambda n: degree[n], reverse=True)[:max_nodes]
        )
        edges = [(a, b) for a, b in edges if a in top_nodes and b in top_nodes]
        nodes = top_nodes

    if not edges:
        return []

    mermaid_source = _build_mermaid(edges, nodes, entity_index, diagram_type, section_title)
    caption = (
        f"{section_title} — {diagram_type} diagram "
        f"({len(nodes)} components, {len(edges)} connections)"
    )
    return [{"mermaid_source": mermaid_source, "caption": caption}]


def _collect_section_entities(
    section_files: list[str],
    entity_index: dict[str, dict],
) -> set[str]:
    """Find all entity qualified names whose file_path is in section_files."""
    file_set = set(section_files)
    result: set[str] = set()
    for qname, info in entity_index.items():
        if info.get("file_path") in file_set:
            result.add(qname)
    return result


def _find_edges(
    section_entities: set[str],
    call_graph: dict[str, list[str]],
    reverse_call_graph: dict[str, list[str]],
) -> list[tuple[str, str]]:
    """Find call-graph edges where EITHER endpoint is in section_entities.

    Relaxed matching: includes cross-section edges to show external callers/callees.
    Deduplicates edges.
    """
    seen: set[tuple[str, str]] = set()
    edges: list[tuple[str, str]] = []

    for caller in section_entities:
        for callee in call_graph.get(caller, []):
            key = (caller, callee)
            if key not in seen:
                seen.add(key)
                edges.append(key)

    for callee in section_entities:
        for caller in reverse_call_graph.get(callee, []):
            key = (caller, callee)
            if key not in seen:
                seen.add(key)
                edges.append(key)

    return edges


def _build_mermaid(
    edges: list[tuple[str, str]],
    nodes: set[str],
    entity_index: dict[str, dict],
    diagram_type: str,
    section_title: str,
) -> str:
    """Build Mermaid syntax string from edges and nodes."""

    def short_name(qname: str) -> str:
        info = entity_index.get(qname)
        if info:
            return info.get("name", qname.rsplit(".", 1)[-1])
        return qname.rsplit(".", 1)[-1]

    def safe_id(qname: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", qname)

    if diagram_type == "sequence":
        lines = ["sequenceDiagram"]
        seen_edges: set[tuple[str, str]] = set()
        for caller, callee in edges[:20]:
            key = (caller, callee)
            if key not in seen_edges:
                seen_edges.add(key)
                lines.append(
                    f"    {short_name(caller)}->>+{short_name(callee)}: calls"
                )
    elif diagram_type == "architecture":
        lines = ["graph TD"]
        for node in nodes:
            sid = safe_id(node)
            lines.append(f"    {sid}[{short_name(node)}]")
        for caller, callee in edges:
            lines.append(f"    {safe_id(caller)} --> {safe_id(callee)}")
    else:  # flowchart
        lines = ["graph LR"]
        for node in nodes:
            sid = safe_id(node)
            lines.append(f"    {sid}[{short_name(node)}]")
        for caller, callee in edges:
            lines.append(f"    {safe_id(caller)} --> {safe_id(callee)}")

    return "\n".join(lines)


def _generate_class_hierarchy(
    section_entities: set[str],
    entity_index: dict[str, dict],
    section_title: str,
    max_nodes: int = 30,
) -> list[dict]:
    """Generate a class hierarchy diagram from qualified_name nesting.

    Infers parent→child from class entities where child qname starts with parent qname.
    Renders as graph BT (bottom-to-top).
    """
    # Filter to class entities in this section
    classes = {
        qname for qname in section_entities
        if entity_index.get(qname, {}).get("entity_type") == "class"
    }
    if len(classes) < 2:
        return []

    # Find parent→child edges: methods/inner classes nested under classes
    edges: list[tuple[str, str]] = []
    for qname in section_entities:
        info = entity_index.get(qname, {})
        if info.get("entity_type") not in ("class", "method"):
            continue
        # Check if this entity is a child of a class (qname starts with class qname + ".")
        for cls_qname in classes:
            if qname != cls_qname and qname.startswith(cls_qname + "."):
                # Only direct children (one level deep)
                remainder = qname[len(cls_qname) + 1:]
                if "." not in remainder:
                    edges.append((cls_qname, qname))

    if len(edges) < 2:
        return []

    nodes = set()
    for a, b in edges:
        nodes.add(a)
        nodes.add(b)

    if len(nodes) > max_nodes:
        nodes = set(sorted(classes)[:max_nodes])
        edges = [(a, b) for a, b in edges if a in nodes and b in nodes]

    if not edges:
        return []

    def short_name(qname: str) -> str:
        info = entity_index.get(qname)
        if info:
            return info.get("name", qname.rsplit(".", 1)[-1])
        return qname.rsplit(".", 1)[-1]

    def safe_id(qname: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", qname)

    lines = ["graph BT"]
    for node in nodes:
        sid = safe_id(node)
        etype = entity_index.get(node, {}).get("entity_type", "")
        shape = f"[{short_name(node)}]" if etype == "class" else f"({short_name(node)})"
        lines.append(f"    {sid}{shape}")
    for parent, child in edges:
        lines.append(f"    {safe_id(child)} --> {safe_id(parent)}")

    mermaid_source = "\n".join(lines)
    caption = (
        f"{section_title} — class hierarchy "
        f"({len(nodes)} entities, {len(edges)} relationships)"
    )
    return [{"mermaid_source": mermaid_source, "caption": caption}]


def _generate_data_flow(
    section_files: list[str],
    section_entities: set[str],
    entity_index: dict[str, dict],
    call_graph: dict[str, list[str]],
    section_title: str,
    max_nodes: int = 30,
) -> list[dict]:
    """Generate a data flow diagram showing file-level interactions.

    Groups entities by file, draws inter-file edges from call graph.
    Renders as graph LR with subgraph clusters per directory.
    """
    from pathlib import PurePosixPath

    # Map entities to files
    file_entities: dict[str, list[str]] = {}
    for qname in section_entities:
        info = entity_index.get(qname, {})
        fp = info.get("file_path", "")
        if fp:
            file_entities.setdefault(fp, []).append(qname)

    if len(file_entities) < 2:
        return []

    # Find inter-file edges
    file_edges: dict[tuple[str, str], int] = {}
    for qname in section_entities:
        info = entity_index.get(qname, {})
        caller_file = info.get("file_path", "")
        for callee in call_graph.get(qname, []):
            callee_info = entity_index.get(callee, {})
            callee_file = callee_info.get("file_path", "")
            if callee_file and callee_file != caller_file and callee_file in file_entities:
                key = (caller_file, callee_file)
                file_edges[key] = file_edges.get(key, 0) + 1

    if len(file_edges) < 2:
        return []

    def safe_id(fp: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", fp)

    def short_file(fp: str) -> str:
        return PurePosixPath(fp).name

    # Group files by directory for subgraphs
    dir_files: dict[str, list[str]] = {}
    all_files_in_edges = set()
    for a, b in file_edges:
        all_files_in_edges.add(a)
        all_files_in_edges.add(b)
    for fp in all_files_in_edges:
        d = str(PurePosixPath(fp).parent)
        dir_files.setdefault(d, []).append(fp)

    lines = ["graph LR"]
    for d, files in dir_files.items():
        dir_label = PurePosixPath(d).name or d
        lines.append(f"    subgraph {safe_id(d)}[{dir_label}]")
        for fp in files:
            entity_count = len(file_entities.get(fp, []))
            lines.append(f"        {safe_id(fp)}[{short_file(fp)}<br/>{entity_count} entities]")
        lines.append("    end")

    for (src, dst), count in file_edges.items():
        label = f"|{count} calls|" if count > 1 else ""
        lines.append(f"    {safe_id(src)} -->{label} {safe_id(dst)}")

    mermaid_source = "\n".join(lines)
    caption = (
        f"{section_title} — data flow "
        f"({len(all_files_in_edges)} files, {len(file_edges)} connections)"
    )
    return [{"mermaid_source": mermaid_source, "caption": caption}]
