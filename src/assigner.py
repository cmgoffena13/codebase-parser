import threading

from src.db import TABLE_BATCH_MAP, CodeDB


class GlobalIDAssigner:
    def __init__(self, db: CodeDB):
        self._counters = {}
        self._lock = threading.Lock()
        self.db = db
        self.tables = TABLE_BATCH_MAP
        self._get_starter_ids()

    def _init_table(self, table: str, start_id: int):
        self._counters[table] = start_id

    def _get_starter_ids(self) -> None:
        for table in self.tables:
            self._init_table(table, self.db.table_max_id(table) + 1)

    def reserve(self, table: str, count: int) -> tuple[int, ...]:
        with self._lock:
            start_id = self._counters[table]
            self._counters[table] = start_id + count
            return tuple(range(start_id, start_id + count))
