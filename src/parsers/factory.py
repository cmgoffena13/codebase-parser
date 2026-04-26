from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.python_lang import PythonParser

FILE_EXTENSION_MAPPING = {
    ".py": "python",
    ".rs": "rust",
}


class ParserFactory:
    parsers = {
        "python": PythonParser,
    }
    active_parsers = {}

    @classmethod
    def get_parser(
        cls,
        language: str,
        assigner: GlobalIDAssigner,
        db: CodeDB,
    ):
        if language not in cls.parsers:
            raise ValueError(
                f"Unsupported Language: {language}; Supported Languages: {', '.join(cls.parsers.keys())}"
            )
        if language not in cls.active_parsers:
            cls.active_parsers[language] = cls.parsers[language](assigner, db)
        return cls.active_parsers[language]
