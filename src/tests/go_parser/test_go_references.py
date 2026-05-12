"""Go symbol references staging; mirrors goals of ``test_py_references``."""

from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_reference_shape,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


def test_stdlib_calls_filtered_from_references(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("basic.go")
    _, _, references = go_parser.parse(1, file_bytes)

    assert_symbol_references_invariants(references)
    assert not any(
        r["ref_kind"] == "call" and r["ref_symbol_name"].startswith("fmt.")
        for r in references
    )
    assert not any(
        r["ref_kind"] == "call" and r["ref_symbol_name"].startswith("strings.")
        for r in references
    )
    assert any(
        r["ref_kind"] == "call" and r["ref_symbol_name"] == "NewServer"
        for r in references
    )


def test_references_fixture_loadconfig_and_field_access(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("references.go")
    symbols, imports, references = go_parser.parse(4, file_bytes)

    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=4)

    assert not any(
        r["ref_kind"] == "call" and "ReadFile" in r["ref_symbol_name"]
        for r in references
    )
    assert any(
        r["ref_kind"] == "call" and r["ref_symbol_name"] == "LoadConfig"
        for r in references
    )
    assert any(
        r["ref_kind"] == "access" and r["ref_symbol_name"] == "a.Config"
        for r in references
    )


def test_symbol_references_ids_are_unique_with_repeated_calls(
    go_parser, go_fixture_bytes
):
    file_bytes = go_fixture_bytes("duplicate_reference_ids.go")
    symbols, imports, references = go_parser.parse(5, file_bytes)

    assert len(symbols) == 2
    assert len(imports) == 0
    assert len(references) == 2
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=5)

    call_refs = [
        r
        for r in references
        if r["ref_kind"] == "call" and r["ref_symbol_name"] == "callee"
    ]
    assert len(call_refs) == 2
    assert {r["source_line"] for r in call_refs} == {6, 7}
