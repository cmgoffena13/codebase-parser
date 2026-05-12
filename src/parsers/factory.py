from typing import ClassVar

import tree_sitter_go as go_language
import tree_sitter_javascript as javascript_language
import tree_sitter_python as python_language
import tree_sitter_typescript as typescript_language
from tree_sitter import Language, Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.base import ParserBase
from src.parsers.go_lang import GoParser
from src.parsers.javascript_lang import JavascriptParser
from src.parsers.python_lang import PythonParser

FILE_EXTENSION_MAPPING = {
    ".go": "go",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
}


class ParserFactory:
    tree_sitter_parsers: ClassVar[dict[str, Parser]] = {
        "go": Parser(Language(go_language.language())),
        "python": Parser(Language(python_language.language())),
        "javascript": Parser(Language(javascript_language.language())),
        "typescript": Parser(Language(typescript_language.language_typescript())),
        "tsx": Parser(Language(typescript_language.language_tsx())),
    }
    parsers: ClassVar[dict[str, type[ParserBase]]] = {
        "go": GoParser,
        "python": PythonParser,
        "javascript": JavascriptParser,
        "typescript": JavascriptParser,
        "tsx": JavascriptParser,
    }
    active_tree_sitter_parsers: ClassVar[dict[str, Parser]] = {}

    @classmethod
    def get_parser(
        cls,
        language: str,
        assigner: GlobalIDAssigner,
        db: CodeDB,
    ):
        if language not in cls.tree_sitter_parsers:
            raise ValueError(
                f"Unsupported Language: {language}; Supported Languages: {', '.join(cls.tree_sitter_parsers.keys())}"
            )
        if language not in cls.parsers:
            raise ValueError(
                f"Unsupported Language: {language}; Supported Languages: {', '.join(cls.parsers.keys())}"
            )
        if language not in cls.active_tree_sitter_parsers:
            cls.active_tree_sitter_parsers[language] = cls.tree_sitter_parsers[language]
        impl = cls.parsers[language]
        ts_parser = cls.active_tree_sitter_parsers[language]
        if impl is JavascriptParser:
            return JavascriptParser(assigner, db, ts_parser, dialect=language)
        return impl(assigner, db, ts_parser)
