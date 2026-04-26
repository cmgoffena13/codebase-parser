PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

-- Watermark table (singleton: only one row allowed)
DROP TABLE IF EXISTS watermarks; -- TODO: Remove this after testing.
CREATE TABLE IF NOT EXISTS watermarks (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_full_parse REAL NOT NULL DEFAULT 0.0,  -- 0.0 forces full parse on first run
    last_incremental REAL DEFAULT 0.0 --epoch time of last incremental parse
);
INSERT OR IGNORE INTO watermarks (id, last_full_parse, last_incremental) VALUES (1, 0.0, 0.0);

DROP  TABLE IF EXISTS directories;
CREATE TABLE IF NOT EXISTS directories (
    id              INTEGER NOT NULL PRIMARY KEY,
    parent_id       INTEGER REFERENCES directories(id),  
    name            TEXT NOT NULL,                     
    path            TEXT UNIQUE NOT NULL,               
    depth           INTEGER NOT NULL,                   
    file_count      INTEGER DEFAULT 0,                   
    total_lines     INTEGER DEFAULT 0                  
);

DROP TABLE IF EXISTS files;
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER NOT NULL PRIMARY KEY,
    directory_id    INTEGER NOT NULL REFERENCES directories(id),
    name            TEXT NOT NULL,                       
    path            TEXT UNIQUE NOT NULL,                
    language        TEXT,                                          
    content_hash    TEXT NOT NULL,                               
    line_count      INTEGER NOT NULL DEFAULT 0                             
);
