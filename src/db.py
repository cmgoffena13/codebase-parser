import sqlite3
from pathlib import Path
from typing import Optional


class CodeDB:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.db_file = self.root / "code.db"
        self.connection = sqlite3.connect(str(self.db_file), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection_closed = False
        self._apply_schema()

    def _apply_schema(self):
        schema_path = Path(__file__).resolve().parent / "schema.sql"
        with open(schema_path, "r") as f:
            self.connection.executescript(f.read())

    def exec_tran(self, query: str, params: tuple) -> None:
        try:
            self.connection.execute(query, params)
            self.connection.commit()
        except sqlite3.Error as e:
            self.connection.rollback()
            raise e

    def exec_query(self, query: str) -> sqlite3.Row:
        row = self.connection.execute(query).fetchone()
        return row

    def get_watermark(self) -> tuple[float, float]:
        row = self.connection.execute(
            "SELECT last_full_parse, last_incremental FROM watermarks WHERE id = 1"
        ).fetchone()
        return row["last_full_parse"], row["last_incremental"]

    def set_watermark(
        self, last_full_parse: Optional[float], last_incremental: float
    ) -> None:
        if last_full_parse is not None:
            query = "UPDATE watermarks SET last_full_parse = ?, last_incremental = ? WHERE id = 1"
            params = (last_full_parse, last_incremental)
        else:
            query = "UPDATE watermarks SET last_incremental = ? WHERE id = 1"
            params = (last_incremental,)
        self.exec_tran(query, params)

    def get_directories_snapshot(self) -> dict[Path, dict]:
        cursor = self.connection.execute("SELECT id, path FROM directories")
        return {Path(row["path"]): {"id": row["id"], "seen": False} for row in cursor}

    def delete_directories(self, directories: dict[str, dict]) -> None:
        dir_ids = [dir["id"] for dir in directories.values() if not dir["seen"]]
        if not dir_ids:
            return
        query = """
            DELETE FROM files WHERE directory_id IN (?)
            DELETE FROM directories WHERE id IN (?)
        """
        self.exec_tran(query, (dir_ids, dir_ids))

    def get_files_snapshot(self) -> dict[Path, dict]:
        cursor = self.connection.execute(
            "SELECT id, path, content_hash, line_count FROM files"
        )
        return {
            Path(row["path"]): {
                "id": row["id"],
                "seen": False,
                "content_hash": row["content_hash"],
                "line_count": row["line_count"],
            }
            for row in cursor
        }

    def delete_files(self, files: dict[Path, dict]) -> None:
        file_ids = [file["id"] for file in files.values() if not file["seen"]]
        if not file_ids:
            return
        query = """
        DELETE FROM files WHERE id IN (?)
        """
        self.exec_tran(query, (file_ids, file_ids))

    def close(self):
        if not self.connection_closed:
            self.connection.close()
            self.connection_closed = True

    def __del__(self):
        if not getattr(self, "connection_closed", True):
            getattr(self, "connection", None).close()
            self.connection_closed = True
