import sqlite3
from collections import OrderedDict

from src.db import CodeDB
from src.mcp.clip import clipped_doc_lines

_SYMBOL_SEARCH_SQL = """
SELECT
    s.qualified_name,
    s.kind,
    s.signature,
    s.docstring,
    f.path AS path,
    s.line_start,
    s.line_end,
    bm25(symbols_fts) AS rank
FROM symbols_fts
INNER JOIN symbols AS s ON s.id = symbols_fts.rowid
INNER JOIN files AS f ON f.id = s.file_id
WHERE symbols_fts MATCH ?
ORDER BY rank
LIMIT ?
"""

_MAX_SIGNATURE_LINES = 200
_MAX_DOCSTRING_CHARS = 100


def _line_span(line_start: int, line_end: int) -> str:
    if line_start == line_end:
        return f"L{line_start}"
    return f"L{line_start}–{line_end}"


def build_fts_query(user_input: str) -> str:
    """Turn free text into an OR-based prefix query for FTS5 (e.g. ``auth login`` → ``auth* OR login*``)."""
    terms = user_input.strip().split()
    if not terms:
        return ""
    return " OR ".join(f"{term}*" for term in terms)


def _sig_doc_lines(detail_prefix: str, sig: str, doc: str) -> list[str]:
    lines: list[str] = []
    sig = sig.strip()
    if sig:
        parts = sig.splitlines()
        total = len(parts)
        if total > _MAX_SIGNATURE_LINES:
            parts = parts[:_MAX_SIGNATURE_LINES]
        lines.append(f"{detail_prefix}Sig: {parts[0]}")
        for extra in parts[1:]:
            lines.append(f"{detail_prefix}    {extra}")
        if total > _MAX_SIGNATURE_LINES:
            lines.append(
                f"{detail_prefix}    ...[truncated {total - _MAX_SIGNATURE_LINES} lines]"
            )
    if doc.strip():
        lines.extend(clipped_doc_lines(detail_prefix, doc, _MAX_DOCSTRING_CHARS))
    return lines


def search_symbols(db: CodeDB, query: str, limit: int = 20) -> str:
    """
    Search indexed symbols via ``symbols_fts``. Returns a tree grouped by file so a
    caller can pick a ``qualified_name`` for follow-up (e.g. ``get_context``).
    """
    stripped = query.strip()
    if not stripped:
        return "No search text given; pass a non-empty query."

    fts_query = build_fts_query(stripped)
    if not fts_query:
        return "No search text given; pass a non-empty query."

    try:
        rows = db.connection.execute(
            _SYMBOL_SEARCH_SQL,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        return f"Search failed for {query!r} ({fts_query!r}): {e}"

    by_path: OrderedDict[str, list] = OrderedDict()
    for row in rows:
        p = row["path"] or ""
        if p not in by_path:
            by_path[p] = []
        by_path[p].append(row)

    lines: list[str] = [
        "Legend: L = Line, Sig = Signature, Doc = Docstring\n",
        f'Results for "{stripped}" ({len(rows)} matches)',
        "",
    ]

    for path_index, (path, sym_rows) in enumerate(by_path.items()):
        if path_index > 0:
            lines.append("")
        lines.append(path)
        max_loc = max(len(_line_span(r["line_start"], r["line_end"])) for r in sym_rows)
        max_kind = max(len(r["kind"] or "") for r in sym_rows)
        last_i = len(sym_rows) - 1
        for i, row in enumerate(sym_rows):
            is_last = i == last_i
            connector = "└─ " if is_last else "├─ "
            detail_prefix = "    " if is_last else "│   "

            qualified_name = row["qualified_name"] or ""
            kind = row["kind"] or ""
            loc = _line_span(row["line_start"], row["line_end"]).ljust(max_loc)
            kind_padded = kind.ljust(max_kind)
            sig = row["signature"] or ""
            doc_raw = row["docstring"] or ""

            lines.append(f"{connector}{loc}  {kind_padded}  {qualified_name}")
            lines.extend(_sig_doc_lines(detail_prefix, sig, doc_raw))

    return "\n".join(lines).rstrip() + "\n"
