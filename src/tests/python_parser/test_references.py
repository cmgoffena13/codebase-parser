from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_reference_shape,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


def test_symbol_references_access_and_type_annotation(python_parser, fixture_bytes):
    file_bytes = fixture_bytes("references_cases.py")
    symbols, imports, references = python_parser.parse(4, file_bytes)

    assert len(symbols) == 6
    assert len(imports) == 1
    assert len(references) == 7
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=4)

    assert any(
        r["ref_kind"] == "access" and r["ref_symbol_name"] == "self.value"
        for r in references
    )
    assert any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "Path"
        for r in references
    )
    assert not any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "int"
        for r in references
    )


def test_symbol_references_ids_are_unique_with_repeated_calls(
    python_parser, fixture_bytes
):
    file_bytes = fixture_bytes("duplicate_reference_ids.py")
    symbols, imports, references = python_parser.parse(5, file_bytes)

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


def test_type_annotations_optional_generics_and_forward_refs(
    python_parser, fixture_bytes
):
    file_bytes = fixture_bytes("type_annotations_complex.py")
    symbols, imports, references = python_parser.parse(13, file_bytes)

    assert len(symbols) == 1
    assert len(imports) == 3
    assert len(references) == 3
    assert_symbol_references_invariants(references)

    # builtins should be skipped; Path should be present (including forward ref)
    assert not any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "list"
        for r in references
    )
    assert any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "Path"
        for r in references
    )
    # Current behavior: forward refs keep quotes (not normalized)
    assert any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == '"Path"'
        for r in references
    )
