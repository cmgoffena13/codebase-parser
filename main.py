from pathlib import Path

from parse.db import CodeDB
from parse.processor import CodeProcessor

PROJECT_ROOT = Path(__file__).resolve().parent
TEST_ROOT = Path("/Users/cortlandgoffena/Documents/repos/coder")


def main():
    db = CodeDB(PROJECT_ROOT)
    parser = CodeProcessor(db, TEST_ROOT)
    parser.parse()


if __name__ == "__main__":
    main()
