import re
from typing import Optional

from tree_sitter import Language, Node, Parser
from tree_sitter_python import language as python_language

TYPES = {
    "function",
    "class",
    "method",
    "call",
    "import",
}


class PythonParser:
    def __init__(self):
        self.parser = Parser(Language(python_language()))
        self.docstring_re = re.compile(r'"""(.*?)"""', re.DOTALL)
        self.function_types = {"function_definition"}
        self.class_types = {"class_definition"}
        self.call_types = {"call"}
        self.import_types = {"import_from_statement", "import_statement"}
        self.symbols = {}
        for type in TYPES:
            self.symbols[type] = []

    def _span_text(self, node: Node | None) -> str:
        """Text of this node exactly as it appears in the source (any node type)."""
        raw = node.text
        if isinstance(raw, str):
            return raw
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        if isinstance(raw, (bytes, bytearray)):
            return raw.decode("utf-8", errors="replace")
        return str(raw)

    def _import_symbol_names(self, node: Node) -> list[str]:
        """Imported symbols only (not ``from`` / ``import`` keywords); one string per binding."""
        names: list[str] = []

        if node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            for child in node.children:
                if child.type not in ("dotted_name", "aliased_import", "identifier"):
                    continue
                if child is module:
                    continue
                text = self._span_text(child).strip()
                if text:
                    names.append(text)
            if not names:
                for child in node.children:
                    if child.type == "wildcard_import":
                        module_text = self._span_text(module).strip()
                        names.append(f"{module_text}.*" if module_text else "*")
                        break
            return names

        if node.type == "import_statement":
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    text = self._span_text(child).strip()
                    if text:
                        names.append(text)
            return names

        return names

    def _definition_name(self, node: Node) -> str:
        """Return the written name for a ``class_definition`` or ``function_definition``.

        For ``class Foo`` or ``def bar``, tree-sitter does not keep ``"Foo"`` on the
        class/function node itself. It stores a child node (field ``"name"``, node type
        ``identifier``) that points at the name in the source. We read that child's
        ``.text`` (often raw bytes from the parse buffer) and return a normal ``str``.
        """
        return self._span_text(node.child_by_field_name("name"))

    def _get_signature(self, file_lines: list[str], start_line: int) -> str:
        """First line of text for a symbol; ``start_line`` is 1-based (same as ``line_start``)."""
        if not file_lines:
            return ""
        idx = start_line - 1
        if idx < 0 or idx >= len(file_lines):
            return ""
        return file_lines[idx].rstrip()

    def _get_docstring(
        self, file_lines: list[str], start: int, end: int
    ) -> Optional[str]:

        start_idx = max(0, start - 1)
        end_idx = min(len(file_lines), end)

        text = "\n".join(file_lines[start_idx:end_idx])
        m = self.docstring_re.search(text)
        return m.group(1) if m else None

    def _owning_class_definition(self, node: Node) -> Optional[Node]:
        """Return the ``class_definition`` for the class that contains this function, if any.

        Returns None at module scope, inside another function, and similar cases where
        walking up does not reach ``class_definition`` -> ``block`` -> this function.

        If the function has decorators, tree-sitter wraps it in a ``decorated_definition``
        parent; the loop climbs past that wrapper node only (not past the function itself).
        ``@classmethod``, ``@staticmethod``, and other decorators still end up classified
        as class methods when the function sits in a class body.
        """
        ancestor = node.parent
        while ancestor is not None and ancestor.type == "decorated_definition":
            ancestor = ancestor.parent

        if ancestor is None or ancestor.type != "block":
            return None

        class_node = ancestor.parent
        if class_node is None or class_node.type not in self.class_types:
            return None

        return class_node

    def _walk(self, node: Node, file_name: str, file_lines: list[str]) -> None:
        for child in node.children:
            if child.type in self.class_types:
                self._parse_class(child, file_name, file_lines)
            elif child.type in self.function_types:
                self._parse_function_or_method(child, file_name, file_lines)
            elif child.type in self.call_types:
                self._parse_call(child, file_name, file_lines)
            elif child.type in self.import_types:
                self._parse_import(child, file_name, file_lines)
            self._walk(child, file_name, file_lines)

    def _parse_function_or_method(
        self, node: Node, file_name: str, file_lines: list[str]
    ) -> None:
        cls = self._owning_class_definition(node)
        if cls is not None:
            class_name = self._definition_name(cls)
            method_name = self._definition_name(node)
            first = node.start_point.row + 1
            last = node.end_point.row + 1
            line_count = last - first + 1
            signature = self._get_signature(file_lines, first)
            docstring = self._get_docstring(file_lines, first, last)
            self.symbols["method"].append(
                {
                    "file_name": file_name,  # NOTE: Needed to lookup file id.
                    "name": method_name,
                    "qualified_name": f"{class_name}.{method_name}",
                    "kind": "method",
                    "line_start": first,
                    "line_end": last,
                    "line_count": line_count,
                    "signature": signature,
                    "language": "python",
                    "docstring": docstring,
                }
            )
        else:
            name = self._definition_name(node)
            first = node.start_point.row + 1
            last = node.end_point.row + 1
            line_count = last - first + 1
            signature = self._get_signature(file_lines, first)
            docstring = self._get_docstring(file_lines, first, last)
            self.symbols["function"].append(
                {
                    "file_name": file_name,  # NOTE: Needed to lookup file id.
                    "qualified_name": None,
                    "name": name,
                    "line_start": first,
                    "line_end": last,
                    "line_count": line_count,
                    "kind": "function",
                    "language": "python",
                    "signature": signature,
                    "docstring": docstring,
                }
            )

    def _parse_class(self, node: Node, file_name: str, file_lines: list[str]) -> None:
        if node.type in self.class_types:
            class_name = self._definition_name(node)
            first = node.start_point.row + 1
            last = node.end_point.row + 1
            line_count = last - first + 1
            signature = self._get_signature(file_lines, first)
            self.symbols["class"].append(
                {
                    "file_name": file_name,  # NOTE: Needed to lookup file id.
                    "qualified_name": None,
                    "name": class_name,
                    "kind": "class",
                    "line_start": first,
                    "line_end": last,
                    "line_count": line_count,
                    "language": "python",
                    "signature": signature,
                    "docstring": None,
                }
            )

    def _parse_call(self, node: Node, file_name: str, file_lines: list[str]) -> None:
        """Record a function call: ``name`` is the callee expression (e.g. ``foo``, ``self.bar``)."""
        first = node.start_point.row + 1
        last = node.end_point.row + 1
        line_count = last - first + 1
        signature = self._get_signature(file_lines, first)

        callee = node.child_by_field_name("function")
        name = self._span_text(callee).strip() or self._span_text(node).strip()

        self.symbols["call"].append(
            {
                "file_name": file_name,  # NOTE: Needed to lookup file id.
                "qualified_name": None,
                "name": name,
                "kind": "call",
                "line_start": first,
                "line_end": last,
                "line_count": line_count,
                "language": "python",
                "signature": signature,
                "docstring": None,
            }
        )

    def _parse_import(self, node: Node, file_name: str, file_lines: list[str]) -> None:
        """One row per imported binding; ``signature`` is the full import line text."""
        first = node.start_point.row + 1
        last = node.end_point.row + 1
        line_count = last - first + 1
        signature = self._get_signature(file_lines, first)
        for name in self._import_symbol_names(node):
            self.symbols["import"].append(
                {
                    "file_name": file_name,  # NOTE: Needed to lookup file id.
                    "qualified_name": None,
                    "name": name,
                    "kind": "import",
                    "line_start": first,
                    "line_end": last,
                    "line_count": line_count,
                    "language": "python",
                    "signature": signature,
                    "docstring": None,
                }
            )

    def parse(self, content: bytes, file_name: str) -> dict[str, list[dict]]:
        tree = self.parser.parse(content)
        root_node = tree.root_node
        file_lines = content.decode("utf-8", errors="replace").splitlines()
        self._walk(root_node, file_name, file_lines)
        return self.symbols
