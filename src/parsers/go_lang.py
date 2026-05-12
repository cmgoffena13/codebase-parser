import re
from typing import Dict, List, Optional, Tuple

from tree_sitter import Node, Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.base import ParserBase
from src.parsers.parser_utils import StackFrame

_GO_BUILTIN_CALLS = frozenset(
    {
        "append",
        "cap",
        "clear",
        "close",
        "complex",
        "copy",
        "delete",
        "imag",
        "len",
        "make",
        "max",
        "min",
        "new",
        "panic",
        "print",
        "println",
        "real",
        "recover",
    }
)

_GO_TYPE_SKIP = frozenset(
    {
        "any",
        "bool",
        "byte",
        "comparable",
        "complex64",
        "complex128",
        "error",
        "float32",
        "float64",
        "int",
        "int8",
        "int16",
        "int32",
        "int64",
        "rune",
        "string",
        "uint",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "uintptr",
    }
)


def _go_std_heuristic(import_path: str) -> bool:
    """True if import path looks like a Go standard-library module (used to filter refs)."""
    if not import_path or import_path.startswith("."):
        return False
    first = import_path.split("/", 1)[0]
    return "." not in first


class GoParser(ParserBase):
    """Parses a single .go file into symbols, imports, and symbol_references rows."""

    def __init__(
        self,
        assigner: GlobalIDAssigner,
        db: CodeDB,
        parser: Parser,
    ):
        self.parser = parser
        self.assigner = assigner
        self.db = db
        self.stack: List[StackFrame] = []
        self.symbols: List[Dict] = []
        self.imports: List[Dict] = []
        self.symbol_references: List[Dict] = []
        self.symbols_snapshot: dict[tuple[str, str], dict] = {}
        self.symbols_references_snapshot: dict[tuple[str, str, int], dict] = {}
        self.imports_snapshot: dict[tuple[str, str], dict] = {}
        self._package = "main"
        self._import_roots: dict[str, str] = {}
        self._receiver: tuple[str, str] | None = None
        self._container_by_qn: dict[str, int] = {}
        self._container_is_test: dict[str, bool] = {}
        self._interpreted_string_import_path_re = re.compile(r'^"([^"]*)"$')

    def parse(
        self, file_id: int, file_bytes: bytes
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        self.stack = []
        self._package = "main"
        self._import_roots = {}
        self._receiver = None
        self._container_by_qn = {}
        self._container_is_test = {}
        self.symbols = []
        self.imports = []
        self.symbol_references = []
        tree = self.parser.parse(file_bytes)
        root = tree.root_node
        self.symbols_snapshot = self.db.get_symbols_snapshot(file_id)
        self.symbols_references_snapshot = self.db.get_symbol_references_snapshot(
            file_id
        )
        self.imports_snapshot = self.db.get_imports_snapshot(file_id)
        self._walk_source_file(root, file_id, file_bytes)
        self.db.delete_symbol_references(self.symbols_references_snapshot)
        self.db.delete_symbols(self.symbols_snapshot)
        self.db.delete_imports(self.imports_snapshot)
        return self.symbols, self.imports, self.symbol_references

    @staticmethod
    def _normalize_signature_bytes(
        file_bytes: bytes, start_byte: int, end_byte: int, *, tail_rstrip: bool
    ) -> str:
        raw = file_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
        text = raw.rstrip() if tail_rstrip else raw.strip()
        return " ".join(text.split())

    def _qn(self, *parts: str) -> str:
        return ".".join((self._package, *parts))

    def _snapshot_is_test(self, kind: str, name: str) -> bool:
        base = self.stack[-1].is_test if self.stack else False
        if kind == "function" and name.startswith("Test") and len(name) > 4:
            return True
        if (
            kind in ("struct", "interface")
            and name.startswith("Test")
            and len(name) > 4
        ):
            return True
        if kind == "method" and name.startswith("Test") and base:
            return True
        return base

    def _container_symbol_dict(
        self,
        symbol_id: int,
        file_id: int,
        parent_id: Optional[int],
        name: str,
        qualified_name: str,
        kind: str,
        line_start: int,
        line_end: int,
        signature: str,
        docstring: Optional[str],
        modifiers: list[str],
        base_classes: list[str],
        is_test: bool,
    ) -> Dict:
        return {
            "id": symbol_id,
            "file_id": file_id,
            "parent_id": parent_id,
            "name": name,
            "qualified_name": qualified_name,
            "kind": kind,
            "line_start": line_start,
            "line_end": line_end,
            "line_count": line_end - line_start + 1,
            "signature": signature,
            "docstring": docstring,
            "modifiers": str(modifiers) if modifiers else None,
            "language": "go",
            "base_classes": str(base_classes) if base_classes else None,
            "is_test": is_test,
        }

    def _variable_symbol_dict(
        self,
        symbol_id: int,
        file_id: int,
        parent_id: Optional[int],
        name: str,
        qualified_name: str,
        kind: str,
        line_start: int,
        line_end: int,
        signature: str,
        is_test: bool,
    ) -> Dict:
        return {
            "id": symbol_id,
            "file_id": file_id,
            "parent_id": parent_id,
            "name": name,
            "qualified_name": qualified_name,
            "kind": kind,
            "line_start": line_start,
            "line_end": line_end,
            "line_count": line_end - line_start + 1,
            "signature": signature,
            "docstring": None,
            "modifiers": None,
            "language": "go",
            "base_classes": None,
            "is_test": is_test,
        }

    def _record_import(
        self,
        file_id: int,
        import_path: str,
        imported_symbol: str,
        alias: Optional[str],
        line_number: int,
        import_type: str,
        import_scope: str,
        signature: str,
    ) -> None:
        key = (import_path, imported_symbol)
        row = {
            "file_id": file_id,
            "import_path": import_path,
            "imported_symbol": imported_symbol,
            "alias": alias,
            "line_number": line_number,
            "import_type": import_type,
            "import_scope": import_scope,
            "signature": signature,
        }
        if key in self.imports_snapshot:
            self.imports_snapshot[key]["seen"] = True
            if self.imports_snapshot[key]["line_number"] != line_number:
                import_id = self.imports_snapshot[key]["id"]
                self.imports.append({"id": import_id, **row})
        else:
            import_id = self.assigner.reserve("imports", 1)[0]
            self.imports_snapshot[key] = {
                "id": import_id,
                "line_number": line_number,
                "seen": True,
            }
            self.imports.append({"id": import_id, **row})

    def _record_symbol_reference(
        self,
        file_id: int,
        target_name: str,
        ref_symbol_qualified_name: str,
        source_line: int,
        ref_kind: str,
        context: str,
        key: Tuple[str, str, int],
    ) -> None:
        row = {
            "ref_symbol_name": target_name,
            "ref_symbol_qualified_name": ref_symbol_qualified_name,
            "source_file_id": file_id,
            "source_line": source_line,
            "ref_kind": ref_kind,
            "context": context,
        }
        if key in self.symbols_references_snapshot:
            self.symbols_references_snapshot[key]["seen"] = True
            if self.symbols_references_snapshot[key]["context"] != context:
                symbol_reference_id = self.symbols_references_snapshot[key]["id"]
                self.symbol_references.append({"id": symbol_reference_id, **row})
                self.symbols_references_snapshot[key]["context"] = context
        else:
            symbol_reference_id = self.assigner.reserve("symbol_references", 1)[0]
            self.symbols_references_snapshot[key] = {
                "id": symbol_reference_id,
                "source_line": source_line,
                "context": context,
                "seen": True,
            }
            self.symbol_references.append({"id": symbol_reference_id, **row})

    def _extract_package(self, node: Node, _file_bytes: bytes) -> None:
        if node.type != "package_clause":
            return
        id_node = node.child_by_field_name("name")
        if id_node is None:
            for ch in node.children:
                if ch.type == "package_identifier" and ch.text:
                    self._package = ch.text.decode("utf-8")
                    return
        elif id_node.text:
            self._package = id_node.text.decode("utf-8")

    def _string_literal_content(self, node: Node, file_bytes: bytes) -> Optional[str]:
        if node.type != "interpreted_string_literal":
            return None
        text = file_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        m = self._interpreted_string_import_path_re.match(text.strip())
        if m:
            return m.group(1)
        return None

    def _extract_import_declaration(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> None:
        if node.text is None:
            return
        signature = node.text.decode("utf-8")
        line_number = node.start_point.row + 1
        import_scope = "module" if not self.stack else "function"

        def record_spec(spec: Node) -> None:
            alias: Optional[str] = None
            path: Optional[str] = None
            for ch in spec.children:
                if ch.type == "package_identifier" and ch.text:
                    alias = ch.text.decode("utf-8")
                elif ch.type == "interpreted_string_literal":
                    path = self._string_literal_content(ch, file_bytes)
            if path is None:
                return
            import_type = "relative" if path.startswith(".") else "absolute"
            imported_symbol = ""
            self._record_import(
                file_id,
                path,
                imported_symbol,
                alias,
                line_number,
                import_type,
                import_scope,
                signature,
            )
            local = alias if alias else path.split("/")[-1]
            if local and local != ".":
                self._import_roots[local] = path

        for ch in node.children:
            if ch.type == "import_spec_list":
                for spec in ch.children:
                    if spec.type == "import_spec":
                        record_spec(spec)
            elif ch.type == "import_spec":
                record_spec(ch)

    def _children_source_file_order(self, node: Node) -> List[Node]:
        if node.type != "source_file":
            return list(node.children)
        imports: list[Node] = []
        rest: list[Node] = []
        for ch in node.children:
            if ch.type == "import_declaration":
                imports.append(ch)
            else:
                rest.append(ch)
        return imports + rest

    def _walk_source_file(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        if node.type == "source_file":
            for ch in self._children_source_file_order(node):
                self._walk(ch, file_id, file_bytes)
            return
        self._walk(node, file_id, file_bytes)

    def _walk(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        if node.type == "package_clause":
            self._extract_package(node, file_bytes)
            return

        if node.type == "import_declaration":
            self._extract_import_declaration(node, file_id, file_bytes)
            return

        self._process_node(node, file_id, file_bytes)

        pushed: Optional[Tuple[int, str, str, bool]] = None
        if node.type == "type_spec":
            pushed = self._maybe_push_type_spec(node, file_id, file_bytes)
        elif node.type in ("function_declaration", "method_declaration"):
            pushed = self._maybe_push_function(node, file_id, file_bytes)

        children = (
            self._children_source_file_order(node)
            if node.type == "source_file"
            else list(node.children)
        )
        for child in children:
            self._walk(child, file_id, file_bytes)

        if pushed is not None:
            self.stack.pop()
            if pushed[2] == "method":
                self._receiver = None

    def _maybe_push_type_spec(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Tuple[int, str, str, bool]]:
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return None
        if type_node.type == "struct_type":
            kind = "struct"
            base_classes: list[str] = []
        elif type_node.type == "interface_type":
            kind = "interface"
            base_classes = self._interface_embeds(type_node)
        else:
            return None

        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        qn = self._qn(name)
        sig = self._normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self._snapshot_is_test(kind, name)
        parent_id = self.stack[-1].symbol_id if self.stack else None
        sym = self._emit_container_symbol(
            file_id,
            parent_id,
            name,
            qn,
            kind,
            line_start,
            line_end,
            sig,
            None,
            [],
            base_classes,
            is_test,
        )
        if sym is None:
            snap_key = (qn, kind)
            if snap_key in self.symbols_snapshot:
                sid = self.symbols_snapshot[snap_key]["id"]
                self._register_container(qn, kind, sid, is_test)
                self.stack.append(
                    StackFrame(sid, qn, kind, self._snapshot_is_test(kind, name))
                )
                return (sid, qn, kind, is_test)
            return None
        self._register_container(qn, kind, sym["id"], sym["is_test"])
        self.stack.append(StackFrame(sym["id"], qn, kind, sym["is_test"]))
        return (sym["id"], qn, kind, sym["is_test"])

    def _interface_embeds(self, iface: Node) -> list[str]:
        out: list[str] = []
        for ch in iface.children:
            if ch.type != "type_elem":
                continue
            for inner in ch.children:
                if inner.type == "type_identifier" and inner.text:
                    out.append(inner.text.decode("utf-8"))
        return out

    def _maybe_push_function(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Tuple[int, str, str, bool]]:
        self._receiver = None
        name: Optional[str] = None
        if node.type == "function_declaration":
            n = node.child_by_field_name("name")
            if n is None or n.text is None:
                return None
            name = n.text.decode("utf-8")
            kind = "function"
            parent_qn = self.stack[-1].qualified_name if self.stack else None
            qn = self._qn(name) if parent_qn is None else f"{parent_qn}.{name}"
        else:
            name_node = node.child_by_field_name("name")
            if name_node is None or name_node.text is None:
                return None
            name = name_node.text.decode("utf-8")
            kind = "method"
            recv = node.child_by_field_name("receiver")
            recv_type = self._receiver_struct_qn(recv)
            qn = f"{recv_type}.{name}" if recv_type else self._qn(name)

        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = self._normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        recv_type_qn: Optional[str] = None
        parent_id: Optional[int] = None
        if kind == "method":
            recv = node.child_by_field_name("receiver")
            recv_type_qn = self._receiver_struct_qn(recv)
            if recv_type_qn:
                self._receiver = self._receiver_param(recv, recv_type_qn)
                parent_id = self._container_by_qn.get(recv_type_qn)
            is_test = (
                bool(recv_type_qn)
                and self._container_is_test.get(recv_type_qn, False)
                and name.startswith("Test")
                and len(name) > 4
            )
        else:
            is_test = name.startswith("Test") and len(name) > 4
            parent_id = self.stack[-1].symbol_id if self.stack else None

        sym = self._emit_container_symbol(
            file_id,
            parent_id,
            name,
            qn,
            kind,
            line_start,
            line_end,
            sig,
            None,
            [],
            [],
            is_test,
        )
        if sym is None:
            snap_key = (qn, kind)
            if snap_key in self.symbols_snapshot:
                sid = self.symbols_snapshot[snap_key]["id"]
                self.stack.append(StackFrame(sid, qn, kind, is_test))
                return (sid, qn, kind, is_test)
            return None
        self.stack.append(StackFrame(sym["id"], qn, kind, sym["is_test"]))
        return (sym["id"], qn, kind, is_test)

    def _receiver_param(
        self, recv: Optional[Node], struct_qn: str
    ) -> tuple[str, str] | None:
        if recv is None:
            return None
        for ch in recv.children:
            if ch.type != "parameter_declaration":
                continue
            id_node = ch.child_by_field_name("name")
            if id_node is None or id_node.text is None:
                for c in ch.children:
                    if c.type == "identifier" and c.text:
                        return (c.text.decode("utf-8"), struct_qn)
            else:
                return (id_node.text.decode("utf-8"), struct_qn)
        return None

    def _receiver_struct_qn(self, recv: Optional[Node]) -> Optional[str]:
        if recv is None:
            return None
        for ch in recv.children:
            if ch.type != "parameter_declaration":
                continue
            for c in ch.children:
                t = self._type_identifier_name(c)
                if t:
                    return self._qn(t)
        return None

    def _type_identifier_name(self, node: Node) -> Optional[str]:
        if node.type == "type_identifier" and node.text:
            return node.text.decode("utf-8")
        for c in node.children:
            found = self._type_identifier_name(c)
            if found:
                return found
        return None

    def _register_container(
        self, qualified_name: str, kind: str, sid: int, is_test: bool
    ) -> None:
        if kind in ("struct", "interface"):
            self._container_by_qn[qualified_name] = sid
            self._container_is_test[qualified_name] = is_test

    def _emit_container_symbol(
        self,
        file_id: int,
        parent_id: Optional[int],
        name: str,
        qualified_name: str,
        kind: str,
        line_start: int,
        line_end: int,
        signature: str,
        docstring: Optional[str],
        modifiers: list[str],
        base_classes: list[str],
        is_test: bool,
    ) -> Optional[Dict]:
        pid = (
            parent_id
            if parent_id is not None
            else (self.stack[-1].symbol_id if self.stack else None)
        )
        key = (qualified_name, kind)
        if key in self.symbols_snapshot:
            self.symbols_snapshot[key]["seen"] = True
            if (line_start, line_end) != (
                self.symbols_snapshot[key]["line_start"],
                self.symbols_snapshot[key]["line_end"],
            ):
                symbol_id = self.symbols_snapshot[key]["id"]
                self.symbols_snapshot[key]["line_start"] = line_start
                self.symbols_snapshot[key]["line_end"] = line_end
                row = self._container_symbol_dict(
                    symbol_id,
                    file_id,
                    pid,
                    name,
                    qualified_name,
                    kind,
                    line_start,
                    line_end,
                    signature,
                    docstring,
                    modifiers,
                    base_classes,
                    is_test,
                )
                self.symbols.append(row)
                self._register_container(qualified_name, kind, symbol_id, is_test)
                return row
            return None
        symbol_id = self.assigner.reserve("symbols", 1)[0]
        self.symbols_snapshot[key] = {
            "id": symbol_id,
            "seen": True,
            "line_start": line_start,
            "line_end": line_end,
        }
        row = self._container_symbol_dict(
            symbol_id,
            file_id,
            pid,
            name,
            qualified_name,
            kind,
            line_start,
            line_end,
            signature,
            docstring,
            modifiers,
            base_classes,
            is_test,
        )
        self.symbols.append(row)
        self._register_container(qualified_name, kind, symbol_id, is_test)
        return row

    def _emit_field_symbol(
        self,
        file_id: int,
        parent_id: int,
        parent_qn: str,
        field_node: Node,
        file_bytes: bytes,
    ) -> None:
        name_node = field_node.child_by_field_name("name")
        if name_node is None:
            for ch in field_node.children:
                if ch.type == "field_identifier" and ch.text:
                    name_node = ch
                    break
        if name_node is None or name_node.text is None:
            return
        name = name_node.text.decode("utf-8")
        qn = f"{parent_qn}.{name}"
        line_start = field_node.start_point.row + 1
        line_end = field_node.end_point.row + 1
        sig = self._normalize_signature_bytes(
            file_bytes, field_node.start_byte, field_node.end_byte, tail_rstrip=True
        )
        kind = "variable"
        is_test = self.stack[-1].is_test if self.stack else False
        key = (qn, kind)
        if key in self.symbols_snapshot:
            self.symbols_snapshot[key]["seen"] = True
            if (line_start, line_end) != (
                self.symbols_snapshot[key]["line_start"],
                self.symbols_snapshot[key]["line_end"],
            ):
                sid = self.symbols_snapshot[key]["id"]
                self.symbols_snapshot[key]["line_start"] = line_start
                self.symbols_snapshot[key]["line_end"] = line_end
                self.symbols.append(
                    self._variable_symbol_dict(
                        sid,
                        file_id,
                        parent_id,
                        name,
                        qn,
                        kind,
                        line_start,
                        line_end,
                        sig,
                        is_test,
                    )
                )
            return
        sid = self.assigner.reserve("symbols", 1)[0]
        self.symbols_snapshot[key] = {
            "id": sid,
            "seen": True,
            "line_start": line_start,
            "line_end": line_end,
        }
        self.symbols.append(
            self._variable_symbol_dict(
                sid,
                file_id,
                parent_id,
                name,
                qn,
                kind,
                line_start,
                line_end,
                sig,
                is_test,
            )
        )

    def _emit_var_const(
        self,
        file_id: int,
        spec: Node,
        file_bytes: bytes,
        *,
        is_const: bool,
    ) -> None:
        name_node = spec.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return
        name = name_node.text.decode("utf-8")
        kind = "constant" if is_const else "variable"
        qn = self._qn(name)
        line_start = spec.start_point.row + 1
        line_end = spec.end_point.row + 1
        sig = self._normalize_signature_bytes(
            file_bytes, spec.start_byte, spec.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test if self.stack else False
        key = (qn, kind)
        if key in self.symbols_snapshot:
            self.symbols_snapshot[key]["seen"] = True
            if (line_start, line_end) != (
                self.symbols_snapshot[key]["line_start"],
                self.symbols_snapshot[key]["line_end"],
            ):
                sid = self.symbols_snapshot[key]["id"]
                self.symbols_snapshot[key]["line_start"] = line_start
                self.symbols_snapshot[key]["line_end"] = line_end
                self.symbols.append(
                    self._variable_symbol_dict(
                        sid,
                        file_id,
                        None,
                        name,
                        qn,
                        kind,
                        line_start,
                        line_end,
                        sig,
                        is_test,
                    )
                )
            return
        sid = self.assigner.reserve("symbols", 1)[0]
        self.symbols_snapshot[key] = {
            "id": sid,
            "seen": True,
            "line_start": line_start,
            "line_end": line_end,
        }
        self.symbols.append(
            self._variable_symbol_dict(
                sid,
                file_id,
                None,
                name,
                qn,
                kind,
                line_start,
                line_end,
                sig,
                is_test,
            )
        )

    def _process_node(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        if node.type == "field_declaration":
            if self.stack and self.stack[-1].kind == "struct":
                parent_id = self.stack[-1].symbol_id
                parent_qn = self.stack[-1].qualified_name
                self._emit_field_symbol(file_id, parent_id, parent_qn, node, file_bytes)
            return

        if node.type in ("const_spec", "var_spec"):
            parent = node.parent
            if parent and parent.type == "const_declaration":
                self._emit_var_const(file_id, node, file_bytes, is_const=True)
            elif parent and parent.type == "var_declaration":
                self._emit_var_const(file_id, node, file_bytes, is_const=False)
            return

        if (
            node.type == "method_elem"
            and self.stack
            and self.stack[-1].kind == "interface"
        ):
            self._emit_interface_method(file_id, node, file_bytes)
            return

        if node.type == "call_expression":
            self._extract_call(node, file_id, file_bytes)
        elif node.type == "selector_expression":
            self._extract_selector_ref(node, file_id, ref_kind="access")
        else:
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                if node.type == "field_declaration":
                    return
                if node.type == "parameter_declaration":
                    pl = node.parent
                    if pl is not None and pl.type == "parameter_list":
                        parent = pl.parent
                        if (
                            parent is not None
                            and parent.type == "method_declaration"
                            and pl == parent.child_by_field_name("receiver")
                        ):
                            return
                self._extract_type_annotation(type_node, file_id, file_bytes)

    def _emit_interface_method(
        self, file_id: int, node: Node, file_bytes: bytes
    ) -> None:
        name: Optional[str] = None
        for ch in node.children:
            if ch.type == "field_identifier" and ch.text:
                name = ch.text.decode("utf-8")
                break
        if not name:
            return
        parent_qn = self.stack[-1].qualified_name
        qn = f"{parent_qn}.{name}"
        kind = "method"
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = self._normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test
        parent_sid = self.stack[-1].symbol_id if self.stack else None
        self._emit_container_symbol(
            file_id,
            parent_sid,
            name,
            qn,
            kind,
            line_start,
            line_end,
            sig,
            None,
            [],
            [],
            is_test,
        )

    def _call_function_text(self, node: Node) -> Optional[str]:
        fn = node.child_by_field_name("function")
        if fn is None or fn.text is None:
            return None
        return fn.text.decode("utf-8")

    def _extract_call(self, node: Node, file_id: int, _file_bytes: bytes) -> None:
        fn = node.child_by_field_name("function")
        if fn is not None and fn.text:
            name = fn.text.decode("utf-8")
            if fn.type == "type_identifier" and name in _GO_TYPE_SKIP:
                return
            if fn.type == "identifier" and name in _GO_TYPE_SKIP:
                return
        target = self._call_function_text(node)
        if not target:
            return
        if self._should_skip_reference_target(target, ref_kind="call"):
            return
        resolved = self._resolve_selector_target(target)
        self._emit_ref(
            file_id,
            target,
            resolved,
            node,
            "call",
        )

    def _extract_selector_ref(
        self,
        node: Node,
        file_id: int,
        *,
        ref_kind: str,
    ) -> None:
        parent = node.parent
        if (
            parent is not None
            and parent.type == "call_expression"
            and parent.child_by_field_name("function") == node
        ):
            return
        if node.text is None:
            return
        target = node.text.decode("utf-8")
        if self._should_skip_reference_target(target, ref_kind=ref_kind):
            return
        resolved = self._resolve_selector_target(target)
        self._emit_ref(file_id, target, resolved, node, ref_kind)

    def _resolve_selector_target(self, target: str) -> str:
        if self._receiver and "." in target:
            recv_name, _, rest = target.partition(".")
            if recv_name == self._receiver[0]:
                return f"{self._receiver[1]}.{rest}"
        if "." not in target and target:
            if target in _GO_TYPE_SKIP:
                return target
            return self._qn(target)
        return target

    def _should_skip_reference_target(self, target: str, *, ref_kind: str) -> bool:
        root = target.split(".", 1)[0]
        if ref_kind == "call" and root in _GO_BUILTIN_CALLS:
            return True
        if root in self._import_roots:
            path = self._import_roots[root]
            if _go_std_heuristic(path):
                return True
        return False

    def _emit_ref(
        self,
        file_id: int,
        target_name: str,
        ref_qn: str,
        node: Node,
        ref_kind: str,
    ) -> None:
        source_line = node.start_point.row + 1
        key = (ref_qn, ref_kind, source_line)
        ctx = (
            node.text.decode("utf-8", errors="replace") if node.text is not None else ""
        )
        self._record_symbol_reference(
            file_id,
            target_name,
            ref_qn,
            source_line,
            ref_kind,
            ctx,
            key,
        )

    def _extract_type_annotation(
        self, type_node: Node, file_id: int, _file_bytes: bytes
    ) -> None:
        if type_node.type in ("interface_type", "struct_type"):
            return
        p = type_node.parent
        if p is not None and p.type == "type_elem":
            return
        simple = self._simple_type_name(type_node)
        if not simple or simple in _GO_TYPE_SKIP:
            return
        target = simple
        if self._should_skip_reference_target(target, ref_kind="type_annotation"):
            return
        resolved = self._resolve_selector_target(target)
        self._emit_ref(
            file_id,
            target,
            resolved,
            type_node,
            "type_annotation",
        )

    def _simple_type_name(self, type_node: Node) -> Optional[str]:
        if type_node.type == "qualified_type" and type_node.text:
            return type_node.text.decode("utf-8")
        if type_node.type == "type_identifier" and type_node.text:
            return type_node.text.decode("utf-8")
        if type_node.type == "pointer_type":
            inner = type_node.child_by_field_name("element")
            if inner is None:
                for c in type_node.children:
                    if c.type in ("type_identifier", "pointer_type", "slice_type"):
                        inner = c
                        break
            if inner is not None:
                return self._simple_type_name(inner)
        if type_node.type == "slice_type":
            inner = type_node.child_by_field_name("element")
            if inner is not None:
                return self._simple_type_name(inner)
        for c in type_node.children:
            got = self._simple_type_name(c)
            if got:
                return got
        return None
