from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_symbols_invariants,
    index_symbols,
)


def test_is_test_detection_go_naming_convention(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("is_test_cases.go")
    symbols, imports, references = go_parser.parse(3, file_bytes)

    assert len(symbols) == 3
    assert len(imports) == 1
    assert len(references) == 0
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)

    by_qn = index_symbols(symbols)

    assert by_qn["istest.TestTop"]["is_test"] is True
    assert by_qn["istest.TestSuite"]["is_test"] is True
    assert by_qn["istest.TestSuite.TestMethod"]["is_test"] is True
