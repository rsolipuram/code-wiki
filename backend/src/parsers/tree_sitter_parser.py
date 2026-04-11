"""Unified Tree-sitter parser for supported languages."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Parser, Query, QueryCursor

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
        self._entity_query = self._load_entity_query()

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

    def _query_language_name(self) -> str:
        if self.language_name == "tsx":
            return "typescript"
        return self.language_name

    def _load_entity_query(self) -> Optional[Query]:
        query_path = Path(__file__).with_name("queries") / f"{self._query_language_name()}.scm"
        if not query_path.exists():
            logger.info("No .scm query file found for %s at %s", self.language_name, query_path)
            return None
        try:
            query_source = query_path.read_text(encoding="utf-8")
            return Query(self._language, query_source)
        except Exception as exc:
            logger.warning("Failed to load Tree-sitter query for %s: %s", self.language_name, exc)
            return None

    def _query_captures(self, root_node) -> dict[str, list]:
        if self._entity_query is None:
            return {}
        try:
            cursor = QueryCursor(self._entity_query)
            captures = cursor.captures(root_node)
            return {name: list(nodes) for name, nodes in captures.items()}
        except Exception as exc:
            logger.warning("Tree-sitter query capture failed for %s: %s", self.language_name, exc)
            return {}

    def _extract_imports(self, root_node, source_bytes: bytes, query_captures: dict[str, list] | None = None) -> list[str]:
        import_nodes = _IMPORT_NODE_TYPES.get(self.language_name, set())
        imports: list[str] = []
        seen: set[str] = set()
        query_import_nodes = (query_captures or {}).get("entity.import", [])

        for node in query_import_nodes:
            raw = _node_text(node, source_bytes).strip().rstrip(";")
            parsed = self._parse_import_statement(raw)
            for item in parsed:
                if item and item not in seen:
                    seen.add(item)
                    imports.append(item)

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
            if parent.type == "impl_item":
                impl_text = _node_text(parent, source_bytes)
                impl_header = impl_text.split("{", 1)[0]
                trait_impl = re.match(
                    r"^\s*impl(?:\s*<[^>]+>)?\s+.+\s+for\s+([A-Za-z0-9_:]+)\s*$",
                    impl_header,
                )
                if trait_impl:
                    owner_name = _normalize_symbol(trait_impl.group(1))
                    if owner_name:
                        return owner_name.split(".")[-1]
                inherent_impl = re.match(
                    r"^\s*impl(?:\s*<[^>]+>)?\s+([A-Za-z0-9_:]+)\s*$",
                    impl_header,
                )
                if inherent_impl:
                    owner_name = _normalize_symbol(inherent_impl.group(1))
                    if owner_name:
                        return owner_name.split(".")[-1]
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

    def _extract_docstring(self, entity_node, source_bytes: bytes) -> Optional[str]:
        """Extract the docstring from a function or class node, if present.

        Looks for the first statement in the function/class body.  If it is a
        string literal (Python triple-quote or regular string, JS/TS template or
        string), extracts and returns the cleaned text.
        """
        body_field_names = ("body", "suite", "class_body", "statement_block")
        body_node = None
        for field_name in body_field_names:
            body_node = entity_node.child_by_field_name(field_name)
            if body_node is not None:
                break

        if body_node is None:
            return None

        # Walk children to find the first named child that is a string literal
        for child in body_node.named_children:
            # Python: expression_statement wrapping a string constant
            actual = child
            if child.type == "expression_statement" and child.named_child_count == 1:
                actual = child.named_children[0]

            if actual.type in {"string", "string_literal", "template_string"}:
                raw = _node_text(actual, source_bytes)
                # Strip triple quotes first, then single quotes
                for quote in ('"""', "'''", '"', "'"):
                    if raw.startswith(quote) and raw.endswith(quote) and len(raw) >= 2 * len(quote):
                        raw = raw[len(quote):-len(quote)]
                        break
                return raw.strip() or None
            break  # Only check first named statement

        return None

    def _extract_entity_metadata(self, entity_node, source_bytes: bytes, language: str) -> dict:
        """Extract decorators, return type, parameters, and base classes from an entity node."""
        metadata: dict = {}

        # --- Decorators ---
        decorators: list[str] = []
        parent = entity_node.parent
        if parent is not None:
            # siblings *before* this node that are decorator nodes
            for sibling in parent.children:
                if sibling == entity_node:
                    break
                if sibling.type in {"decorator", "decoration"}:
                    decorators.append(_node_text(sibling, source_bytes).strip())
        if decorators:
            metadata["decorators"] = decorators

        # --- Return type ---
        return_type_node = entity_node.child_by_field_name("return_type")
        if return_type_node is not None:
            rt = _node_text(return_type_node, source_bytes).strip().lstrip("->:").strip()
            if rt:
                metadata["return_type"] = rt

        # --- Parameters ---
        params_node = entity_node.child_by_field_name("parameters")
        if params_node is None:
            params_node = entity_node.child_by_field_name("formal_parameters")
        if params_node is not None:
            params: list[dict] = []
            for param in params_node.named_children:
                pname_node = param.child_by_field_name("name") or (
                    param if param.type in _IDENTIFIER_NODE_TYPES else None
                )
                if pname_node is None:
                    for child in param.named_children:
                        if child.type in _IDENTIFIER_NODE_TYPES:
                            pname_node = child
                            break
                if pname_node is None:
                    continue
                pname = _node_text(pname_node, source_bytes).strip()
                ptype_node = param.child_by_field_name("type") or param.child_by_field_name("annotation")
                ptype = _node_text(ptype_node, source_bytes).strip().lstrip(":").strip() if ptype_node else None
                params.append({"name": pname, "type": ptype})
            if params:
                metadata["parameters"] = params

        # --- Base classes (Python class_definition) ---
        if language == "python" and entity_node.type == "class_definition":
            superclasses_node = entity_node.child_by_field_name("superclasses") or \
                                entity_node.child_by_field_name("argument_list")
            if superclasses_node is not None:
                bases: list[str] = []
                for child in superclasses_node.named_children:
                    if child.type in _IDENTIFIER_NODE_TYPES:
                        bases.append(_node_text(child, source_bytes).strip())
                    elif child.type == "attribute":
                        bases.append(_node_text(child, source_bytes).strip())
                if bases:
                    metadata["base_classes"] = bases

        # --- Base classes / implements (TypeScript class_declaration) ---
        if language in {"typescript", "tsx"} and entity_node.type in {"class_declaration", "class"}:
            bases = []
            for clause in entity_node.named_children:
                if clause.type in {"class_heritage", "extends_clause", "implements_clause"}:
                    for child in clause.named_children:
                        if child.type in _IDENTIFIER_NODE_TYPES | {"type_identifier"}:
                            bases.append(_node_text(child, source_bytes).strip())
            if bases:
                metadata["base_classes"] = bases

        return metadata

    def _entity_kind_from_capture(self, capture_name: str, entity_node) -> Optional[str]:
        if capture_name == "entity.class":
            return "class"
        if capture_name == "entity.interface":
            return "interface"
        if capture_name == "entity.method":
            return "method"
        if capture_name == "entity.function":
            return "method" if self._is_method(entity_node) else "function"
        return None

    def _qualified_name_for_entity(
        self,
        module_name: str,
        entity_type: str,
        entity_name: str,
        owner: Optional[str],
    ) -> str:
        if entity_type in {"class", "interface"}:
            return f"{module_name}.{entity_name}"
        if entity_type == "method" and owner:
            return f"{module_name}.{owner}.{entity_name}"
        return f"{module_name}.{entity_name}"

    def _extract_entities_from_query(self, query_captures: dict[str, list], source_bytes: bytes, module_name: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        capture_priority = {
            "entity.interface": 4,
            "entity.class": 3,
            "entity.method": 2,
            "entity.function": 1,
        }
        selected: dict[tuple[int, int], tuple[int, str, object, object]] = {}

        for capture_name, nodes in query_captures.items():
            if not capture_name.startswith("entity.") or capture_name == "entity.import":
                continue
            for name_node in nodes:
                entity_node = name_node.parent
                if entity_node is None:
                    continue
                key = (entity_node.start_byte, entity_node.end_byte)
                priority = capture_priority.get(capture_name, 0)
                existing = selected.get(key)
                if existing is None or priority > existing[0]:
                    selected[key] = (priority, capture_name, entity_node, name_node)

        ordered_captures = sorted(selected.items(), key=lambda item: (item[0][0], item[0][1]))

        for _, (_, capture_name, entity_node, name_node) in ordered_captures:

            entity_type = self._entity_kind_from_capture(capture_name, entity_node)
            if entity_type is None:
                continue

            name = _normalize_symbol(_node_text(name_node, source_bytes))
            if not name:
                continue

            owner = self._enclosing_owner(entity_node, source_bytes)
            qualified_name = self._qualified_name_for_entity(module_name, entity_type, name, owner)
            line_start, line_end = _line_span(entity_node)
            signature = _node_text(entity_node, source_bytes).splitlines()[0].strip()
            calls = self._extract_calls(entity_node, source_bytes, exclude={name, qualified_name})
            docstring = self._extract_docstring(entity_node, source_bytes)
            entity_metadata = self._extract_entity_metadata(entity_node, source_bytes, self.language_name)
            entities.append(
                ParsedEntity(
                    name=name,
                    qualified_name=qualified_name,
                    entity_type=entity_type,
                    file_path="",
                    line_start=line_start,
                    line_end=line_end,
                    signature=signature[:500] if signature else None,
                    calls=calls,
                    imports=[],
                    docstring=docstring,
                    entity_metadata=entity_metadata,
                )
            )

        return entities

    def _extract_entities_fallback(self, root, source_bytes: bytes, module_name: str, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
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
                else:
                    entity_type = "method" if is_method else "function"
                qualified_name = self._qualified_name_for_entity(module_name, entity_type, name, owner)
                line_start, line_end = _line_span(node)
                signature = _node_text(node, source_bytes).splitlines()[0].strip()
                calls = self._extract_calls(node, source_bytes, exclude={name, qualified_name})
                docstring = self._extract_docstring(node, source_bytes)
                entity_metadata = self._extract_entity_metadata(node, source_bytes, self.language_name)
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
                        docstring=docstring,
                        entity_metadata=entity_metadata,
                    )
                )
            stack.extend(reversed(node.children))
        return entities

    def parse_file(self, file_path: str, repo_path: str = "") -> list[ParsedEntity]:
        try:
            tree, source_bytes = self._parse(file_path)
        except Exception as exc:
            logger.warning("Tree-sitter parse failed for %s: %s", file_path, exc)
            return []

        root = tree.root_node
        module_name = _module_name(file_path, repo_path)
        total_lines = source_bytes.count(b"\n") + 1
        query_captures = self._query_captures(root)
        imports = self._extract_imports(root, source_bytes, query_captures)

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

        extracted = self._extract_entities_from_query(query_captures, source_bytes, module_name)
        if extracted:
            for entity in extracted:
                entity.file_path = file_path
            entities.extend(extracted)
        else:
            entities.extend(self._extract_entities_fallback(root, source_bytes, module_name, file_path))

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
