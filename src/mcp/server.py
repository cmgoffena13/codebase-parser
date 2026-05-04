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
Tools read a pre-built SQLite code index (``code.db`` in the project root).
Set environment variable CODEBASE_PARSER_ROOT to the indexed repository root
(the directory that contains ``code.db``). If unset, the process current working
directory is used. Build or refresh the index with CodeProcessor before querying.
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
def directory_tree(ctx: Context) -> str:
    """Directory/file tree for the index with line and symbol counts per file."""
    processor = _processor(ctx)
    processor.process()
    return get_directory_tree(_db(ctx))


@mcp.tool()
def file_overview(file_path: str, ctx: Context) -> str:
    """Imports and symbol tree for one file. ``file_path`` is relative to the index root (POSIX)."""
    processor = _processor(ctx)
    processor.process()
    return get_file_overview(_db(ctx), file_path.strip())


@mcp.tool()
def search_symbols(query: str, ctx: Context, limit: int = 20) -> str:
    """Search symbols via FTS5; results are grouped by file. Use ``full_name`` with ``symbol_context``."""
    processor = _processor(ctx)
    processor.process()
    return run_symbol_search(_db(ctx), query, limit)


@mcp.tool()
def symbol_context(full_name: str, ctx: Context) -> str:
    """Definition lines and grouped references for one symbol (indexed ``full_name``)."""
    processor = _processor(ctx)
    processor.process()
    return get_symbol_context(_db(ctx), full_name.strip())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
