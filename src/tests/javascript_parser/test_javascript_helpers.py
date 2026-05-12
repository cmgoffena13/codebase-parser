"""Branch coverage for small javascript_lang helpers."""

import tree_sitter_javascript as js
from tree_sitter import Language, Parser

from src.parsers import javascript_lang as jl


def test_normalize_signature_bytes_tail_rstrip():
    raw = b"  foo()  \n"
    assert jl._normalize_signature_bytes(raw, 0, len(raw), tail_rstrip=True) == "foo()"


def test_string_literal_path_and_import_export_module():
    p = Parser(Language(js.language()))
    tree = p.parse(b'import x from "pkg/mod";')
    imp = tree.root_node.children[0]
    src = imp.child_by_field_name("source")
    assert src is not None
    assert jl._string_literal_path(src, b'import x from "pkg/mod";') == "pkg/mod"
    assert jl._import_export_module_path(imp, b'import x from "pkg/mod";') == "pkg/mod"


def test_is_functionish_value():
    p = Parser(Language(js.language()))
    root = p.parse(b"const a = () => 1;").root_node
    decl = root.children[0]
    assert decl.type == "lexical_declaration"
    vd = next(c for c in decl.children if c.type == "variable_declarator")
    val = vd.child_by_field_name("value")
    assert val is not None
    assert jl._is_functionish_value(val) is True
    root2 = p.parse(b"const n = 3;").root_node
    decl2 = root2.children[0]
    vd2 = next(c for c in decl2.children if c.type == "variable_declarator")
    num = vd2.child_by_field_name("value")
    assert num is not None
    assert jl._is_functionish_value(num) is False
