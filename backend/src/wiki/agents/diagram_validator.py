"""Mermaid diagram validation and auto-fix utilities.

Uses heuristic checks to catch common mermaid syntax errors, then
calls the LLM to fix them.  Max 2 fix attempts per diagram.

Also provides `fix_prose_diagrams()` for post-assembly validation
on prose_segments (the final structured output stored in the DB).
"""

import logging
import re
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 2


# ── Public API ────────────────────────────────────────────────────────────────

def validate_mermaid(source: str) -> Tuple[bool, str]:
    """Validate Mermaid diagram syntax via structural heuristics.

    Returns:
        (is_valid, error_message)  — error_message is "" when valid.
    """
    source = source.strip()
    if not source:
        return False, "Empty diagram source"

    errors = _heuristic_check(source)
    if errors:
        return False, "; ".join(errors)

    return True, ""


def fix_mermaid(
    source: str,
    error: str,
    llm_fn: Callable[[str, str], str],
    *,
    max_attempts: int = MAX_FIX_ATTEMPTS,
) -> Optional[str]:
    """Attempt to fix invalid Mermaid diagram syntax using LLM.

    Returns:
        Fixed diagram source, or None if unfixable after max tries.
    """
    current = source
    current_error = error

    for attempt in range(1, max_attempts + 1):
        logger.info("Mermaid fix attempt %d/%d: %s", attempt, max_attempts, current_error[:120])

        fixed = _call_llm_fix(current, current_error, llm_fn)
        fixed = _extract_mermaid_block(fixed) or fixed.strip()

        is_valid, new_error = validate_mermaid(fixed)
        if is_valid:
            logger.info("Mermaid fixed after %d attempt(s)", attempt)
            return fixed

        current = fixed
        current_error = new_error

    logger.warning("Mermaid diagram unfixable after %d attempts — will drop", max_attempts)
    return None


def fix_prose_diagrams(
    prose_segments: list[dict],
    llm_fn: Callable[[str, str], str],
) -> list[dict]:
    """Validate and fix diagram segments in assembled prose_segments.

    Invalid diagrams that can't be fixed are replaced with an info callout.
    Returns a new list (does not mutate the input).
    """
    result: list[dict] = []
    for seg in prose_segments:
        if seg.get("type") != "diagram":
            result.append(seg)
            continue

        source = (seg.get("mermaid_source") or "").strip()
        if not source:
            result.append(seg)
            continue

        is_valid, error = validate_mermaid(source)
        if is_valid:
            result.append(seg)
            continue

        caption = seg.get("caption", "Diagram")
        logger.info("Invalid mermaid in prose_segments (%s): %s", caption, error[:120])

        fixed = fix_mermaid(source, error, llm_fn)
        if fixed:
            result.append({**seg, "mermaid_source": fixed})
        else:
            # Replace unfixable diagram with a text callout
            result.append({
                "type": "callout",
                "callout_type": "info",
                "content": f"[Diagram: {caption}] — could not be rendered.",
            })

    return result


# ── Private helpers ───────────────────────────────────────────────────────────

_VALID_STARTERS = {
    "graph", "flowchart", "sequencediagram", "classdiagram",
    "statediagram", "statediagram-v2", "erdiagram", "gantt", "pie",
    "mindmap", "timeline", "gitgraph", "xychart-beta",
    "block-beta", "architecture-beta", "journey", "quadrantchart",
    "requirementdiagram", "c4context", "c4container", "c4component",
    "c4deployment", "sankey-beta", "packet-beta",
}


def _heuristic_check(source: str) -> list[str]:
    """Return list of detected syntax issues."""
    errors: list[str] = []
    lines = source.splitlines()

    # 1. Must start with a known diagram type keyword
    first_token = lines[0].strip().split()[0].lower() if lines else ""
    if first_token not in _VALID_STARTERS:
        errors.append(f"Must start with a diagram type keyword (got: {first_token!r})")
        return errors  # can't do further checks if type is unknown

    # 2. Unmatched brackets / braces / parens (ignoring strings)
    stripped = _strip_quoted(source)
    for open_c, close_c, name in [("(", ")", "parentheses"), ("[", "]", "brackets"), ("{", "}", "braces")]:
        diff = stripped.count(open_c) - stripped.count(close_c)
        if diff != 0:
            errors.append(f"Unmatched {name}: {'+' if diff > 0 else ''}{diff}")

    # 3. Unmatched subgraph/end
    if first_token in ("graph", "flowchart"):
        sub_count = len(re.findall(r"^\s*subgraph\b", source, re.MULTILINE))
        end_count = len(re.findall(r"^\s*end\b", source, re.MULTILINE))
        if sub_count != end_count:
            errors.append(f"Unmatched subgraph/end: {sub_count} subgraph vs {end_count} end")

    # 4. Arrow syntax — common LLM mistakes
    # Double arrows with no target: A -->
    if re.search(r"-->\s*$", source, re.MULTILINE):
        errors.append("Arrow with no target (line ends with -->)")

    # Arrow to empty node: --> [] or --> ()
    if re.search(r"-->\s*\[\s*\]", source) or re.search(r"-->\s*\(\s*\)", source):
        errors.append("Arrow points to empty node definition")

    # 5. Unmatched quotes in node labels
    for i, line in enumerate(lines, 1):
        dq = line.count('"')
        if dq % 2 != 0:
            errors.append(f"Unmatched double quote on line {i}")
            break  # one is enough

    # 6. Parentheses inside square-bracket node labels (must be quoted)
    #    e.g. A[Frontend (React)] → mermaid v11 interprets (React) as a shape
    #    Fix: A["Frontend (React)"]
    if first_token in ("graph", "flowchart"):
        for i, line in enumerate(lines, 1):
            # Match unquoted bracket labels containing parens: ID[...(...)]
            if re.search(r'\w\[(?!")[^"\]]*\([^)]*\)[^"\]]*\]', line):
                errors.append(
                    f"Line {i}: parentheses inside [...] node label must be quoted — "
                    f'use ["label (detail)"] instead of [label (detail)]'
                )
                break

    # 7. Sequence diagram specific: missing colon after participant
    if first_token == "sequencediagram":
        for i, line in enumerate(lines[1:], 2):
            stripped_line = line.strip()
            if stripped_line and not stripped_line.startswith("%%"):
                # Messages need ->> or -->> with colon
                if ("->>" in stripped_line or "-->>" in stripped_line) and ":" not in stripped_line:
                    errors.append(f"Sequence message on line {i} missing colon separator")
                    break

    # 8. Detect HTML-style tags that mermaid doesn't support
    if re.search(r"<(?!br|sub|sup|b|i|em|strong)[a-zA-Z]+[^>]*>", stripped):
        errors.append("Contains unsupported HTML tags in node labels")

    return errors


def _strip_quoted(source: str) -> str:
    """Remove content inside double-quoted strings to avoid false positives."""
    return re.sub(r'"[^"]*"', '""', source)


def _call_llm_fix(source: str, error: str, llm_fn: Callable[[str, str], str]) -> str:
    system = (
        "You are a Mermaid diagram syntax expert. "
        "Fix the provided diagram so it renders without errors in Mermaid v11. "
        "Common issues: unmatched brackets/quotes, missing 'end' for subgraph, "
        "special characters in node labels need quoting with double quotes. "
        "Return ONLY the corrected Mermaid source code — no markdown fences, "
        "no explanation, no surrounding text."
    )
    user = f"Validation error: {error}\n\nBroken diagram:\n```\n{source}\n```"
    try:
        return llm_fn(system, user)
    except Exception as exc:
        logger.warning("LLM fix call failed: %s", exc)
        return source


def _extract_mermaid_block(text: str) -> Optional[str]:
    """Extract content from ```mermaid ... ``` fences if present."""
    m = re.search(r"```(?:mermaid)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None
