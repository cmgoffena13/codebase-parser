import sys
from pathlib import Path
from typing import Callable

import pytest

# Ensure repository root is importable (so `import src.*` works)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.assigner import GlobalIDAssigner  # noqa: E402
from src.db import CodeDB  # noqa: E402
from src.parsers.factory import ParserFactory  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path: Path) -> CodeDB:
    return CodeDB(tmp_path)


@pytest.fixture
def assigner(tmp_db: CodeDB) -> GlobalIDAssigner:
    return GlobalIDAssigner(tmp_db)


@pytest.fixture
def python_parser(tmp_db: CodeDB, assigner: GlobalIDAssigner):
    return ParserFactory.get_parser("python", assigner, tmp_db)


@pytest.fixture
def python_fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "files_to_parse" / "python"


@pytest.fixture
def fixture_bytes(python_fixtures_dir: Path) -> Callable[[str], bytes]:
    def _read(name: str) -> bytes:
        return (python_fixtures_dir / name).read_bytes()

    return _read
