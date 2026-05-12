"""Factory wiring for JavaScript / TypeScript / TSX parsers."""

from src.parsers.factory import FILE_EXTENSION_MAPPING, ParserFactory
from src.parsers.javascript_lang import JavascriptParser


def test_file_extension_mapping_includes_js_ts_tsx():
    assert FILE_EXTENSION_MAPPING[".js"] == "javascript"
    assert FILE_EXTENSION_MAPPING[".jsx"] == "javascript"
    assert FILE_EXTENSION_MAPPING[".mjs"] == "javascript"
    assert FILE_EXTENSION_MAPPING[".cjs"] == "javascript"
    assert FILE_EXTENSION_MAPPING[".ts"] == "typescript"
    assert FILE_EXTENSION_MAPPING[".mts"] == "typescript"
    assert FILE_EXTENSION_MAPPING[".cts"] == "typescript"
    assert FILE_EXTENSION_MAPPING[".tsx"] == "tsx"


def test_get_parser_returns_javascript_parser_for_each_dialect(
    tmp_db,
    assigner,
):
    for lang in ("javascript", "typescript", "tsx"):
        p = ParserFactory.get_parser(lang, assigner, tmp_db)
        assert isinstance(p, JavascriptParser)
        assert p.dialect == lang
