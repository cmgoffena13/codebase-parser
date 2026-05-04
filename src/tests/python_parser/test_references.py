from src.tests.python_parser._assertions import (
    assert_imports_invariants,
    assert_reference_shape,
    assert_symbol_references_invariants,
    assert_symbols_invariants,
)


def test_import_after_path_use_same_suite_still_filters_path_call(
    python_parser, fixture_bytes
):
    """Import below Path(...) must still register before sibling refs (import-first walk)."""
    file_bytes = fixture_bytes("import_after_use_path.py")
    _, _, references = python_parser.parse(45, file_bytes)

    assert_symbol_references_invariants(references)
    assert not any(
        r["ref_kind"] == "call" and r["ref_symbol_name"].startswith("Path")
        for r in references
    )


def test_stdlib_import_and_literal_calls_filtered_from_references(
    python_parser, fixture_bytes
):
    """Path(...) and str.join skipped; project name like files kept."""
    file_bytes = fixture_bytes("external_refs_filter.py")
    symbols, imports, references = python_parser.parse(41, file_bytes)

    assert_symbol_references_invariants(references)
    assert not any(
        r["ref_kind"] == "call" and r["ref_symbol_name"].startswith("Path")
        for r in references
    )
    assert not any(
        r["ref_kind"] == "call" and "join" in r["ref_symbol_name"] for r in references
    )
    assert any(
        r["ref_kind"] == "call" and r["ref_symbol_name"] == "files.values"
        for r in references
    )


def test_self_attr_call_resolves_via_init_param_annotation(
    python_parser, fixture_bytes
):
    """self.dep.* resolves via __init__ param type (DependencyType)."""
    file_bytes = fixture_bytes("ctor_param_self_call.py")
    symbols, imports, references = python_parser.parse(40, file_bytes)

    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)

    call = next(
        r
        for r in references
        if r["ref_kind"] == "call" and r["ref_symbol_name"] == "self.dep.invoke"
    )
    assert call["ref_symbol_qualified_name"] == "DependencyType.invoke"

    access = next(
        r
        for r in references
        if r["ref_kind"] == "access" and r["ref_symbol_name"] == "self.dep"
    )
    assert access["ref_symbol_qualified_name"] == "DependencyType"


def test_symbol_references_access_and_type_annotation(python_parser, fixture_bytes):
    file_bytes = fixture_bytes("references_cases.py")
    symbols, imports, references = python_parser.parse(4, file_bytes)

    assert len(symbols) == 6
    assert len(imports) == 1
    assert len(references) == 4
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=4)

    assert any(
        r["ref_kind"] == "access" and r["ref_symbol_name"] == "self.value"
        for r in references
    )
    assert not any(
        r["ref_kind"] == "type_annotation" and r["ref_symbol_name"] == "int"
        for r in references
    )
    assert not any("Path" in r["ref_symbol_name"] for r in references)


def test_symbol_references_ids_are_unique_with_repeated_calls(
    python_parser, fixture_bytes
):
    file_bytes = fixture_bytes("duplicate_reference_ids.py")
    symbols, imports, references = python_parser.parse(5, file_bytes)

    assert len(symbols) == 2
    assert len(imports) == 0
    assert len(references) == 2
    assert_symbols_invariants(symbols)
    assert_imports_invariants(imports)
    assert_symbol_references_invariants(references)
    for r in references:
        assert_reference_shape(r, expected_file_id=5)

    call_refs = [
        r
        for r in references
        if r["ref_kind"] == "call" and r["ref_symbol_name"] == "callee"
    ]
    assert len(call_refs) == 2
    assert {r["source_line"] for r in call_refs} == {6, 7}
