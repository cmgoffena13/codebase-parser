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
        with open("parse/schema.sql", "r") as f:
            self.connection.executescript(f.read())

    def exec_tran(self, query: str, params: tuple) -> None:
        try:
            self.connection.execute(query, params)
            self.connection.commit()
        except sqlite3.Error as e:
            self.connection.rollback()
            raise e

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

    def file_is_stale(self, relative_path: Path, file_hash: str) -> bool:
        row = self.connection.execute(
            "SELECT file_hash FROM files WHERE path = ?",
            (str(relative_path),),
        ).fetchone()
        if row is None:
            return True
        return row["file_hash"] != file_hash

    def insert_files(self, files: list) -> None:
        pass

    def insert_directories(self, directories: list) -> None:
        pass

    def close(self):
        if not self.connection_closed:
            self.connection.close()
            self.connection_closed = True

    def __del__(self):
        if not getattr(self, "connection_closed", True):
            getattr(self, "connection", None).close()
            self.connection_closed = True
