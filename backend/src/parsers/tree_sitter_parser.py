"""Unified Tree-sitter parser for supported languages."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Parser

from src.parsers.base import CallEdge, CodeParser, Dependency, ParsedEntity

logger = logging.getLogger(__name__)

_LANG_LOADERS: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "rust": ("tree_sitter_rust", "language"),
    "csharp": ("tree_sitter_c_sharp", "language"),
    "java": ("tree_sitter_java", "language"),
}

_IMPORT_NODE_TYPES: dict[str, set[str]] = {
    "python": {"import_statement", "import_from_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
    "rust": {"use_declaration"},
    "csharp": {"using_directive"},
    "java": {"import_declaration"},
}

_CLASS_NODE_TYPES = {
    "class_definition",
    "class_declaration",
    "class_specifier",
    "struct_item",
    "struct_declaration",
    "trait_item",
    "interface_declaration",
    "enum_declaration",
}

_FUNCTION_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "function_item",
    "method_definition",
    "method_declaration",
    "constructor_declaration",
}

_CALL_NODE_TYPES = {"call", "call_expression", "function_call", "invocation_expression"}
_IDENTIFIER_NODE_TYPES = {"identifier", "field_identifier", "property_identifier", "type_identifier"}


def _module_name(file_path: str, repo_path: str = "") -> str:
    p = Path(file_path).resolve()
    if repo_path:
        root = Path(repo_path).resolve()
        try:
            rel = p.with_suffix("").relative_to(root)
            return ".".join(rel.parts)
        except ValueError:
            pass
    parts = [part for part in p.with_suffix("").parts if part not in {"/", ""}]
    while parts and parts[0] in {"src", "backend", "app", "cache", "repos"}:
        parts.pop(0)
    return ".".join(parts) if parts else p.stem


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line_span(node) -> tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _normalize_symbol(name: str) -> str:
    cleaned = re.sub(r"<[^>]*>", "", name).strip()
    cleaned = cleaned.replace("::", ".")
    cleaned = re.sub(r"[^A-Za-z0-9_.]", "", cleaned)
    return cleaned


class TreeSitterParser(CodeParser):
    """Language-parameterized parser backed by Tree-sitter."""

    def __init__(self, language_name: str):
        if language_name not in _LANG_LOADERS:
            raise ValueError(f"Unsupported tree-sitter language: {language_name}")
        self.language_name = language_name
        self._language = self._load_language(language_name)
        self._parser = Parser(self._language)

    def _load_language(self, language_name: str) -> Language:
        module_name, function_name = _LANG_LOADERS[language_name]
        module = __import__(module_name)
        lang_fn = getattr(module, function_name, None)
        if lang_fn is None:
            if language_name == "typescript":
                lang_fn = getattr(module, "language", None)
            if lang_fn is None:
                raise RuntimeError(f"Missing language loader {module_name}.{function_name}")
        return Language(lang_fn())

    def _parse(self, file_path: str):
        source_bytes = Path(file_path).read_bytes()
        tree = self._parser.parse(source_bytes)
        return tree, source_bytes

    def _extract_imports(self, root_node, source_bytes: bytes) -> list[str]:
        import_nodes = _IMPORT_NODE_TYPES.get(self.language_name, set())
        imports: list[str] = []
        seen: set[str] = set()
        stack = [root_node]
        while stack:
            node = stack.pop()
            if node.type in import_nodes:
                raw = _node_text(node, source_bytes).strip().rstrip(";")
                parsed = self._parse_import_statement(raw)
                for item in parsed:
                    if item and item not in seen:
                        seen.add(item)
                        imports.append(item)
            stack.extend(reversed(node.children))
        return imports

    def _parse_import_statement(self, statement: str) -> list[str]:
        s = " ".join(statement.replace("\n", " ").split())
        if self.language_name == "python":
            if s.startswith("import "):
                return [part.strip() for part in s[len("import "):].split(",") if part.strip()]
            if s.startswith("from "):
                m = re.match(r"from\s+([A-Za-z0-9_\.]+)\s+import\s+(.+)$", s)
                if not m:
                    return []
                module_name = m.group(1)
                targets_raw = m.group(2).strip().strip("()")
                targets = [re.sub(r"\s+as\s+.+$", "", x.strip()) for x in targets_raw.split(",")]
                return [f"{module_name}.{t}" for t in targets if t and t != "*"]
            return []
        if self.language_name == "rust":
            if not s.startswith("use "):
                return []
            body = s[len("use "):].rstrip(";").replace("::", ".")
            return [body]
        if self.language_name in {"typescript", "tsx"}:
            m = re.search(r"from\s+['\"]([^'\"]+)['\"]", s)
            if m:
                return [m.group(1)]
            if s.startswith("import "):
                return [s]
            return []
        if self.language_name == "java":
            m = re.match(r"import\s+(?:static\s+)?([A-Za-z0-9_\.]+)", s)
            return [m.group(1)] if m else []
        if self.language_name == "csharp":
            m = re.match(r"using\s+([A-Za-z0-9_\.]+)", s)
            return [m.group(1)] if m else []
        return []

    def _entity_name_node(self, node):
        field = node.child_by_field_name("name")
        if field is not None:
            return field
        for child in node.children:
            if child.type in _IDENTIFIER_NODE_TYPES:
                return child
        return None

    def _is_method(self, node) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.type in _CLASS_NODE_TYPES or parent.type == "impl_item":
                return True
            if parent.type in {"module", "program", "source_file"}:
                return False
            parent = parent.parent
        return False

    def _enclosing_owner(self, node, source_bytes: bytes) -> Optional[str]:
        parent = node.parent
        while parent is not None:
            if parent.type in _CLASS_NODE_TYPES:
                name_node = self._entity_name_node(parent)
                if name_node is not None:
                    return _normalize_symbol(_node_text(name_node, source_bytes))
            parent = parent.parent
        return None

    def _extract_calls(self, node, source_bytes: bytes, exclude: set[str] | None = None) -> list[str]:
        excluded = exclude or set()
        calls: list[str] = []
        seen: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in _CALL_NODE_TYPES:
                target = current.child_by_field_name("function") or current.child_by_field_name("name")
                if target is None and current.named_children:
                    target = current.named_children[0]
                if target is not None:
                    raw = _normalize_symbol(_node_text(target, source_bytes))
                    short = raw.split(".")[-1]
                    if raw and raw not in excluded and short not in excluded and raw not in seen:
                        seen.add(raw)
                        calls.append(raw)
            stack.extend(reversed(current.children))
        return calls

    def parse_file(self, file_path: str, repo_path: str = "") -> list[ParsedEntity]:
        try:
            tree, source_bytes = self._parse(file_path)
        except Exception as exc:
            logger.warning("Tree-sitter parse failed for %s: %s", file_path, exc)
            return []

        root = tree.root_node
        module_name = _module_name(file_path, repo_path)
        total_lines = source_bytes.count(b"\n") + 1
        imports = self._extract_imports(root, source_bytes)

        entities: list[ParsedEntity] = [
            ParsedEntity(
                name=module_name.split(".")[-1],
                qualified_name=module_name,
                entity_type="module",
                file_path=file_path,
                line_start=1,
                line_end=total_lines,
                imports=imports,
            )
        ]

        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in _CLASS_NODE_TYPES | _FUNCTION_NODE_TYPES:
                name_node = self._entity_name_node(node)
                if name_node is None:
                    stack.extend(reversed(node.children))
                    continue
                name = _normalize_symbol(_node_text(name_node, source_bytes))
                if not name:
                    stack.extend(reversed(node.children))
                    continue
                owner = self._enclosing_owner(node, source_bytes)
                is_method = self._is_method(node)
                if node.type in _CLASS_NODE_TYPES:
                    entity_type = "class" if "interface" not in node.type and "trait" not in node.type else "interface"
                    qualified_name = f"{module_name}.{name}"
                else:
                    entity_type = "method" if is_method else "function"
                    if owner and is_method:
                        qualified_name = f"{module_name}.{owner}.{name}"
                    else:
                        qualified_name = f"{module_name}.{name}"
                line_start, line_end = _line_span(node)
                signature = _node_text(node, source_bytes).splitlines()[0].strip()
                calls = self._extract_calls(node, source_bytes, exclude={name, qualified_name})
                entities.append(
                    ParsedEntity(
                        name=name,
                        qualified_name=qualified_name,
                        entity_type=entity_type,
                        file_path=file_path,
                        line_start=line_start,
                        line_end=line_end,
                        signature=signature[:500] if signature else None,
                        calls=calls,
                        imports=[],
                    )
                )
            stack.extend(reversed(node.children))

        return entities

    def resolve_imports(self, file_path: str, repo_path: str = "") -> list[Dependency]:
        try:
            tree, source_bytes = self._parse(file_path)
        except Exception as exc:
            logger.warning("Tree-sitter import parse failed for %s: %s", file_path, exc)
            return []
        imports = self._extract_imports(tree.root_node, source_bytes)
        return [Dependency(source_file=file_path, imported_name=item, resolved_path=None) for item in imports]

    def get_call_graph(self, file_path: str, repo_path: str = "") -> list[CallEdge]:
        entities = self.parse_file(file_path, repo_path)
        edges: list[CallEdge] = []
        for entity in entities:
            if entity.entity_type == "module":
                continue
            for callee in entity.calls:
                edges.append(CallEdge(caller=entity.qualified_name, callee=callee))
        return edges
