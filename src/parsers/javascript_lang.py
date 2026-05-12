import re
from typing import Dict, List, Optional, Tuple

from tree_sitter import Node, Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.base import ParserBase
from src.parsers.parser_utils import StackFrame

_JS_GLOBAL_CALL_SKIP = frozenset(
    {
        "console",
        "Math",
        "Object",
        "Array",
        "Number",
        "String",
        "Boolean",
        "JSON",
        "Promise",
        "parseInt",
        "parseFloat",
        "isNaN",
        "isFinite",
        "setTimeout",
        "setInterval",
        "clearTimeout",
        "clearInterval",
        "require",
    }
)

_TS_PREDEFINED_TYPES = frozenset(
    {
        "string",
        "number",
        "boolean",
        "void",
        "unknown",
        "any",
        "never",
        "object",
        "symbol",
        "bigint",
        "null",
        "undefined",
    }
)


def _normalize_signature_bytes(
    file_bytes: bytes, start_byte: int, end_byte: int, *, tail_rstrip: bool
) -> str:
    raw = file_bytes[start_byte:end_byte].decode("utf-8", errors="replace")
    text = raw.rstrip() if tail_rstrip else raw.strip()
    return " ".join(text.split())


def _string_literal_path(node: Node, file_bytes: bytes) -> Optional[str]:
    if node.type != "string":
        return None
    inner = node.child_by_field_name("fragment")
    if inner is not None and inner.text is not None:
        return inner.text.decode("utf-8")
    text = file_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    m = re.match(r'^["\'](.+)["\']$', text.strip())
    return m.group(1) if m else None


def _import_export_module_path(node: Node, file_bytes: bytes) -> Optional[str]:
    src = node.child_by_field_name("source")
    if src is None:
        return None
    return _string_literal_path(src, file_bytes)


def _is_functionish_value(n: Node) -> bool:
    return n.type in (
        "arrow_function",
        "function",
        "function_expression",
        "generator_function",
    )


class JavascriptParser(ParserBase):
    """Parses .js / .jsx / .mjs / .cjs / .ts / .mts / .cts / .tsx into index rows."""

    def __init__(
        self,
        assigner: GlobalIDAssigner,
        db: CodeDB,
        parser: Parser,
        dialect: str = "javascript",
    ):
        self.parser = parser
        self.assigner = assigner
        self.db = db
        self.dialect = dialect
        self.stack: List[StackFrame] = []
        self.symbols: List[Dict] = []
        self.imports: List[Dict] = []
        self.symbol_references: List[Dict] = []
        self.symbols_snapshot: dict[tuple[str, str], dict] = {}
        self.symbols_references_snapshot: dict[tuple[str, str, int], dict] = {}
        self.imports_snapshot: dict[tuple[str, str], dict] = {}
        self._class_stack: List[str] = []

    def parse(
        self, file_id: int, file_bytes: bytes
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        self.stack = []
        self._class_stack = []
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
        if root.type == "program":
            self._walk_program(root, file_id, file_bytes)
        else:
            self._walk(root, file_id, file_bytes)
        self.db.delete_symbol_references(self.symbols_references_snapshot)
        self.db.delete_symbols(self.symbols_snapshot)
        self.db.delete_imports(self.imports_snapshot)
        return self.symbols, self.imports, self.symbol_references

    def _import_scope(self) -> str:
        return "function" if self.stack else "module"

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
            "language": self.dialect,
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
            "language": self.dialect,
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

    def _snapshot_is_test(self, kind: str, name: str) -> bool:
        base = self.stack[-1].is_test if self.stack else False
        if kind in ("function", "method") and name.startswith("test") and len(name) > 4:
            return True
        if kind == "method" and name.startswith("test") and len(name) > 4 and base:
            return True
        return base

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
        return row

    def _emit_variable_symbol(
        self,
        file_id: int,
        parent_id: Optional[int],
        name: str,
        qualified_name: str,
        kind: str,
        line_start: int,
        line_end: int,
        signature: str,
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
                row = self._variable_symbol_dict(
                    symbol_id,
                    file_id,
                    pid,
                    name,
                    qualified_name,
                    kind,
                    line_start,
                    line_end,
                    signature,
                    is_test,
                )
                self.symbols.append(row)
                return row
            return None
        symbol_id = self.assigner.reserve("symbols", 1)[0]
        self.symbols_snapshot[key] = {
            "id": symbol_id,
            "seen": True,
            "line_start": line_start,
            "line_end": line_end,
        }
        row = self._variable_symbol_dict(
            symbol_id,
            file_id,
            pid,
            name,
            qualified_name,
            kind,
            line_start,
            line_end,
            signature,
            is_test,
        )
        self.symbols.append(row)
        return row

    def _qualified_var_name(self, name: str) -> str:
        if self.stack:
            return f"{self.stack[-1].qualified_name}.{name}"
        return name

    def _class_base_names(self, node: Node) -> list[str]:
        out: list[str] = []
        for ch in node.children:
            if ch.type != "class_heritage":
                continue
            for h in ch.children:
                if h.type == "identifier" and h.text:
                    out.append(h.text.decode("utf-8"))
                elif h.type == "member_expression":
                    t = self._member_expression_text(h)
                    if t:
                        out.append(t)
        return out

    def _interface_extends_from_declaration(self, node: Node) -> list[str]:
        out: list[str] = []
        for ch in node.children:
            if ch.type != "extends_type_clause":
                continue
            for c in ch.children:
                if c.type in ("type_identifier", "identifier") and c.text:
                    out.append(c.text.decode("utf-8"))
                elif c.type == "nested_type_identifier" and c.text:
                    out.append(c.text.decode("utf-8", errors="replace"))
        return out

    def _walk_program(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        for ch in node.children:
            self._walk(ch, file_id, file_bytes)

    def _walk(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        if node.type == "import_statement":
            self._extract_import_statement(node, file_id, file_bytes)
            return

        if node.type == "export_statement":
            self._extract_export_statement(node, file_id, file_bytes)

        self._process_references(node, file_id, file_bytes)

        pushed: Optional[Tuple[int, str, str, bool]] = None
        skip_children = False

        if node.type in ("function_declaration", "generator_function_declaration"):
            pushed = self._maybe_push_function(node, file_id, file_bytes)
        elif node.type == "class_declaration":
            pushed = self._maybe_push_class(node, file_id, file_bytes)
        elif node.type == "interface_declaration":
            pushed = self._maybe_push_interface(node, file_id, file_bytes)
        elif node.type == "type_alias_declaration":
            pushed = self._maybe_push_type_alias(node, file_id, file_bytes)
            if self.dialect in ("typescript", "tsx"):
                val = node.child_by_field_name("value")
                if val is not None:
                    self._emit_ts_refs_from_type_tree(val, file_id)
        elif node.type in ("lexical_declaration", "variable_declaration"):
            self._emit_declarations(node, file_id, file_bytes)
        elif node.type == "method_definition":
            pushed = self._maybe_push_method_definition(node, file_id, file_bytes)
        elif node.type == "field_definition":
            skip_children = self._emit_field_definition(node, file_id, file_bytes)

        if self.dialect in ("typescript", "tsx"):
            self._extract_ts_type_refs_from_node(node, file_id, file_bytes)

        if not skip_children:
            for child in node.children:
                self._walk(child, file_id, file_bytes)

        if pushed is not None:
            self.stack.pop()
            if pushed[2] == "class":
                self._class_stack.pop()

    def _maybe_push_function(
        self,
        node: Node,
        file_id: int,
        file_bytes: bytes,
    ) -> Optional[Tuple[int, str, str, bool]]:
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        kind = "function"
        parent_qn = self.stack[-1].qualified_name if self.stack else None
        qn = f"{parent_qn}.{name}" if parent_qn else name
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
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
        return (sym["id"], qn, kind, sym["is_test"])

    def _maybe_push_class(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Tuple[int, str, str, bool]]:
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        kind = "class"
        parent_qn = self.stack[-1].qualified_name if self.stack else None
        qn = f"{parent_qn}.{name}" if parent_qn else name
        bases = self._class_base_names(node)
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test if self.stack else False
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
            bases,
            is_test,
        )
        if sym is None:
            snap_key = (qn, kind)
            if snap_key in self.symbols_snapshot:
                sid = self.symbols_snapshot[snap_key]["id"]
                self._class_stack.append(qn)
                self.stack.append(StackFrame(sid, qn, kind, is_test))
                return (sid, qn, kind, is_test)
            return None
        self._class_stack.append(qn)
        self.stack.append(StackFrame(sym["id"], qn, kind, sym["is_test"]))
        return (sym["id"], qn, kind, sym["is_test"])

    def _maybe_push_interface(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Tuple[int, str, str, bool]]:
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        kind = "interface"
        parent_qn = self.stack[-1].qualified_name if self.stack else None
        qn = f"{parent_qn}.{name}" if parent_qn else name
        bases = self._interface_extends_from_declaration(node)
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test if self.stack else False
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
            bases,
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
        return (sym["id"], qn, kind, sym["is_test"])

    def _maybe_push_type_alias(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Tuple[int, str, str, bool]]:
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        kind = "type"
        parent_qn = self.stack[-1].qualified_name if self.stack else None
        qn = f"{parent_qn}.{name}" if parent_qn else name
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test if self.stack else False
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
        return (sym["id"], qn, kind, sym["is_test"])

    def _maybe_push_method_definition(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> Optional[Tuple[int, str, str, bool]]:
        if not self._class_stack:
            return None
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.text is None:
            return None
        name = name_node.text.decode("utf-8")
        class_qn = self._class_stack[-1]
        kind = "method"
        qn = f"{class_qn}.{name}"
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
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
        return (sym["id"], qn, kind, sym["is_test"])

    def _emit_field_definition(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> bool:
        if not self._class_stack:
            return False
        prop = node.child_by_field_name("property")
        if prop is None or prop.text is None:
            for ch in node.children:
                if (
                    ch.type
                    in (
                        "property_identifier",
                        "private_property_identifier",
                    )
                    and ch.text
                ):
                    prop = ch
                    break
        if prop is None or prop.text is None:
            return False
        name = prop.text.decode("utf-8")
        class_qn = self._class_stack[-1]
        qn = f"{class_qn}.{name}"
        val = node.child_by_field_name("value")
        kind = (
            "method" if val is not None and _is_functionish_value(val) else "variable"
        )
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test if self.stack else False
        parent_id = self.stack[-1].symbol_id if self.stack else None
        if kind == "method":
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
            sid: Optional[int] = None
            frame_test = is_test
            if sym is not None:
                sid = sym["id"]
                frame_test = sym["is_test"]
            else:
                snap_key = (qn, kind)
                if snap_key in self.symbols_snapshot:
                    sid = self.symbols_snapshot[snap_key]["id"]
            if sid is not None:
                self.stack.append(StackFrame(sid, qn, kind, frame_test))
                for child in node.children:
                    self._walk(child, file_id, file_bytes)
                self.stack.pop()
            return True
        self._emit_variable_symbol(
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
        return False

    def _emit_declarations(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        is_const = node.type == "lexical_declaration" and any(
            ch.type == "const" for ch in node.children
        )
        for ch in node.children:
            if ch.type != "variable_declarator":
                continue
            self._emit_variable_declarator(ch, file_id, file_bytes, is_const=is_const)

    def _emit_variable_declarator(
        self, node: Node, file_id: int, file_bytes: bytes, *, is_const: bool
    ) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        if name_node.type not in (
            "identifier",
            "shorthand_property_identifier_pattern",
        ):
            return
        if name_node.text is None:
            return
        name = name_node.text.decode("utf-8")
        qn = self._qualified_var_name(name)
        kind = "constant" if is_const else "variable"
        line_start = node.start_point.row + 1
        line_end = node.end_point.row + 1
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        is_test = self.stack[-1].is_test if self.stack else False
        self._emit_variable_symbol(
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

    def _extract_import_statement(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> None:
        path = _import_export_module_path(node, file_bytes)
        if path is None:
            return
        line_number = node.start_point.row + 1
        import_type = "relative" if path.startswith(".") else "absolute"
        scope = self._import_scope()
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        clause = None
        for ch in node.children:
            if ch.type == "import_clause":
                clause = ch
                break
        if clause is None:
            self._record_import(
                file_id, path, "", None, line_number, import_type, scope, sig
            )
            return
        self._record_import_clauses(
            file_id, path, clause, line_number, import_type, scope, sig
        )

    def _record_import_clauses(
        self,
        file_id: int,
        path: str,
        clause: Node,
        line_number: int,
        import_type: str,
        scope: str,
        signature: str,
    ) -> None:
        for ch in clause.children:
            if ch.type == "identifier":
                if ch.text is None:
                    continue
                self._record_import(
                    file_id,
                    path,
                    "",
                    ch.text.decode("utf-8"),
                    line_number,
                    import_type,
                    scope,
                    signature,
                )
            elif ch.type == "namespace_import":
                alias_s: Optional[str] = None
                for c in ch.children:
                    if c.type == "identifier" and c.text:
                        alias_s = c.text.decode("utf-8")
                        break
                self._record_import(
                    file_id,
                    path,
                    "",
                    alias_s,
                    line_number,
                    import_type,
                    scope,
                    signature,
                )
            elif ch.type == "named_imports":
                for spec in ch.children:
                    if spec.type != "import_specifier":
                        continue
                    orig = spec.child_by_field_name("name")
                    al = spec.child_by_field_name("alias")
                    if orig is None or orig.text is None:
                        continue
                    orig_s = orig.text.decode("utf-8")
                    alias_s = al.text.decode("utf-8") if al and al.text else None
                    self._record_import(
                        file_id,
                        path,
                        orig_s,
                        alias_s,
                        line_number,
                        import_type,
                        scope,
                        signature,
                    )

    def _extract_export_statement(
        self, node: Node, file_id: int, file_bytes: bytes
    ) -> None:
        path = _import_export_module_path(node, file_bytes)
        line_number = node.start_point.row + 1
        import_type = "relative" if path and path.startswith(".") else "absolute"
        scope = self._import_scope()
        sig = _normalize_signature_bytes(
            file_bytes, node.start_byte, node.end_byte, tail_rstrip=True
        )
        if path:
            clause = None
            for ch in node.children:
                if ch.type == "export_clause":
                    clause = ch
                    break
            if clause is not None:
                for spec in clause.children:
                    if spec.type != "export_specifier":
                        continue
                    orig = spec.child_by_field_name("name")
                    if orig is None or orig.text is None:
                        continue
                    orig_s = orig.text.decode("utf-8")
                    al = spec.child_by_field_name("alias")
                    alias_s = al.text.decode("utf-8") if al and al.text else None
                    self._record_import(
                        file_id,
                        path,
                        orig_s,
                        alias_s,
                        line_number,
                        import_type,
                        scope,
                        sig,
                    )
            else:
                self._record_import(
                    file_id, path, "*", None, line_number, import_type, scope, sig
                )

    def _process_references(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        if node.type == "call_expression":
            self._ref_call_expression(node, file_id, file_bytes)
        elif node.type == "new_expression":
            self._ref_new_expression(node, file_id, file_bytes)
        elif node.type == "member_expression":
            parent = node.parent
            if parent is None or parent.type != "call_expression":
                self._ref_member_expression_access(node, file_id, file_bytes)
        elif node.type == "subscript_expression":
            self._ref_subscript_expression(node, file_id, file_bytes)

    def _call_callee_text(self, func: Node, file_bytes: bytes) -> Optional[str]:
        if func.type == "identifier" and func.text:
            return func.text.decode("utf-8")
        if func.type == "member_expression":
            return self._member_expression_text(func)
        if func.type == "parenthesized_expression":
            inner = func.named_children[0] if func.named_children else None
            if inner is not None:
                return self._call_callee_text(inner, file_bytes)
        return None

    def _member_expression_text(self, node: Node) -> Optional[str]:
        if node.text is not None:
            return node.text.decode("utf-8", errors="replace")
        return None

    def _ref_call_expression(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        func = node.child_by_field_name("function")
        if func is None:
            return
        text = self._call_callee_text(func, file_bytes)
        if not text:
            return
        root = text.split(".", 1)[0]
        if root in _JS_GLOBAL_CALL_SKIP:
            return
        self._emit_ref(file_id, text, text, func, "call")

    def _ref_new_expression(self, node: Node, file_id: int, file_bytes: bytes) -> None:
        ctor = node.child_by_field_name("constructor")
        if ctor is None:
            return
        text = self._call_callee_text(ctor, file_bytes)
        if not text:
            return
        root = text.split(".", 1)[0]
        if root in _JS_GLOBAL_CALL_SKIP:
            return
        self._emit_ref(file_id, text, text, ctor, "call")

    def _ref_member_expression_access(
        self, node: Node, file_id: int, _file_bytes: bytes
    ) -> None:
        prop = node.child_by_field_name("property")
        if prop is None or prop.text is None:
            return
        text = self._member_expression_text(node)
        if not text:
            return
        root = text.split(".", 1)[0]
        if root in _JS_GLOBAL_CALL_SKIP:
            return
        self._emit_ref(file_id, text, text, node, "access")

    def _ref_subscript_expression(
        self, node: Node, file_id: int, _file_bytes: bytes
    ) -> None:
        if node.text is None:
            return
        text = node.text.decode("utf-8", errors="replace")
        obj = node.child_by_field_name("object")
        if obj is None or obj.type != "identifier" or not obj.text:
            return
        root = obj.text.decode("utf-8")
        if root in _JS_GLOBAL_CALL_SKIP:
            return
        self._emit_ref(file_id, text, text, node, "access")

    def _type_annotation_inner(self, node: Node) -> Optional[Node]:
        t = node.child_by_field_name("type")
        if t is not None:
            return t
        for ch in node.children:
            if ch.is_named:
                return ch
        return None

    def _emit_ts_refs_from_type_tree(self, root: Node, file_id: int) -> None:
        for id_node in self._collect_type_identifiers(root):
            if id_node.text is None:
                continue
            name = id_node.text.decode("utf-8")
            if name in _TS_PREDEFINED_TYPES:
                continue
            self._emit_ref(file_id, name, name, id_node, "type_annotation")

    def _extract_ts_type_refs_from_node(
        self, node: Node, file_id: int, _file_bytes: bytes
    ) -> None:
        if node.type != "type_annotation":
            return
        t = self._type_annotation_inner(node)
        if t is None:
            return
        self._emit_ts_refs_from_type_tree(t, file_id)

    def _collect_type_identifiers(self, node: Node) -> List[Node]:
        out: List[Node] = []
        stack = [node]
        while stack:
            n = stack.pop()
            if n.type == "nested_type_identifier" and n.text:
                out.append(n)
                continue
            if n.type == "type_identifier" and n.text:
                out.append(n)
                continue
            for c in n.children:
                stack.append(c)
        return out
