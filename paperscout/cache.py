from __future__ import annotations

import json
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DB_PATH = Path(os.environ.get("PAPERSCOUT_DB_PATH", ".paperscout/cache.db"))
_ENABLE_DB = os.environ.get("PAPERSCOUT_ENABLE_DB_CACHE", "1") == "1"
_SEARCH_TTL = int(os.environ.get("PAPERSCOUT_SEARCH_CACHE_TTL", "86400"))
_PAPER_TTL = int(os.environ.get("PAPERSCOUT_PAPER_CACHE_TTL", "2592000"))

_connection: sqlite3.Connection | None = None


def _now() -> int:
    return int(time.time())


def _get_conn() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        _init_schema(conn)
        _migrate_schema(conn)
        _connection = conn
    return _connection


_SCHEMA_SQL = Path(__file__).parent / "data" / "schema.sql"


def _init_schema(conn: sqlite3.Connection) -> None:
    if _SCHEMA_SQL.exists():
        with open(_SCHEMA_SQL, encoding="utf-8") as f:
            conn.executescript(f.read())
    else:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS search_cache (
                cache_key    TEXT PRIMARY KEY,
                result_ids   TEXT NOT NULL,
                total_found  INTEGER,
                fetched_at   INTEGER NOT NULL,
                ttl_seconds  INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id         TEXT PRIMARY KEY,
                title            TEXT,
                abstract         TEXT,
                authors_json     TEXT,
                published        TEXT,
                updated          TEXT,
                primary_category TEXT,
                categories_json  TEXT,
                fetched_at       INTEGER NOT NULL,
                ttl_seconds      INTEGER NOT NULL,
                domain          TEXT DEFAULT '',
                use_count      INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_papers_fetched_at ON papers(fetched_at);
            CREATE INDEX IF NOT EXISTS idx_search_fetched_at ON search_cache(fetched_at);
        """)


@contextmanager
def _cursor():
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA table_info(papers)")
        columns = {row[1] for row in cur.fetchall()}
        if "domain" not in columns:
            cur.execute("ALTER TABLE papers ADD COLUMN domain TEXT DEFAULT ''")
        if "use_count" not in columns:
            cur.execute("ALTER TABLE papers ADD COLUMN use_count INTEGER DEFAULT 0")

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers_notes'")
        if not cur.fetchone():
            conn.executescript("""
                CREATE TABLE papers_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    arxiv_id TEXT NOT NULL,
                    note_type TEXT NOT NULL CHECK(note_type IN ('llm', 'user')),
                    content TEXT NOT NULL,
                    domain TEXT DEFAULT '',
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (arxiv_id) REFERENCES papers(arxiv_id)
                );
                CREATE INDEX IF NOT EXISTS idx_notes_arxiv_id ON papers_notes(arxiv_id);
                CREATE INDEX IF NOT EXISTS idx_notes_domain ON papers_notes(domain);
            """)

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_summaries'")
        if not cur.fetchone():
            conn.executescript("""
                CREATE TABLE memory_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    from_turn INTEGER NOT NULL,
                    to_turn INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_session ON memory_summaries(session_key);
            """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _is_expired(fetched_at: int, ttl_seconds: int) -> bool:
    return (_now() - fetched_at) >= ttl_seconds


def _may_purge() -> None:
    if random.random() < 0.1:
        purge_expired()


# ── Search cache ──────────────────────────────────────────────────────────────

def get_cached_search(cache_key: str) -> tuple[list[str], int] | None:
    if not _ENABLE_DB:
        return None
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT result_ids, total_found, fetched_at, ttl_seconds FROM search_cache WHERE cache_key=?",
                (cache_key,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        result_ids, total_found, fetched_at, ttl_seconds = row
        if _is_expired(fetched_at, ttl_seconds):
            with _cursor() as cur:
                cur.execute("DELETE FROM search_cache WHERE cache_key=?", (cache_key,))
            return None
        return (json.loads(result_ids), total_found)
    except Exception:
        return None


def set_cached_search(cache_key: str, arxiv_ids: list[str], total_found: int, ttl_seconds: int = _SEARCH_TTL) -> None:
    if not _ENABLE_DB:
        return
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO search_cache (cache_key, result_ids, total_found, fetched_at, ttl_seconds) VALUES (?, ?, ?, ?, ?)",
                (cache_key, json.dumps(arxiv_ids), total_found, _now(), ttl_seconds),
            )
        _may_purge()
    except Exception:
        pass


# ── Paper cache ───────────────────────────────────────────────────────────────

def get_paper(arxiv_id: str) -> dict[str, Any] | None:
    if not _ENABLE_DB:
        return None
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT title, abstract, authors_json, published, updated, primary_category, categories_json, fetched_at, ttl_seconds FROM papers WHERE arxiv_id=?",
                (arxiv_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        title, abstract, authors_json, published, updated, primary_category, categories_json, fetched_at, ttl_seconds = row
        if _is_expired(fetched_at, ttl_seconds):
            with _cursor() as cur:
                cur.execute("DELETE FROM papers WHERE arxiv_id=?", (arxiv_id,))
            return None
        return {
            "title": title,
            "abstract": abstract,
            "authors": json.loads(authors_json) if authors_json else [],
            "published": published,
            "updated": updated,
            "primary_category": primary_category,
            "categories": json.loads(categories_json) if categories_json else [],
        }
    except Exception:
        return None


def get_papers(arxiv_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not _ENABLE_DB or not arxiv_ids:
        return {}
    result: dict[str, dict[str, Any]] = {}
    try:
        with _cursor() as cur:
            placeholders = ",".join("?" * len(arxiv_ids))
            cur.execute(
                f"SELECT arxiv_id, title, abstract, authors_json, published, updated, primary_category, categories_json, fetched_at, ttl_seconds FROM papers WHERE arxiv_id IN ({placeholders})",
                arxiv_ids,
            )
            rows = cur.fetchall()
        now = _now()
        for row in rows:
            arxiv_id, title, abstract, authors_json, published, updated, primary_category, categories_json, fetched_at, ttl_seconds = row
            if _is_expired(fetched_at, ttl_seconds):
                with _cursor() as cur:
                    cur.execute("DELETE FROM papers WHERE arxiv_id=?", (arxiv_id,))
                continue
            result[arxiv_id] = {
                "title": title,
                "abstract": abstract,
                "authors": json.loads(authors_json) if authors_json else [],
                "published": published,
                "updated": updated,
                "primary_category": primary_category,
                "categories": json.loads(categories_json) if categories_json else [],
            }
    except Exception:
        pass
    return result


def set_paper(arxiv_id: str, meta: dict[str, Any], ttl_seconds: int = _PAPER_TTL) -> None:
    if not _ENABLE_DB:
        return
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO papers (arxiv_id, title, abstract, authors_json, published, updated, primary_category, categories_json, fetched_at, ttl_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    arxiv_id,
                    meta.get("title"),
                    meta.get("abstract"),
                    json.dumps(meta.get("authors", [])),
                    meta.get("published"),
                    meta.get("updated"),
                    meta.get("primary_category"),
                    json.dumps(meta.get("categories", [])),
                    _now(),
                    ttl_seconds,
                ),
            )
    except Exception:
        pass


def set_papers(papers: list[dict[str, Any]], ttl_seconds: int = _PAPER_TTL) -> None:
    if not _ENABLE_DB or not papers:
        return
    try:
        now = _now()
        rows = [
            (
                _normalize_arxiv_id(p.get("arxiv_url", "")),
                p.get("title"),
                p.get("abstract"),
                json.dumps(p.get("authors", [])),
                p.get("published"),
                p.get("updated"),
                p.get("primary_category"),
                json.dumps(p.get("categories", [])),
                now,
                ttl_seconds,
            )
            for p in papers
        ]
        with _cursor() as cur:
            cur.executemany(
                "INSERT OR REPLACE INTO papers (arxiv_id, title, abstract, authors_json, published, updated, primary_category, categories_json, fetched_at, ttl_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        _may_purge()
    except Exception:
        pass


# ── Utilities ────────────────────────────────────────────────────────────────

def _normalize_arxiv_id(url_or_id: str) -> str:
    import re
    m = re.search(r"abs/([0-9]+\.[0-9]+)", url_or_id)
    if m:
        return m.group(1)
    m = re.search(r"([0-9]+\.[0-9]+)", url_or_id)
    if m:
        return m.group(1)
    return url_or_id.strip()


def purge_expired() -> int:
    if not _ENABLE_DB:
        return 0
    total = 0
    try:
        now = _now()
        with _cursor() as cur:
            cur.execute("SELECT cache_key, fetched_at, ttl_seconds FROM search_cache")
            expired_keys = [row[0] for row in cur.fetchall() if _is_expired(row[1], row[2])]
            if expired_keys:
                placeholders = ",".join("?" * len(expired_keys))
                cur.execute(f"DELETE FROM search_cache WHERE cache_key IN ({placeholders})", expired_keys)
                total += len(expired_keys)
            cur.execute("SELECT arxiv_id, fetched_at, ttl_seconds FROM papers")
            expired_ids = [row[0] for row in cur.fetchall() if _is_expired(row[1], row[2])]
            if expired_ids:
                placeholders = ",".join("?" * len(expired_ids))
                cur.execute(f"DELETE FROM papers WHERE arxiv_id IN ({placeholders})", expired_ids)
                total += len(expired_ids)
    except Exception:
        pass
    return total


# ── Paper notes ───────────────────────────────────────────────────────────────

def add_paper_note(arxiv_id: str, note_type: str, content: str, domain: str = "") -> None:
    if not _ENABLE_DB:
        return
    if note_type not in ("llm", "user"):
        return
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO papers_notes (arxiv_id, note_type, content, domain, created_at) VALUES (?, ?, ?, ?, ?)",
                (arxiv_id, note_type, content, domain, _now()),
            )
    except Exception:
        pass


def get_paper_notes(arxiv_id: str) -> list[dict[str, Any]]:
    if not _ENABLE_DB:
        return []
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT id, note_type, content, domain, created_at FROM papers_notes WHERE arxiv_id=? ORDER BY created_at DESC",
                (arxiv_id,),
            )
            return [
                {
                    "id": row[0],
                    "note_type": row[1],
                    "content": row[2],
                    "domain": row[3],
                    "created_at": row[4],
                }
                for row in cur.fetchall()
            ]
    except Exception:
        return []


def get_notes_by_domain(domain: str) -> list[dict[str, Any]]:
    if not _ENABLE_DB:
        return []
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT arxiv_id, note_type, content, domain, created_at FROM papers_notes WHERE domain=? ORDER BY created_at DESC",
                (domain,),
            )
            return [
                {
                    "arxiv_id": row[0],
                    "note_type": row[1],
                    "content": row[2],
                    "domain": row[3],
                    "created_at": row[4],
                }
                for row in cur.fetchall()
            ]
    except Exception:
        return []


def search_notes(keyword: str, domain: str = "") -> list[dict[str, Any]]:
    if not _ENABLE_DB:
        return []
    try:
        with _cursor() as cur:
            if domain:
                cur.execute(
                    "SELECT arxiv_id, note_type, content, domain, created_at FROM papers_notes WHERE domain=? AND content LIKE ? ORDER BY created_at DESC",
                    (domain, f"%{keyword}%"),
                )
            else:
                cur.execute(
                    "SELECT arxiv_id, note_type, content, domain, created_at FROM papers_notes WHERE content LIKE ? ORDER BY created_at DESC",
                    (f"%{keyword}%",),
                )
            return [
                {
                    "arxiv_id": row[0],
                    "note_type": row[1],
                    "content": row[2],
                    "domain": row[3],
                    "created_at": row[4],
                }
                for row in cur.fetchall()
            ]
    except Exception:
        return []


# ── Memory summaries ───────────────────────────────────────────────────────────────

def add_memory_summary(session_key: str, summary: str, from_turn: int, to_turn: int) -> None:
    if not _ENABLE_DB:
        return
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO memory_summaries (session_key, summary, from_turn, to_turn, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_key, summary, from_turn, to_turn, _now()),
            )
    except Exception:
        pass


def get_memory_summary(session_key: str) -> str | None:
    if not _ENABLE_DB:
        return None
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT summary FROM memory_summaries WHERE session_key=? ORDER BY created_at DESC LIMIT 1",
                (session_key,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def get_memory_history(session_key: str) -> list[dict[str, Any]]:
    if not _ENABLE_DB:
        return []
    try:
        with _cursor() as cur:
            cur.execute(
                "SELECT id, summary, from_turn, to_turn, created_at FROM memory_summaries WHERE session_key=? ORDER BY from_turn ASC",
                (session_key,),
            )
            return [
                {
                    "id": row[0],
                    "summary": row[1],
                    "from_turn": row[2],
                    "to_turn": row[3],
                    "created_at": row[4],
                }
                for row in cur.fetchall()
            ]
    except Exception:
        return []


# ── Paper domain & use_count ──────────────────────────────────────────────────────────

def update_paper_domain(arxiv_id: str, domain: str) -> None:
    if not _ENABLE_DB:
        return
    try:
        with _cursor() as cur:
            cur.execute(
                "UPDATE papers SET domain=? WHERE arxiv_id=?",
                (domain, arxiv_id),
            )
    except Exception:
        pass


def increment_paper_use_count(arxiv_id: str) -> None:
    if not _ENABLE_DB:
        return
    try:
        with _cursor() as cur:
            cur.execute(
                "UPDATE papers SET use_count = use_count + 1 WHERE arxiv_id=?",
                (arxiv_id,),
            )
    except Exception:
        pass
