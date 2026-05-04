from collections import defaultdict
from typing import Optional

from src.db import CodeDB
from src.mcp.clip import clipped_doc_lines

_SYMBOLS_SQL = """
SELECT id, parent_id, kind, full_name, name, line_start, line_end, signature, docstring
FROM symbols
WHERE file_id = ?
ORDER BY line_start, line_end, full_name
"""

_IMPORTS_SQL = """
SELECT line_number, signature
FROM imports
WHERE file_id = ?
ORDER BY line_number
"""

_MAX_SIGNATURE_LINES = 200
_MAX_DOCSTRING_CHARS = 100


def _line_span(line_start: int, line_end: int) -> str:
    if line_start == line_end:
        return f"L{line_start}"
    return f"L{line_start}–{line_end}"


def _format_sig_doc(detail_prefix: str, row) -> list[str]:
    """``detail_prefix`` is the column before ``Sig:`` / ``Doc:`` (e.g. ``│   `` or ``    ``)."""
    lines: list[str] = []
    sig = (row["signature"] or "").strip()
    if sig:
        sig_parts = sig.splitlines()
        total_sig_lines = len(sig_parts)
        if total_sig_lines > _MAX_SIGNATURE_LINES:
            sig_parts = sig_parts[:_MAX_SIGNATURE_LINES]
        lines.append(f"{detail_prefix}Sig: {sig_parts[0]}")
        for extra in sig_parts[1:]:
            lines.append(f"{detail_prefix}    {extra}")
        if total_sig_lines > _MAX_SIGNATURE_LINES:
            omitted = total_sig_lines - _MAX_SIGNATURE_LINES
            lines.append(f"{detail_prefix}    ...[truncated {omitted} lines]")
    doc_raw = (row["docstring"] or "").strip()
    if doc_raw:
        first_line = doc_raw.splitlines()[0].strip()
        lines.extend(clipped_doc_lines(detail_prefix, first_line, _MAX_DOCSTRING_CHARS))
    return lines


def _symbol_branch_lines(
    children_by_parent_id: dict[Optional[int], list],
    parent_id: Optional[int],
    branch_prefix: str,
) -> list[str]:
    lines: list[str] = []
    siblings = children_by_parent_id.get(parent_id, ())
    last_i = len(siblings) - 1
    for index, row in enumerate(siblings):
        is_last = index == last_i
        connector = "└─ " if is_last else "├─ "
        loc = _line_span(row["line_start"], row["line_end"])
        child_name = (row["name"] or "").strip()
        label = child_name if child_name else (row["full_name"] or "").strip()
        lines.append(f"{branch_prefix}{connector}{loc}  {row['kind']}  {label}")
        detail_prefix = branch_prefix + ("    " if is_last else "│   ")
        lines.extend(_format_sig_doc(detail_prefix, row))
        continuation = "   " if is_last else "│  "
        lines.extend(
            _symbol_branch_lines(
                children_by_parent_id, row["id"], branch_prefix + continuation
            )
        )
    return lines


def get_file_overview(db: CodeDB, file_path: str) -> str:
    """
    Return a readable overview of symbols (tree by ``parent_id``, with ``Sig`` /
    ``Doc`` lines) and imports (source line + statement text) for one file.

    ``file_path`` must match ``files.path`` for the index (POSIX path relative to the
    index root, e.g. ``pkg/mod.py``).
    """
    file_row = db.connection.execute(
        "SELECT id, path, language, line_count FROM files WHERE path = ?",
        (file_path,),
    ).fetchone()
    if file_row is None:
        return (
            f"No indexed file matches {file_path!r}. "
            f"Use the local path as stored in the index (relative to {db.root})."
        )

    file_id = file_row["id"]
    imp_rows = list(db.connection.execute(_IMPORTS_SQL, (file_id,)))
    sym_rows = list(db.connection.execute(_SYMBOLS_SQL, (file_id,)))

    lines_out: list[str] = [
        "Legend: L = Line, Sig = Signature, Doc = Docstring\n",
        f"File: {file_row['path']}",
        f"Language: {file_row['language'] or '—'}\nLines: {file_row['line_count']}",
        "",
        f"## Imports ({len(imp_rows)})",
    ]
    if not imp_rows:
        lines_out.append("_(none)_")
    else:
        # One DB row per imported name from `from m import a, b` repeats the same
        # statement `signature`; show each distinct signature once.
        seen_signatures: set[str] = set()
        for row in imp_rows:
            sig = (row["signature"] or "").strip()
            if sig:
                if sig in seen_signatures:
                    continue
                seen_signatures.add(sig)
                lines_out.append(f"L{row['line_number']}: {sig}")
            else:
                lines_out.append(f"L{row['line_number']}: —")

    lines_out.extend(["", f"## Symbols ({len(sym_rows)})"])

    if not sym_rows:
        lines_out.append("_(none)_")
    else:
        ids_in_file = {r["id"] for r in sym_rows}

        def effective_parent_id(row) -> Optional[int]:
            pid = row["parent_id"]
            if pid is None:
                return None
            if pid not in ids_in_file:
                return None
            return pid

        children_by_parent_id: dict[Optional[int], list] = defaultdict(list)
        for row in sym_rows:
            children_by_parent_id[effective_parent_id(row)].append(row)
        for bucket in children_by_parent_id.values():
            bucket.sort(key=lambda r: (r["line_start"], r["line_end"], r["full_name"]))

        roots = children_by_parent_id.get(None, ())
        for root_index, row in enumerate(roots):
            if root_index > 0:
                lines_out.append("")
            loc = _line_span(row["line_start"], row["line_end"])
            root_label = (row["name"] or row["full_name"] or "").strip()
            lines_out.append(f"{loc}  {row['kind']}  {root_label}")
            lines_out.extend(_format_sig_doc("│   ", row))
            lines_out.extend(_symbol_branch_lines(children_by_parent_id, row["id"], ""))

    return "\n".join(lines_out)
