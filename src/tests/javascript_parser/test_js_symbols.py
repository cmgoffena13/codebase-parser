from src.tests.python_parser._assertions import (
    assert_symbol_references_invariants,
    assert_symbols_invariants,
    index_symbols,
    symbol_key,
)


def test_js_symbols_fixture(javascript_parser, javascript_fixture_bytes):
    """FieldDefinition: arrow/function value is ``method``; plain value is ``variable``."""
    file_bytes = javascript_fixture_bytes("test_js_symbols.js")
    symbols, _imports, references = javascript_parser.parse(1, file_bytes)

    assert_symbols_invariants(symbols)
    assert_symbol_references_invariants(references)
    assert len(_imports) == 0

    by_qn = index_symbols(symbols)
    qns = {symbol_key(s) for s in symbols}

    assert "TOP" in qns
    assert by_qn["TOP"]["kind"] == "constant"
    assert "counter" in qns
    assert by_qn["counter"]["kind"] == "variable"
    assert "legacy" in qns
    assert by_qn["legacy"]["kind"] == "variable"
    assert "outer" in qns
    assert by_qn["outer"]["kind"] == "function"
    assert "outer.inner" in qns
    assert by_qn["outer.inner"]["kind"] == "function"
    assert "gen" in qns
    assert by_qn["gen"]["kind"] == "function"
    assert "Base" in qns
    assert by_qn["Base"]["kind"] == "class"
    assert "Widget" in qns
    assert by_qn["Widget"]["kind"] == "class"
    assert by_qn["Widget"]["base_classes"] is not None
    assert "Base" in by_qn["Widget"]["base_classes"]
    assert "Widget.count" in qns
    assert by_qn["Widget.count"]["kind"] == "variable"
    assert "Widget.arrowRun" in qns
    assert by_qn["Widget.arrowRun"]["kind"] == "method"
    assert "Widget.method" in qns
    assert by_qn["Widget.method"]["kind"] == "method"
    assert "testWidgetRuns" in qns
    assert by_qn["testWidgetRuns"]["is_test"] is True
