-- PaperScout Database Schema
-- Version: 1.0

-- Search cache: temporary search results
CREATE TABLE IF NOT EXISTS search_cache (
    cache_key    TEXT PRIMARY KEY,
    result_ids   TEXT NOT NULL,
    total_found  INTEGER,
    fetched_at   INTEGER NOT NULL,
    ttl_seconds  INTEGER NOT NULL
);

-- Papers cache: arXiv paper metadata (base columns)
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id          TEXT PRIMARY KEY,
    title            TEXT,
    abstract         TEXT,
    authors_json     TEXT,
    published       TEXT,
    updated         TEXT,
    primary_category TEXT,
    categories_json TEXT,
    fetched_at      INTEGER NOT NULL,
    ttl_seconds     INTEGER NOT NULL
);

-- Paper notes: LLM or user generated notes for papers
CREATE TABLE IF NOT EXISTS papers_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id    TEXT NOT NULL,
    note_type   TEXT NOT NULL CHECK(note_type IN ('llm', 'user')),
    content     TEXT NOT NULL,
    domain      TEXT DEFAULT '',
    created_at  INTEGER NOT NULL,
    FOREIGN KEY (arxiv_id) REFERENCES papers(arxiv_id)
);

-- Memory summaries: session context compression history
CREATE TABLE IF NOT EXISTS memory_summaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key    TEXT NOT NULL,
    summary        TEXT NOT NULL,
    from_turn      INTEGER NOT NULL,
    to_turn        INTEGER NOT NULL,
    created_at     INTEGER NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_papers_fetched_at ON papers(fetched_at);
CREATE INDEX IF NOT EXISTS idx_search_fetched_at ON search_cache(fetched_at);
CREATE INDEX IF NOT EXISTS idx_notes_arxiv_id ON papers_notes(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_notes_domain ON papers_notes(domain);
CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_summaries(session_key);