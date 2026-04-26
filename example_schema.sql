PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

-- Watermark table (singleton: only one row allowed)
CREATE TABLE IF NOT EXISTS watermarks (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_full_parse REAL NOT NULL DEFAULT 0.0,  -- 0.0 forces full parse on first run
    last_incremental REAL DEFAULT 0.0 --epoch time of last incremental parse
);
INSERT OR IGNORE INTO watermarks (id, last_full_parse, last_incremental) VALUES (1, 0.0, 0.0);


-- Directories (hierarchy for structure + aggregation)
CREATE TABLE IF NOT EXISTS directories (
    id              INTEGER NOT NULL PRIMARY KEY,
    parent_id       INTEGER REFERENCES directories(id),  -- null = root
    name            TEXT NOT NULL,                      -- "auth"
    path            TEXT UNIQUE NOT NULL,                -- "/src/auth"
    depth           INTEGER NOT NULL,                    -- 0 = root, 1 = src, etc.
    file_count      INTEGER DEFAULT 0,                   -- aggregated from files
    total_lines     INTEGER DEFAULT 0,                   -- aggregated from files
);

-- To easily find all files under a directory without recursion.
CREATE TABLE IF NOT EXISTS directory_closure (
    ancestor_path   TEXT NOT NULL,       -- The path of the ancestor (e.g., "/src")
    descendant_id   INTEGER NOT NULL,    -- The ID of the descendant directory
    depth           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ancestor_path, descendant_id)
);
-- Index for fast lookups
CREATE INDEX idx_closure_ancestor ON directory_closure(ancestor_path);

-- Files now reference directories
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER NOT NULL PRIMARY KEY,
    directory_id    INTEGER NOT NULL REFERENCES directories(id),
    name            TEXT NOT NULL,                       -- "auth.py"
    path            TEXT UNIQUE NOT NULL,                -- "/src/auth/auth.py"
    language        TEXT,                               -- "python"             
    content_hash    TEXT NOT NULL,                                -- hash of the file content
    line_count      INTEGER NOT NULL DEFAULT 0                             -- number of lines in the file
);

-- Symbol definitions (classes, functions, methods, variables)
CREATE TABLE IF NOT EXISTS symbols (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    parent_id       INTEGER REFERENCES symbols(id),  -- class→method nesting
    name            TEXT NOT NULL,                  -- "login"
    qualified_name  TEXT,                            -- e.g. "AuthService.login"
    kind            TEXT NOT NULL,                   -- class, function, method, variable
    line_start      INTEGER NOT NULL,                -- 10
    line_end        INTEGER NOT NULL,                -- 12
    line_count      INTEGER NOT NULL,                -- 3
    signature       TEXT,                            -- "def login(self, username: str, password: str) -> bool"
    docstring       TEXT,                            -- "Login to the system"
    modifiers       TEXT,                           -- ["@login_required"] --decorators
    base_classes    TEXT,                           -- ["BaseService"]
    language        TEXT NOT NULL                    -- "python"
);

-- Staging table for references - holds first pass results.
CREATE TABLE IF NOT EXISTS symbol_references_staging (
    ref_symbol_name     TEXT NOT NULL,                  -- resolve to target_symbol_id by name
    ref_symbol_qualified_name  TEXT NOT NULL,
    source_file_id  INTEGER NOT NULL,
    source_line     INTEGER NOT NULL,                -- 10
    ref_kind        TEXT NOT NULL,                   -- call, access, and type_annotation
    context         TEXT                             -- "print('Hello, world!')" -- HOW the api interface is used
);

-- Where symbols are used (calls, access, type_annotation)
-- Execution, Retrieval, and Declaration References
CREATE TABLE IF NOT EXISTS symbol_references (
    id              INTEGER NOT NULL PRIMARY KEY,
    ref_symbol_id       INTEGER REFERENCES symbols(id), -- link to internal symbol if found, otherwise null
    ref_symbol_name     TEXT NOT NULL,       --  requests.get() -- external library call
    ref_symbol_qualified_name TEXT NULL,
    source_file_id  INTEGER NOT NULL REFERENCES files(id), -- link to the file that contains the reference
    source_line     INTEGER NOT NULL,                -- 10
    ref_kind        TEXT NOT NULL,                   -- call, access, and type_annotation
    context         TEXT                             -- "print('Hello, world!')" -- HOW the api interface is used
);

-- File-level imports (for reach analysis)
CREATE TABLE IF NOT EXISTS imports (
    id              INTEGER NOT NULL PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    import_path     TEXT NOT NULL,                            -- "os.path"
    imported_symbol TEXT NOT NULL DEFAULT '',                            -- "join" or "*"
    alias           TEXT,                            -- "np"
    line_number     INTEGER NOT NULL,                         -- 10
    import_type     TEXT NOT NULL, -- 'absolute', 'relative', 'stdlib'
    import_scope    TEXT NOT NULL, -- 'module' or 'function' -- address lazy imports
    signature       TEXT NOT NULL, -- "from os.path import join"
    imported_file_id INTEGER REFERENCES files(id) -- file_id to the imported file (if found)
);

-- Class Hierarchy - used for inheritance analysis. Factory Patterns, Polymorphism, etc.
CREATE TABLE IF NOT EXISTS class_hierarchy (
    parent_id       INTEGER NOT NULL REFERENCES symbols(id),
    child_id        INTEGER NOT NULL REFERENCES symbols(id),
    PRIMARY KEY (parent_id, child_id)
);

-- NOTE: FTS for symbols and symbol_references.
-- Symbols can be maintained in pass 1 incrementally. Symbol References needs to be maintained in pass 2.

CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name, 
    qualified_name, 
    docstring, 
    signature,
    content='symbols',
    content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS symbol_references_fts USING fts5(
    ref_symbol_name,  
    ref_symbol_qualified_name,
    context,         
    content='symbol_references',
    content_rowid='id'
);