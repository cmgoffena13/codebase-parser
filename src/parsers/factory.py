import tree_sitter_python as python_language
from tree_sitter import Language, Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.python_lang import PythonParser

FILE_EXTENSION_MAPPING = {
    ".py": "python",
}


class ParserFactory:
    tree_sitter_parsers = {
        "python": Parser(Language(python_language.language())),
    }
    parsers = {
        "python": PythonParser,
    }
    active_tree_sitter_parsers = {}

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
        return cls.parsers[language](
            assigner, db, cls.active_tree_sitter_parsers[language]
        )
