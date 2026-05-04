# codebase-parser
Utilizes TreeSitter to parse a codebase and store the relationships. This empowers AI tooling to better understand and maneuver a codebase.

## Notes
- Two Phase Parsing Strategy
    - Per-File Pass (Whats in the file) - WALK THE CODEBASE
        - Also includes Delta Directory Stat Updates
        - Includes Directory Closure Table Update
    - Cross-File Pass (How does the code in the file relate across the codebase) - ONLY DATABASE OPERATIONS
        - Resolve Import `imported_file_id`
        - Resolve Symbol_References `ref_symbol_id`
        - Build Class Hierarchy
        - Build File Dependency Hierarchy

- Batch Processing
    - Respecting table relationships while also optimizing for performance through bulk operations
    - Bulk Resolution Steps (key lookups)

## Data Model
Main Categories:
- Structure
    - What: Directory Tree, File Paths, Line Counts
    - Value: Module Boundaries, overview of codebase
- Symbols (in a file)
    - What: Classes, Functions, Class Methods, Variables
    - Value: Where code lives, Public API Surfaces
- Symbol References (across codebase) - the CORE, the Graph Edges. Everything else are nodes.
    - What: Calls, Imports, Custom Type Annotations
    - Value: Execution Flow, Impact Analysis
- Imports (across codebase) - references at the file/module level
    - What: Imports
    - Values: File/Module Relationships
- Hierarchy (Classes)
    - What: Inheritances, Method Overrides
    - Value: Follow Factory Patterns, Polymorphism, etc.

### Tables

#### Symbols
Definitions. Things that exist in the file.

Fields:
- id: auto-created
- file_id: 
- parent_id: classid or functionid
- name: `node.child_by_field_name('name').text`
- qualified_name: dotted path for lookup (unique per index)
- signature: `node.text` - API Surface
- docstring: `node.child_by_field_name('body') → Find first string node`
- modifiers: iterate node.children for decorator nodes. Outputs as array ex. `["@login_required"]`
- line_start: `node.start_point.row + 1 (1-indexed)`
- line_end: `node.end_point.row + 1`
- line_count: `line_end - line_start + 1`
- language: `python`
- kind: `["class", "method", "function", "variable"]`

Notes
- Need to consider nested functions. Similar to class methods, but not the same.
- `self` and `cls` variables will have a parent id of the class.

Example Record in Parser:
```python
{
  "file_id": 123,
  "name": "calculate_total",
  "qualified_name": "OrderService.calculate_total",
  "kind": "method",
  "line_start": 45,
  "line_end": 52,
  "line_count": 8,
  "signature": "def calculate_total(self, items: list, tax: float = 0.0) -> float:",
  "docstring": "Calculates the total with tax.",
  "decorators": ["@cache_result"],
  "language": "python"
}
```

## Architecture
How do we efficiently parse and maintain a tree of the codebase?

We need a global ID assigner so we DO NOT need to a trip to the database for parent IDs.
- Maintain a stack of Parent IDs as we traverse
    - Child found = stack.top()
    - Enter another container (class, function, etc.) - stack.push()
    - Leave container - stack.pop()

We need to pull snapshots into memory before we parse so we can know:
- New Data (Insert)
- Changed Data (Update)
- Deleted/Moved Data (Delete - this could get complicated)

How do we maintain a repo structure of the codebase?
- Before a walk the codebase, query for the last snapshot of the directories.
    - Snapshot Fields Needed:
        - id - to reuse
        - path - lookup key

- Before we walk the codebase, query for the last snapshot of the files.
    - Snapshot Fields Needed:
        - id - to reuse
        - path - lookup key
        - content_hash - to detect content changes
        - line_count - stored per file row (e.g. display, tree rendering)
        - symbol_count - prior count of symbol rows for this file; refreshed to `len(symbols)` after each parse

How do we maintain the symbols, imports, and references of a file?
- Before we parse a file, query for the last snapshot of the symbols for that ``file_id``.
    - Snapshot shape (see ``get_symbols_snapshot``): keyed by ``(qualified_name, kind)``.
        - ``id`` — reuse when the same symbol occurrence still exists.
        - ``line_start``, ``line_end`` — compared on each parse; if the span changed, emit an update row for that ``id``.
        - ``seen`` — set when the key appears in the new parse; rows left unseen are deleted (removed symbol or kind/name identity changed).
- Before we parse a file, query for the last snapshot of the imports for that ``file_id``.
    - Snapshot shape: keyed by ``(import_path, imported_symbol)``.
        - ``id`` — reuse when the same import binding still exists.
        - ``line_number`` — compared on each parse; if the statement moved lines, emit an update row.
        - Unseen keys are deleted (import removed or composite key no longer present).
- Before we parse a file, query for the last snapshot of the symbol references already stored in ``symbol_references`` for that file as ``source_file_id`` (see ``get_symbol_references_snapshot``).
    - Snapshot shape: keyed by ``(ref_symbol_qualified_name, ref_kind, source_line)`` — that triple is the stable identity of one reference site.
        - ``id`` — reuse when the same occurrence still exists.
        - ``context`` — compared on each parse; if the source text at that site changed, emit an update row for that ``id``.
        - Unseen keys are deleted (reference removed or the occurrence moved so the triple no longer matches).
    - First-pass rows go to ``symbol_references_staging``; ``resolve_symbol_references`` inserts into ``symbol_references`` only when ``ref_symbol_qualified_name`` matches a ``symbols.qualified_name`` (otherwise the staging row is dropped and never becomes a resolved edge).