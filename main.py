from pathlib import Path

from src.db import CodeDB
from src.mcp.directory_tree import get_directory_tree
from src.mcp.file_overview import get_file_overview
from src.mcp.search_symbols import search_symbols
from src.mcp.symbol_context import get_symbol_context
from src.processor import CodeProcessor

PROJECT_ROOT = Path(__file__).resolve().parent
TEST_ROOT = Path("/Users/cortlandgoffena/Documents/repos/coder")


def main():
    db = CodeDB(PROJECT_ROOT)
    processor = CodeProcessor(db, PROJECT_ROOT)
    processor.process(full=True)
    print(get_directory_tree(db))
    print("--------------------------------")
    print(get_file_overview(db, "src/mcp/directory_tree.py"))
    print("--------------------------------")
    print(search_symbols(db, "symbol"))
    print("--------------------------------")
    print(get_symbol_context(db, "CodeProcessor._process_file"))


if __name__ == "__main__":
    main()
