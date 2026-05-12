from src.db import CodeDB


def test_resolve_symbol_references_drops_unresolvable_type_annotations(tmp_db: CodeDB):
    with tmp_db.connection:
        tmp_db.connection.execute(
            """
            INSERT INTO files (id, directory_id, name, path, normalized_path, language, content_hash, line_count)
            VALUES (1, NULL, 'main.go', 'main.go', 'main', 'go', 'x', 1)
            """
        )

        tmp_db.connection.execute(
            """
            INSERT INTO symbol_references_staging
            (id, ref_symbol_name, ref_symbol_qualified_name, source_file_id, source_line, ref_kind, context)
            VALUES (1, 'int', 'int', 1, 1, 'type_annotation', 'int')
            """
        )

    tmp_db.resolve_symbol_references()

    row = tmp_db.connection.execute(
        """
        SELECT COUNT(*) AS c
        FROM symbol_references
        WHERE ref_symbol_qualified_name = 'int' AND ref_kind = 'type_annotation'
        """
    ).fetchone()
    assert row["c"] == 0
