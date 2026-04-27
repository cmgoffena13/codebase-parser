import json
import os
import time
from pathlib import Path

import xxhash

from src.assigner import GlobalIDAssigner
from src.db import TABLE_BATCH_MAP, CodeDB
from src.git_utils import GIT_IGNORE_LIST  # NOTE: placeholder for now
from src.parsers.factory import FILE_EXTENSION_MAPPING, ParserFactory


class CodeProcessor:
    def __init__(self, db: CodeDB, root: Path):
        self.db = db
        self.assigner = GlobalIDAssigner(db)
        self.root = root
        self.last_full_parse, self.last_incremental = self.db.get_watermark()
        self.ignore_names: set[str] = GIT_IGNORE_LIST

        self.db_batch_size = 1000
        self.db_batches: dict[str, list[dict]] = dict()
        for table in TABLE_BATCH_MAP:
            self.db_batches[table] = []

        self.files_skipped: int = 0
        self.files_indexed: int = 0

        self.directories_snapshot = self.db.get_directories_snapshot()
        self.files_snapshot = self.db.get_files_snapshot()

    def _process_directories(
        self, directory_names: list[str], directory_path: Path
    ) -> None:
        for directory_name in directory_names:
            directory_relative_path = (directory_path / directory_name).relative_to(
                self.root
            )
            if directory_relative_path in self.directories_snapshot:
                self.directories_snapshot[directory_relative_path]["seen"] = True
                continue

            # NOTE: Assign a new ID for the directory.
            directory_id = self.assigner.reserve("directories", 1)[0]
            parent_row = self.directories_snapshot.get(directory_relative_path.parent)
            parent_id = None if parent_row is None else parent_row["id"]
            depth = len(directory_relative_path.parts) - 1
            self.db_batches["directories"].append(
                {
                    "id": directory_id,
                    "parent_id": parent_id,
                    "name": directory_name,
                    "path": str(directory_relative_path),
                    "depth": depth,
                    "file_count": 0,
                    "total_lines": 0,
                }
            )
            self.directories_snapshot[directory_relative_path] = {
                "id": directory_id,
                "seen": True,
            }
        self.db.delete_directories(self.directories_snapshot)

    def _process_file(self, file_name: str, directory_path: Path, full: bool) -> None:
        file_path = directory_path / file_name
        file_relative_path = file_path.relative_to(self.root)
        file_last_modified = file_path.lstat().st_mtime
        file_extension = file_relative_path.suffix
        dir_path = file_path.parent.relative_to(self.root)
        if str(dir_path) == ".":
            directory_id = None
        else:
            directory_id = self.directories_snapshot[dir_path]["id"]

        if file_relative_path in self.files_snapshot:
            self.files_snapshot[file_relative_path]["seen"] = True
            file_id = self.files_snapshot[file_relative_path]["id"]
        else:
            file_id = self.assigner.reserve("files", 1)[0]

        try:
            file_bytes = file_path.read_bytes()
            file_hash = xxhash.xxh128(file_bytes).hexdigest()
            line_count = file_bytes.count(b"\n") + 1 if file_bytes else 0
        except OSError:
            self.files_skipped += 1
            return

        self.db_batches["files"].append(
            {
                "id": file_id,
                "directory_id": directory_id,
                "name": file_name,
                "path": str(file_relative_path),
                "language": FILE_EXTENSION_MAPPING.get(file_extension, None),
                "content_hash": file_hash,
                "line_count": line_count,
            }
        )
        self.files_snapshot[file_relative_path] = {
            "id": file_id,
            "seen": True,
            "content_hash": file_hash,
            "line_count": line_count,
        }

        # NOTE: Two Gateway Checks for parsing: 1. Time 2. Content Hash.
        if full or (
            file_last_modified > self.last_incremental
            and file_hash != self.files_snapshot[file_relative_path]["content_hash"]
        ):
            if file_extension not in FILE_EXTENSION_MAPPING:
                self.files_skipped += 1
                return

            parser = ParserFactory.get_parser(
                FILE_EXTENSION_MAPPING[file_extension], self.assigner, self.db
            )
            symbols, imports, references = parser.parse(file_id, file_bytes)
            self.db_batches["symbols"].extend(symbols)
            self.db_batches["imports"].extend(imports)
            self.db_batches["symbol_references"].extend(references)
            self.files_indexed += 1
            self._insert_batch()
        else:
            return

    def _process_files(
        self, file_names: list[str], directory_path: Path, full: bool
    ) -> None:
        for file_name in file_names:
            self._process_file(file_name, directory_path, full)

        self.db.delete_files(self.files_snapshot)

    def _insert_batch(self, final: bool = False) -> None:
        if not final:
            if not any(
                len(batch) >= self.db_batch_size for batch in self.db_batches.values()
            ):
                return

        self.db.bulk_insert(self.db_batches)
        self.db_batches = dict()
        for table in TABLE_BATCH_MAP:
            self.db_batches[table] = []

    def _bulk_operations(self) -> None:
        pass

    def process(self, full: bool = False) -> None:
        start_time = time.time()
        for directory_path, directory_names, file_names in os.walk(self.root):
            directory_names[:] = [
                d for d in directory_names if d not in self.ignore_names
            ]
            file_names[:] = [f for f in file_names if f not in self.ignore_names]

            directory_path = Path(directory_path)
            self._process_directories(directory_names, directory_path)
            self._process_files(file_names, directory_path, full)

        self._insert_batch(final=True)
        self._bulk_operations()

        time_now = time.time()
        if full:
            self.last_full_parse = time_now
            self.last_incremental = time_now
        else:
            self.last_full_parse = None
            self.last_incremental = time_now

        print(json.dumps(self.db_batches.get("symbol_references", []), indent=4))
        self.db.set_watermark(self.last_full_parse, self.last_incremental)

        duration = time_now - start_time
        duration_ms = duration * 1000
        print(f"Indexed {self.files_indexed} files in {duration_ms:.2f} ms")
