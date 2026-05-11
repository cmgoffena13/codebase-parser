import hashlib
import os
import sys
import tomllib
from pathlib import Path


def get_version() -> str:
    """Get the version of the application."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if not isinstance(meipass, str):
            raise RuntimeError("frozen build missing sys._MEIPASS")
        pyproject_path = Path(meipass) / "pyproject.toml"
        if not pyproject_path.exists():
            exe = Path(getattr(sys, "executable", None) or sys.argv[0])
            pyproject_path = exe.parent / "pyproject.toml"
    else:
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"Could not find pyproject.toml at {pyproject_path}")

    with pyproject_path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def ensure_dir(path: Path) -> Path:
    """Create a directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_codebase_parser_config_dir(*parts: str) -> Path:
    """
    Base directory for codebase-parser local config/data.

    Uses ``$CODEBASE_PARSER_CONFIG_DIR`` when set (e.g. tests); otherwise
    ``~/.config/codebase-parser``.

    If ``parts`` are provided, returns ``<base>/<parts...>`` and creates it.
    """
    override = os.environ.get("CODEBASE_PARSER_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".config" / "codebase-parser"
    return ensure_dir(base.joinpath(*parts))


def db_path_for_index_root(index_root: Path) -> Path:
    """SQLite path for an indexed tree: ``<config>/databases/<sha256(root)>.db``."""
    key = str(index_root.resolve()).encode()
    digest = hashlib.sha256(key).hexdigest()
    return get_codebase_parser_config_dir("databases") / f"{digest}.db"
