import subprocess
from pathlib import Path

GIT_IGNORE_LIST = {
    ".git",
    ".venv",
    ".env",
    ".DS_Store",
    ".gitignore",
    "__pycache__",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".parse_index",
}

GIT_TIMEOUT = 5


def _convert_path_for_git_command(relative_path: Path) -> str:
    return relative_path.as_posix()


def _convert_git_log_line_to_path(line: str) -> Path:
    return Path(line.strip())


def run_git(cwd: Path, args: list[str], fallback: str = "") -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_TIMEOUT,
        )
        return result.stdout.strip() or fallback
    except Exception:
        return fallback


def _run_git_log_paths(root: Path, relative_paths: list[Path]) -> str:
    path_strings = [_convert_path_for_git_command(path) for path in relative_paths]
    return run_git(
        root,
        [
            "log",
            "--no-renames",
            "--format=%H\t%ai",
            "--name-only",
            "--",
            *path_strings,
        ],
        fallback="",
    )
