"""TypeScript ``import type`` is recorded like a normal import."""

from src.tests.python_parser._assertions import assert_imports_invariants


def test_ts_import_type_recorded(typescript_parser, javascript_fixture_bytes):
    file_bytes = javascript_fixture_bytes("test_ts_import_type.ts")
    symbols, imports, references = typescript_parser.parse(9, file_bytes)

    assert len(symbols) == 1
    assert len(references) == 1
    assert references[0]["ref_kind"] == "type_annotation"
    assert_imports_invariants(imports)
    assert any(
        i["import_path"] == "zmod"
        and i["imported_symbol"] == "Z"
        and i["alias"] is None
        for i in imports
    )
