from src.tests.python_parser._assertions import assert_symbol_references_invariants


def test_type_annotations_two_distinct_types_same_signature_line(
    go_parser, go_fixture_bytes
):
    file_bytes = go_fixture_bytes("type_annotations_more.go")
    symbols, imports, references = go_parser.parse(13, file_bytes)

    assert len(symbols) == 3
    assert len(imports) == 0
    assert len(references) == 2
    assert_symbol_references_invariants(references)

    annos = [r for r in references if r["ref_kind"] == "type_annotation"]
    assert len(annos) == 2
    qns = {r["ref_symbol_qualified_name"] for r in annos}
    assert qns == {"ta.Red", "ta.Blue"}
    assert all(r["source_line"] == annos[0]["source_line"] for r in annos)

    assert not any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "int"
        for r in references
    )
