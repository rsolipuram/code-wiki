"""V4 Code Embedder — deterministic-first code extraction.

Primary behavior is deterministic:
1) file + lines     -> exact slice
2) file + symbol    -> exact CodeEntity span from DB index
3) symbol only      -> unique CodeEntity span from DB index

Only when confidence is low do we allow an LLM override to pick a line range
from a concrete source file. The override is strictly validated before use.
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine, or_
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.code_entity import CodeEntity, Module
from src.models.wiki import Wiki
from src.wiki.agents.model import get_wiki_model

logger = logging.getLogger(__name__)

MAX_EXPLICIT_LINES = 240
MAX_SYMBOL_LINES = 180
MAX_QDRANT_WINDOW = 50
MAX_LLM_OVERRIDE_LINES = 100

def _env_float(name: str, default: float) -> float:
    """Safely parse a float env var, with warning + fallback + clamping."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; falling back to %.2f", name, raw, default)
        return default
    if value < 0.0 or value > 1.0:
        clamped = max(0.0, min(1.0, value))
        logger.warning("%s=%s out of range [0,1]; clamped to %.2f", name, value, clamped)
        return clamped
    return value


LOW_CONF_THRESHOLD = _env_float("WIKI_CODE_LOW_CONF_THRESHOLD", 0.60)
LLM_OVERRIDE_MIN_CONFIDENCE = _env_float("WIKI_CODE_LLM_MIN_CONF", 0.60)
ALLOW_LLM_OVERRIDE_ON_LOW_CONF = (
    os.environ.get("WIKI_CODE_LLM_OVERRIDE_ON_LOW_CONF", "true").strip().lower() in {"1", "true", "yes", "on"}
)
_ENGINE: Optional[Engine] = None


def _detect_language(file_path: str) -> str:
    """Infer language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".md": "markdown",
    }
    suffix = Path(file_path).suffix.lower()
    return ext_map.get(suffix, "text")


def _normalize_rel_path(path: str) -> str:
    """Normalize repository-relative paths for matching."""
    normalized = str(Path(path)).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _escape_like(term: str) -> str:
    """Escape SQL LIKE metacharacters for literal matching."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _get_engine() -> Engine:
    """Create or reuse the shared SQLAlchemy engine for this process."""
    global _ENGINE
    if _ENGINE is None:
        settings = get_settings()
        _ENGINE = create_engine(settings.database_url)
    return _ENGINE


def _resolve_repo_file(repo_path: str, file_path: str) -> Optional[Path]:
    """Resolve and validate a repository-relative file path."""
    root = Path(repo_path).resolve()
    full = (root / file_path).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        return None
    if not full.is_file():
        return None
    return full


def _read_file_span(
    repo_path: str,
    file_path: str,
    start_line: int,
    end_line: int,
    *,
    max_lines: int,
) -> Optional[dict]:
    """Read an exact file span with bounded length."""
    full_path = _resolve_repo_file(repo_path, file_path)
    if full_path is None:
        return None

    try:
        content = full_path.read_text(errors="replace")
    except Exception:
        return None

    lines = content.splitlines()
    total = len(lines)
    start = max(1, start_line)
    end = min(total, end_line)
    if end < start:
        return None
    if end - start + 1 > max_lines:
        return None

    selected = lines[start - 1:end]
    return {
        "code": "\n".join(selected),
        "language": _detect_language(file_path),
        "file_path": _normalize_rel_path(file_path),
        "start_line": start,
        "end_line": end,
        "validated": bool(selected),
    }


def _parse_line_range(lines_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse line ranges ('10-35' or '10') to tuple."""
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", lines_str or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^\s*(\d+)\s*$", lines_str or "")
    if m:
        start = int(m.group(1))
        return start, start
    return None, None


def _search_qdrant(query: str, repository_id: str, entity_type: Optional[str] = None) -> Optional[dict]:
    """Return top Qdrant hit with payload + score."""
    try:
        from src.llm.embeddings import embed
        from src.storage.vector_db import search
    except ImportError:
        logger.warning("Qdrant/embeddings not available")
        return None

    try:
        vector = embed(query)
        filters = {"repo_id": repository_id}
        if entity_type:
            filters["entity_type"] = entity_type
        results = search(
            collection="code_entities",
            vector=vector,
            limit=1,
            filters=filters,
            score_threshold=0.25,
        )
        if not results:
            return None
        top = results[0]
        payload = top.get("payload", {}) or {}
        return {
            "file_path": payload.get("file_path", ""),
            "line_start": payload.get("line_start"),
            "line_end": payload.get("line_end"),
            "score": float(top.get("score", 0.0) or 0.0),
        }
    except Exception as exc:
        logger.warning("Qdrant search failed for %r: %s", query, exc)
        return None


def _lookup_entity_span(
    db: Session,
    repository_id: str,
    symbol: str,
    file_path: Optional[str] = None,
) -> tuple[Optional[tuple[str, int, int]], str]:
    """Resolve symbol to a unique entity span from persisted code_entities."""
    try:
        base_query = (
            db.query(CodeEntity)
            .join(Module, CodeEntity.module_id == Module.id)
            .join(Wiki, Module.wiki_id == Wiki.id)
            .filter(Wiki.repository_id == repository_id)
        )

        norm_file = _normalize_rel_path(file_path or "")
        if norm_file:
            base_query = base_query.filter(CodeEntity.file_path == norm_file)

        def _valid(rows: list[CodeEntity]) -> list[CodeEntity]:
            return [r for r in rows if r.file_path and r.line_start and r.line_end]

        # Deterministic phase 1: exact qualified_name
        exact_qn = _valid(
            base_query
            .filter(CodeEntity.qualified_name == symbol)
            .order_by(CodeEntity.file_path.asc(), CodeEntity.line_start.asc())
            .all()
        )
        if len(exact_qn) == 1:
            c = exact_qn[0]
            return (_normalize_rel_path(c.file_path), int(c.line_start), int(c.line_end)), ""

        # Deterministic phase 2: exact short name
        exact_name = _valid(
            base_query
            .filter(CodeEntity.name == symbol)
            .order_by(CodeEntity.file_path.asc(), CodeEntity.line_start.asc())
            .all()
        )
        if len(exact_name) == 1:
            c = exact_name[0]
            return (_normalize_rel_path(c.file_path), int(c.line_start), int(c.line_end)), ""

        # Fallback phase: qualified suffix matches, deterministically ordered and capped.
        escaped_symbol = _escape_like(symbol)
        suffix_matches = _valid(
            base_query
            .filter(CodeEntity.qualified_name.like(f"%.{escaped_symbol}", escape="\\"))
            .order_by(CodeEntity.file_path.asc(), CodeEntity.line_start.asc())
            .limit(200)
            .all()
        )
        if len(suffix_matches) == 1:
            c = suffix_matches[0]
            return (_normalize_rel_path(c.file_path), int(c.line_start), int(c.line_end)), ""

        if not (exact_qn or exact_name or suffix_matches):
            return None, "symbol_not_found"
        return None, "symbol_ambiguous"
    except Exception as exc:
        logger.warning("Entity span DB lookup failed (symbol=%r): %s", symbol, exc)
        return None, "db_lookup_failed"


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract first JSON object from model output."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("```")
        ).strip()

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_override_range(
    spec: dict,
    repo_path: str,
    candidate_file: str,
    candidate_center_line: Optional[int],
) -> Optional[dict]:
    """Use LLM to pick a line range for low-confidence cases, then validate."""
    full_path = _resolve_repo_file(repo_path, candidate_file)
    if full_path is None:
        return None

    try:
        all_lines = full_path.read_text(errors="replace").splitlines()
    except Exception:
        return None

    if not all_lines:
        return None

    total = len(all_lines)
    if candidate_center_line and 1 <= candidate_center_line <= total:
        win_start = max(1, candidate_center_line - 220)
        win_end = min(total, candidate_center_line + 220)
    else:
        win_start = 1
        win_end = min(total, 440)

    window_lines = all_lines[win_start - 1:win_end]
    numbered = "\n".join(f"{win_start + i}: {line}" for i, line in enumerate(window_lines))

    symbol = (spec.get("symbol") or "").strip()
    context = (spec.get("context") or "").strip()

    prompt = (
        "Select the best contiguous code range from the provided source window.\n"
        "Return ONLY JSON object:\n"
        '{"start_line": <int>, "end_line": <int>, "confidence": <0-1>, "reason": "<short>"}\n\n'
        f"File: {candidate_file}\n"
        f"Requested symbol: {symbol or '(none)'}\n"
        f"Requested context: {context or '(none)'}\n"
        f"Allowed window: {win_start}-{win_end}\n"
        f"Max range length: {MAX_LLM_OVERRIDE_LINES} lines\n"
        "Rules:\n"
        "1) start_line/end_line MUST be inside allowed window.\n"
        "2) Range MUST be contiguous.\n"
        "3) If symbol is present, selected range should include that symbol text.\n\n"
        "Source window:\n"
        f"{numbered}"
    )

    try:
        model = get_wiki_model(temperature=0.0, max_tokens=400)
        resp = model.invoke([{"role": "user", "content": prompt}])
        data = _extract_json_object(resp.content if hasattr(resp, "content") else str(resp))
    except Exception as exc:
        logger.warning("LLM override failed for %r: %s", candidate_file, exc)
        return None

    if not data:
        return None

    try:
        start = int(data.get("start_line"))
        end = int(data.get("end_line"))
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None

    if conf < LLM_OVERRIDE_MIN_CONFIDENCE:
        return None
    if start < win_start or end > win_end or end < start:
        return None
    if end - start + 1 > MAX_LLM_OVERRIDE_LINES:
        return None

    span = _read_file_span(
        repo_path=repo_path,
        file_path=candidate_file,
        start_line=start,
        end_line=end,
        max_lines=MAX_LLM_OVERRIDE_LINES,
    )
    if not span or not span.get("code"):
        return None

    if symbol and symbol not in span["code"]:
        return None

    return {
        **span,
        "confidence": conf,
        "resolution": "llm-override",
        "llm_override_used": True,
    }


def _base_result(spec: dict) -> dict:
    """Create an unresolved default result object."""
    return {
        "tag_index": int(spec.get("tag_index", 0) or 0),
        "code": "",
        "language": spec.get("lang", "") or "text",
        "file_path": "",
        "start_line": None,
        "end_line": None,
        "validated": False,
        "context": spec.get("context", "") or "",
        "confidence": 0.0,
        "resolution": "unresolved",
        "unresolved_reason": "",
        "llm_override_used": False,
    }


def _resolve_one_spec(
    spec: dict,
    repo_path: str,
    repository_id: str,
    db: Session,
) -> dict:
    """Resolve one code spec with deterministic-first + low-confidence override."""
    result = _base_result(spec)
    file_path = _normalize_rel_path(spec.get("file", "") or "")
    lines_str = (spec.get("lines", "") or "").strip()
    symbol = (spec.get("symbol", "") or "").strip()
    context = (spec.get("context", "") or "").strip()
    forced_lang = (spec.get("lang", "") or "").strip()
    strict_file_symbol = bool(file_path and symbol)

    candidate_file = file_path or ""
    candidate_line = None
    low_confidence = False

    # 1) Explicit file + lines (strict deterministic)
    if file_path and lines_str:
        start, end = _parse_line_range(lines_str)
        if start is None or end is None:
            result["unresolved_reason"] = "invalid_lines_format"
            return result

        span = _read_file_span(
            repo_path=repo_path,
            file_path=file_path,
            start_line=start,
            end_line=end,
            max_lines=MAX_EXPLICIT_LINES,
        )
        if not span:
            result["unresolved_reason"] = "file_or_range_invalid"
            return result

        if forced_lang:
            span["language"] = forced_lang
        return {
            **result,
            **span,
            "confidence": 1.0,
            "resolution": "explicit-lines",
            "unresolved_reason": "",
        }

    # 2) file + symbol (strict deterministic via DB entity span)
    if file_path and symbol:
        resolved, reason = _lookup_entity_span(
            db=db,
            repository_id=repository_id,
            symbol=symbol,
            file_path=file_path,
        )
        if resolved:
            rs_file, rs_start, rs_end = resolved
            span_len = rs_end - rs_start + 1
            if span_len > MAX_SYMBOL_LINES:
                low_confidence = True
                candidate_file = rs_file
                candidate_line = rs_start
                result["unresolved_reason"] = "symbol_span_too_large"
            else:
                span = _read_file_span(
                    repo_path=repo_path,
                    file_path=rs_file,
                    start_line=rs_start,
                    end_line=rs_end,
                    max_lines=MAX_SYMBOL_LINES,
                )
                if span:
                    if forced_lang:
                        span["language"] = forced_lang
                    return {
                        **result,
                        **span,
                        "confidence": 1.0,
                        "resolution": "file-symbol-db",
                        "unresolved_reason": "",
                    }
                result["unresolved_reason"] = "file_or_range_invalid"
                return result
        else:
            low_confidence = True
            result["unresolved_reason"] = reason or "symbol_not_found"

    # 3) file-only deterministic fallback (bounded top-of-file excerpt)
    if file_path and not lines_str and not symbol:
        span = _read_file_span(
            repo_path=repo_path,
            file_path=file_path,
            start_line=1,
            end_line=MAX_QDRANT_WINDOW,
            max_lines=MAX_QDRANT_WINDOW,
        )
        if span:
            if forced_lang:
                span["language"] = forced_lang
            return {
                **result,
                **span,
                "confidence": 1.0,
                "resolution": "file-only",
                "unresolved_reason": "",
            }
        result["unresolved_reason"] = "file_or_range_invalid"
        return result

    # 4) symbol-only deterministic via DB if unique
    if not file_path and symbol:
        resolved, reason = _lookup_entity_span(
            db=db,
            repository_id=repository_id,
            symbol=symbol,
            file_path=None,
        )
        if resolved:
            rs_file, rs_start, rs_end = resolved
            span_len = rs_end - rs_start + 1
            if span_len <= MAX_SYMBOL_LINES:
                span = _read_file_span(
                    repo_path=repo_path,
                    file_path=rs_file,
                    start_line=rs_start,
                    end_line=rs_end,
                    max_lines=MAX_SYMBOL_LINES,
                )
                if span:
                    if forced_lang:
                        span["language"] = forced_lang
                    return {
                        **result,
                        **span,
                        "confidence": 1.0,
                        "resolution": "symbol-db",
                        "unresolved_reason": "",
                    }
            low_confidence = True
            candidate_file = rs_file
            candidate_line = rs_start
            result["unresolved_reason"] = "symbol_span_too_large"
        else:
            low_confidence = True
            result["unresolved_reason"] = reason or "symbol_not_found"

    # 5) Qdrant hint (low-confidence candidate only)
    q_query = symbol or context
    qdrant_score = 0.0
    if q_query:
        hit = _search_qdrant(q_query, repository_id)
        if hit:
            qdrant_score = float(hit.get("score", 0.0) or 0.0)
            hit_file = _normalize_rel_path(hit.get("file_path", "") or "")
            hit_line = hit.get("line_start")
            if hit_file:
                if strict_file_symbol:
                    # Keep file+symbol contract strict: no cross-file substitution.
                    if hit_file == file_path:
                        candidate_file = hit_file
                else:
                    candidate_file = hit_file
            if isinstance(hit_line, int) and hit_line > 0:
                candidate_line = hit_line

            if (
                not strict_file_symbol
                and candidate_file
                and candidate_line
                and qdrant_score >= 0.78
            ):
                span = _read_file_span(
                    repo_path=repo_path,
                    file_path=candidate_file,
                    start_line=max(1, candidate_line - 2),
                    end_line=candidate_line + (MAX_QDRANT_WINDOW - 3),
                    max_lines=MAX_QDRANT_WINDOW,
                )
                if span:
                    if forced_lang:
                        span["language"] = forced_lang
                    provisional = {
                        **result,
                        **span,
                        "confidence": qdrant_score,
                        "resolution": "qdrant-candidate",
                        "unresolved_reason": "low_confidence_candidate",
                    }
                    low_confidence = qdrant_score < LOW_CONF_THRESHOLD
                    if not low_confidence:
                        return provisional
                    result = provisional
            else:
                low_confidence = True

    # 6) LLM override only when confidence is low and candidate file exists
    if (
        ALLOW_LLM_OVERRIDE_ON_LOW_CONF
        and low_confidence
        and candidate_file
        and _resolve_repo_file(repo_path, candidate_file) is not None
    ):
        override = _llm_override_range(
            spec=spec,
            repo_path=repo_path,
            candidate_file=candidate_file,
            candidate_center_line=candidate_line,
        )
        if override:
            if forced_lang:
                override["language"] = forced_lang
            return {
                **result,
                **override,
                "validated": True,
                "unresolved_reason": "",
            }
        if not result.get("validated"):
            result["unresolved_reason"] = "llm_override_failed"

    if not result.get("validated") and not result.get("unresolved_reason"):
        result["unresolved_reason"] = "could_not_resolve_spec"

    logger.warning(
        "Code embedder unresolved tag_index=%s file=%r symbol=%r reason=%s",
        result["tag_index"],
        file_path,
        symbol,
        result.get("unresolved_reason", ""),
    )
    return result


def v4_code_embedder_node(state: dict) -> dict:
    """LangGraph node: retrieve source code for all code placeholders."""
    code_specs = state.get("code_specs") or []
    if not code_specs:
        return {"code_results": []}

    repo_path = state.get("repo_path", "")
    repository_id = state.get("repository_id", "")

    t0 = time.monotonic()
    engine = _get_engine()
    with Session(engine) as db:
        results = []
        for spec in code_specs:
            try:
                results.append(_resolve_one_spec(spec, repo_path, repository_id, db))
            except Exception as exc:
                unresolved = _base_result(spec)
                unresolved["unresolved_reason"] = "resolver_exception"
                logger.warning(
                    "Code embedder spec failed tag_index=%s: %s",
                    unresolved["tag_index"],
                    exc,
                )
                results.append(unresolved)
    elapsed = time.monotonic() - t0

    resolved_count = sum(1 for r in results if r.get("validated"))
    llm_override_count = sum(1 for r in results if r.get("llm_override_used"))
    logger.info(
        "Code embedder: %d/%d resolved, %d via llm override, %.1fs",
        resolved_count,
        len(results),
        llm_override_count,
        elapsed,
    )

    return {"code_results": results}
