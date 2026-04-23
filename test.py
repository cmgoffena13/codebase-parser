import os
from pathlib import Path

from tree_sitter import Language, Node, Parser
from tree_sitter_python import language as python_language

parser = Parser(Language(python_language()))

directory = "/Users/cortlandgoffena/Documents/repos/coder"
directory = Path(directory)
root = directory.resolve()
ignore = {
    ".git",
    ".venv",
    ".env",
    ".DS_Store",
    ".gitignore",
    "__pycache__",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".parse_index",
}

python_function_types = {"function_definition"}
python_class_types = {"class_definition"}
python_call_types = {"call"}
python_import_types = {"import_from_statement", "import_statement"}


def _enclosing_class_for_direct_method(method: Node) -> Node | None:
    """If `method` is a class body def, return its `class_definition`; else None."""
    parent = method.parent
    while parent is not None and parent.type == "decorated_definition":
        parent = parent.parent
    if parent is None or parent.type != "block":
        return None
    grandparent = parent.parent
    if grandparent is not None and grandparent.type in python_class_types:
        return grandparent
    return None


def _is_direct_class_method(node: Node) -> bool:
    return (
        node.type in python_function_types
        and _enclosing_class_for_direct_method(node) is not None
    )


def _definition_name(node: Node) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is None or name_node.text is None:
        return ""
    return name_node.text.decode("utf-8", errors="replace")


def list_functions(root_node: Node) -> list[tuple[str, int, int]]:
    """Each (name, first_line, last_line) for defs that are not class methods."""
    found: list[tuple[str, int, int]] = []

    def visit(node: Node) -> None:
        if node.type in python_function_types and not _is_direct_class_method(node):
            name = _definition_name(node)
            first = node.start_point.row + 1
            last = node.end_point.row + 1
            found.append((name, first, last))
        for child in node.children:
            visit(child)

    visit(root_node)
    return found


def list_class_methods(
    root_node: Node,
) -> list[tuple[str, str, int, int]]:
    """Each (class_name, method_name, first_line, last_line) for defs directly in a class body."""
    found: list[tuple[str, str, int, int]] = []

    def visit(node: Node) -> None:
        if node.type in python_function_types:
            cls = _enclosing_class_for_direct_method(node)
            if cls is not None:
                class_name = _definition_name(cls)
                method_name = _definition_name(node)
                first = node.start_point.row + 1
                last = node.end_point.row + 1
                found.append((class_name, method_name, first, last))
        for child in node.children:
            visit(child)

    visit(root_node)
    return found


for directory_path, directory_names, file_names in os.walk(root):
    directory_names[:] = [d for d in directory_names if d not in ignore]
    file_names[:] = [file_name for file_name in file_names if file_name not in ignore]

    directory_path = Path(directory_path)
    for file_name in file_names:
        file_path = directory_path / file_name
        file_relative_path = file_path.relative_to(root)
        if file_relative_path.suffix != ".py":
            continue

        if file_name == "agent.py":
            content = file_path.read_bytes()
            tree = parser.parse(content)
            root_node = tree.root_node
            print(file_relative_path)
            print("  functions:")
            for name, first_line, last_line in list_functions(root_node):
                print(f"    {name}  lines {first_line}-{last_line}")
            print("  class methods:")
            for class_name, method_name, first_line, last_line in list_class_methods(
                root_node
            ):
                print(f"    {class_name}.{method_name}  lines {first_line}-{last_line}")
            break
