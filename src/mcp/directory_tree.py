from collections import defaultdict

from src.db import CodeDB

_TREE_SQL = """
SELECT 'directory' AS row_type, id, parent_id AS parent_id, name, NULL AS line_count, NULL AS symbol_count
FROM directories
UNION ALL
SELECT 'file' AS row_type, id, directory_id AS parent_id, name, line_count, symbol_count FROM files
"""


def _lines_under_parent(children_by_parent_id, parent_key, branch_prefix):
    lines = []
    siblings = children_by_parent_id.get(parent_key, ())
    last_index = len(siblings) - 1
    for index, (is_directory, row) in enumerate(siblings):
        is_last_child = index == last_index
        connector = "└── " if is_last_child else "├── "
        if is_directory:
            display_name = row["name"] + "/"
        else:
            lines_n = row["line_count"]
            symbols_n = row["symbol_count"] if row["symbol_count"] is not None else 0
            stats = f"({lines_n}L)" if symbols_n == 0 else f"({lines_n}L, {symbols_n}S)"
            display_name = f"{row['name']} {stats}"
        lines.append(f"{branch_prefix}{connector}{display_name}")
        if is_directory:
            continuation = "    " if is_last_child else "│   "
            next_prefix = branch_prefix + continuation
            lines.extend(
                _lines_under_parent(children_by_parent_id, row["id"], next_prefix)
            )
    return lines


def get_directory_tree(db: CodeDB) -> str:
    children_by_parent_id = defaultdict(list)
    for row in db.connection.execute(_TREE_SQL):
        is_directory = row["row_type"] == "directory"
        children_by_parent_id[row["parent_id"]].append((is_directory, row))
    for sibling_list in children_by_parent_id.values():
        sibling_list.sort(
            key=lambda item: (not item[0], item[1]["name"].lower()),
        )
    body_lines = _lines_under_parent(children_by_parent_id, None, "")
    if not body_lines:
        return "."
    return "(L = Lines, S = Symbols)\n" + ".\n" + "\n".join(body_lines)
