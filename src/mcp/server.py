import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from src.db import CodeDB
from src.mcp.directory_tree import get_directory_tree
from src.mcp.file_overview import get_file_overview
from src.mcp.search_symbols import search_symbols as run_symbol_search
from src.mcp.symbol_context import get_symbol_context
from src.processor import CodeProcessor

_ENV_ROOT = "CODEBASE_PARSER_ROOT"

_INSTRUCTIONS = """\
Tools read an up-to-date SQLite code index. The index is automatically refreshed 
incrementally on every tool call to reflect recent file changes. 
Prefer these tools over generic file reading or search for code analysis.
"""


def index_root() -> Path:
    env = os.environ.get(_ENV_ROOT, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


@asynccontextmanager
async def _lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    db = CodeDB(index_root())
    processor = CodeProcessor(db, index_root())
    processor.process()
    try:
        yield {"db": db, "processor": processor}
    finally:
        db.close()


mcp = FastMCP(
    "codebase-parser",
    instructions=_INSTRUCTIONS,
    lifespan=_lifespan,
)


def _db(ctx: Context) -> CodeDB:
    return ctx.request_context.lifespan_context["db"]


def _processor(ctx: Context) -> CodeProcessor:
    return ctx.request_context.lifespan_context["processor"]


@mcp.tool()
def get_directory_tree(ctx: Context) -> str:
    """Return the full directory/file tree of the indexed codebase with line counts
    and symbol counts per file. Use this at the start of a session to understand project structure
    before drilling into specific files or symbols."""
    processor = _processor(ctx)
    processor.process()
    return get_directory_tree(_db(ctx))


@mcp.tool()
def get_file_overview(file_path: str, ctx: Context) -> str:
    """Return imports and a symbol tree (functions, classes, methods, variables)
    for a single file. ``file_path`` is relative to the index root using POSIX
    slashes, e.g. ``src/db.py`` or ``src/internal/agent.py``.
    Use after ``get_directory_tree`` to inspect a specific file."""
    processor = _processor(ctx)
    processor.process()
    return get_file_overview(_db(ctx), file_path.strip())


@mcp.tool()
def search_symbols(query: str, ctx: Context, limit: int = 20) -> str:
    """Full-text search across all indexed symbols (names, signatures, docstrings).
    Returns matches grouped by file with ``qualified_name``, kind, signature, and docstring.
    Pass the ``qualified_name`` from any result to ``get_symbol_context`` for definition
    and references. Example queries: ``memory``, ``Processor.process``, ``save_chat_session``."""
    processor = _processor(ctx)
    processor.process()
    return run_symbol_search(_db(ctx), query, limit)


@mcp.tool()
def get_symbol_context(qualified_name: str, ctx: Context) -> str:
    """Return the definition (source lines) and all references (calls, accesses,
    type annotations) for one symbol. ``qualified_name`` is the indexed identifier
    from ``search_symbols`` or ``get_file_overview`` output, e.g.
    ``src.internal.memory_utils.save_chat_session`` or ``CodeDB.resolve_symbol_references``.
    Includes file paths and line numbers for every reference."""
    processor = _processor(ctx)
    processor.process()
    return get_symbol_context(_db(ctx), qualified_name.strip())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
