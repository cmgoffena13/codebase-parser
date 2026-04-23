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


-- Directories (hierarchy for structure + aggregation)
CREATE TABLE IF NOT EXISTS directories (
    id              INTEGER PRIMARY KEY,
    parent_id       INTEGER REFERENCES directories(id),  -- null = root
    name            TEXT NOT NULL,                      -- "auth"
    path            TEXT UNIQUE NOT NULL,                -- "/src/auth"
    depth           INTEGER NOT NULL,                    -- 0 = root, 1 = src, etc.
    file_count      INTEGER DEFAULT 0,                   -- aggregated from files
    total_lines     INTEGER DEFAULT 0                    -- aggregated from files
);

-- Files now reference directories
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY,
    directory_id    INTEGER NOT NULL REFERENCES directories(id),
    name            TEXT NOT NULL,                       -- "auth.py"
    path            TEXT UNIQUE NOT NULL,                -- "/src/auth/auth.py"
    language        TEXT,                               -- "python"             
    file_hash       TEXT,                                -- hash of the file content
    line_count      INTEGER,                             -- number of lines in the file
    last_git_modified   TEXT,                            -- last time the file was modified
    last_git_commit_hash TEXT                            -- last commit hash that modified the file
);

