"""JavaScript import and re-export rows."""

from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


def test_js_imports_fixture(javascript_parser, javascript_fixture_bytes):
    file_bytes = javascript_fixture_bytes("test_js_imports.js")
    symbols, imports, references = javascript_parser.parse(2, file_bytes)

    assert len(symbols) == 0
    assert_symbols_invariants(symbols)
    assert_symbol_references_invariants(references)
    assert_imports_invariants(imports)
    assert len(imports) >= 6

    paths = {(i["import_path"], i["imported_symbol"], i["alias"]) for i in imports}
    assert ("./side_effect.js", "", None) in paths
    assert ("some-pkg", "", "defaultExport") in paths
    assert ("./relative/mod.js", "alpha", "renamed") in paths
    assert ("./relative/mod.js", "beta", None) in paths
    assert ("star-module", "", "Star") in paths
    assert ("./reexport.js", "beta", None) in paths
