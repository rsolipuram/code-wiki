"""V4 Placeholder Parser — extract self-closing XML tags from writer markdown.

Parses two tag types from the Writer agent's output:
  <diagram type="..." caption="..." context="..."/>
  <code file="..." symbol="..." lines="..." context="..."/>

Returns indexed specs and split markdown parts for later assembly.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Self-closing <diagram .../> tag
_DIAGRAM_PLACEHOLDER = re.compile(
    r'<diagram\s+([^>]*?)\s*/>',
    re.DOTALL | re.IGNORECASE,
)

# Self-closing <code .../> tag
_CODE_PLACEHOLDER = re.compile(
    r'<code\s+([^>]*?)\s*/>',
    re.DOTALL | re.IGNORECASE,
)

# Combined pattern for splitting — matches either self-closing tag
_ANY_PLACEHOLDER = re.compile(
    r'(<diagram\s+[^>]*?/>|<code\s+[^>]*?/>)',
    re.DOTALL | re.IGNORECASE,
)

# Attribute extraction: key="value" or key='value'
_ATTR_RE = re.compile(r'(\w+)\s*=\s*["\']([^"\']*?)["\']')


def _parse_attrs(attr_str: str) -> dict[str, str]:
    """Extract key=value pairs from an XML tag's attribute string."""
    return {m.group(1): m.group(2) for m in _ATTR_RE.finditer(attr_str)}


def parse_placeholders(writer_markdown: str) -> tuple[list[dict], list[dict]]:
    """Parse self-closing XML placeholders from writer markdown.

    Args:
        writer_markdown: Raw markdown from the Writer agent containing
            <diagram .../> and <code .../> self-closing tags.

    Returns:
        Tuple of (diagram_specs, code_specs) where each spec is a dict:
          diagram_specs: [{tag_index, type, caption, context}, ...]
          code_specs:    [{tag_index, file, lines, symbol, context, lang}, ...]

        tag_index is the 0-based position of the placeholder in the
        markdown (order of appearance), used by the Assembler to
        substitute results back into the correct position.
    """
    diagram_specs: list[dict] = []
    code_specs: list[dict] = []
    tag_index = 0

    for m in _ANY_PLACEHOLDER.finditer(writer_markdown):
        tag_text = m.group(0)
        attrs = _parse_attrs(tag_text)

        if tag_text.lower().startswith("<diagram"):
            diagram_specs.append({
                "tag_index": tag_index,
                "type": attrs.get("type", "flowchart"),
                "caption": attrs.get("caption", ""),
                "context": attrs.get("context", ""),
            })
        elif tag_text.lower().startswith("<code"):
            code_specs.append({
                "tag_index": tag_index,
                "file": attrs.get("file", ""),
                "lines": attrs.get("lines", ""),
                "symbol": attrs.get("symbol", ""),
                "context": attrs.get("context", ""),
                "lang": attrs.get("lang", ""),
            })

        tag_index += 1

    logger.info(
        "Parsed %d diagram + %d code placeholders from writer output",
        len(diagram_specs), len(code_specs),
    )
    return diagram_specs, code_specs


def split_on_placeholders(writer_markdown: str) -> list[dict]:
    """Split writer markdown into interleaved prose and placeholder parts.

    Returns a list of dicts, each either:
      {"type": "prose", "content": "...markdown text..."}
      {"type": "diagram_placeholder", "tag_index": N, "attrs": {...}}
      {"type": "code_placeholder", "tag_index": N, "attrs": {...}}

    The Assembler uses this ordered list to substitute specialist
    results back into the correct positions.
    """
    parts: list[dict] = []
    last_end = 0
    tag_index = 0

    for m in _ANY_PLACEHOLDER.finditer(writer_markdown):
        # Capture prose before this placeholder
        prose = writer_markdown[last_end:m.start()]
        if prose.strip():
            parts.append({"type": "prose", "content": prose})

        # Capture the placeholder
        tag_text = m.group(0)
        attrs = _parse_attrs(tag_text)

        if tag_text.lower().startswith("<diagram"):
            parts.append({
                "type": "diagram_placeholder",
                "tag_index": tag_index,
                "attrs": attrs,
            })
        elif tag_text.lower().startswith("<code"):
            parts.append({
                "type": "code_placeholder",
                "tag_index": tag_index,
                "attrs": attrs,
            })

        tag_index += 1
        last_end = m.end()

    # Trailing prose after last placeholder
    trailing = writer_markdown[last_end:]
    if trailing.strip():
        parts.append({"type": "prose", "content": trailing})

    return parts
