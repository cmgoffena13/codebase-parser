"""Go symbol extraction; mirrors coverage goals of ``test_py_symbols``."""

from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
    index_symbols,
    symbol_key,
)


def test_basic_fixture_symbols_imports_and_references(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("basic.go")
    symbols, imports, references = go_parser.parse(1, file_bytes)

    assert len(symbols) == 9
    assert len(imports) == 2
    assert len(references) == 4
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)

    qn = {symbol_key(s) for s in symbols}
    assert "basic.Server" in qn
    assert "basic.Server.Start" in qn
    assert "basic.Server.Handle" in qn
    assert "basic.Handler" in qn
    assert "basic.NewServer" in qn
    assert "basic.main" in qn

    by_qn = index_symbols(symbols)
    assert by_qn["basic.Server.Name"]["kind"] == "variable"
    assert by_qn["basic.Server.Name"]["parent_id"] == by_qn["basic.Server"]["id"]
    assert by_qn["basic.Server.Start"]["kind"] == "method"
    assert by_qn["basic.Server.Start"]["parent_id"] == by_qn["basic.Server"]["id"]

    new_server = by_qn["basic.NewServer"]
    assert "\n" not in new_server["signature"]
    assert new_server["signature"].startswith("func NewServer(")


def test_interfaces_fixture_embedding_and_methods(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("interfaces.go")
    symbols, imports, references = go_parser.parse(2, file_bytes)

    assert len(imports) == 0
    assert len(references) == 0
    assert_symbols_invariants(symbols)
    by_qn = index_symbols(symbols)

    assert by_qn["iface.ReadWriter"]["kind"] == "interface"
    assert by_qn["iface.ReadWriter"]["base_classes"] is not None
    assert "Reader" in by_qn["iface.ReadWriter"]["base_classes"]
    assert "Writer" in by_qn["iface.ReadWriter"]["base_classes"]

    assert by_qn["iface.Reader.Read"]["kind"] == "method"
    assert by_qn["iface.File.Read"]["kind"] == "method"


def test_references_fixture_symbols(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("references.go")
    symbols, imports, references = go_parser.parse(3, file_bytes)

    assert len(symbols) == 7
    assert len(imports) == 1
    assert len(references) == 2
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)

    by_qn = index_symbols(symbols)
    assert "refs.ConfigPath" in by_qn
    assert by_qn["refs.ConfigPath"]["kind"] == "variable"
    assert "refs.MaxRetries" in by_qn
    assert by_qn["refs.MaxRetries"]["kind"] == "constant"
    assert "refs.LoadConfig" in by_qn
    assert "refs.App" in by_qn
    assert "refs.App.Run" in by_qn
