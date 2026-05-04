from collections import defaultdict

from src.db import CodeDB

_MAX_REFERENCE_CONTEXT = 150
_REFERENCE_FETCH_LIMIT = 50

_SYMBOL_ROW_SQL = """
SELECT s.line_start, s.line_end, s.full_name, f.path AS file_path, s.kind,
       f.language AS file_language
FROM symbols AS s
JOIN files AS f ON f.id = s.file_id
WHERE s.full_name = ?
"""

_REFERENCES_SQL = """
SELECT f.path AS source_path, sr.source_line, sr.context, sr.ref_kind
FROM symbol_references AS sr
JOIN files AS f ON f.id = sr.source_file_id
WHERE sr.ref_symbol_full_name = ?
ORDER BY sr.ref_kind, f.path, sr.source_line
LIMIT ?
"""

_REF_KIND_SECTIONS: tuple[tuple[str, str], ...] = (
    ("call", "## Calls"),
    ("access", "## Access"),
    ("type_annotation", "## Type Annotations"),
)


def _lines_range_header(line_start: int, line_end: int) -> str:
    """Human range for the header line (e.g. ``145–148`` or ``145``)."""
    if line_start == line_end:
        return str(line_start)
    return f"{line_start}–{line_end}"


def _truncate_context(text: str, max_len: int = _MAX_REFERENCE_CONTEXT) -> str:
    t = text.replace("\n", " ").strip()
    if len(t) > max_len:
        return t[: max_len - 3] + "..."
    return t


def get_symbol_context(db: CodeDB, full_name: str) -> str:
    """
    Return symbol metadata, source for the indexed span, and reference subsections
    grouped by ``ref_kind`` (only kinds with at least one row are shown).
    """
    key = full_name.strip()
    if not key:
        return "No symbol name given; pass a non-empty full_name."

    row = db.connection.execute(_SYMBOL_ROW_SQL, (key,)).fetchone()
    if row is None:
        return f"No symbol with full_name {key!r} in the index."

    path = row["file_path"]
    line_start = int(row["line_start"])
    line_end = int(row["line_end"])
    lang = row["file_language"] or "—"

    abs_path = db.root / path
    body_lines: list[str] = []
    try:
        raw_lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line_start < 1:
            body_lines.append("    (invalid line_start in index)")
        else:
            chunk = raw_lines[line_start - 1 : line_end]
            if not chunk:
                body_lines.append("    (no lines in range)")
            else:
                for ln in chunk:
                    body_lines.append(f"    {ln}")
    except OSError as e:
        body_lines.append(f"    (could not read source file: {e})")

    ref_rows = db.connection.execute(
        _REFERENCES_SQL, (key, _REFERENCE_FETCH_LIMIT)
    ).fetchall()

    lines: list[str] = [
        f"Symbol: {key}",
        f"Kind: {row['kind']}",
        f"File: {path}",
        f"Language: {lang}",
        f"Lines: {_lines_range_header(line_start, line_end)}",
        "",
        "## Definition",
        "",
    ]
    lines.extend(body_lines)

    by_kind: defaultdict[str, list] = defaultdict(list)
    for r in ref_rows:
        by_kind[r["ref_kind"]].append(r)

    covered = {k for k, _ in _REF_KIND_SECTIONS}
    for kind, heading in _REF_KIND_SECTIONS:
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines.append("")
        lines.append(f"{heading} ({len(items)})")
        for r in items:
            ctx = _truncate_context(r["context"] or "")
            lines.append(f"  • {r['source_path']}:{r['source_line']} - {ctx}")

    for kind in sorted(by_kind.keys()):
        if kind in covered:
            continue
        items = by_kind[kind]
        if not items:
            continue
        title = kind.replace("_", " ").title()
        lines.append("")
        lines.append(f"## {title} ({len(items)})")
        for r in items:
            ctx = _truncate_context(r["context"] or "")
            lines.append(f"  • {r['source_path']}:{r['source_line']} - {ctx}")

    return "\n".join(lines) + "\n"
