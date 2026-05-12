from pathlib import Path

_SKILL_INSTRUCTIONS = """\
---
name: Codebase-Parser
description: A skill that enables you to use the Codebase-Parser MCP Server effectively.
allowed-tools: get_directory_tree get_file_overview search_symbols get_symbol_context
---

## Workflow

### Phase 1: Orient
Call `get_directory_tree` first. This gives you the full project layout with line counts and symbol counts per file. Use it to:
- Identify the main source directories and entrypoints (e.g. `main.py`, `app.py`, `index.html`)
- Spot high-symbol-count files (likely core modules)
- Understand the project's shape before diving deeper

### Phase 2: Locate
Call `search_symbols` with keywords extracted from the user's request. This searches names, signatures, and docstrings via Full-Text Search.
- Use specific keywords that are likely to be in the codebase.
- Note the symbol name from each result — you need it for Phase 3

### Phase 3: Understand
Call `get_symbol_context` with the symbol name from Phase 2. This returns:
- The **definition** (actual source lines)
- All **references** (calls, accesses, type annotations) with file paths and line numbers
- Use this to trace how a symbol is used across the codebase

### Phase 4: Inspect (optional)
Call `get_file_overview` when you need the full picture of a single file — its imports and complete symbol tree. Useful when:
- You need to understand a file's contents
- You want to see all symbols in a file and their relationships, not just one
- `file_path` is relative to repo root with POSIX slashes (e.g. `src/db.py`)

## Rules
- Always start with `get_directory_tree` to orient yourself if you don't have a directory map in your memory.
- Never guess a symbol name. Always derive it from `search_symbols` or `get_file_overview` output.
- For "where is X defined" or "who calls X" questions, go straight to `search_symbols` → `get_symbol_context`.
- Cite file paths and line numbers in every response.
"""


def generate_skill() -> None:
    output_path = Path.cwd() / ".claude" / "skills" / "codebase-parser" / "SKILL.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_SKILL_INSTRUCTIONS, encoding="utf-8")


if __name__ == "__main__":
    path = generate_skill()
