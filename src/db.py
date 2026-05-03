import sqlite3
from pathlib import Path
from typing import Any, Optional

TABLE_BATCH_MAP = {
    "directories",
    "files",
    "symbols",
    "imports",
    "symbol_references",
}


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

    def delete_ids(self, table: str, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join(["?"] * len(ids))
        query = f"DELETE FROM {table} WHERE id IN ({placeholders})"
        self.exec_tran(query, tuple(ids))

    def exec_query(self, query: str) -> sqlite3.Row:
        row = self.connection.execute(query).fetchone()
        return row

    def get_watermark(self) -> tuple[int, int]:
        row = self.connection.execute(
            "SELECT last_full_parse, last_incremental FROM watermarks WHERE id = 1"
        ).fetchone()
        return row["last_full_parse"], row["last_incremental"]

    def set_watermark(
        self, last_full_parse: Optional[int], last_incremental: int
    ) -> None:
        if last_full_parse is not None:
            query = "UPDATE watermarks SET last_full_parse = ?, last_incremental = ? WHERE id = 1"
            params = (last_full_parse, last_incremental)
        else:
            query = "UPDATE watermarks SET last_incremental = ? WHERE id = 1"
            params = (last_incremental,)
        self.exec_tran(query, params)

    def get_directories_snapshot(self) -> dict[Path, dict[str, Any]]:
        cursor = self.connection.execute("SELECT id, path FROM directories")
        return {Path(row["path"]): {"id": row["id"], "seen": False} for row in cursor}

    def delete_directories(self, directories: dict[Path, dict[str, Any]]) -> None:
        dir_ids = [dir["id"] for dir in directories.values() if not dir["seen"]]
        self.delete_ids("directories", dir_ids)

    def get_files_snapshot(self) -> dict[Path, dict[str, Any]]:
        cursor = self.connection.execute(
            "SELECT id, directory_id, path, content_hash, line_count FROM files"
        )
        return {
            Path(row["path"]): {
                "id": row["id"],
                "directory_id": row["directory_id"],
                "seen": False,
                "content_hash": row["content_hash"],
                "line_count": row["line_count"],
            }
            for row in cursor
        }

    def delete_files(self, files: dict[Path, dict[str, Any]]) -> None:
        file_ids = [file["id"] for file in files.values() if not file["seen"]]
        self.delete_ids("files", file_ids)

    def apply_directory_deltas(self, deltas: dict[int, dict[str, int]]) -> None:
        if not deltas:
            return
        rows = [
            (id, dir["file_count"], dir["total_lines"]) for id, dir in deltas.items()
        ]
        with self.connection:
            self.connection.execute("DROP TABLE IF EXISTS _directory_delta;")
            self.connection.execute(
                """
                CREATE TEMP TABLE IF NOT EXISTS _directory_delta (
                    id INTEGER NOT NULL,
                    file_count INTEGER NOT NULL,
                    total_lines INTEGER NOT NULL
                )
                """
            )
            self.connection.executemany(
                "INSERT INTO _directory_delta (id, file_count, total_lines) VALUES (?,?,?)",
                rows,
            )
            self.connection.execute(
                """
                UPDATE directories AS d
                SET file_count = d.file_count + s.file_count,
                    total_lines = d.total_lines + s.total_lines
                FROM _directory_delta AS s
                WHERE d.id = s.id
                """
            )

    def get_symbols_snapshot(
        self, file_id: int
    ) -> dict[tuple[str, str], dict[str, Any]]:
        query = """
            SELECT
            id,
            full_name AS name,
            kind,
            line_start,
            line_end
            FROM symbols
            WHERE file_id = ?
            """
        cursor = self.connection.execute(query, (file_id,))
        return {
            (row["name"], row["kind"]): {
                "id": row["id"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "seen": False,
            }
            for row in cursor
        }

    def delete_symbols(
        self, symbols_snapshot: dict[tuple[str, str], dict[str, Any]]
    ) -> None:
        symbol_ids = [
            symbol["id"] for symbol in symbols_snapshot.values() if not symbol["seen"]
        ]
        if not symbol_ids:
            return
        with self.connection:
            ids_placeholder = ",".join(["?"] * len(symbol_ids))
            self.connection.execute(
                f"""DELETE FROM symbols WHERE id IN ({ids_placeholder})""",
                symbol_ids,
            )
            self.connection.execute(
                f"""DELETE FROM symbols_fts WHERE rowid IN ({ids_placeholder})""",
                symbol_ids,
            )

    def get_symbol_references_snapshot(
        self, file_id: int
    ) -> dict[tuple[str, str, int], dict[str, Any]]:
        query = """
        SELECT
        id,
        ref_symbol_full_name AS name,
        ref_kind,
        source_line,
        context
        FROM symbol_references
        WHERE source_file_id = ?
        """
        cursor = self.connection.execute(query, (file_id,))
        return {
            (row["name"], row["ref_kind"], row["source_line"]): {
                "id": row["id"],
                "source_line": row["source_line"],
                "context": row["context"],
                "seen": False,
            }
            for row in cursor
        }

    def delete_symbol_references(
        self, symbol_references_snapshot: dict[tuple[str, str, int], dict[str, Any]]
    ) -> None:
        symbol_reference_ids = [
            symbol_reference["id"]
            for symbol_reference in symbol_references_snapshot.values()
            if not symbol_reference["seen"]
        ]
        if not symbol_reference_ids:
            return
        with self.connection:
            ids_placeholder = ",".join(["?"] * len(symbol_reference_ids))
            self.connection.execute(
                f"""DELETE FROM symbol_references WHERE id IN ({ids_placeholder})""",
                symbol_reference_ids,
            )
            self.connection.execute(
                f"""DELETE FROM symbol_references_fts WHERE rowid IN ({ids_placeholder})""",
                symbol_reference_ids,
            )

    def get_imports_snapshot(
        self, file_id: int
    ) -> dict[tuple[str, str], dict[str, Any]]:
        query = """
        SELECT
        id,
        import_path,
        imported_symbol,
        line_number
        FROM imports
        WHERE file_id = ?
        """
        cursor = self.connection.execute(query, (file_id,))
        return {
            (row["import_path"], row["imported_symbol"]): {
                "id": row["id"],
                "line_number": row["line_number"],
                "seen": False,
            }
            for row in cursor
        }

    def delete_imports(
        self, imports_snapshot: dict[tuple[str, str], dict[str, Any]]
    ) -> None:
        import_ids = [i["id"] for i in imports_snapshot.values() if not i["seen"]]
        self.delete_ids("imports", import_ids)

    def bulk_insert(self, db_batches: dict[str, list[dict[str, Any]]]) -> None:
        directories = db_batches["directories"]
        files = db_batches["files"]
        symbols = db_batches["symbols"]
        symbol_references = db_batches["symbol_references"]
        imports = db_batches["imports"]
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO directories
                (id, parent_id, name, path, depth, file_count, total_lines)
                VALUES (:id, :parent_id, :name, :path, :depth, :file_count, :total_lines)
                """,
                directories,
            )

            self.connection.executemany(
                """
                INSERT OR REPLACE INTO files
                (id, directory_id, name, path, normalized_path, language, content_hash, line_count)
                VALUES (:id, :directory_id, :name, :path, :normalized_path, :language, :content_hash, :line_count)
                """,
                files,
            )

            self.connection.executemany(
                """
                INSERT OR REPLACE INTO symbols
                (id, file_id, parent_id, name, qualified_name, full_name, kind, line_start, line_end, line_count, signature, docstring, modifiers, base_classes, language, is_test)
                VALUES (:id, :file_id, :parent_id, :name, :qualified_name, :full_name, :kind, :line_start, :line_end, :line_count, :signature, :docstring, :modifiers, :base_classes, :language, :is_test)
                """,
                symbols,
            )

            fts_symbols = [
                (s["id"], s["full_name"], s["docstring"], s["signature"])
                for s in symbols
            ]
            self.connection.executemany(
                """
                INSERT OR REPLACE INTO symbols_fts (rowid, full_name, docstring, signature)
                VALUES (?, ?, ?, ?)
                """,
                fts_symbols,
            )

            self.connection.executemany(
                """
                INSERT INTO symbol_references_staging
                (id, ref_symbol_name, ref_symbol_qualified_name, ref_symbol_full_name, source_file_id, source_line, ref_kind, context)
                VALUES (:id, :ref_symbol_name, :ref_symbol_qualified_name, :ref_symbol_full_name, :source_file_id, :source_line, :ref_kind, :context)
                """,
                symbol_references,
            )

            self.connection.executemany(
                """
                INSERT OR REPLACE INTO imports
                (id, file_id, import_path, imported_symbol, alias, line_number, import_type, import_scope, signature)
                VALUES (:id, :file_id, :import_path, :imported_symbol, :alias, :line_number, :import_type, :import_scope, :signature)
                """,
                imports,
            )

    def resolve_symbol_references(self) -> None:
        with self.connection:
            self.connection.execute("""
            INSERT INTO symbol_references
            (id, ref_symbol_id, ref_symbol_file_id, ref_symbol_name, ref_symbol_qualified_name, ref_symbol_full_name, source_file_id, source_line, ref_kind, context)
            SELECT
            s.id,
            sy.id AS ref_symbol_id,
            sy.file_id AS ref_symbol_file_id,
            s.ref_symbol_name,
            s.ref_symbol_qualified_name,
            s.ref_symbol_full_name,
            s.source_file_id,
            s.source_line,
            s.ref_kind,
            s.context
            FROM symbol_references_staging AS s
            INNER JOIN symbols AS sy
                ON s.ref_symbol_full_name = sy.full_name
            WHERE NOT EXISTS (SELECT 1 FROM symbol_references AS sr WHERE sr.id = s.id);
            """)
            self.connection.execute("DELETE FROM symbol_references_staging;")

    def resolve_imports(self, now: int, last_incremental: int) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE imports
                SET imported_file_id = f.id,
                    watermark = ?
                FROM files AS f
                WHERE f.normalized_path = imports.import_path
                    AND imports.watermark BETWEEN ? AND ?
                """,
                (last_incremental, now, last_incremental),
            )

    def close(self):
        if not self.connection_closed:
            self.connection.close()
            self.connection_closed = True

    def __del__(self):
        if not getattr(self, "connection_closed", True):
            conn = getattr(self, "connection", None)
            if conn is not None:
                conn.close()
            self.connection_closed = True
