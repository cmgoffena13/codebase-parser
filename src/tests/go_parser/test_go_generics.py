from __future__ import annotations

from src.tests.python_parser._assertions import assert_reference_shape


def test_go_generics_fixture(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("test_generics.go")
    _, _, references = go_parser.parse(1, file_bytes)

    def has_ref(ref_symbol_name: str, ref_kind: str, ref_qn: str) -> bool:
        return any(
            r["ref_symbol_name"] == ref_symbol_name
            and r["ref_kind"] == ref_kind
            and r["ref_symbol_qualified_name"] == ref_qn
            for r in references
        )

    assert has_ref("Container[string]", "type_annotation", "main.Container")
    assert has_ref("Container[T]", "type_annotation", "main.Container")
    assert has_ref("NewContainer[string]", "call", "main.NewContainer")


def test_go_generics_reference_shapes(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("test_generics.go")
    _, _, references = go_parser.parse(7, file_bytes)
    for r in references:
        if r["ref_kind"] in ("type_annotation", "call"):
            assert_reference_shape(r, expected_file_id=7)
