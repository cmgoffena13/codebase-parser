import pytest

from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


@pytest.mark.parametrize(
    ("fixture_name", "file_id", "expected_counts"),
    [
        ("basic.go", 1, (9, 2, 4)),
        ("references.go", 2, (7, 1, 2)),
        ("interfaces.go", 3, (8, 0, 0)),
        ("is_test_cases.go", 4, (3, 1, 0)),
        ("duplicate_reference_ids.go", 5, (2, 0, 2)),
    ],
)
def test_parse_twice_counts_unchanged(
    go_parser,
    go_fixture_bytes,
    fixture_name: str,
    file_id: int,
    expected_counts: tuple,
):
    file_bytes = go_fixture_bytes(fixture_name)
    first = go_parser.parse(file_id, file_bytes)
    second = go_parser.parse(file_id, file_bytes)

    assert tuple(len(x) for x in first) == expected_counts
    assert tuple(len(x) for x in second) == expected_counts

    for batch in (first, second):
        symbols, imports, references = batch
        assert_symbols_invariants(symbols)
        assert_imports_invariants(imports)
        if references:
            assert_symbol_references_invariants(references)
