from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from paperscout.tools import arxiv as arxiv_module


@pytest.fixture(autouse=True)
def clear_cache():
    arxiv_module._arxiv_result_cache.clear()
    yield
    arxiv_module._arxiv_result_cache.clear()


class _Author:
    def __init__(self, name: str):
        self.name = name


class _Paper:
    def __init__(self, title: str, idx: int):
        self.title = title
        self.authors = [_Author("Test Author")]
        self.published = datetime(2023, 1, 1)
        self.updated = datetime(2023, 1, 2)
        self.entry_id = f"http://arxiv.org/abs/2301.{idx:05d}v1"
        self.summary = "This is a test abstract about machine learning."
        self.primary_category = "cs.AI"
        self.categories = ["cs.AI", "cs.LG"]


class _SearchStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _ClientStub:
    calls = 0
    papers: list[_Paper] = []

    def results(self, search):
        _ClientStub.calls += 1
        return list(_ClientStub.papers)


def _patch_network(monkeypatch, papers: list[_Paper]) -> None:
    _ClientStub.calls = 0
    _ClientStub.papers = papers
    monkeypatch.setattr(arxiv_module.arxiv_lib, "Client", lambda: _ClientStub())
    monkeypatch.setattr(arxiv_module.arxiv_lib, "Search", _SearchStub)


def test_cache_key_ignores_query_edge_whitespace():
    assert arxiv_module._cache_key(" query ", "relevance") == arxiv_module._cache_key("query", "relevance")


def test_same_query_sort_hits_cache_on_second_call(monkeypatch):
    _patch_network(monkeypatch, [_Paper("Paper A", 1)])
    payload = {"query": "diffusion", "max_results": 1, "sort_by": "relevance"}

    first = json.loads(arxiv_module._execute(payload))
    second = json.loads(arxiv_module._execute(payload))

    assert first.get("cached") is not True
    assert second.get("cached") is True
    assert _ClientStub.calls == 1


def test_smaller_max_results_uses_cached_slice(monkeypatch):
    _patch_network(monkeypatch, [_Paper(f"Paper {i}", i) for i in range(8)])
    first = json.loads(arxiv_module._execute({"query": "vision", "max_results": 8, "sort_by": "relevance"}))
    second = json.loads(arxiv_module._execute({"query": "vision", "max_results": 3, "sort_by": "relevance"}))

    assert len(first["results"]) == 8
    assert second.get("cached") is True
    assert len(second["results"]) == 3
    assert _ClientStub.calls == 1


def test_larger_max_results_than_cached_refetches(monkeypatch):
    _patch_network(monkeypatch, [_Paper(f"Paper {i}", i) for i in range(3)])
    json.loads(arxiv_module._execute({"query": "nlp", "max_results": 3, "sort_by": "relevance"}))
    _patch_network(monkeypatch, [_Paper(f"Paper {i}", i) for i in range(7)])
    second = json.loads(arxiv_module._execute({"query": "nlp", "max_results": 7, "sort_by": "relevance"}))

    assert second.get("cached") is not True
    assert len(second["results"]) == 7
    assert _ClientStub.calls == 1


def test_different_sort_by_does_not_share_cache(monkeypatch):
    _patch_network(monkeypatch, [_Paper("Paper A", 1)])
    json.loads(arxiv_module._execute({"query": "ir", "max_results": 5, "sort_by": "relevance"}))
    json.loads(arxiv_module._execute({"query": "ir", "max_results": 5, "sort_by": "submittedDate"}))

    assert _ClientStub.calls == 2


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PAPERSCOUT_CACHE_REQUESTS", "0")
    _patch_network(monkeypatch, [_Paper("Paper A", 1)])
    first = json.loads(arxiv_module._execute({"query": "db", "max_results": 5, "sort_by": "relevance"}))
    second = json.loads(arxiv_module._execute({"query": "db", "max_results": 5, "sort_by": "relevance"}))

    assert first.get("cached") is not True
    assert second.get("cached") is not True
    assert _ClientStub.calls == 2
