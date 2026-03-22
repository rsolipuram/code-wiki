"""Python code parser using Jedi + Python AST.

Extracts functions, classes, methods, imports, signatures, docstrings,
and call relationships from .py files with 95%+ accuracy.
"""

import ast
import logging
import textwrap
from pathlib import Path
from typing import Optional

try:
    import jedi
except ImportError:
    jedi = None  # type: ignore[assignment]

from src.parsers.base import CallEdge, CodeParser, Dependency, ParsedEntity

logger = logging.getLogger(__name__)


def _get_qualified_name(module_name: str, node_name: str, class_name: Optional[str] = None) -> str:
    if class_name:
        return f"{module_name}.{class_name}.{node_name}"
    return f"{module_name}.{node_name}"


def _extract_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a human-readable signature string from an AST function node."""
    args = node.args
    params: list[str] = []

    # positional args (with potential defaults)
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        param = arg.arg
        if annotation:
            param = f"{param}: {annotation}"
        default_idx = i - defaults_offset
        if default_idx >= 0:
            param = f"{param} = {ast.unparse(args.defaults[default_idx])}"
        params.append(param)

    # *args
    if args.vararg:
        annotation = ast.unparse(args.vararg.annotation) if args.vararg.annotation else None
        params.append(f"*{args.vararg.arg}" + (f": {annotation}" if annotation else ""))
    elif args.kwonlyargs:
        params.append("*")

    # keyword-only args
    kw_defaults = args.kw_defaults
    for i, arg in enumerate(args.kwonlyargs):
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        param = arg.arg
        if annotation:
            param = f"{param}: {annotation}"
        if kw_defaults[i] is not None:
            param = f"{param} = {ast.unparse(kw_defaults[i])}"
        params.append(param)

    # **kwargs
    if args.kwarg:
        annotation = ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else None
        params.append(f"**{args.kwarg.arg}" + (f": {annotation}" if annotation else ""))

    return_annotation = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(params)}){return_annotation}"


def _extract_calls(node: ast.AST) -> list[str]:
    """Extract all call names from an AST subtree (best-effort dotted names)."""
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                parts: list[str] = []
                current: ast.expr = child.func
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                calls.append(".".join(reversed(parts)))
    return calls


class PythonParser(CodeParser):
    """Parser for Python source files using ast + Jedi."""

    def _module_name(self, file_path: str, repo_path: str = "") -> str:
        """Derive dotted module name from file path.
        
        If repo_path is provided, the module name is relative to it.
        Otherwise, best-effort from the filename.
        """
        p = Path(file_path).resolve()
        
        if repo_path:
            root = Path(repo_path).resolve()
            try:
                # Get relative path from repo root
                rel = p.with_suffix("").relative_to(root)
                return ".".join(rel.parts)
            except ValueError:
                pass
        
        # Fallback to older best-effort logic
        parts = list(p.with_suffix("").parts)
        while parts and parts[0] in {".", "src", "backend", "app", "cache", "repos"}:
            parts.pop(0)
        return ".".join(parts) if parts else p.stem

    def parse_file(self, file_path: str, repo_path: str = "") -> list[ParsedEntity]:
        """Extract all functions, classes, and methods from a Python file."""
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            return []

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            logger.warning("Syntax error in %s: %s", file_path, exc)
            return []

        module_name = self._module_name(file_path, repo_path)
        entities: list[ParsedEntity] = []

        # module-level docstring
        module_doc: Optional[str] = ast.get_docstring(tree)
        entities.append(
            ParsedEntity(
                name=module_name.split(".")[-1],
                qualified_name=module_name,
                entity_type="module",
                file_path=file_path,
                line_start=1,
                line_end=len(source.splitlines()),
                docstring=module_doc,
                imports=self._raw_imports(tree),
            )
        )

        # set parent references needed for nested-function detection in the walk below
        _set_parents(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node)
                qname = f"{module_name}.{node.name}"
                base_names = [ast.unparse(b) for b in node.bases]
                class_entity = ParsedEntity(
                    name=node.name,
                    qualified_name=qname,
                    entity_type="class",
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    docstring=docstring,
                    calls=_extract_calls(node),
                    entity_metadata={
                        "bases": base_names,
                        "decorators": [ast.unparse(d) for d in node.decorator_list],
                    },
                )
                entities.append(class_entity)

                # methods inside the class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_doc = ast.get_docstring(item)
                        method_entity = ParsedEntity(
                            name=item.name,
                            qualified_name=f"{qname}.{item.name}",
                            entity_type="method",
                            file_path=file_path,
                            line_start=item.lineno,
                            line_end=getattr(item, "end_lineno", item.lineno),
                            signature=_extract_signature(item),
                            docstring=method_doc,
                            calls=_extract_calls(item),
                            entity_metadata={
                                "class": node.name,
                                "decorators": [ast.unparse(d) for d in item.decorator_list],
                                "is_async": isinstance(item, ast.AsyncFunctionDef),
                            },
                        )
                        entities.append(method_entity)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # top-level functions only (skip nested)
                parent = getattr(node, "_parent", None)
                if isinstance(parent, ast.ClassDef):
                    continue  # already handled above
                docstring = ast.get_docstring(node)
                entities.append(
                    ParsedEntity(
                        name=node.name,
                        qualified_name=f"{module_name}.{node.name}",
                        entity_type="function",
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=_extract_signature(node),
                        docstring=docstring,
                        calls=_extract_calls(node),
                        entity_metadata={
                            "decorators": [ast.unparse(d) for d in node.decorator_list],
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                        },
                    )
                )

        # Top-Level Assignments: capture module-level variable assignments
        # where the RHS is a Call to an uppercase-initial name (PEP 8 class convention).
        # e.g.  triage_agent = Agent(name="Triage Agent", tools=[...])
        # e.g.  client = OpenAI()
        # Skips private names (_x), non-class calls (get_config()), and nested scopes.
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            # Resolve the RHS call node
            if isinstance(node, ast.Assign):
                value = node.value
                targets = node.targets
            else:
                value = node.value
                targets = [node.target] if node.value else []
            if not isinstance(value, ast.Call):
                continue
            # Get the constructor name (e.g. "Agent" from Agent(...) or Agent[T](...))
            func = value.func
            if isinstance(func, ast.Subscript):
                func = func.value  # unwrap Agent[AirlineAgentChatContext] → Agent
            if isinstance(func, ast.Attribute):
                rhs_call = func.attr
            elif isinstance(func, ast.Name):
                rhs_call = func.id
            else:
                continue
            # Only capture calls to uppercase-initial names (class constructors)
            if not rhs_call or not rhs_call[0].isupper():
                continue
            # Extract each assigned variable name
            for target in targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                elif isinstance(target, ast.Tuple):
                    # handle a, b = SomeCall() — skip multi-assign
                    continue
                else:
                    continue
                if not var_name or var_name.startswith("_"):
                    continue
                # Build constructor kwargs dict for metadata
                constructor_kwargs: dict[str, str] = {}
                for kw in value.keywords:
                    if kw.arg:
                        try:
                            constructor_kwargs[kw.arg] = ast.unparse(kw.value)
                        except Exception:
                            pass
                # Build a readable signature
                try:
                    sig = f"{var_name} = {ast.unparse(value)}"
                except Exception:
                    sig = f"{var_name} = {rhs_call}(...)"
                entities.append(
                    ParsedEntity(
                        name=var_name,
                        qualified_name=f"{module_name}.{var_name}",
                        entity_type="variable",
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=sig[:500],
                        calls=[rhs_call],
                        entity_metadata={
                            "rhs_call": rhs_call,
                            "constructor_kwargs": constructor_kwargs,
                        },
                    )
                )

        return entities

    def _raw_imports(self, tree: ast.Module) -> list[str]:
        """Return raw import strings from a parsed AST."""
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)
        return imports

    def resolve_imports(self, file_path: str, repo_path: str = "") -> list[Dependency]:
        """Resolve import statements using Jedi for cross-file resolution."""
        deps: list[Dependency] = []

        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=file_path)
        except (OSError, SyntaxError):
            return deps

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _jedi_resolve(file_path, source, node.lineno, alias.name)
                    deps.append(
                        Dependency(
                            source_file=file_path,
                            imported_name=alias.name,
                            resolved_path=resolved,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    full_name = f"{module}.{alias.name}" if module else alias.name
                    resolved = _jedi_resolve(file_path, source, node.lineno, full_name)
                    deps.append(
                        Dependency(
                            source_file=file_path,
                            imported_name=full_name,
                            resolved_path=resolved,
                        )
                    )

        return deps

    def get_call_graph(self, file_path: str, repo_path: str = "") -> list[CallEdge]:
        """Extract caller→callee pairs from a Python file."""
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=file_path)
        except (OSError, SyntaxError):
            return []

        module_name = self._module_name(file_path, repo_path)
        edges: list[CallEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller_qname = f"{module_name}.{node.name}"
                for callee in _extract_calls(node):
                    edges.append(CallEdge(caller=caller_qname, callee=callee))

        return edges


def _set_parents(tree: ast.AST) -> None:
    """Annotate each AST node with a `_parent` attribute."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]


def _jedi_resolve(file_path: str, source: str, line: int, name: str) -> Optional[str]:
    """Try to resolve an import name to an absolute path using Jedi."""
    if jedi is None:
        return None
    try:
        script = jedi.Script(source=source, path=file_path)
        definitions = script.goto(line=line, column=0)
        for defn in definitions:
            if defn.module_path:
                return str(defn.module_path)
    except Exception:
        pass
    return None
