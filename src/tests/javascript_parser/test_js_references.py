"""JavaScript call / access references and global filtering."""

from src.tests.python_parser._assertions import (
    assert_reference_shape,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


def test_js_references_fixture(javascript_parser, javascript_fixture_bytes):
    file_bytes = javascript_fixture_bytes("test_js_references.js")
    symbols, _imports, references = javascript_parser.parse(3, file_bytes)

    assert_symbols_invariants(symbols)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=3)

    kinds = {(r["ref_kind"], r["ref_symbol_name"]) for r in references}
    assert ("call", "myFunc") in kinds
    assert ("call", "helper") in kinds
    assert ("access", "obj.prop") in kinds
    assert ("call", "obj.meth") in kinds
    assert ("access", "maybe?.prop") in kinds
    assert ("call", "maybe?.meth") in kinds
    assert ("access", "arr[0]") in kinds

    assert not any(r["ref_symbol_name"].startswith("console.") for r in references)
    assert not any(r["ref_symbol_name"].startswith("Math.") for r in references)
