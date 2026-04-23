from typing import Optional

from tree_sitter import Node

TYPES = {
    "function",
    "class",
    "class_method",
    "call",
    "import",
}


class PythonParser:
    def __init__(self):
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as python_language

        self.parser = Parser(Language(python_language()))
        self.function_types = {"function_definition"}
        self.class_types = {"class_definition"}
        self.call_types = {"call"}
        self.import_types = {"import_from_statement", "import_statement"}
        self.symbols = {}
        for type in TYPES:
            self.symbols[type] = []

    def _enclosing_class_for_direct_method(self, node: Node) -> Optional[Node]:
        result = None
        parent = node.parent
        while parent is not None and parent.type == "decorated_definition":
            result = parent.parent
        if parent is None or parent.type != "block":
            return None
        grandparent = parent.parent
        if grandparent is not None and grandparent.type in self.class_types:
            result = grandparent
        return result

    def _is_direct_class_method(self, node: Node) -> bool:
        return (
            node.type in self.function_types
            and self._enclosing_class_for_direct_method(node) is not None
        )

    def _walk(self, node: Node, file_name: str) -> None:
        for child in node.children:
            if child.type in self.class_types or child.type in self.function_types:
                self._parse_class_and_function(child, file_name)
            elif child.type in self.call_types:
                self._parse_call(child, file_name)
            elif child.type in self.import_types:
                self._parse_import(child, file_name)
            self._walk(child, file_name)

    def _parse_class_and_function(self, node: Node, file_name: str) -> None:
        if node.type in self.class_types:
            class_name = node.child_by_field_name("name")
            first = node.start_point.row + 1
            last = node.end_point.row + 1
            line_count = last - first + 1
            # TODO: Add signature, docstring
            self.symbols["class"].append(
                {
                    "file_name": file_name,  # NOTE: Needed to lookup file id.
                    "name": class_name,
                    "kind": "class",
                    "line_start": first,
                    "line_end": last,
                    "line_count": line_count,
                    "language": "python",
                }
            )

        if node.type in self.function_types:
            cls = self._enclosing_class_for_direct_method(node)
            if cls is not None:
                class_name = cls.child_by_field_name("name")
                method_name = node.child_by_field_name("name")
                first = node.start_point.row + 1
                last = node.end_point.row + 1
                line_count = last - first + 1
                # TODO: Add signature, docstring
                self.symbols["class_method"].append(
                    {
                        "file_name": file_name,  # NOTE: Needed to lookup file id.
                        "method_name": class_name,
                        "qualified_name": f"{class_name}.{method_name}",
                        "kind": "class_method",
                        "line_start": first,
                        "line_end": last,
                        "line_count": line_count,
                        "language": "python",
                    }
                )
            else:
                if not self._is_direct_class_method(node):
                    name = node.child_by_field_name("name")
                    first = node.start_point.row + 1
                    last = node.end_point.row + 1
                    line_count = last - first + 1
                    # TODO: Add signature, docstring
                    self.symbols["function"].append(
                        {
                            "file_name": file_name,  # NOTE: Needed to lookup file id.
                            "name": name,
                            "line_start": first,
                            "line_end": last,
                            "line_count": line_count,
                            "kind": "function",
                            "language": "python",
                        }
                    )

    def _parse_call(self, node: Node, file_name: str) -> None:
        pass

    def _parse_import(self, node: Node, file_name: str) -> None:
        pass

    def parse(self, content: bytes, file_name: str) -> dict[str, list[dict]]:
        tree = self.parser.parse(content)
        root_node = tree.root_node
        self._walk(root_node, file_name)
        return self.symbols
