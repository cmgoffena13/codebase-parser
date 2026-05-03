# codebase-parser
Utilizes TreeSitter to parse a codebase and store the relationships. This empowers AI tooling to better understand and maneuver a codebase.

## Notes
- Two Phase Parsing Strategry
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
- qualified_name: Parent.name + . + name
- signature: `node.text` - API Surface
- docstring: `node.child_by_field_name('body') → Find first string node`
- modifiers: iterate node.children for decorator nodes. Ouputs as array ex. `["@login_required"]`
- line_start: `node.start_point.row + 1 (1-indexed)`
- line_end: `node.end_point.row + 1`
- line_count: `line_end - line_start + 1`
- language: `python`
- kind: `["class", "method", "function", "variable"]`

Notes
- Need to consider nested functions. Similar to class methods, but not the same.
- `self` and `cls` variables will have a parent id of the class.

Example Record in Paser:
```python
{
  "file_id": 123,
  "name": "calculate_total",
  "qualified_name": "OrderService.calculate_total",
  "kind": "method",
  "line_start": 45,
  "line_end": 52,
  "line_count": 8
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

How do we maintain the symbols, imports, and references of a file?
- Before we parse a file, query for the last snapshot of the symbols using file path.
    - Snapshot Fields Needed:
        - id - to reuse
        - qualified_name - lookup key, its always COALECES(qualified_name, name)
        - kind - lookup key (make sure its `action` the function rather than `action` the variable)
        - line_start - to detect change and update
        - line_end - to detect change and update
- Before we parse a file, query for the last snapshot of the imports using file path.
    - Snapshot Fields Needed:
        - id - to reuse
        - import_path - part of composite lookup key
        - imported_symobl - part of composite lookup key
- Before we parse a file, query for the last snapshot of the references using file path.
    - Snapshot Fields Needed:
        - id - to reuse
        - ref_symbol_id - only for conditional logic
        - ref_symbol_name - lookup key for external references (if ref_symbol_id is NULL)
        - ref_symbol_qualified_name - lookup key for internal references with ref_symbol_name (if ref_symbol_id is NOT NULL)
        - ref_kind - lookup key
        - source_line - to detect change and update
    NOTE: Very specific logic here for the lookup. If NOT FOUND, its gotta go in the staging table.