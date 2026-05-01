"""Integration tests: CodeProcessor + DB idempotency across repeated runs."""

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db import CodeDB  # noqa: E402
from src.processor import CodeProcessor  # noqa: E402

# Nested package + class + method + call so an unchanged outer def must still
# push the parser stack (regression for snapshot/re-parse churn).
NESTED_PKG_MOD = '''"""nested pkg module."""
class Outer:
    def method(self):
        x = 1
        self.method()
'''


def _db_counts(tmp: Path) -> dict:
    db_file = tmp / "code.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        dirs = conn.execute(
            "SELECT id, file_count, total_lines FROM directories ORDER BY id"
        ).fetchall()
        return {
            "directories": [(r["id"], r["file_count"], r["total_lines"]) for r in dirs],
            "files": conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"],
            "symbols": conn.execute("SELECT COUNT(*) AS c FROM symbols").fetchone()[
                "c"
            ],
            "symbol_references": conn.execute(
                "SELECT COUNT(*) AS c FROM symbol_references"
            ).fetchone()["c"],
            "imports": conn.execute("SELECT COUNT(*) AS c FROM imports").fetchone()[
                "c"
            ],
        }
    finally:
        conn.close()


def _write_nested_fixture(tmp: Path) -> None:
    pkg = tmp / "pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "mod.py").write_text(NESTED_PKG_MOD, encoding="utf-8")


def test_two_full_indexes_identical_counts(tmp_path: Path) -> None:
    _write_nested_fixture(tmp_path)

    db1 = CodeDB(tmp_path)
    CodeProcessor(db1, tmp_path).process(full=True)
    first = _db_counts(tmp_path)

    db2 = CodeDB(tmp_path)
    CodeProcessor(db2, tmp_path).process(full=True)
    second = _db_counts(tmp_path)

    assert first == second
    assert first["files"] >= 1
    assert first["symbols"] >= 1
    assert first["symbol_references"] >= 1


def test_full_then_incremental_identical_counts(tmp_path: Path) -> None:
    _write_nested_fixture(tmp_path)

    db1 = CodeDB(tmp_path)
    CodeProcessor(db1, tmp_path).process(full=True)
    after_full = _db_counts(tmp_path)

    db2 = CodeDB(tmp_path)
    CodeProcessor(db2, tmp_path).process(full=False)
    after_inc = _db_counts(tmp_path)

    assert after_full == after_inc
