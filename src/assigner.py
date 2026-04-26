import threading

from src.db import CodeDB


class GlobalIDAssigner:
    def __init__(self, db: CodeDB):
        self._counters = {}
        self._lock = threading.Lock()
        self.db = db
        self.tables = {"directories", "files"}
        self._get_starter_ids()

    def _init_table(self, table: str, start_id: int):
        self._counters[table] = start_id

    def _get_starter_ids(self) -> None:
        for table in self.tables:
            row = self.db.exec_query(
                f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {table}"
            )
            self._init_table(table, row["max_id"] + 1)

    def reserve(self, table: str, count: int) -> tuple[int]:
        with self._lock:
            start_id = self._counters[table]
            self._counters[table] = start_id + count
            return tuple(range(start_id, start_id + count))
