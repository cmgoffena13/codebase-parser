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


@pytest.fixture(autouse=True)
def _isolate_codebase_parser_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep index DBs under this test's tmp dir (see ``utils.get_codebase_parser_config_dir``)."""
    monkeypatch.setenv(
        "CODEBASE_PARSER_CONFIG_DIR",
        str(tmp_path / "codebase-parser-config"),
    )


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


@pytest.fixture
def go_parser(tmp_db: CodeDB, assigner: GlobalIDAssigner):
    return ParserFactory.get_parser("go", assigner, tmp_db)


@pytest.fixture
def go_fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "files_to_parse" / "golang"


@pytest.fixture
def go_fixture_bytes(go_fixtures_dir: Path) -> Callable[[str], bytes]:
    def _read(name: str) -> bytes:
        return (go_fixtures_dir / name).read_bytes()

    return _read
