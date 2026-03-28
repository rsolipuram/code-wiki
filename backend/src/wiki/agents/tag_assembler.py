"""Tag Assembler — parses deep agent markdown output into typed prose_segments.

Handles V3 special XML tags:
  <code file="..." lines="..." lang="...">...</code>
  <diagram type="mermaid" caption="...">...</diagram>
  <callout type="warning|info|tip">...</callout>
  <cross-ref section="...">...</cross-ref>

Validates code blocks (file + line range must exist in repo).
Emits validated=false flag for blocks that can't be verified.
Plain markdown between tags becomes text segments.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tag parsing regexes ───────────────────────────────────────────────────────

_CODE_TAG = re.compile(
    r'<code\s+file=["\']([^"\']+)["\']'           # file="..."
    r'(?:\s+lines=["\']([^"\']+)["\'])?'           # lines="N-M" (optional)
    r'(?:\s+lang=["\']([^"\']+)["\'])?'            # lang="..." (optional)
    r'[^>]*>(.*?)</code>',
    re.DOTALL | re.IGNORECASE,
)

_DIAGRAM_TAG = re.compile(
    r'<diagram\s+type=["\']([^"\']+)["\']'         # type="mermaid"
    r'(?:\s+caption=["\']([^"\']*)["\'])?'         # caption="..." (optional)
    r'[^>]*>(.*?)</diagram>',
    re.DOTALL | re.IGNORECASE,
)

_CALLOUT_TAG = re.compile(
    r'<callout\s+type=["\']([^"\']+)["\']'         # type="warning|info|tip"
    r'[^>]*>(.*?)</callout>',
    re.DOTALL | re.IGNORECASE,
)

_CROSSREF_TAG = re.compile(
    r'<cross-ref\s+section=["\']([^"\']+)["\']'   # section="Section Title"
    r'[^>]*>(.*?)</cross-ref>',
    re.DOTALL | re.IGNORECASE,
)

# Combined pattern to split on ANY known tag
_ANY_TAG = re.compile(
    r'(<code\s[^>]*>.*?</code>'
    r'|<diagram\s[^>]*>.*?</diagram>'
    r'|<callout\s[^>]*>.*?</callout>'
    r'|<cross-ref\s[^>]*>.*?</cross-ref>)',
    re.DOTALL | re.IGNORECASE,
)


def assemble(raw_markdown: str, repo_path: Optional[str] = None) -> list[dict]:
    """Parse raw markdown with special tags → typed prose_segments.

    Args:
        raw_markdown: LLM output containing markdown + XML tags.
        repo_path: Absolute repo path for code block validation. None = skip.

    Returns:
        List of prose segment dicts (compatible with V2 ProseSegment type).
    """
    segments: list[dict] = []
    parts = _ANY_TAG.split(raw_markdown)

    for part in parts:
        if not part.strip():
            continue

        # Try parsing as each tag type
        seg = (
            _parse_code_tag(part, repo_path)
            or _parse_diagram_tag(part)
            or _parse_callout_tag(part)
            or _parse_crossref_tag(part)
        )

        if seg:
            segments.append(seg)
        else:
            # Plain markdown text — split into text + heading segments
            segments.extend(_parse_plain_markdown(part))

    return segments


# ── Tag parsers ───────────────────────────────────────────────────────────────

def _parse_code_tag(text: str, repo_path: Optional[str]) -> Optional[dict]:
    m = _CODE_TAG.fullmatch(text.strip())
    if not m:
        return None

    file_path = m.group(1).strip()
    lines_str = (m.group(2) or "").strip()
    lang = (m.group(3) or "").strip()
    code_content = m.group(4).strip()

    start_line = None
    end_line = None
    if lines_str:
        try:
            if "-" in lines_str:
                parts = lines_str.split("-", 1)
                start_line = int(parts[0])
                end_line = int(parts[1])
            else:
                start_line = int(lines_str)
        except ValueError:
            pass

    # Validate code block exists in repo
    validated = True
    if repo_path and file_path:
        validated = _validate_code_location(repo_path, file_path, start_line, end_line, code_content)

    # Infer lang from extension if not provided
    if not lang and "." in file_path:
        lang = _ext_to_lang(file_path.rsplit(".", 1)[-1])

    seg: dict = {
        "type": "code_block",
        "code": code_content,
        "language": lang or "text",
        "file_path": file_path,
        "validated": validated,
    }
    if start_line:
        seg["start_line"] = start_line
    if end_line:
        seg["end_line"] = end_line
    return seg


def _parse_diagram_tag(text: str) -> Optional[dict]:
    m = _DIAGRAM_TAG.fullmatch(text.strip())
    if not m:
        return None

    diagram_type = m.group(1).strip().lower()
    caption = (m.group(2) or "").strip()
    content = m.group(3).strip()

    if diagram_type == "mermaid":
        return {
            "type": "diagram",
            "mermaid_source": content,
            "caption": caption,
        }
    # Other diagram types degrade to code blocks
    return {
        "type": "code_block",
        "code": content,
        "language": diagram_type,
        "caption": caption,
    }


def _parse_callout_tag(text: str) -> Optional[dict]:
    m = _CALLOUT_TAG.fullmatch(text.strip())
    if not m:
        return None

    callout_type = m.group(1).strip().lower()
    if callout_type not in ("warning", "info", "tip"):
        callout_type = "info"

    return {
        "type": "callout",
        "callout_type": callout_type,
        "content": m.group(2).strip(),
    }


def _parse_crossref_tag(text: str) -> Optional[dict]:
    m = _CROSSREF_TAG.fullmatch(text.strip())
    if not m:
        return None

    return {
        "type": "cross-ref",
        "section_title": m.group(1).strip(),
        "section_slug": "",   # resolved in cross_link_resolver
        "text": m.group(2).strip(),
    }


# ── Plain markdown parser ─────────────────────────────────────────────────────

_HEADING = re.compile(r'^(#{1,6})\s+(.+)$')
_TABLE_ROW = re.compile(r'^\s*\|')


def _parse_plain_markdown(text: str) -> list[dict]:
    """Split plain markdown text into text/heading segments."""
    segments: list[dict] = []
    lines = text.splitlines()
    buffer: list[str] = []
    in_table = False
    table_lines: list[str] = []

    def _flush_buffer() -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip()
        if content:
            segments.append({"type": "text", "content": content})
        buffer = []

    def _flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        try:
            headers = [h.strip() for h in table_lines[0].strip("|").split("|")]
            rows = [
                [c.strip() for c in row.strip("|").split("|")]
                for row in table_lines[2:]  # skip separator
                if row.strip() and not re.match(r'^[\s|:-]+$', row)
            ]
            segments.append({"type": "table", "headers": headers, "rows": rows})
        except Exception:
            segments.append({"type": "text", "content": "\n".join(table_lines)})
        table_lines = []

    for line in lines:
        # Heading
        hm = _HEADING.match(line)
        if hm:
            _flush_buffer()
            _flush_table()
            in_table = False
            level = len(hm.group(1))
            segments.append({"type": "heading", "level": level, "text": hm.group(2).strip()})
            continue

        # Table row detection
        if _TABLE_ROW.match(line):
            if not in_table:
                _flush_buffer()
                in_table = True
            table_lines.append(line)
            continue

        # End of table
        if in_table and not _TABLE_ROW.match(line):
            _flush_table()
            in_table = False

        buffer.append(line)

    _flush_buffer()
    _flush_table()

    return segments


# ── Code validation ───────────────────────────────────────────────────────────

def _validate_code_location(
    repo_path: str,
    file_path: str,
    start_line: Optional[int],
    end_line: Optional[int],
    code_content: str,
) -> bool:
    """Return True if the file exists and (optionally) the line range is valid."""
    full = Path(repo_path) / file_path
    if not full.is_file():
        logger.debug("Code block validation: file not found: %s", file_path)
        return False

    if start_line is None:
        return True  # file exists, no line constraint

    try:
        lines = full.read_text(errors="replace").splitlines()
        total = len(lines)
        if start_line > total:
            logger.debug(
                "Code block validation: start_line %d > %d total lines in %s",
                start_line, total, file_path,
            )
            return False
        if end_line and end_line > total:
            return False  # end_line out of range
        return True
    except Exception:
        return False


_LANG_MAP = {
    "py": "python", "js": "javascript", "ts": "typescript",
    "tsx": "tsx", "jsx": "jsx", "go": "go", "rs": "rust",
    "java": "java", "kt": "kotlin", "cs": "csharp", "rb": "ruby",
    "sh": "bash", "yaml": "yaml", "yml": "yaml", "json": "json",
    "md": "markdown", "html": "html", "css": "css", "sql": "sql",
    "toml": "toml", "tf": "hcl",
}


def _ext_to_lang(ext: str) -> str:
    return _LANG_MAP.get(ext.lower(), "text")
