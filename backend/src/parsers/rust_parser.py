"""Rust source parser using regex + brace tracking.

This parser is intentionally lightweight and dependency-free. It extracts:
- module entity with imports
- top-level functions
- impl methods
- structs/enums (as class entities)
- traits (as interface entities)
- top-level const/static/type aliases (as variable entities)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from src.parsers.base import CallEdge, CodeParser, Dependency, ParsedEntity

logger = logging.getLogger(__name__)


_FN_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe)\s+)*fn\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)(?:\s*<[^>]+>)?\s*\("
)
_STRUCT_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_ENUM_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_TRAIT_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_IMPL_START_RE = re.compile(r"^\s*(?:unsafe\s+)?impl\b")
_CONST_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const|static|type)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_USE_RE = re.compile(r"(?ms)^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+(.+?);")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_:]*)(?:\s*::\s*<[^>]+>)?\s*(?:!\s*)?\(")

_RUST_CALL_EXCLUDE = {
    "if",
    "for",
    "while",
    "loop",
    "match",
    "return",
    "let",
    "fn",
    "impl",
    "struct",
    "enum",
    "trait",
    "const",
    "static",
    "type",
    "pub",
    "use",
    "where",
    "async",
    "await",
    "move",
    "unsafe",
    "crate",
    "self",
    "super",
    "Self",
}


def _strip_inline_comment(line: str) -> str:
    """Best-effort inline comment stripping for brace counting and matching."""
    idx = line.find("//")
    if idx >= 0:
        return line[:idx]
    return line


def _looks_like_char_literal_start(line: str, idx: int) -> bool:
    """Return True when line[idx] appears to start a Rust char literal.

    Distinguishes `'x'` / `'\\n'` from lifetime annotations like `'a`.
    """
    if idx < 0 or idx >= len(line) or line[idx] != "'":
        return False
    if idx + 2 >= len(line):
        return False
    if line[idx + 1] == "\\":
        end = idx + 3
    else:
        end = idx + 2
    return end < len(line) and line[end] == "'"


def _raw_string_prefix_len(line: str, idx: int) -> int:
    """Return Rust raw-string prefix length at idx, else 0.

    Supports: r" .. ", r#" .. "#, br" .. ", br#" .. "#.
    """
    n = len(line)
    if idx >= n:
        return 0
    if line[idx] == "r":
        j = idx + 1
    elif line[idx] == "b" and idx + 1 < n and line[idx + 1] == "r":
        j = idx + 2
    else:
        return 0

    while j < n and line[j] == "#":
        j += 1
    if j < n and line[j] == '"':
        return j - idx + 1
    return 0


def _consume_raw_string(line: str, idx: int) -> tuple[int, Optional[int]]:
    """Consume Rust raw string from idx.

    Returns (next_index, open_hashes):
    - open_hashes is None when the raw string closed on this line.
    - open_hashes is an integer when string remains open across lines.
    """
    prefix_len = _raw_string_prefix_len(line, idx)
    if prefix_len == 0:
        return idx, None
    start = idx
    hashes = line[start:start + prefix_len].count("#")
    end_seq = '"' + ("#" * hashes)
    j = start + prefix_len
    k = line.find(end_seq, j)
    if k == -1:
        return len(line), hashes
    return k + len(end_seq), None


def _structural_code(
    line: str,
    block_comment_depth: int,
    in_string: bool = False,
    in_char: bool = False,
    raw_string_hashes: Optional[int] = None,
) -> tuple[str, int, bool, bool, Optional[int]]:
    """Return code used for structural parsing (brace counting, fn matching).

    Removes line/block comments and string/char literals so braces inside those
    regions do not corrupt parser depth tracking.

    Literal state is carried across lines to avoid counting braces from
    unterminated string/char/raw-string literals.
    """
    out: list[str] = []
    i = 0
    n = len(line)

    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""

        if raw_string_hashes is not None:
            end_seq = '"' + ("#" * raw_string_hashes)
            k = line.find(end_seq, i)
            if k == -1:
                i = n
                continue
            raw_string_hashes = None
            i = k + len(end_seq)
            continue

        if block_comment_depth > 0:
            if ch == "/" and nxt == "*":
                block_comment_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_comment_depth -= 1
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and nxt == "*":
            block_comment_depth += 1
            i += 2
            continue
        if ch == "/" and nxt == "/":
            break
        raw_advance, raw_open_hashes = _consume_raw_string(line, i)
        if raw_advance > i:
            raw_string_hashes = raw_open_hashes
            i = raw_advance
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            if _looks_like_char_literal_start(line, i):
                in_char = True
                i += 1
                continue
            # Likely a lifetime annotation (e.g. `'a`) — keep it as code.
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out), block_comment_depth, in_string, in_char, raw_string_hashes


def _module_name(file_path: str, repo_path: str = "") -> str:
    p = Path(file_path).resolve()
    if repo_path:
        root = Path(repo_path).resolve()
        try:
            rel = p.with_suffix("").relative_to(root)
            return ".".join(rel.parts)
        except ValueError:
            pass
    return ".".join(p.with_suffix("").parts)


def _collect_doc_comments(lines: list[str], idx: int) -> Optional[str]:
    """Collect contiguous Rust doc comments immediately above line idx."""
    docs: list[str] = []
    i = idx - 1
    while i >= 0:
        raw = lines[i].strip()
        if raw.startswith("///"):
            docs.append(raw[3:].strip())
            i -= 1
            continue
        if raw.startswith("//!"):
            docs.append(raw[3:].strip())
            i -= 1
            continue
        break
    if not docs:
        return None
    docs.reverse()
    return "\n".join(d for d in docs if d)


def _collect_module_doc(lines: list[str]) -> Optional[str]:
    docs: list[str] = []
    for line in lines:
        raw = line.strip()
        if raw.startswith("//!"):
            docs.append(raw[3:].strip())
            continue
        if raw == "":
            if docs:
                continue
            continue
        break
    if not docs:
        return None
    return "\n".join(d for d in docs if d)


def _collect_signature(lines: list[str], idx: int) -> str:
    parts: list[str] = []
    for i in range(idx, min(len(lines), idx + 8)):
        s = lines[i].strip()
        if not s:
            continue
        parts.append(s)
        if "{" in s or s.endswith(";"):
            break
    return " ".join(parts).strip()


def _find_block_end(lines: list[str], start_idx: int) -> int:
    """Find closing brace line for a declaration. Returns 1-based line number."""
    saw_open = False
    depth = 0
    block_comment_depth = 0
    in_string = False
    in_char = False
    raw_string_hashes: Optional[int] = None
    for i in range(start_idx, len(lines)):
        code, block_comment_depth, in_string, in_char, raw_string_hashes = _structural_code(
            lines[i],
            block_comment_depth,
            in_string,
            in_char,
            raw_string_hashes,
        )
        opens = code.count("{")
        closes = code.count("}")
        if opens > 0:
            saw_open = True
        depth += opens
        depth -= closes
        if saw_open and depth <= 0:
            return i + 1
    return start_idx + 1


def _extract_use_paths(source: str) -> list[str]:
    imports: list[str] = []
    seen: set[str] = set()

    for m in _USE_RE.finditer(source):
        clause = " ".join(m.group(1).split())
        clause = re.sub(r"\s+as\s+[A-Za-z_][A-Za-z0-9_]*", "", clause)
        clause = clause.strip()
        if not clause:
            continue

        expanded = _expand_use_clause(clause)

        for raw in expanded:
            normalized = raw.replace("::", ".").replace(" ", "")
            if normalized and normalized not in seen:
                seen.add(normalized)
                imports.append(normalized)

    return imports


def _extract_calls(code: str, exclude: Optional[set[str]] = None) -> list[str]:
    excluded = _RUST_CALL_EXCLUDE | (exclude or set())
    calls: list[str] = []
    seen: set[str] = set()
    for match in _CALL_RE.finditer(code):
        raw = match.group(1).strip()
        if not raw:
            continue
        short = raw.split("::")[-1]
        if short in excluded:
            continue
        normalized = raw.replace("::", ".")
        if normalized not in seen:
            seen.add(normalized)
            calls.append(normalized)
    return calls


def _split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
            current.append(ch)
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            current.append(ch)
            continue
        if ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
            continue
        current.append(ch)
    token = "".join(current).strip()
    if token:
        parts.append(token)
    return parts


def _join_use_path(prefix: str, token: str) -> str:
    p = prefix.strip()
    t = token.strip()
    if t == "self":
        return p.rstrip(":")
    if not p:
        return t
    if p.endswith("::"):
        return f"{p}{t}"
    return f"{p}::{t}"


def _expand_use_clause(clause: str) -> list[str]:
    """Expand grouped use trees with brace-depth awareness.

    Example:
      crate::{a::{b,c}, d} -> [crate::a::b, crate::a::c, crate::d]
    """
    clause = clause.strip()
    if not clause:
        return []

    if "{" not in clause:
        return [clause]

    brace_idx = clause.find("{")
    prefix = clause[:brace_idx].rstrip()
    if prefix.endswith("::"):
        base = prefix
    else:
        base = f"{prefix}::" if prefix else ""

    inner = clause[brace_idx + 1:]
    if inner.endswith("}"):
        inner = inner[:-1]

    expanded: list[str] = []
    for token in _split_top_level_csv(inner):
        token = token.strip()
        if not token:
            continue
        if "{" in token and token.endswith("}"):
            nested_prefix = token[:token.find("{")].strip()
            nested_inner = token[token.find("{") + 1:-1]
            combined_prefix = _join_use_path(base.rstrip(":"), nested_prefix)
            nested_clause = f"{combined_prefix}::{{{nested_inner}}}"
            expanded.extend(_expand_use_clause(nested_clause))
            continue
        expanded.append(_join_use_path(base.rstrip(":"), token))
    return expanded


def _split_top_level_keyword(text: str, keyword: str) -> tuple[str, str] | None:
    """Split `text` on keyword when outside angle/paren/bracket/brace groups."""
    k = f" {keyword} "
    angle = 0
    paren = 0
    bracket = 0
    brace = 0
    i = 0
    while i <= len(text) - len(k):
        ch = text[i]
        if ch == "<":
            angle += 1
        elif ch == ">":
            if angle > 0:
                angle -= 1
        elif ch == "(":
            paren += 1
        elif ch == ")":
            if paren > 0:
                paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            if bracket > 0:
                bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            if brace > 0:
                brace -= 1

        if angle == 0 and paren == 0 and bracket == 0 and brace == 0:
            if text[i:i + len(k)] == k:
                return text[:i], text[i + len(k):]
        i += 1
    return None


def _strip_top_level_where(text: str) -> str:
    split = _split_top_level_keyword(text, "where")
    if split is None:
        return text
    return split[0].strip()


def _strip_leading_impl_generics(text: str) -> str:
    s = text.strip()
    if not s.startswith("<"):
        return s
    depth = 0
    for i, ch in enumerate(s):
        if ch == "<":
            depth += 1
        elif ch == ">":
            if depth > 0:
                depth -= 1
            if depth == 0:
                return s[i + 1:].strip()
    return s


def _remove_angle_groups(text: str) -> str:
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch == "<":
            depth += 1
            continue
        if ch == ">":
            if depth > 0:
                depth -= 1
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def _normalize_type_name(raw: str) -> str:
    s = raw.strip()
    s = _strip_top_level_where(s)
    s = s.split("=", 1)[0].strip()
    s = s.split("+", 1)[0].strip()
    s = re.sub(r"^\s*(?:dyn\s+)?", "", s)
    s = re.sub(r"^[&*]+\s*", "", s)
    s = re.sub(r"\bmut\s+", "", s)
    s = _remove_angle_groups(s)
    s = s.replace("::", ".")
    s = re.sub(r"[^A-Za-z0-9_.]", "", s)
    if not s:
        return ""
    return s


def _extract_impl_target(raw_header: str) -> tuple[str, Optional[str]]:
    """Return (owner_name, trait_name?) for impl headers."""
    header = raw_header.strip()
    if "{" in header:
        header = header.split("{", 1)[0].strip()
    header = re.sub(r"^\s*(?:unsafe\s+)?impl\s*", "", header)
    header = _strip_leading_impl_generics(header)
    header = _strip_top_level_where(header)

    split = _split_top_level_keyword(header, "for")
    if split is not None:
        trait_raw, target_raw = split
        trait_name = _normalize_type_name(trait_raw)
        owner = _normalize_type_name(target_raw) or "Impl"
        return owner, (trait_name or None)

    owner = _normalize_type_name(header) or "Impl"
    return owner, None


def _find_impl_blocks(lines: list[str]) -> list[tuple[int, int, str, Optional[str]]]:
    """Return (start_line, end_line, owner_name, trait_name?) for top-level impl blocks."""
    blocks: list[tuple[int, int, str, Optional[str]]] = []
    depth = 0
    block_comment_depth = 0
    in_string = False
    in_char = False
    raw_string_hashes: Optional[int] = None
    header_start: Optional[int] = None
    header_parts: list[str] = []
    for idx, line in enumerate(lines):
        code, block_comment_depth, in_string, in_char, raw_string_hashes = _structural_code(
            line,
            block_comment_depth,
            in_string,
            in_char,
            raw_string_hashes,
        )
        stripped = code.strip()
        if depth == 0:
            if header_start is None and _IMPL_START_RE.match(stripped):
                header_start = idx + 1
                header_parts = [stripped]
            elif header_start is not None and stripped:
                header_parts.append(stripped)

            if header_start is not None and "{" in stripped:
                header = " ".join(header_parts)
                owner, trait = _extract_impl_target(header)
                end_line = _find_block_end(lines, header_start - 1)
                blocks.append((header_start, end_line, owner, trait))
                header_start = None
                header_parts = []
            elif header_start is not None and stripped.endswith(";"):
                # e.g., trait impl declarations without body (rare/invalid contexts)
                header_start = None
                header_parts = []

        depth += code.count("{")
        depth -= code.count("}")
        if depth < 0:
            depth = 0
    return blocks


def _find_fn_names_at_depth(code: str, starting_depth: int, target_depth: int = 1) -> list[str]:
    """Find function names declared while scanner depth equals target_depth."""
    names: list[str] = []
    depth = starting_depth
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == target_depth:
            m = _FN_RE.match(code[i:])
            if m:
                names.append(m.group(1))
                i += max(m.end(), 1)
                continue
        i += 1
    return names


class RustParser(CodeParser):
    """Parser for Rust source files."""

    def parse_file(self, file_path: str, repo_path: str = "") -> list[ParsedEntity]:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            return []

        lines = source.splitlines()
        total_lines = len(lines)
        module_name = _module_name(file_path, repo_path)
        imports = _extract_use_paths(source)

        entities: list[ParsedEntity] = [
            ParsedEntity(
                name=module_name.split(".")[-1],
                qualified_name=module_name,
                entity_type="module",
                file_path=file_path,
                line_start=1,
                line_end=max(total_lines, 1),
                docstring=_collect_module_doc(lines),
                imports=imports,
            )
        ]

        impl_blocks = _find_impl_blocks(lines)

        # Top-level declarations.
        depth = 0
        block_comment_depth = 0
        in_string = False
        in_char = False
        raw_string_hashes: Optional[int] = None
        for idx, line in enumerate(lines):
            code, block_comment_depth, in_string, in_char, raw_string_hashes = _structural_code(
                line,
                block_comment_depth,
                in_string,
                in_char,
                raw_string_hashes,
            )
            stripped = code.strip()
            line_no = idx + 1

            if depth == 0 and stripped:
                doc = _collect_doc_comments(lines, idx)

                m_struct = _STRUCT_RE.match(stripped)
                if m_struct:
                    name = m_struct.group(1)
                    end = _find_block_end(lines, idx)
                    entities.append(
                        ParsedEntity(
                            name=name,
                            qualified_name=f"{module_name}.{name}",
                            entity_type="class",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=end,
                            docstring=doc,
                            entity_metadata={"kind": "struct"},
                        )
                    )

                m_enum = _ENUM_RE.match(stripped)
                if m_enum:
                    name = m_enum.group(1)
                    end = _find_block_end(lines, idx)
                    entities.append(
                        ParsedEntity(
                            name=name,
                            qualified_name=f"{module_name}.{name}",
                            entity_type="class",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=end,
                            docstring=doc,
                            entity_metadata={"kind": "enum"},
                        )
                    )

                m_trait = _TRAIT_RE.match(stripped)
                if m_trait:
                    name = m_trait.group(1)
                    end = _find_block_end(lines, idx)
                    entities.append(
                        ParsedEntity(
                            name=name,
                            qualified_name=f"{module_name}.{name}",
                            entity_type="interface",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=end,
                            docstring=doc,
                            entity_metadata={"kind": "trait"},
                        )
                    )

                m_const = _CONST_RE.match(stripped)
                if m_const:
                    name = m_const.group(1)
                    entities.append(
                        ParsedEntity(
                            name=name,
                            qualified_name=f"{module_name}.{name}",
                            entity_type="variable",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=line_no,
                            docstring=doc,
                        )
                    )

                m_fn = _FN_RE.match(stripped)
                if m_fn:
                    name = m_fn.group(1)
                    end = _find_block_end(lines, idx)
                    snippet = "\n".join(lines[idx:end])
                    entities.append(
                        ParsedEntity(
                            name=name,
                            qualified_name=f"{module_name}.{name}",
                            entity_type="function",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=end,
                            signature=_collect_signature(lines, idx),
                            docstring=doc,
                            calls=_extract_calls(snippet, exclude={name}),
                            entity_metadata={"is_async": "async fn" in stripped},
                        )
                    )

            depth += code.count("{")
            depth -= code.count("}")
            if depth < 0:
                depth = 0

        # Impl methods: only capture direct children of impl blocks (depth == 1),
        # not nested local functions inside method bodies.
        for start_line, end_line, target, trait_name in impl_blocks:
            impl_depth = 0
            block_comment_depth = 0
            in_string = False
            in_char = False
            raw_string_hashes: Optional[int] = None
            for line_no in range(start_line, end_line + 1):
                idx = line_no - 1
                code, block_comment_depth, in_string, in_char, raw_string_hashes = _structural_code(
                    lines[idx],
                    block_comment_depth,
                    in_string,
                    in_char,
                    raw_string_hashes,
                )
                depth_before = impl_depth

                for name in _find_fn_names_at_depth(code, depth_before, target_depth=1):
                    method_end = min(_find_block_end(lines, idx), end_line)
                    snippet = "\n".join(lines[idx:method_end])
                    q_owner = target
                    if trait_name:
                        q_owner = f"{target}.{trait_name}"
                    entities.append(
                        ParsedEntity(
                            name=name,
                            qualified_name=f"{module_name}.{q_owner}.{name}",
                            entity_type="method",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=method_end,
                            signature=_collect_signature(lines, idx),
                            docstring=_collect_doc_comments(lines, idx),
                            calls=_extract_calls(snippet, exclude={name}),
                            entity_metadata={
                                "class": target,
                                "trait": trait_name,
                                "is_async": "async fn" in code,
                            },
                        )
                    )

                impl_depth += code.count("{")
                impl_depth -= code.count("}")
                if impl_depth < 0:
                    impl_depth = 0

        return entities

    def resolve_imports(self, file_path: str, repo_path: str = "") -> list[Dependency]:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            return []

        return [
            Dependency(source_file=file_path, imported_name=imp, resolved_path=None)
            for imp in _extract_use_paths(source)
        ]

    def get_call_graph(self, file_path: str, repo_path: str = "") -> list[CallEdge]:
        entities = self.parse_file(file_path, repo_path)
        edges: list[CallEdge] = []
        for entity in entities:
            if entity.entity_type == "module":
                continue
            for callee in entity.calls:
                edges.append(CallEdge(caller=entity.qualified_name, callee=callee))
        return edges
