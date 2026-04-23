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
    id              INTEGER PRIMARY KEY,
    parent_id       INTEGER REFERENCES directories(id),  -- null = root
    name            TEXT NOT NULL,                      -- "auth"
    path            TEXT UNIQUE NOT NULL,                -- "/src/auth"
    depth           INTEGER NOT NULL,                    -- 0 = root, 1 = src, etc.
    file_count      INTEGER DEFAULT 0,                   -- aggregated from files
    total_lines     INTEGER DEFAULT 0,                   -- aggregated from files
);

-- Files now reference directories
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY,
    directory_id    INTEGER NOT NULL REFERENCES directories(id),
    name            TEXT NOT NULL,                       -- "auth.py"
    path            TEXT UNIQUE NOT NULL,                -- "/src/auth/auth.py"
    language        TEXT,                               -- "python"             
    content_hash    TEXT,                                -- hash of the file content
    last_indexed    REAL,                                -- last time the file was indexed
    line_count      INTEGER,                             -- number of lines in the file
    last_modified   TEXT,                                -- last time the file was modified
    last_commit_hash TEXT                                -- last commit hash that modified the file
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
    language        TEXT NOT NULL                    -- "python"
);

-- Staging table for references - MAYBE.
CREATE TABLE IF NOT EXISTS symbol_references_staging (
    target_name     TEXT NOT NULL,                  -- resolve to target_id by name
    source_file_id  INTEGER NOT NULL,
    source_line     INTEGER NOT NULL,                -- 10
    ref_kind        TEXT NOT NULL,                   -- call, import, inheritance, type_annotation
    context         TEXT                             -- "print('Hello, world!')"
);

-- Where symbols are used (calls, imports, inheritance, type refs)
CREATE TABLE IF NOT EXISTS symbol_references (
    id              INTEGER PRIMARY KEY,
    target_id       INTEGER REFERENCES symbols(id),
    source_file_id  INTEGER NOT NULL REFERENCES files(id),
    source_line     INTEGER NOT NULL,                -- 10
    ref_kind        TEXT NOT NULL,                   -- call, import, inheritance, type_annotation
    context         TEXT                             -- "print('Hello, world!')"
);

-- File-level imports (for reach analysis)
CREATE TABLE IF NOT EXISTS imports (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    import_path     TEXT,                            -- "os.path"
    imported_name   TEXT,                            -- "join" or "*"
    alias           TEXT,                            -- "np"
    line_number     INTEGER,                         -- 10
    import_type     TEXT, -- 'absolute', 'relative', 'stdlib', 'alias'
    resolved_path   TEXT -- Full path to the imported file (if found)
);

-- FTS for symbols (with auto-sync triggers)
CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    name, qualified_name, kind, docstring, signature,
    content=symbols, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS trg_symbols_after_insert AFTER INSERT ON symbols BEGIN
    INSERT INTO symbols_fts(rowid, name, qualified_name, kind, docstring, signature)
    VALUES (new.id, new.name, new.qualified_name, new.kind, new.docstring, new.signature);
END;

CREATE TRIGGER IF NOT EXISTS trg_symbols_after_delete AFTER DELETE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid)
    VALUES ('delete', old.id);
END;

CREATE TRIGGER IF NOT EXISTS trg_symbols_after_update AFTER UPDATE ON symbols BEGIN
    INSERT INTO symbols_fts(symbols_fts, rowid)
    VALUES ('delete', old.id);
    INSERT INTO symbols_fts(rowid, name, qualified_name, kind, docstring, signature)
    VALUES (new.id, new.name, new.qualified_name, new.kind, new.docstring, new.signature);
END;

-- FTS for references (searchable call context)
CREATE VIRTUAL TABLE IF NOT EXISTS symbol_references_fts USING fts5(
    symbol_name,   -- denormalized from symbols.qualified_name
    ref_kind,      -- "call", "import", etc.
    context,       -- "print('Hello, world!')"
    content=references, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS trg_symbol_references_after_insert AFTER INSERT ON symbol_references BEGIN
    INSERT INTO symbol_references_fts(rowid, symbol_name, ref_kind, context)
    VALUES (
        new.id,
        (SELECT COALESCE(qualified_name, name) FROM symbols WHERE id = new.target_id),
        new.ref_kind,
        new.context
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_symbol_references_after_delete AFTER DELETE ON symbol_references BEGIN
    INSERT INTO symbol_references_fts(symbol_references_fts, rowid)
    VALUES ('delete', old.id);
END;

CREATE TRIGGER IF NOT EXISTS trg_symbol_references_after_update AFTER UPDATE ON symbol_references BEGIN
    INSERT INTO symbol_references_fts(symbol_references_fts, rowid)
    VALUES ('delete', old.id);

    INSERT INTO symbol_references_fts(rowid, symbol_name, ref_kind, context)
    VALUES (
        new.id,
        (SELECT COALESCE(qualified_name, name) FROM symbols WHERE id = new.target_id),
        new.ref_kind,
        new.context
    );
END;

-- Performance indexes (Review.)
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_id);
CREATE INDEX IF NOT EXISTS idx_symbols_parent_kind ON symbols(parent_id, kind);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file_line ON symbols(file_id, line_start);
CREATE INDEX IF NOT EXISTS idx_references_target ON references(target_id);
CREATE INDEX IF NOT EXISTS idx_references_target_kind ON symbol_references(target_id, ref_kind);
CREATE INDEX IF NOT EXISTS idx_references_source ON symbol_references(source_file_id);
CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id);
CREATE INDEX IF NOT EXISTS idx_imports_name ON imports(imported_name);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_directory ON files(directory_id);