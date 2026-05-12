"""TSX: JSX parses under TSX grammar; symbols and call refs inside callbacks."""

from src.tests.python_parser._assertions import (
    assert_reference_shape,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
    symbol_key,
)


def test_tsx_component_fixture(tsx_parser, javascript_fixture_bytes):
    file_bytes = javascript_fixture_bytes("test_tsx_component.tsx")
    symbols, _imports, references = tsx_parser.parse(5, file_bytes)

    assert_symbols_invariants(symbols)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=5)

    qns = {symbol_key(s) for s in symbols}
    assert "handler" in qns
    assert "App" in qns
    assert any(
        r["ref_kind"] == "call" and r["ref_symbol_name"] == "handler"
        for r in references
    )
