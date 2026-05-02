from pathlib import Path

from src.db import CodeDB
from src.mcp.structure import directory_tree
from src.processor import CodeProcessor

PROJECT_ROOT = Path(__file__).resolve().parent
TEST_ROOT = Path("/Users/cortlandgoffena/Documents/repos/coder")


def main():
    db = CodeDB(PROJECT_ROOT)
    processor = CodeProcessor(db, TEST_ROOT)
    processor.process(full=True)
    print(directory_tree(db))


if __name__ == "__main__":
    main()
