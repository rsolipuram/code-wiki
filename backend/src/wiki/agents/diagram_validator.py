"""Mermaid diagram validation and auto-fix utilities.

Uses the LLM to fix syntax errors when mermaid-cli is unavailable.
Max 3 fix attempts per diagram.
"""

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 3


def validate_mermaid(source: str) -> Tuple[bool, str]:
    """Validate Mermaid diagram syntax.

    Tries npx @mermaid-js/mermaid-cli if available.
    Falls back to simple structural heuristics.

    Returns:
        (is_valid, error_message)  — error_message is "" when valid.
    """
    source = source.strip()
    if not source:
        return False, "Empty diagram source"

    # Quick structural check — must start with a known diagram type keyword
    first_line = source.splitlines()[0].strip().lower()
    known_starters = (
        "graph ", "graph\n", "flowchart ", "flowchart\n",
        "sequencediagram", "classDiagram", "statediagram",
        "erdiagram", "gantt", "pie", "mindmap", "timeline",
        "gitgraph", "xychart", "block-beta", "architecture-beta",
        "journey", "quadrantchart", "requirementdiagram",
    )
    has_valid_start = any(first_line.startswith(s.lower()) for s in known_starters)
    if not has_valid_start:
        # Also accept if it starts with a direction (LR, TD, etc.)
        has_valid_start = bool(re.match(r"^(graph|flowchart)\s+(lr|rl|td|tb|bt|lrtb)\b", first_line))

    if not has_valid_start:
        return False, f"Diagram must start with a valid type keyword (got: {first_line[:60]!r})"

    # Try mermaid-cli via npx if available
    try:
        result = _validate_via_cli(source)
        return result
    except FileNotFoundError:
        # npx not available — use heuristic only
        pass
    except Exception as exc:
        logger.debug("mermaid-cli validation failed: %s", exc)

    # Heuristic: check for obvious syntax errors
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
) -> str:
    """Attempt to fix invalid Mermaid diagram syntax using LLM.

    Args:
        source: The invalid diagram source.
        error: The validation error message.
        llm_fn: Callable(system_prompt, user_prompt) → response_text.
        max_attempts: Maximum fix iterations (default 3).

    Returns:
        Fixed diagram source (best attempt, even if still invalid after max tries).
    """
    current = source
    current_error = error

    for attempt in range(1, max_attempts + 1):
        logger.info("Mermaid fix attempt %d/%d: %s", attempt, max_attempts, current_error[:100])

        fixed = _call_llm_fix(current, current_error, llm_fn)
        fixed = _extract_mermaid_block(fixed) or fixed.strip()

        is_valid, new_error = validate_mermaid(fixed)
        if is_valid:
            logger.info("Mermaid fixed after %d attempt(s)", attempt)
            return fixed

        current = fixed
        current_error = new_error

    logger.warning("Mermaid diagram could not be fixed after %d attempts", max_attempts)
    return current  # best-effort: return last attempt


# ── Private helpers ───────────────────────────────────────────────────────────

def _validate_via_cli(source: str) -> Tuple[bool, str]:
    """Validate using npx @mermaid-js/mermaid-cli."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp_in = f.name

    tmp_out = tmp_in.replace(".mmd", ".svg")
    try:
        result = subprocess.run(
            ["npx", "--yes", "-q", "@mermaid-js/mermaid-cli", "-i", tmp_in, "-o", tmp_out],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, ""
        stderr = (result.stderr or result.stdout or "").strip()
        # Extract relevant error line
        error_lines = [l for l in stderr.splitlines() if "error" in l.lower() or "parse" in l.lower()]
        error_msg = error_lines[0] if error_lines else stderr[:200]
        return False, error_msg
    finally:
        Path(tmp_in).unlink(missing_ok=True)
        Path(tmp_out).unlink(missing_ok=True)


def _heuristic_check(source: str) -> list[str]:
    """Return list of detected syntax issues."""
    errors = []

    # Unmatched brackets/braces
    for open_c, close_c in [("(", ")"), ("[", "]"), ("{", "}")]:
        opens = source.count(open_c)
        closes = source.count(close_c)
        if opens != closes:
            errors.append(f"Unmatched {open_c!r}: {opens} open vs {closes} close")

    # Empty node IDs like []  or ()
    if re.search(r"-->\s*\[\s*\]", source) or re.search(r"-->\s*\(\s*\)", source):
        errors.append("Arrow points to empty node definition")

    return errors


def _call_llm_fix(source: str, error: str, llm_fn: Callable[[str, str], str]) -> str:
    system = (
        "You are a Mermaid diagram syntax expert. "
        "Fix the provided diagram so it renders without errors. "
        "Return ONLY the corrected Mermaid source code — no markdown fences, no explanation."
    )
    user = f"Error: {error}\n\nDiagram to fix:\n{source}"
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
