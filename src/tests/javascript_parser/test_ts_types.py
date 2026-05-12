"""TypeScript interfaces, type aliases, and type_annotation references."""

from src.tests.python_parser._assertions import (
    assert_reference_shape,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
    index_symbols,
    symbol_key,
)


def test_ts_types_fixture(typescript_parser, javascript_fixture_bytes):
    file_bytes = javascript_fixture_bytes("test_ts_types.ts")
    symbols, _imports, references = typescript_parser.parse(4, file_bytes)

    assert_symbols_invariants(symbols)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=4)

    by_qn = index_symbols(symbols)
    qns = {symbol_key(s) for s in symbols}
    assert "I" in qns
    assert by_qn["I"]["kind"] == "interface"
    assert by_qn["I"]["base_classes"] is not None
    assert "A" in by_qn["I"]["base_classes"]
    assert "T" in qns
    assert by_qn["T"]["kind"] == "type"
    assert "typedFn" in qns
    assert by_qn["typedFn"]["kind"] == "function"

    kinds = {(r["ref_kind"], r["ref_symbol_name"]) for r in references}
    assert ("type_annotation", "B") in kinds
    assert ("type_annotation", "T") in kinds
    assert ("type_annotation", "I") in kinds
