"""Parse-twice stability (snapshot paths) for JS/TS fixtures."""

import pytest

from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


@pytest.mark.parametrize(
    ("fixture_name", "parser_fixture", "file_id", "expected_counts"),
    [
        ("test_js_symbols.js", "javascript_parser", 1, (12, 0, 1)),
        ("test_js_imports.js", "javascript_parser", 2, (0, 6, 0)),
        ("test_ts_types.ts", "typescript_parser", 4, (6, 0, 4)),
        ("test_tsx_component.tsx", "tsx_parser", 5, (2, 0, 1)),
    ],
)
def test_parse_twice_counts_unchanged(
    request,
    javascript_fixture_bytes,
    fixture_name: str,
    parser_fixture: str,
    file_id: int,
    expected_counts: tuple,
):
    parser = request.getfixturevalue(parser_fixture)
    file_bytes = javascript_fixture_bytes(fixture_name)
    first = parser.parse(file_id, file_bytes)
    second = parser.parse(file_id, file_bytes)

    assert tuple(len(x) for x in first) == expected_counts
    assert tuple(len(x) for x in second) == expected_counts

    for batch in (first, second):
        symbols, imports, references = batch
        assert_symbols_invariants(symbols)
        assert_imports_invariants(imports)
        if references:
            assert_symbol_references_invariants(references)
