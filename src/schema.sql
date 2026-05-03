PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

-- DROP TABLE IF EXISTS watermarks; -- TODO: Remove this after testing.
-- DROP TABLE IF EXISTS directories;
-- DROP TABLE IF EXISTS files;
-- DROP TABLE IF EXISTS symbols;
-- DROP TABLE IF EXISTS symbol_references_staging;
-- DROP TABLE IF EXISTS symbol_references;
-- DROP TABLE IF EXISTS imports;
-- DROP TABLE IF EXISTS symbols_fts;
-- DROP TABLE IF EXISTS symbol_references_fts;

CREATE TABLE IF NOT EXISTS watermarks (
    id                  INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),
    last_full_parse     INTEGER NOT NULL DEFAULT 0,
    last_incremental    INTEGER DEFAULT 0
);
INSERT OR IGNORE INTO watermarks (id, last_full_parse, last_incremental) VALUES (1, 0, 0);

CREATE TABLE IF NOT EXISTS directories (
    id              INTEGER NOT NULL PRIMARY KEY,
    parent_id       INTEGER REFERENCES directories(id),  
    name            TEXT NOT NULL,                     
    path            TEXT UNIQUE NOT NULL,               
    depth           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id              INTEGER NOT NULL PRIMARY KEY,
    directory_id    INTEGER REFERENCES directories(id),
    name            TEXT NOT NULL,                       
    path            TEXT UNIQUE NOT NULL,   
    normalized_path TEXT UNIQUE NOT NULL,             
    language        TEXT,                                          
    content_hash    TEXT NOT NULL,                               
    line_count      INTEGER NOT NULL DEFAULT 0,
    symbol_count    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS symbols (
    id              INTEGER NOT NULL PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id),
    parent_id       INTEGER REFERENCES symbols(id), 
    name            TEXT NOT NULL,                  
    qualified_name  TEXT,   
    full_name       TEXT UNIQUE NOT NULL,                        
    kind            TEXT NOT NULL,                  
    line_start      INTEGER NOT NULL,                
    line_end        INTEGER NOT NULL,                
    line_count      INTEGER NOT NULL,               
    signature       TEXT NOT NULL,                           
    docstring       TEXT,                            
    modifiers       TEXT,                           
    base_classes    TEXT,                          
    language        TEXT NOT NULL,
    is_test         BOOLEAN NOT NULL DEFAULT FALSE               
);
CREATE INDEX IF NOT EXISTS symbols_file_id_index ON symbols (file_id);

CREATE TABLE IF NOT EXISTS symbol_references_staging (
    id                          INTEGER NOT NULL,
    ref_symbol_name             TEXT NOT NULL,                 
    ref_symbol_qualified_name   TEXT NULL,
    ref_symbol_full_name        TEXT NOT NULL,
    source_file_id              INTEGER NOT NULL REFERENCES files(id),
    source_line                 INTEGER NOT NULL,                
    ref_kind                    TEXT NOT NULL,                  
    context                     TEXT                             
);

CREATE TABLE IF NOT EXISTS symbol_references (
    id                          INTEGER NOT NULL PRIMARY KEY,
    ref_symbol_id               INTEGER NOT NULL REFERENCES symbols(id), 
    ref_symbol_file_id          INTEGER NOT NULL REFERENCES files(id),
    ref_symbol_name             TEXT NOT NULL,       
    ref_symbol_qualified_name   TEXT NULL,
    ref_symbol_full_name        TEXT NOT NULL,
    source_file_id              INTEGER NOT NULL REFERENCES files(id), 
    source_line                 INTEGER NOT NULL,                
    ref_kind                    TEXT NOT NULL,                  
    context                     TEXT NOT NULL                     
);
CREATE INDEX IF NOT EXISTS symbol_references_source_file_id_index ON symbol_references (source_file_id);

CREATE TABLE IF NOT EXISTS imports (
    id                    INTEGER NOT NULL PRIMARY KEY,
    file_id               INTEGER NOT NULL REFERENCES files(id),
    import_path           TEXT NOT NULL,                           
    imported_symbol       TEXT NOT NULL DEFAULT '',                           
    alias                 TEXT,                           
    line_number           INTEGER NOT NULL,                        
    import_type           TEXT NOT NULL, 
    import_scope          TEXT NOT NULL, 
    signature             TEXT NOT NULL, 
    imported_file_id      INTEGER REFERENCES files(id),
    watermark             INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS imports_file_id_index ON imports (file_id);


/* NOTE: Full Text Search "Tables" for symbols and symbol_references. */
CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
    full_name,
    docstring,
    signature,
    content='symbols',
    content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS symbol_references_fts USING fts5(
    ref_symbol_full_name,
    context,
    content='symbol_references',
    content_rowid='id'
);