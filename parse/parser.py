import os
import time
from pathlib import Path

import xxhash

from parse.db import CodeDB
from parse.git_utils import GIT_IGNORE_LIST  # NOTE: placeholder for now

FILE_EXTENSION_MAPPING = {
    ".py": "python",
    ".rs": "rust",
}

TABLE_BATCH_MAP = {
    "directories",
    "files",
}


class CodeParser:
    def __init__(self, db: CodeDB, root: Path):
        self.db = db
        self.root = root
        self.last_full_parse, self.last_incremental = self.db.get_watermark()
        self.ignore_names: set[str] = GIT_IGNORE_LIST

        self.db_batch_size = 1000
        self.db_batches: dict[list[dict]] = dict()
        for table in TABLE_BATCH_MAP:
            self.db_batches[table] = []

        self.seen_relative_file_paths: set[Path] = set()
        self.seen_relative_dir_paths: set[Path] = set()
        self.files_skipped: int = 0
        self.files_indexed: int = 0

    def _process_directory(
        self, directory_path: Path, directory_name: str, depth: int
    ) -> None:
        dir_path = directory_path / directory_name
        directory_relative_path = dir_path.relative_to(self.root)
        self.seen_relative_dir_paths.add(directory_relative_path)
        self.db_batches["directories"].append(
            {
                "name": directory_name,
                "path": str(directory_relative_path),
                "depth": depth,
            }
        )

    def _parse_file(self, file_path: Path) -> None:
        pass

    def _process_files(
        self, file_names: list[str], directory_path: Path, full: bool
    ) -> None:
        for file_name in file_names:
            file_path = directory_path / file_name
            file_relative_path = file_path.relative_to(self.root)
            self.seen_relative_file_paths.add(file_relative_path)
            file_last_modified = file_path.lstat().st_mtime

            # NOTE: First Gateway Check.
            if full or (file_last_modified > self.last_incremental):
                try:
                    file_bytes = file_path.read_bytes()
                except OSError:
                    self.files_skipped += 1
                    continue

                file_hash = xxhash.xxh128(file_bytes).hexdigest()

                # NOTE: Second Gateway Check.
                if self.db.file_is_stale(file_relative_path, file_hash):
                    file_extension = file_relative_path.suffix
                    dir_path = file_relative_path.parent
                    if file_extension not in FILE_EXTENSION_MAPPING:
                        self.files_skipped += 1
                        continue
                    self._parse_file(file_path)
                    self.files_indexed += 1

                    self.db_batches["files"].append(
                        {
                            "dir_path": str(dir_path),
                            "name": file_name,
                            "path": str(file_relative_path),
                            "language": FILE_EXTENSION_MAPPING[file_extension],
                            "file_hash": file_hash,
                            "line_count": 0,
                        }
                    )
                else:
                    continue
            else:
                continue

    def parse(self, full: bool = False) -> None:
        start_time = time.time()
        for directory_path, directory_names, file_names in os.walk(self.root):
            directory_names[:] = [
                d for d in directory_names if d not in self.ignore_names
            ]
            file_names[:] = [f for f in file_names if f not in self.ignore_names]

            directory_path = Path(directory_path)
            for depth, directory_name in enumerate(directory_names):
                self._process_directory(directory_path, directory_name, depth)

            self._process_files(file_names, directory_path, full)

        time_now = time.time()
        if full:
            self.last_full_parse = time_now
            self.last_incremental = time_now
        else:
            self.last_full_parse = None
            self.last_incremental = time_now

        self.db.set_watermark(self.last_full_parse, self.last_incremental)

        duration = time_now - start_time
        duration_ms = duration * 1000
        print(f"Indexed {self.files_indexed} files in {duration_ms:.2f} ms")
