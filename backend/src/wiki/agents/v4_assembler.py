"""V4 Assembler — deterministic merge of writer prose + specialist outputs.

Takes the Writer's markdown (with self-closing XML placeholders), the
Diagrammer's mermaid results, and the Code Embedder's code results,
and produces a V3-compatible prose_segments[] list.

No LLM calls — purely mechanical substitution and markdown parsing.
"""

import logging
import re
from typing import Optional

from src.wiki.agents.v4_placeholder_parser import split_on_placeholders

logger = logging.getLogger(__name__)

# ── Markdown parsing helpers (reused from V3 tag_assembler patterns) ──────────

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
_TABLE_RE = re.compile(
    r'^\|(.+)\|\s*\n\|[-:\s|]+\|\s*\n((?:\|.+\|\s*\n?)+)',
    re.MULTILINE,
)

# V3-compatible callout/cross-ref tags that may appear in prose
_CALLOUT_TAG = re.compile(
    r'<callout\s+type=["\']([^"\']+)["\'][^>]*>(.*?)</callout>',
    re.DOTALL | re.IGNORECASE,
)
_CROSSREF_TAG = re.compile(
    r'<cross-ref\s+section=["\']([^"\']+)["\'][^>]*>(.*?)</cross-ref>',
    re.DOTALL | re.IGNORECASE,
)


def _parse_plain_markdown(text: str) -> list[dict]:
    """Parse plain markdown into heading, text, and table segments.

    Compatible with V3 tag_assembler output format.
    """
    segments: list[dict] = []
    remaining = text

    # Extract tables first
    tables = list(_TABLE_RE.finditer(remaining))
    if tables:
        last_end = 0
        for m in tables:
            before = remaining[last_end:m.start()]
            if before.strip():
                segments.extend(_parse_headings_and_text(before))

            header_row = m.group(1).strip()
            body_text = m.group(2).strip()
            headers = [c.strip() for c in header_row.split("|") if c.strip()]
            rows = []
            for line in body_text.split("\n"):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if cells:
                    rows.append(cells)
            segments.append({"type": "table", "headers": headers, "rows": rows})
            last_end = m.end()

        after = remaining[last_end:]
        if after.strip():
            segments.extend(_parse_headings_and_text(after))
    else:
        segments.extend(_parse_headings_and_text(remaining))

    return segments


def _parse_headings_and_text(text: str) -> list[dict]:
    """Split text into heading and text segments."""
    segments: list[dict] = []
    parts = _HEADING_RE.split(text)

    i = 0
    while i < len(parts):
        chunk = parts[i]

        # Check if this is a heading marker (##, ###, etc.)
        if re.match(r'^#{1,6}$', chunk.strip()):
            level = len(chunk.strip())
            heading_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if heading_text:
                segments.append({
                    "type": "heading",
                    "level": level,
                    "text": heading_text,
                })
            i += 2
        else:
            # Parse inline callouts and cross-refs
            sub_segments = _parse_inline_tags(chunk)
            segments.extend(sub_segments)
            i += 1

    return segments


def _parse_inline_tags(text: str) -> list[dict]:
    """Parse callout and cross-ref tags within text, returning segments."""
    segments: list[dict] = []

    # Split on callout and cross-ref tags
    combined = re.compile(
        r'(<callout\s[^>]*>.*?</callout>|<cross-ref\s[^>]*>.*?</cross-ref>)',
        re.DOTALL | re.IGNORECASE,
    )
    parts = combined.split(text)

    for part in parts:
        if not part.strip():
            continue

        # Try callout
        cm = _CALLOUT_TAG.fullmatch(part.strip())
        if cm:
            segments.append({
                "type": "callout",
                "callout_type": cm.group(1).strip().lower(),
                "content": cm.group(2).strip(),
            })
            continue

        # Try cross-ref
        xm = _CROSSREF_TAG.fullmatch(part.strip())
        if xm:
            segments.append({
                "type": "cross_ref",
                "section": xm.group(1).strip(),
                "text": xm.group(2).strip(),
            })
            continue

        # Plain text
        if part.strip():
            segments.append({"type": "text", "content": part.strip()})

    return segments


def _make_diagram_segment(result: dict) -> dict:
    """Create a diagram prose_segment from a diagrammer result."""
    if result.get("valid") and result.get("mermaid_source"):
        return {
            "type": "diagram",
            "mermaid_source": result["mermaid_source"],
            "caption": result.get("caption", ""),
        }
    # Failed diagram — insert info callout
    caption = result.get("caption", "Diagram")
    return {
        "type": "callout",
        "callout_type": "info",
        "content": f"[{caption}] — diagram could not be rendered.",
    }


def _make_code_segment(result: dict) -> dict:
    """Create a code_block prose_segment from a code embedder result."""
    if result.get("validated") and result.get("code"):
        return {
            "type": "code_block",
            "code": result["code"],
            "language": result.get("language", "text"),
            "file_path": result.get("file_path", ""),
            "start_line": result.get("start_line"),
            "end_line": result.get("end_line"),
            "validated": True,
        }
    # Failed code retrieval — insert info callout
    context = result.get("context", "Code example")
    return {
        "type": "callout",
        "callout_type": "info",
        "content": f"[{context}] — code example unavailable.",
    }


def v4_assemble(
    writer_markdown: str,
    diagram_results: list[dict],
    code_results: list[dict],
) -> list[dict]:
    """Merge writer prose + specialist outputs into V3-compatible prose_segments.

    Args:
        writer_markdown: Raw writer output with self-closing XML placeholders.
        diagram_results: List of {tag_index, mermaid_source, caption, valid} dicts.
        code_results: List of {tag_index, code, language, file_path, ...} dicts.

    Returns:
        List of typed prose_segment dicts (same format as V3 tag_assembler).
    """
    # Index results by tag_index for O(1) lookup
    diagram_map = {r["tag_index"]: r for r in diagram_results}
    code_map = {r["tag_index"]: r for r in code_results}

    # Split writer markdown into ordered parts
    parts = split_on_placeholders(writer_markdown)
    segments: list[dict] = []

    for part in parts:
        part_type = part["type"]

        if part_type == "prose":
            # Parse the prose markdown into typed segments
            prose_segs = _parse_plain_markdown(part["content"])
            segments.extend(prose_segs)

        elif part_type == "diagram_placeholder":
            tag_idx = part["tag_index"]
            result = diagram_map.get(tag_idx)
            if result:
                segments.append(_make_diagram_segment(result))
            else:
                caption = part.get("attrs", {}).get("caption", "Diagram")
                segments.append({
                    "type": "callout",
                    "callout_type": "info",
                    "content": f"[{caption}] — diagram not generated.",
                })

        elif part_type == "code_placeholder":
            tag_idx = part["tag_index"]
            result = code_map.get(tag_idx)
            if result:
                segments.append(_make_code_segment(result))
            else:
                context = part.get("attrs", {}).get("context", "Code example")
                segments.append({
                    "type": "callout",
                    "callout_type": "info",
                    "content": f"[{context}] — code not retrieved.",
                })

    logger.info(
        "Assembled %d segments (%d diagrams, %d code blocks)",
        len(segments),
        sum(1 for s in segments if s.get("type") == "diagram"),
        sum(1 for s in segments if s.get("type") == "code_block"),
    )
    return segments


def v4_assembler_node(state: dict) -> dict:
    """LangGraph node: merge all outputs into prose_segments."""
    writer_markdown = state.get("writer_markdown", "")
    diagram_results = state.get("diagram_results") or []
    code_results = state.get("code_results") or []

    prose_segments = v4_assemble(writer_markdown, diagram_results, code_results)

    # Count words
    word_count = sum(
        len((seg.get("content") or seg.get("text") or "").split())
        for seg in prose_segments
        if seg.get("type") in ("text", "heading")
    )

    section_spec = state.get("section_spec") or {}
    return {
        "prose_segments": prose_segments,
        "word_count": word_count,
        "section_slug": section_spec.get("slug", ""),
        "section_title": section_spec.get("title", ""),
    }
