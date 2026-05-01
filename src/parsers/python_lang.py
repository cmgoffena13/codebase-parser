import ast
import builtins
import sys
import typing
from typing import Dict, List, Optional, Tuple

from tree_sitter import Node, Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.base import ParserBase


class PythonParser(ParserBase):
    def __init__(
        self,
        assigner: GlobalIDAssigner,
        db: CodeDB,
        parser: Parser,
    ):
        self.parser = parser
        self.assigner = assigner
        self.db = db
        self.builtin_names: set[str] = set(dir(builtins))
        self.builtin_names.update(
            name for name in getattr(typing, "__all__", []) if isinstance(name, str)
        )
        self.std_module_names: set[str] = getattr(sys, "stdlib_module_names", set())
        self.stack: List[Tuple[int, str, str, bool]] = []
        self.symbols: List[Dict] = []
        self.imports: List[Dict] = []
        self.symbol_references_staging: List[Dict] = []
        self.symbols_snapshot = {}
        self.symbols_references_snapshot = {}
        self.imports_snapshot = {}

    def parse(
        self, file_id: int, file_bytes: bytes
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        self.stack = []
        self.symbols = []
        self.imports = []
        self.symbol_references_staging = []
        tree = self.parser.parse(file_bytes)
        root_node = tree.root_node
        self.symbols_snapshot = self.db.get_symbols_snapshot(file_id)
        self.symbols_references_snapshot = self.db.get_symbol_references_snapshot(
            file_id
        )
        self.imports_snapshot = self.db.get_imports_snapshot(file_id)
        self._walk(root_node, file_id, file_bytes)
        return self.symbols, self.imports, self.symbol_references_staging

    def _walk(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        """Recursive DFS traversal."""
        # 1. Extract Data for CURRENT node
        self._process_node(node, file_id)

        # 2. Push to stack if it's a container (Class/Function)
        # We need to know the ID *before* recursing so children can use it as parent
        symbol_id = None
        qualified_name = None

        if node.type in (
            "class_definition",
            "function_definition",
            "async_function_definition",
        ):
            # Extract symbol details first
            symbol_data = self._extract_symbol(node, file_id, file_bytes)
            if symbol_data:
                symbol_id = symbol_data["id"]
                qualified_name = symbol_data["qualified_name"] or symbol_data["name"]
                self.symbols.append(symbol_data)
                # Push to stack
                self.stack.append(
                    (
                        symbol_id,
                        qualified_name,
                        symbol_data["kind"],
                        symbol_data.get("is_test", False),
                    )
                )
        elif node.type in (
            "assignment",
            "annotated_assignment",
            "augmented_assignment",
        ):
            # Variable symbols (module/class/function scope)
            for symbol_data in self._extract_variable_symbols(
                node, file_id, file_bytes
            ):
                self.symbols.append(symbol_data)

        # 3. Recurse
        for child in node.children:
            self._walk(child, file_id, file_bytes)

        # 4. Pop from stack if we pushed
        if symbol_id is not None:
            self.stack.pop()

    def _extract_variable_symbols(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> list[Dict]:
        symbols: list[Dict] = []

        # Only capture module/class plus __init__ assignments.
        if (
            self.stack
            and self.stack[-1][2] != "class"
            and not self.stack[-1][1].endswith(".__init__")
        ):
            return symbols

        # target is usually in field 'left' for assignment/augmented_assignment
        target = node.child_by_field_name("left") or node.child_by_field_name("target")
        if target is None:
            return symbols

        name = ""
        if target.type == "identifier" and target.text is not None:
            name = target.text.decode("utf-8")
        elif target.type == "attribute" and target.text is not None:
            text = target.text.decode("utf-8")
            if text.startswith("self.") or text.startswith("cls."):
                name = text.split(".", 1)[1]
        if not name:
            return symbols
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1

        if self.stack:
            parent_qn = self.stack[-1][1]
            if target.type == "attribute" and parent_qn.endswith(".__init__"):
                parent_qn = parent_qn.rsplit(".", 1)[0]
            qualified_name = f"{parent_qn}.{name}"
            parent_id = self.stack[-1][0]
        else:
            qualified_name = None
            parent_id = None

        signature = (
            file_bytes[node.start_byte : node.end_byte]
            .decode("utf-8", errors="replace")
            .strip()
        )
        signature = " ".join(signature.split())

        kind = "variable"
        is_test = self.stack[-1][3] if self.stack else False
        symbol_identity = qualified_name if qualified_name is not None else name
        coalesced_name = symbol_identity
        key = (symbol_identity, kind)
        if key in self.symbols_snapshot:
            self.symbols_snapshot[key]["seen"] = True
            if (line_start, line_end) != (
                self.symbols_snapshot[key]["line_start"],
                self.symbols_snapshot[key]["line_end"],
            ):
                symbol_id = self.symbols_snapshot[key]["id"]
                symbols.append(
                    {
                        "id": symbol_id,
                        "file_id": file_id,
                        "parent_id": parent_id,
                        "name": name,
                        "qualified_name": qualified_name,
                        "coalesced_name": coalesced_name,
                        "kind": kind,
                        "line_start": line_start,
                        "line_end": line_end,
                        "line_count": line_end - line_start + 1,
                        "signature": signature,
                        "docstring": None,
                        "modifiers": None,
                        "language": "python",
                        "base_classes": None,
                        "is_test": is_test,
                    }
                )
        else:
            symbol_id = self.assigner.reserve("symbols", 1)[0]
            self.symbols_snapshot[key] = {
                "id": symbol_id,
                "seen": True,
                "line_start": line_start,
                "line_end": line_end,
            }
            symbols.append(
                {
                    "id": symbol_id,
                    "file_id": file_id,
                    "parent_id": parent_id,
                    "name": name,
                    "qualified_name": qualified_name,
                    "coalesced_name": coalesced_name,
                    "kind": kind,
                    "line_start": line_start,
                    "line_end": line_end,
                    "line_count": line_end - line_start + 1,
                    "signature": signature,
                    "docstring": None,
                    "modifiers": None,
                    "language": "python",
                    "base_classes": None,
                    "is_test": is_test,
                }
            )

        return symbols

    def _process_node(self, node: Node, file_id: int) -> None:
        """Handle Imports and References."""
        # --- IMPORTS ---
        if node.type in ("import_statement", "import_from_statement"):
            self._extract_import(node, file_id)
            return  # Imports don't have children that are symbols

        # --- REFERENCES ---
        if node.type == "call":
            self._extract_reference(node, "call", file_id)
        elif node.type == "attribute":
            self._extract_reference(node, "access", file_id)
        else:
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                self._extract_reference(type_node, "type_annotation", file_id)

    def _extract_symbol(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Dict]:
        """Extract symbol definition (Class, Function, Variable)."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        if name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1

        if node.type == "class_definition":
            kind = "class"
        elif node.type in ("function_definition", "async_function_definition"):
            # Check if inside a class
            if self.stack and self.stack[-1][2] == "class":
                kind = "method"
            else:
                kind = "function"
        else:
            kind = "variable"  # Fallback for assignments

        if self.stack:
            parent_qn = self.stack[-1][1]
            qualified_name = f"{parent_qn}.{name}"
        else:
            qualified_name = None

        # Extract Modifiers (Decorators)
        modifiers = []
        if node.parent and node.parent.type == "decorated_definition":
            for child in node.parent.children:
                if child.type == "decorator":
                    if child.text is None:
                        continue
                    dec_text = child.text.decode("utf-8", errors="replace").strip()
                    if dec_text.startswith("@"):
                        dec_text = dec_text[1:].strip()
                    if dec_text:
                        modifiers.append(dec_text)

        # Extract Base Classes (for classes only)
        base_classes: list[str] = []
        if kind == "class":
            # tree-sitter-python represents bases as an `argument_list` child.
            for child in node.children:
                if child.type != "argument_list":
                    continue
                for base in child.named_children:
                    if base.type in ("identifier", "dotted_name", "attribute"):
                        if base.text is None:
                            continue
                        base_classes.append(base.text.decode("utf-8"))

        # Extract Signature
        # Slice from the start of the definition up to the start of the body.
        body_node = node.child_by_field_name("body")
        end_byte = body_node.start_byte if body_node is not None else node.end_byte
        signature = (
            file_bytes[node.start_byte : end_byte]
            .decode("utf-8", errors="replace")
            .rstrip()
        )
        signature = " ".join(signature.split())

        # Extract Docstring (First string in body)
        docstring = None
        body = node.child_by_field_name("body")
        if body:
            # In tree-sitter-python, docstrings usually appear as:
            # block -> expression_statement -> string
            for stmt in body.named_children:
                str_node = None
                if stmt.type == "expression_statement":
                    # expression_statement's first named child is typically the string
                    if stmt.named_children:
                        candidate = stmt.named_children[0]
                        if candidate.type == "string":
                            str_node = candidate
                elif stmt.type == "string":
                    str_node = stmt

                if str_node is not None:
                    if str_node.text is None:
                        continue
                    raw = str_node.text.decode("utf-8", errors="replace")
                    try:
                        docstring = ast.literal_eval(raw)
                    except Exception:
                        docstring = raw.strip("\"'")
                    break

        # Determine is_test (pytest + unittest)
        parent_is_test = self.stack[-1][3] if self.stack else False
        is_test = False
        # Pytest
        if kind == "function" and name.startswith("test_"):
            is_test = True
        elif kind == "class" and name.startswith("Test"):
            is_test = True
        # Unittest
        elif kind == "class" and any("TestCase" in bc for bc in base_classes):
            is_test = True
        # Method inside a test class
        elif kind == "method" and name.startswith("test_") and parent_is_test:
            is_test = True

        symbol_identity = qualified_name if qualified_name is not None else name
        coalesced_name = symbol_identity
        key = (symbol_identity, kind)
        if key in self.symbols_snapshot:
            self.symbols_snapshot[key]["seen"] = True

            # NOTE: if lines changed, we need to update the symbol so return
            if (line_start, line_end) != (
                self.symbols_snapshot[key]["line_start"],
                self.symbols_snapshot[key]["line_end"],
            ):
                symbol_id = self.symbols_snapshot[key]["id"]
                return {
                    "id": symbol_id,
                    "file_id": file_id,
                    "parent_id": self.stack[-1][0] if self.stack else None,
                    "name": name,
                    "qualified_name": qualified_name,
                    "coalesced_name": coalesced_name,
                    "kind": kind,
                    "line_start": line_start,
                    "line_end": line_end,
                    "line_count": line_end - line_start + 1,
                    "signature": signature,
                    "docstring": docstring,
                    "modifiers": str(modifiers) if modifiers else None,
                    "language": "python",
                    "base_classes": str(base_classes) if base_classes else None,
                    "is_test": is_test,
                }
            else:
                return None
        else:
            symbol_id = self.assigner.reserve("symbols", 1)[0]
            self.symbols_snapshot[key] = {
                "id": symbol_id,
                "seen": True,
                "line_start": line_start,
                "line_end": line_end,
            }
            return {
                "id": symbol_id,
                "file_id": file_id,
                "parent_id": self.stack[-1][0] if self.stack else None,
                "name": name,
                "qualified_name": qualified_name,
                "coalesced_name": coalesced_name,
                "kind": kind,
                "line_start": line_start,
                "line_end": line_end,
                "line_count": line_end - line_start + 1,
                "signature": signature,
                "docstring": docstring,
                "modifiers": str(modifiers) if modifiers else None,
                "language": "python",
                "base_classes": str(base_classes) if base_classes else None,
                "is_test": is_test,
            }

    def _extract_import(self, node: Node, file_id: int) -> None:
        """Extract Import Statement."""
        line_number = node.start_point.row + 1
        if node.text is None:
            return
        signature = node.text.decode("utf-8")
        import_scope = "module" if not self.stack else "function"

        # Determine Type (Relative vs Absolute)
        if node.type == "import_from_statement":
            import_type = "absolute"
            import_path = ""

            # Relative imports come through as `relative_import` nodes, e.g. `.base` / `..pkg`
            relative_node = None
            for child in node.children:
                if child.type == "relative_import":
                    relative_node = child
                    break
            if relative_node is not None:
                import_type = "relative"
                if relative_node.text is None:
                    return
                import_path = relative_node.text.decode("utf-8")

            # Absolute import fallback (e.g. `from typing import X`)
            if not import_path:
                for child in node.children:
                    if child.type == "dotted_name":
                        if child.text is None:
                            continue
                        import_path = child.text.decode("utf-8")
                        break

            for child in node.children:
                imported_symbol = None
                alias = None
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if not name_node:
                        continue
                    if name_node.text is None:
                        continue
                    imported_symbol = name_node.text.decode("utf-8")
                    alias = (
                        alias_node.text.decode("utf-8")
                        if alias_node is not None and alias_node.text is not None
                        else None
                    )
                elif child.type == "dotted_name":
                    # Skip the module part (absolute dotted_name or relative_import's dotted_name)
                    if (
                        relative_node is not None
                        and child.start_byte < relative_node.end_byte
                    ):
                        continue
                    if (
                        relative_node is None
                        and child.text is not None
                        and child.text.decode("utf-8") == import_path
                    ):
                        continue
                    if child.text is None:
                        continue
                    imported_symbol = child.text.decode("utf-8")

                if imported_symbol is None:
                    continue

                key = (import_path, imported_symbol)
                if key in self.imports_snapshot:
                    self.imports_snapshot[key]["seen"] = True
                else:
                    import_id = self.assigner.reserve("imports", 1)[0]
                    self.imports_snapshot[key] = {"id": import_id, "seen": True}
                    self.imports.append(
                        {
                            "id": import_id,
                            "file_id": file_id,
                            "import_path": import_path,
                            "imported_symbol": imported_symbol,
                            "alias": alias,
                            "line_number": line_number,
                            "import_type": import_type,
                            "import_scope": import_scope,
                            "signature": signature,
                        }
                    )

        elif node.type == "import_statement":
            import_type = "absolute"
            for child in node.children:
                import_path = None
                alias = None
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if not name_node:
                        continue
                    if name_node.text is None:
                        continue
                    import_path = name_node.text.decode("utf-8")
                    alias = (
                        alias_node.text.decode("utf-8")
                        if alias_node is not None and alias_node.text is not None
                        else None
                    )
                elif child.type == "dotted_name":
                    if child.text is None:
                        continue
                    import_path = child.text.decode("utf-8")

                if import_path is None:
                    continue

                imported_symbol = ""
                key = (import_path, imported_symbol)
                if key in self.imports_snapshot:
                    self.imports_snapshot[key]["seen"] = True
                else:
                    import_id = self.assigner.reserve("imports", 1)[0]
                    self.imports_snapshot[key] = {"id": import_id, "seen": True}
                    self.imports.append(
                        {
                            "id": import_id,
                            "file_id": file_id,
                            "import_path": import_path,
                            "imported_symbol": imported_symbol,
                            "alias": alias,
                            "line_number": line_number,
                            "import_type": import_type,
                            "import_scope": import_scope,
                            "signature": signature,
                        }
                    )

    def _extract_reference(self, node: Node, ref_kind: str, file_id: int) -> None:
        """Extract Reference (Call, Access, Type)."""

        # Skip access nodes that are the function part of a call — the call already
        # captures this reference (call is a stricter access).
        if ref_kind == "access":
            parent = node.parent
            if (
                parent is not None
                and parent.type == "call"
                and parent.child_by_field_name("function") == node
            ):
                return

        target_name = ""

        if ref_kind == "call":
            # func() -> target is 'func'
            func_node = node.child_by_field_name("function")
            if func_node:
                if func_node.text is None:
                    return
                target_name = func_node.text.decode("utf-8")
        elif ref_kind == "access":
            # obj.attr -> target is full chain like "obj.attr" or "a.b.c"
            attr_node = node.child_by_field_name("attribute")
            obj_node = node.child_by_field_name("object")
            if not attr_node or attr_node.text is None:
                return

            leaf_name = attr_node.text.decode("utf-8")
            if obj_node is not None and obj_node.text is not None:
                obj_text = obj_node.text.decode("utf-8")
                target_name = f"{obj_text}.{leaf_name}" if obj_text else leaf_name
            else:
                target_name = leaf_name
        elif ref_kind == "type_annotation":
            # x: Type -> normalize annotation target
            if node.text is None:
                return
            target_name = node.text.decode("utf-8").strip()
            if target_name.endswith("]"):
                if target_name.startswith("Optional["):
                    target_name = target_name[len("Optional[") : -1].strip()
                elif target_name.startswith("typing.Optional["):
                    target_name = target_name[len("typing.Optional[") : -1].strip()
            if "[" in target_name:
                target_name = target_name.split("[", 1)[0].strip()

        if not target_name:
            return

        base_name = target_name.split(".", 1)[0]
        if ref_kind == "type_annotation":
            if base_name in self.builtin_names:
                return
        else:
            if base_name in self.builtin_names or base_name in self.std_module_names:
                return

        # Build Qualified Name only when we can resolve parent context.
        qualified_name = None
        if target_name.startswith("self.") or target_name.startswith("cls."):
            suffix = target_name.split(".", 1)[1]
            for entry in reversed(self.stack):
                if entry[2] == "class":
                    qualified_name = f"{entry[1]}.{suffix}"
                    break
            else:
                if self.stack:
                    qualified_name = f"{self.stack[-1][1]}.{suffix}"

        # If it's a simple name, we can't resolve it yet, so keep raw
        # But if it's "module.func", we keep "module.func"

        source_line = node.start_point.row + 1
        key = (target_name, ref_kind, source_line)
        if key in self.symbols_references_snapshot:
            self.symbols_references_snapshot[key]["seen"] = True
        else:
            ref_symbol_coalesced_name = (
                qualified_name if qualified_name is not None else target_name
            )
            self.symbol_references_staging.append(
                {
                    "ref_symbol_name": target_name,
                    "ref_symbol_qualified_name": qualified_name,
                    "ref_symbol_coalesced_name": ref_symbol_coalesced_name,
                    "source_file_id": file_id,
                    "source_line": source_line,
                    "ref_kind": ref_kind,
                    "context": (
                        node.text.decode("utf-8") if node.text is not None else ""
                    ),
                }
            )
            self.symbols_references_snapshot[key] = {"id": None, "seen": True}
        return
