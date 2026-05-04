"""Shared output clipping for MCP tools."""

MAX_TOOL_OUTPUT = 100_000


def clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def clipped_doc_lines(detail_prefix: str, doc_raw: str, limit: int) -> list[str]:
    """
    Normalize docstring to a single line for display, ``clip`` to ``limit``, and
    return tree lines (``Doc:`` plus optional continuation lines after ``clip``'s
    newline).
    """
    t = doc_raw.replace("\n", " ").strip()
    if not t:
        return []
    c = clip(t, limit)
    if "\n" not in c:
        escaped = c.replace("\\", "\\\\").replace('"', '\\"')
        return [f'{detail_prefix}Doc: "{escaped}"']
    body, tail = c.split("\n", 1)
    escaped = body.replace("\\", "\\\\").replace('"', '\\"')
    lines = [f'{detail_prefix}Doc: "{escaped}"']
    lines.extend(f"{detail_prefix}    {ln}" for ln in tail.splitlines())
    return lines
