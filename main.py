from pathlib import Path

from parse.db import CodeDB
from parse.parser import CodeParser

PROJECT_ROOT = Path(__file__).resolve().parent
TEST_ROOT = Path("/Users/cortlandgoffena/Documents/repos/coder")


def main():
    db = CodeDB(PROJECT_ROOT)
    parser = CodeParser(db, TEST_ROOT)
    parser.parse()


if __name__ == "__main__":
    main()
