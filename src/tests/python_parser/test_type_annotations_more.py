from src.tests.python_parser._assertions import assert_symbol_references_invariants


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
