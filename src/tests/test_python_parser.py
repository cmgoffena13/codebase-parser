def _index_by(items: list[dict], key: str) -> dict:
    return {item[key]: item for item in items}


def _symbol_key(symbol: dict) -> str:
    return symbol["coalesced_name"]


def _index_symbols(symbols: list[dict]) -> dict:
    return {_symbol_key(symbol): symbol for symbol in symbols}


def _assert_reference_shape(ref: dict, expected_file_id: int) -> None:
    assert ref["ref_kind"] in {"call", "access", "type_annotation"}
    assert isinstance(ref["ref_symbol_name"], str) and ref["ref_symbol_name"]
    assert ref["ref_symbol_qualified_name"] is None or isinstance(
        ref["ref_symbol_qualified_name"], str
    )
    assert ref["source_file_id"] == expected_file_id
    assert isinstance(ref["source_line"], int) and ref["source_line"] >= 1
    assert isinstance(ref["context"], str) and ref["context"]


def test_python_fixture_file_parses_symbols_imports_and_references(
    python_parser, fixture_bytes
):
    file_bytes = fixture_bytes("file.py")
    symbols, imports, references = python_parser.parse(1, file_bytes)

    assert symbols, "expected symbols from fixture file"

    qn = {_symbol_key(s) for s in symbols}

    # Class + method nesting
    assert "FakeClass" in qn
    assert "FakeClass.__init__" in qn
    assert "FakeClass.fake_method" in qn
    assert "FakeClass.fake_property" in qn

    # Function + nested function
    assert "fake_function" in qn
    assert "fake_function.nested_fake_function" in qn

    # Variable symbols exist
    assert "fake_path" in qn
    assert "alias_variable_in_another_file" in qn
    by_qn = _index_symbols(symbols)
    assert by_qn["fake_path"]["kind"] == "variable"
    assert by_qn["alias_variable_in_another_file"]["kind"] == "variable"

    # Signatures are normalized to one line
    fake_fn = _index_symbols(symbols)["fake_function"]
    assert "\n" not in fake_fn["signature"]
    multiline = _index_symbols(symbols)["multiline_signature"]
    assert "\n" not in multiline["signature"]
    assert multiline["signature"].startswith("def multiline_signature(")
    assert multiline["signature"].endswith(") -> int:")

    # Docstrings extracted
    fake_class = _index_symbols(symbols)["FakeClass"]
    assert fake_class["docstring"]
    assert "Fake Class Milti Line Docstring" in fake_class["docstring"]
    assert (
        "This is a fake class with a multi line docstring." in fake_class["docstring"]
    )
    assert fake_fn["docstring"] and "Fake Function Docstring" in fake_fn["docstring"]

    # Decorators/modifiers extracted (stored as string currently)
    fake_prop = _index_symbols(symbols)["FakeClass.fake_property"]
    assert fake_prop["modifiers"] is not None
    assert "property" in fake_prop["modifiers"]

    # Imports extracted (spot-check a few)
    assert any(
        i["import_path"] == "json" and i["imported_symbol"] == "" for i in imports
    )
    assert any(
        i["import_path"] == "pathlib" and i["imported_symbol"] == "Path"
        for i in imports
    )
    assert any(i["import_type"] == "relative" for i in imports)

    # References: validate shape + expected signals
    assert isinstance(references, list)
    assert references, "expected some symbol references"
    for r in references:
        _assert_reference_shape(r, expected_file_id=1)

    assert any(
        r["ref_kind"] == "call" and r["ref_symbol_name"] == "nested_fake_function"
        for r in references
    )
    assert any(
        r["ref_kind"] == "access" and r["ref_symbol_name"] == "self.fake_data"
        for r in references
    )
    # type annotations from multiline_signature args skip builtins like int
    assert not any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "int"
        for r in references
    )


def test_python_fixture_another_file_has_fakeclass_call_reference(
    python_parser, fixture_bytes
):
    file_bytes = fixture_bytes("another_file.py")
    symbols, imports, references = python_parser.parse(2, file_bytes)
    by_qn = _index_symbols(symbols)

    # Should contain a call reference to FakeClass()
    assert any(
        r["ref_kind"] == "call" and "FakeClass" in r["ref_symbol_name"]
        for r in references
    )

    # Base classes extracted
    assert "AnotherClass" in by_qn
    assert by_qn["AnotherClass"]["base_classes"] is not None
    assert "FakeClass" in by_qn["AnotherClass"]["base_classes"]


def test_symbol_references_access_and_type_annotation(python_parser, fixture_bytes):
    file_bytes = fixture_bytes("references_cases.py")
    symbols, _, references = python_parser.parse(4, file_bytes)
    by_qn = _index_symbols(symbols)

    assert "RefClass.value" in by_qn
    assert by_qn["RefClass.value"]["kind"] == "variable"

    assert any(
        r["ref_kind"] == "access" and r["ref_symbol_name"] == "self.value"
        for r in references
    )
    # type annotations should include non-builtins and skip builtins
    assert any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "Path"
        for r in references
    )
    assert not any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "int"
        for r in references
    )


def test_is_test_detection_pytest_and_unittest(python_parser, fixture_bytes):
    file_bytes = fixture_bytes("is_test_cases.py")
    symbols, _, _ = python_parser.parse(3, file_bytes)
    by_qn = _index_symbols(symbols)

    assert by_qn["test_top"]["is_test"] is True
    assert by_qn["TestPy"]["is_test"] is True
    assert by_qn["TestPy.test_m"]["is_test"] is True
    assert by_qn["UT"]["is_test"] is True
    assert by_qn["UT.test_u"]["is_test"] is True
