"""Phase 3: Deterministic post-processing — zero LLM calls.

Transforms raw narrated prose (with [[marker]] patterns) into structured
prose_segments that the frontend renders safely via React components.
Also generates Mermaid diagrams and component tables from the call graph.
"""

import logging
import re
from pathlib import Path

from src.config import get_settings
from src.parsers.base import ParsedEntity
from src.wiki.diagram_generator import generate_diagram
from src.wiki.table_generator import generate_table
from src.wiki.v2_types import (
    EnrichedSection,
    NarratedSection,
    WikiPlan,
    WikiSectionPlan,
)

logger = logging.getLogger(__name__)


def enrich_section(
    section: NarratedSection,
    entity_index: dict[str, dict],
    repo_url: str,
    commit_hash: str,
    repo_path: str,
    call_graph: dict[str, list[str]],
    plan: WikiPlan,
    section_plan: WikiSectionPlan | None = None,
    entities: list[ParsedEntity] | None = None,
    reverse_call_graph: dict[str, list[str]] | None = None,
) -> EnrichedSection:
    """Run all enrichment steps on a narrated section.

    Returns an EnrichedSection with structured prose_segments (no raw HTML).
    """
    # Build name→qname lookup for fuzzy matching
    name_to_qname: dict[str, str] = {}
    for qname, info in entity_index.items():
        short = info.get("name", qname.rsplit(".", 1)[-1])
        if short not in name_to_qname:
            name_to_qname[short] = qname

    # 3a: Source link injection
    segments, source_links = inject_source_links(
        section.prose, entity_index, name_to_qname, repo_url, commit_hash,
    )

    # 3b: Code block embedding
    segments, code_blocks = inject_code_blocks(segments, repo_path)

    # 3b2: Backtick fence conversion (LLM sometimes uses ``` despite prompt)
    segments = extract_backtick_fences(segments)

    # 3e: Cross-section link resolution (before diagrams/tables which append)
    segments = resolve_cross_section_links(segments, plan)

    # 3f: Heading marker resolution
    segments = resolve_heading_markers(segments)

    # 3g: Auto-detect entity references in prose text
    segments, auto_links = auto_detect_entity_references(
        segments, entity_index, name_to_qname, repo_url, commit_hash,
    )
    source_links.extend(auto_links)

    # 3c: Mermaid diagram generation (file-based, not narrator-dependent)
    #     Try all diagram types and keep any that produce unique edge sets (D1+D4)
    diagrams: list[dict] = []
    rcg = reverse_call_graph or {}
    if section_plan:
        seen_edge_sets: list[frozenset] = []
        # Use planner hint as first type, then try the rest
        preferred = section_plan.diagram_type if section_plan.diagram_type != "none" else "architecture"
        diagram_types = [preferred] + [
            t for t in ("architecture", "flowchart", "sequence", "class_hierarchy", "data_flow")
            if t != preferred
        ]
        for dtype in diagram_types:
            result = generate_diagram(
                section_files=section_plan.all_relevant_files,
                entity_index=entity_index,
                call_graph=call_graph,
                reverse_call_graph=rcg,
                diagram_type=dtype,
                section_title=section.title,
            )
            for d in result:
                # Deduplicate by checking if edge set is identical
                edge_sig = frozenset(d.get("mermaid_source", "").splitlines())
                if edge_sig not in seen_edge_sets:
                    seen_edge_sets.append(edge_sig)
                    diagrams.append(d)

    # 3c2: Per-subsection mini-diagrams for large sections (D5)
    if section_plan and len(section_plan.subsections) >= 3:
        sub_diagram_count = 0
        for sub in section_plan.subsections:
            if sub_diagram_count >= 3:
                break
            if not sub.relevant_files:
                continue
            sub_result = generate_diagram(
                section_files=sub.relevant_files,
                entity_index=entity_index,
                call_graph=call_graph,
                reverse_call_graph=rcg,
                diagram_type="architecture",
                section_title=sub.title,
                max_nodes=15,
            )
            for d in sub_result:
                d["caption"] = f"{sub.title} — {d.get('caption', '')}"
                diagrams.append(d)
                sub_diagram_count += 1

    # 3d: Component table generation (file-based, not narrator-dependent)
    tables = list(section.tables)  # start with LLM-provided tables
    if section_plan and section_plan.table_type != "none" and entities:
        generated_tables = generate_table(
            section_files=section_plan.all_relevant_files,
            entities=entities,
            entity_index=entity_index,
            reverse_call_graph=rcg,
            table_type=section_plan.table_type,
            repo_path=repo_path,
        )
        tables.extend(generated_tables)

    # Build subsections list
    subsections = [
        {"id": sub["id"], "title": sub["title"], "anchor": sub["id"]}
        for sub in section.subsections
    ]

    # Count words in text segments
    word_count = sum(
        len(seg.get("content", "").split())
        for seg in segments
        if seg.get("type") == "text"
    )

    return EnrichedSection(
        section_id=section.section_id,
        title=section.title,
        prose_segments=segments,
        diagrams=diagrams,
        tables=tables,
        source_links=source_links,
        code_blocks=code_blocks,
        subsections=subsections,
        word_count=word_count,
    )


# ── 3a: Source link injection ────────────────────────────────────────────────


_ENTITY_MARKER = re.compile(r"\[\[entity:([^\]]+)\]\]")
_HEADING_MARKER = re.compile(r"\[\[heading:(?:(\d+):)?([^\]]+)\]\]")


def inject_source_links(
    prose: str,
    entity_index: dict[str, dict],
    name_to_qname: dict[str, str],
    repo_url: str,
    commit_hash: str,
) -> tuple[list[dict], list[dict]]:
    """Replace [[entity:QualifiedName]] markers with source_link segments.

    Returns (prose_segments, source_links_metadata).
    """
    segments: list[dict] = []
    source_links: list[dict] = []
    last_end = 0
    unresolved = 0

    for match in _ENTITY_MARKER.finditer(prose):
        # Add text before this marker
        if match.start() > last_end:
            text = prose[last_end:match.start()]
            if text:
                segments.append({"type": "text", "content": text})

        ref_name = match.group(1).strip()

        # Resolve: try exact qname, then fuzzy short name
        info = entity_index.get(ref_name)
        if not info:
            # Try fuzzy: extract short name from qualified
            short = ref_name.rsplit(".", 1)[-1]
            qname = name_to_qname.get(short) or name_to_qname.get(ref_name)
            if qname:
                info = entity_index.get(qname)
                ref_name = qname

        if info:
            file_path = info.get("file_path", "")
            line = info.get("line_start", 1)
            # Build GitHub URL
            clean_url = repo_url.rstrip("/")
            url = f"{clean_url}/blob/{commit_hash}/{file_path}#L{line}"
            display_name = info.get("name", ref_name.rsplit(".", 1)[-1])

            segments.append({
                "type": "source_link",
                "name": display_name,
                "qname": ref_name,
                "url": url,
            })
            source_links.append({
                "entity_name": display_name,
                "qualified_name": ref_name,
                "url": url,
                "line": line,
            })
        else:
            # Unresolved — render as plain text
            display = ref_name.rsplit(".", 1)[-1]
            segments.append({"type": "text", "content": display})
            unresolved += 1

        last_end = match.end()

    # Trailing text
    if last_end < len(prose):
        segments.append({"type": "text", "content": prose[last_end:]})

    if unresolved:
        logger.warning("Source links: %d markers unresolved", unresolved)

    return segments, source_links


# ── 3b: Code block embedding ────────────────────────────────────────────────


# Standard format: [[code:filepath:start:end]]
# LLM variant formats: [code: filepath:start-end], [code:filepath:start:end]
_CODE_MARKER = re.compile(
    r"\[\[code:([^:\]]+):(\d+):(\d+)\]\]"         # [[code:path:10:20]]
    r"|\[code:\s*([^:\]]+):(\d+)[:-](\d+)\]"      # [code: path:10-20] or [code:path:10:20]
)

_LANG_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".toml": "toml",
}


def _is_likely_truncated_snippet(lines: list[str]) -> bool:
    """Heuristic guard against mid-expression/mid-block snippet windows."""
    if not lines:
        return True

    first = lines[0].strip()
    if not first:
        return True

    # Continuation-like starts usually indicate line-window clipping
    if first.startswith((")", "]", "}", ",", ".", "->", "=>")):
        return True
    if first in {"else:", "elif:", "except:", "finally:"}:
        return True

    # If first line is syntactically balanced and standalone-like, keep it.
    if first.count("=") == 1:
        lhs = first.split("=", 1)[0].strip()
        if lhs.isidentifier():
            return False

    return False


def inject_code_blocks(
    segments: list[dict],
    repo_path: str,
) -> tuple[list[dict], list[dict]]:
    """Replace [[code:filepath:start:end]] markers in text segments with code_block segments.

    Reads actual source from the cloned repo.
    Returns (updated_segments, code_blocks_metadata).
    """
    updated: list[dict] = []
    code_blocks_meta: list[dict] = []

    for seg in segments:
        if seg.get("type") != "text":
            updated.append(seg)
            continue

        text = seg["content"]
        sub_segments: list[dict] = []
        last_end = 0

        for match in _CODE_MARKER.finditer(text):
            # Text before marker
            if match.start() > last_end:
                before = text[last_end:match.start()]
                if before:
                    sub_segments.append({"type": "text", "content": before})

            # Handle alternation: groups 1-3 for [[...]], groups 4-6 for [...]
            file_path = (match.group(1) or match.group(4) or "").strip()
            start_line = int(match.group(2) or match.group(5) or 0)
            end_line = int(match.group(3) or match.group(6) or 0)

            # Read source file
            full_path = Path(repo_path) / file_path
            code = ""
            try:
                if full_path.is_file():
                    lines = full_path.read_text(errors="replace").splitlines()
                    # Convert 1-indexed to 0-indexed
                    snippet_lines = lines[max(0, start_line - 1):end_line]
                    if snippet_lines and not _is_likely_truncated_snippet(snippet_lines):
                        code = "\n".join(snippet_lines)
                    else:
                        logger.warning(
                            "Rejected likely-truncated snippet %s:%s-%s",
                            file_path,
                            start_line,
                            end_line,
                        )
            except Exception as exc:
                logger.warning("Failed to read %s: %s", full_path, exc)

            ext = Path(file_path).suffix
            language = _LANG_MAP.get(ext, ext.lstrip(".") or "text")

            if code:
                sub_segments.append({
                    "type": "code_block",
                    "language": language,
                    "code": code,
                    "file_path": file_path,
                    "start_line": start_line,
                })
                code_blocks_meta.append({
                    "language": language,
                    "code": code,
                    "file_path": file_path,
                    "start_line": start_line,
                })
            else:
                # Failed to read — keep prose readable without leaking marker syntax
                sub_segments.append({
                    "type": "text",
                    "content": (
                        f"(code snippet unavailable from {file_path}:{start_line}-{end_line})"
                    ),
                })

            last_end = match.end()

        # Trailing text
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                sub_segments.append({"type": "text", "content": remaining})

        if sub_segments:
            updated.extend(sub_segments)
        else:
            updated.append(seg)

    return updated, code_blocks_meta


# ── 3b2: Backtick fence extraction ─────────────────────────────────────────


_BACKTICK_FENCE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def extract_backtick_fences(segments: list[dict]) -> list[dict]:
    """Convert markdown backtick code fences in text segments into code_block segments."""
    updated: list[dict] = []

    for seg in segments:
        if seg.get("type") != "text":
            updated.append(seg)
            continue

        text = seg["content"]
        last_end = 0
        found = False

        for match in _BACKTICK_FENCE.finditer(text):
            found = True
            if match.start() > last_end:
                before = text[last_end:match.start()]
                if before.strip():
                    updated.append({"type": "text", "content": before})

            lang = match.group(1) or "text"
            code = match.group(2).rstrip("\n")
            if code:
                updated.append({
                    "type": "code_block",
                    "language": lang,
                    "code": code,
                })

            last_end = match.end()

        if found:
            if last_end < len(text):
                remaining = text[last_end:]
                if remaining.strip():
                    updated.append({"type": "text", "content": remaining})
        else:
            updated.append(seg)

    return updated


# ── 3e: Cross-section link resolution ───────────────────────────────────────


_SECTION_MARKER = re.compile(r"\[\[section:([^\]]+)\]\]")


def resolve_heading_markers(segments: list[dict]) -> list[dict]:
    """Replace [[heading:level:Title]] markers with heading segments."""
    updated: list[dict] = []
    for seg in segments:
        if seg.get("type") != "text":
            updated.append(seg)
            continue

        text = seg["content"]
        sub: list[dict] = []
        last_end = 0

        for match in _HEADING_MARKER.finditer(text):
            if match.start() > last_end:
                before = text[last_end:match.start()]
                if before:
                    sub.append({"type": "text", "content": before})

            level_str = match.group(1)
            title = match.group(2).strip()
            level = int(level_str) if level_str else 2
            sub.append({
                "type": "heading",
                "level": level,
                "text": title,
            })
            last_end = match.end()

        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                sub.append({"type": "text", "content": remaining})

        if sub:
            updated.extend(sub)
        else:
            updated.append(seg)

    return updated


# ── 3g: Auto-detect entity references ──────────────────────────────────────

# Hard skip: true language keywords — never auto-link these
_HARD_SKIP = frozenset({
    "self", "none", "true", "false", "type", "args", "kwargs", "init",
    "async", "await", "return", "import", "from", "with", "print",
    "this", "that", "class", "open", "close", "read", "write",
})

# Soft skip: generic but sometimes meaningful — skip only for functions/variables
_SOFT_SKIP = frozenset({
    "name", "data", "list", "dict", "main", "test", "error",
    "file", "path", "node", "item", "base", "info", "help",
    "call", "func", "util", "tool", "model", "state", "event",
    "value", "index", "query", "result", "config", "setup", "level", "agent",
})

# Minimum entity name length for auto-detection
_MIN_AUTO_LINK_LEN = 3


def auto_detect_entity_references(
    segments: list[dict],
    entity_index: dict[str, dict],
    name_to_qname: dict[str, str],
    repo_url: str,
    commit_hash: str,
) -> tuple[list[dict], list[dict]]:
    """Scan text segments for entity names and auto-link up to 3 occurrences per entity.

    Uses split skip-word lists: hard-skip always blocked, soft-skip only for functions/variables.
    Min name length: 3 chars.
    Returns (updated_segments, new_source_links).
    """
    settings = get_settings()
    if not settings.wiki_auto_entity_linking_enabled:
        return segments, []

    # Build reverse map: short_name → (qname, info)
    candidates: dict[str, tuple[str, dict]] = {}
    for qname, info in entity_index.items():
        short = info.get("name", qname.rsplit(".", 1)[-1])
        lower = short.lower()
        if len(short) < _MIN_AUTO_LINK_LEN or lower in _HARD_SKIP:
            continue
        # Soft-skip: only block for function/variable entities
        if lower in _SOFT_SKIP and info.get("entity_type") in ("function", "variable"):
            continue
        if short not in candidates:
            candidates[short] = (qname, info)

    # Track link counts per entity (allow up to 3 per entity per section)
    _MAX_LINKS_PER_ENTITY = 3
    link_count: dict[str, int] = {}
    # Count existing source_link segments
    for seg in segments:
        if seg.get("type") == "source_link":
            name = seg.get("name", "")
            qname = seg.get("qname", "")
            link_count[name] = link_count.get(name, 0) + 1
            link_count[qname] = link_count.get(qname, 0) + 1

    updated: list[dict] = []
    new_links: list[dict] = []

    for seg in segments:
        if seg.get("type") != "text":
            updated.append(seg)
            continue

        text = seg["content"]
        sub: list[dict] = []
        last_end = 0

        # Find all candidate matches sorted by position
        matches: list[tuple[int, int, str, str, dict]] = []
        for short_name, (qname, info) in candidates.items():
            # Check if entity has reached link limit
            if link_count.get(short_name, 0) >= _MAX_LINKS_PER_ENTITY:
                continue
            # Whole-word match — find all occurrences
            pattern = re.compile(r"\b" + re.escape(short_name) + r"\b")
            for m in pattern.finditer(text):
                if link_count.get(short_name, 0) >= _MAX_LINKS_PER_ENTITY:
                    break
                matches.append((m.start(), m.end(), short_name, qname, info))

        # Sort by position and filter overlaps
        matches.sort(key=lambda x: x[0])
        filtered: list[tuple[int, int, str, str, dict]] = []
        for start, end, short, qname, info in matches:
            if link_count.get(short, 0) >= _MAX_LINKS_PER_ENTITY:
                continue
            # Check no overlap with previous matches
            if filtered and start < filtered[-1][1]:
                continue
            filtered.append((start, end, short, qname, info))
            link_count[short] = link_count.get(short, 0) + 1
            link_count[qname] = link_count.get(qname, 0) + 1

        if not filtered:
            updated.append(seg)
            continue

        for start, end, short_name, qname, info in filtered:
            if start > last_end:
                before = text[last_end:start]
                if before:
                    sub.append({"type": "text", "content": before})

            file_path = info.get("file_path", "")
            line = info.get("line_start", 1)
            clean_url = repo_url.rstrip("/")
            url = f"{clean_url}/blob/{commit_hash}/{file_path}#L{line}"

            sub.append({
                "type": "source_link",
                "name": short_name,
                "qname": qname,
                "url": url,
            })
            new_links.append({
                "entity_name": short_name,
                "qualified_name": qname,
                "url": url,
                "line": line,
            })
            last_end = end

        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                sub.append({"type": "text", "content": remaining})

        updated.extend(sub)

    return updated, new_links


def resolve_cross_section_links(
    segments: list[dict],
    plan: WikiPlan,
) -> list[dict]:
    """Replace [[section:slug]] markers with section_link segments."""
    # Build slug→title map
    slug_to_title: dict[str, str] = {}
    for section in plan.sections:
        slug_to_title[section.id] = section.title

    updated: list[dict] = []
    for seg in segments:
        if seg.get("type") != "text":
            updated.append(seg)
            continue

        text = seg["content"]
        sub: list[dict] = []
        last_end = 0

        for match in _SECTION_MARKER.finditer(text):
            if match.start() > last_end:
                before = text[last_end:match.start()]
                if before:
                    sub.append({"type": "text", "content": before})

            slug = match.group(1).strip()
            title = slug_to_title.get(slug, slug.replace("-", " ").title())

            sub.append({
                "type": "section_link",
                "slug": slug,
                "title": title,
            })
            last_end = match.end()

        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                sub.append({"type": "text", "content": remaining})

        if sub:
            updated.extend(sub)
        else:
            updated.append(seg)

    return updated
