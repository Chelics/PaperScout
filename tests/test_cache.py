from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class _PaperStub:
    def __init__(self, arxiv_id: str):
        self.entry_id = f"http://arxiv.org/abs/{arxiv_id}v1"


class _PapersScoutCacheInit:
    _initialized = False


def test_normalize_arxiv_id_full_url():
    from paperscout.cache import _normalize_arxiv_id

    assert _normalize_arxiv_id("http://arxiv.org/abs/2301.00001v1") == "2301.00001"
    assert _normalize_arxiv_id("https://arxiv.org/abs/2403.00099") == "2403.00099"
    assert _normalize_arxiv_id("2301.00001v3") == "2301.00001"
    assert _normalize_arxiv_id("  2301.00001  ") == "2301.00001"


class TestCacheDisabled:
    def test_cache_disabled_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "0")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        result = cache_module.get_cached_search("any_key")
        assert result is None


class TestSearchCache:
    def test_set_and_get_search_cache(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        cache_module.set_cached_search("diffusion::relevance", ["2301.00001", "2302.00002"], 2, 3600)
        result = cache_module.get_cached_search("diffusion::relevance")

        assert result is not None
        ids, total = result
        assert ids == ["2301.00001", "2302.00002"]
        assert total == 2

    def test_search_cache_expired(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        cache_module.set_cached_search("query::relevance", ["2301.00001"], 1, ttl_seconds=-1)
        result = cache_module.get_cached_search("query::relevance")

        assert result is None

    def test_search_cache_miss(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        result = cache_module.get_cached_search("nonexistent_key::relevance")
        assert result is None


class TestPaperCache:
    def test_set_and_get_paper(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        meta = {
            "title": "Test Paper",
            "abstract": "Test abstract",
            "authors": ["Author A", "Author B"],
            "published": "2023-01-01",
            "updated": "2023-01-02",
            "primary_category": "cs.AI",
            "categories": ["cs.AI", "cs.LG"],
        }
        cache_module.set_paper("2301.00001", meta, 3600)
        result = cache_module.get_paper("2301.00001")

        assert result is not None
        assert result["title"] == "Test Paper"
        assert result["abstract"] == "Test abstract"
        assert result["authors"] == ["Author A", "Author B"]

    def test_paper_cache_expired(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        cache_module.set_paper("2301.00001", {"title": "Old Paper"}, ttl_seconds=-1)
        result = cache_module.get_paper("2301.00001")
        assert result is None

    def test_paper_cache_miss(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        result = cache_module.get_paper("nonexistent.id")
        assert result is None

    def test_set_papers_batch(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        papers = [
            {
                "arxiv_url": "http://arxiv.org/abs/2301.00001v1",
                "title": "Paper One",
                "abstract": "Abstract one",
                "authors": ["Author A"],
                "published": "2023-01-01",
                "updated": "2023-01-02",
                "primary_category": "cs.AI",
                "categories": ["cs.AI"],
            },
            {
                "arxiv_url": "http://arxiv.org/abs/2302.00002v1",
                "title": "Paper Two",
                "abstract": "Abstract two",
                "authors": ["Author B"],
                "published": "2023-02-01",
                "updated": "2023-02-02",
                "primary_category": "cs.LG",
                "categories": ["cs.LG"],
            },
        ]
        cache_module.set_papers(papers, 3600)

        p1 = cache_module.get_paper("2301.00001")
        p2 = cache_module.get_paper("2302.00002")
        assert p1 is not None and p1["title"] == "Paper One"
        assert p2 is not None and p2["title"] == "Paper Two"

    def test_get_papers_batch(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        cache_module._connection = None

        papers = [
            {
                "arxiv_url": "http://arxiv.org/abs/2301.00001v1",
                "title": "Paper One",
                "abstract": "Abstract one",
                "authors": [],
                "published": "2023-01-01",
                "updated": "2023-01-02",
                "primary_category": "cs.AI",
                "categories": [],
            },
        ]
        cache_module.set_papers(papers, 3600)

        result = cache_module.get_papers(["2301.00001", "nonexistent.id"])
        assert len(result) == 1
        assert "2301.00001" in result
        assert "nonexistent.id" not in result


class TestPurgeExpired:
    def test_purge_expired(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PAPERSCOUT_ENABLE_DB_CACHE", "1")
        monkeypatch.setenv("PAPERSCOUT_DB_PATH", str(tmp_path / "test.db"))

        from paperscout import cache as cache_module
        import time

        cache_module._connection = None

        cache_module.set_cached_search("old_query::relevance", ["2301.00001"], 1, ttl_seconds=1)
        cache_module.set_paper("old.paper", {"title": "Old"}, ttl_seconds=1)
        cache_module.set_cached_search("fresh_query::relevance", ["2302.00002"], 1, 86400)
        cache_module.set_paper("fresh.paper", {"title": "Fresh"}, ttl_seconds=86400)

        time.sleep(2)

        purged = cache_module.purge_expired()

        assert purged >= 2
        assert cache_module.get_cached_search("old_query::relevance") is None
        assert cache_module.get_paper("old.paper") is None
        assert cache_module.get_cached_search("fresh_query::relevance") is not None
        assert cache_module.get_paper("fresh.paper") is not None
