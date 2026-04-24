import re
from typing import Optional

from tree_sitter import Node

TYPES = {
    "function",
    "class",
    "method",
    "call",
    "import",
}


class PythonParser:
    def __init__(self):
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as python_language

        self.parser = Parser(Language(python_language()))
        self.docstring_re = re.compile(r'"""(.*?)"""', re.DOTALL)
        self.function_types = {"function_definition"}
        self.class_types = {"class_definition"}
        self.call_types = {"call"}
        self.import_types = {"import_from_statement", "import_statement"}
        self.symbols = {}
        for type in TYPES:
            self.symbols[type] = []

    def _definition_name(self, node: Node) -> str:
        """Decode the ``name`` field (``identifier``) for a class or function node."""
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return ""
        text = name_node.text
        if isinstance(text, (bytes, bytearray)):
            return text.decode("utf-8", errors="replace")
        if isinstance(text, memoryview):
            return text.tobytes().decode("utf-8", errors="replace")
        return str(text)

    def _get_signature(self, file_lines: list[str], start: int) -> str:
        return file_lines[start] if file_lines else ""

    def _get_docstring(
        self, file_lines: list[str], start: int, end: int
    ) -> Optional[str]:
        if not file_lines:
            return None

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
            if child.type in self.class_types or child.type in self.function_types:
                self._parse_class_and_function(child, file_name, file_lines)
            elif child.type in self.call_types:
                self._parse_call(child, file_name, file_lines)
            elif child.type in self.import_types:
                self._parse_import(child, file_name, file_lines)
            self._walk(child, file_name, file_lines)

    def _parse_class_and_function(
        self, node: Node, file_name: str, file_lines: list[str]
    ) -> None:
        if node.type in self.class_types:
            class_name = self._definition_name(node)
            first = node.start_point.row + 1
            last = node.end_point.row + 1
            line_count = last - first + 1
            signature = self._get_signature(file_lines, first)
            docstring = self._get_docstring(file_lines, first, last)
            self.symbols["class"].append(
                {
                    "file_name": file_name,  # NOTE: Needed to lookup file id.
                    "name": class_name,
                    "kind": "class",
                    "line_start": first,
                    "line_end": last,
                    "line_count": line_count,
                    "language": "python",
                    "signature": signature,
                    "docstring": docstring,
                }
            )

        if node.type in self.function_types:
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
                        "class_name": class_name,
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
                print(f"class method: {class_name}.{method_name}")
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

    def _parse_call(self, node: Node, file_name: str, file_lines: list[str]) -> None:
        pass

    def _parse_import(self, node: Node, file_name: str, file_lines: list[str]) -> None:
        pass

    def parse(self, content: bytes, file_name: str) -> dict[str, list[dict]]:
        tree = self.parser.parse(content)
        root_node = tree.root_node
        file_lines = content.decode("utf-8", errors="replace").splitlines()
        self._walk(root_node, file_name, file_lines)
        return self.symbols
