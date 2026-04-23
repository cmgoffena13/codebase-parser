from parse.parsers.python_lang import PythonParser

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
    def get_parser(cls, language: str):
        if language not in cls.parsers:
            raise ValueError(
                f"Unsupported Language: {language}; Supported Languages: {', '.join(cls.parsers.keys())}"
            )
        if language not in cls.active_parsers:
            cls.active_parsers[language] = cls.parsers[language]()
        return cls.active_parsers[language]
