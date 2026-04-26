import ast
from typing import Dict, List, Optional, Tuple

import tree_sitter_python as python_language
from tree_sitter import Language, Node, Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB


class PythonParser:
    def __init__(
        self,
        assigner: GlobalIDAssigner,
        db: CodeDB,
    ):
        self.parser = Parser(Language(python_language.language()))
        self.assigner = assigner
        self.db = db
        self.symbols_snapshot = {}
        self.stack: List[Tuple[int, str, str]] = []
        self.symbols: List[Dict] = []
        self.imports: List[Dict] = []
        self.symbol_references_staging: List[Dict] = []

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
        self._walk(root_node, file_id, file_bytes)
        return self.symbols, self.imports, self.symbol_references_staging

    def _walk(self, node: Node, file_id: int, file_bytes: bytes):
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
            sym_data = self._extract_symbol(node, file_id, file_bytes)
            if sym_data:
                symbol_id = sym_data["id"]
                qualified_name = sym_data["qualified_name"]
                self.symbols.append(sym_data)
                # Push to stack
                self.stack.append((symbol_id, qualified_name, sym_data["kind"]))

        # 3. Recurse
        for child in node.children:
            self._walk(child, file_id, file_bytes)

        # 4. Pop from stack if we pushed
        if symbol_id is not None:
            self.stack.pop()

    def _process_node(self, node: Node, file_id: int):
        """Handle Imports and References."""
        # --- IMPORTS ---
        if node.type in ("import_statement", "import_from_statement"):
            self._extract_import(node, file_id)
            return  # Imports don't have children that are symbols

        # --- REFERENCES ---
        # Check for Calls, Attributes, and Type Hints
        if node.type == "call":
            self._extract_reference(node, "call", file_id)
        elif node.type == "attribute":
            self._extract_reference(node, "access", file_id)
        else:
            # Type hint found (e.g., def foo(x: User))
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

        name = name_node.text.decode("utf-8")
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1

        # Determine Kind
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

        # Build Qualified Name
        if self.stack:
            parent_qn = self.stack[-1][1]
            qualified_name = f"{parent_qn}.{name}"
        else:
            qualified_name = name

        # Extract Modifiers (Decorators)
        modifiers = []
        if node.parent and node.parent.type == "decorated_definition":
            for child in node.parent.children:
                if child.type == "decorator":
                    dec_text = child.text.decode("utf-8", errors="replace").strip()
                    if dec_text.startswith("@"):
                        dec_text = dec_text[1:].strip()
                    if dec_text:
                        modifiers.append(dec_text)

        # Extract Base Classes (for classes only)
        base_classes = []
        if kind == "class":
            superclasses = node.child_by_field_name("superclasses")
            if superclasses:
                for base in superclasses.children:
                    if base.type in ("identifier", "dotted_name"):
                        base_classes.append(base.text.decode("utf-8"))

        # Extract Signature (supports multi-line defs)
        # Slice from the start of the definition up to the start of the body.
        body_node = node.child_by_field_name("body")
        end_byte = body_node.start_byte if body_node is not None else node.end_byte
        signature = (
            file_bytes[node.start_byte : end_byte]
            .decode("utf-8", errors="replace")
            .rstrip()
        )

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
                    # fallback
                    str_node = stmt

                if str_node is not None:
                    raw = str_node.text.decode("utf-8", errors="replace")
                    try:
                        # Handles single/double/triple quotes and escapes
                        docstring = ast.literal_eval(raw)
                    except Exception:
                        docstring = raw.strip("\"'")
                    break

        # Reserve ID
        sym_id = self.assigner.reserve("symbols", 1)[0]

        return {
            "id": sym_id,
            "file_id": file_id,
            "parent_id": self.stack[-1][0] if self.stack else None,
            "name": name,
            "qualified_name": qualified_name,
            "kind": kind,
            "line_start": line_start,
            "line_end": line_end,
            "line_count": line_end - line_start + 1,
            "signature": signature,
            "docstring": docstring,
            "modifiers": str(modifiers) if modifiers else None,
            "language": "python",
            "base_classes": str(base_classes) if base_classes else None,
        }

    def _extract_import(self, node: Node, file_id: int):
        """Extract Import Statement."""
        import_path = ""
        imported_symbol = ""
        alias = None
        import_type = "absolute"  # Default

        # Determine Type (Relative vs Absolute)
        if node.type == "import_from_statement":
            level_node = node.child_by_field_name("level")
            if level_node:
                level = int(level_node.text.decode())
                if level > 0:
                    import_type = "relative"

            # Get module path
            module_node = node.child_by_field_name("module")
            if module_node:
                import_path = module_node.text.decode("utf-8")

            # Get imported names
            # import_from_statement can have multiple names: from x import a, b
            for child in node.children:
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node:
                        imported_symbol = name_node.text.decode("utf-8")
                        if alias_node:
                            alias = alias_node.text.decode("utf-8")

                        # Add to list
                        self.imports.append(
                            {
                                "file_id": file_id,
                                "import_path": import_path,
                                "imported_symbol": imported_symbol,
                                "alias": alias,
                                "line_number": node.start_point.row + 1,
                                "import_type": import_type,
                                "import_scope": "module"
                                if not self.stack
                                else "function",
                                "signature": node.text.decode("utf-8"),
                            }
                        )
                elif child.type == "dotted_name" and not import_path:
                    # Fallback for simple "from x import y"
                    pass

        elif node.type == "import_statement":
            # import x, y
            import_type = "absolute"
            for child in node.children:
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node:
                        import_path = name_node.text.decode("utf-8")
                        if alias_node:
                            alias = alias_node.text.decode("utf-8")

                        self.imports.append(
                            {
                                "file_id": file_id,
                                "import_path": import_path,
                                "imported_symbol": "",  # No specific symbol imported
                                "alias": alias,
                                "line_number": node.start_point.row + 1,
                                "import_type": import_type,
                                "import_scope": "module"
                                if not self.stack
                                else "function",
                                "signature": node.text.decode("utf-8"),
                            }
                        )

    def _extract_reference(self, node: Node, ref_kind: str, file_id: int):
        """Extract Reference (Call, Access, Type)."""
        # Determine Target Name
        target_name = ""

        if ref_kind == "call":
            # func() -> target is 'func'
            func_node = node.child_by_field_name("function")
            if func_node:
                target_name = func_node.text.decode("utf-8")
        elif ref_kind == "access":
            # obj.attr -> target is 'attr'
            attr_node = node.child_by_field_name("attribute")
            if attr_node:
                target_name = attr_node.text.decode("utf-8")
        elif ref_kind == "type_annotation":
            # x: Type -> target is 'Type'
            target_name = node.text.decode("utf-8")

        if not target_name:
            return

        # Build Qualified Name for Context
        # If it's "self.method", we know it's inside a class
        qualified_name = target_name
        if target_name.startswith("self.") or target_name.startswith("cls."):
            if self.stack:
                parent_qn = self.stack[-1][1]
                # Replace self/cls with parent name
                suffix = target_name.split(".", 1)[1]
                qualified_name = f"{parent_qn}.{suffix}"

        # If it's a simple name, we can't resolve it yet, so keep raw
        # But if it's "module.func", we keep "module.func"

        self.symbol_references_staging.append(
            {
                "ref_symbol_name": target_name,
                "ref_symbol_qualified_name": qualified_name,
                "source_file_id": file_id,
                "source_line": node.start_point.row + 1,
                "ref_kind": ref_kind,
                "context": node.text.decode("utf-8"),
            }
        )
