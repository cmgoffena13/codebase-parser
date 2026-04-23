class PythonParser:
    def __init__(self):
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as python_language

        self.parser = Parser(Language(python_language()))
        self.function_types = {"function_definition"}
        self.class_types = {"class_definition"}
        self.call_types = {"call"}
        self.import_types = {"import_from_statement", "import_statement"}

    def parse(self, content: bytes) -> None:
        tree = self.parser.parse(content)
        root_node = tree.root_node
        pass
