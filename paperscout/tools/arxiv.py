from __future__ import annotations

import json
import os
import random
import time
from typing import Any

import arxiv as arxiv_lib

from . import register

_SCHEMA = {
    "name": "search_arxiv",
    "description": (
        "Search arXiv for academic papers matching a query. "
        "Returns paper titles, authors, abstracts, publication dates, and arXiv URLs. "
        "Call multiple times with different queries to get broader or more specific results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The search query. Supports arXiv-style prefixes: "
                    "ti: (title), abs: (abstract), au: (author). "
                    "Example: 'ti:diffusion models image generation'"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 10,
            },
            "sort_by": {
                "type": "string",
                "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                "description": "How to sort results. Default is relevance.",
                "default": "relevance",
            },
        },
        "required": ["query"],
    },
}

_SORT_MAP = {
    "relevance": arxiv_lib.SortCriterion.Relevance,
    "lastUpdatedDate": arxiv_lib.SortCriterion.LastUpdatedDate,
    "submittedDate": arxiv_lib.SortCriterion.SubmittedDate,
}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _is_retryable_error(e: Exception) -> bool:
    name = type(e).__name__.lower()
    if any(k in name for k in ["timeout", "connection", "temporar", "ratelimit"]):
        return True
    if isinstance(e, OSError):
        return True

    msg = str(e).lower()
    if any(k in msg for k in ["timed out", "timeout", "connection", "reset by peer", "temporar", "503", "502", "504"]):
        return True

    try:
        import requests  # type: ignore

        if isinstance(e, requests.exceptions.RequestException):
            return True
    except Exception:
        pass

    return False


def _sleep_backoff(attempt: int, base_seconds: float) -> None:
    delay = base_seconds * (2**attempt)
    delay = min(delay, 4.0)
    delay += random.uniform(0, delay * 0.2)
    time.sleep(delay)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _execute(tool_input: dict) -> str:
    query = tool_input["query"]
    max_results = tool_input.get("max_results", 10)
    sort_by = tool_input.get("sort_by", "relevance")

    max_retries = _env_int("PAPERSCOUT_ARXIV_MAX_RETRIES", 2)
    backoff_base_seconds = _env_float("PAPERSCOUT_ARXIV_BACKOFF_BASE_SECONDS", 0.5)
    venue_hints_enabled = _env_bool("PAPERSCOUT_VENUE_HINTS", False)

    _venue_match: Any = None
    if venue_hints_enabled:
        try:
            from paperscout.venues import match_paper_venues
            _venue_match = match_paper_venues
        except Exception:
            pass

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            client = arxiv_lib.Client()
            search = arxiv_lib.Search(
                query=query,
                max_results=max_results,
                sort_by=_SORT_MAP.get(sort_by, arxiv_lib.SortCriterion.Relevance),
            )
            results = []
            for paper in client.results(search):
                paper_dict = {
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors[:5]],
                    "published": paper.published.strftime("%Y-%m-%d"),
                    "updated": paper.updated.strftime("%Y-%m-%d"),
                    "arxiv_url": paper.entry_id,
                    "abstract": paper.summary[:800],
                    "primary_category": paper.primary_category,
                    "categories": paper.categories[:3],
                }
                if _venue_match is not None:
                    matched = _venue_match(paper.title, paper.summary[:800])
                    if matched:
                        paper_dict["venue_hints"] = [
                            {"short_name": v.short_name, "ccf_level": v.ccf_level}
                            for v in matched
                        ]
                results.append(paper_dict)

            if not results:
                return json.dumps({
                    "results": [],
                    "message": f"No papers found for query: '{query}'. Try different keywords.",
                })

            return json.dumps({"results": results, "total_found": len(results)})

        except Exception as e:
            last_error = e
            if attempt >= max_retries or not _is_retryable_error(e):
                return json.dumps({"error": str(e), "error_type": type(e).__name__, "results": []})
            _sleep_backoff(attempt=attempt, base_seconds=backoff_base_seconds)

    if last_error is None:
        return json.dumps({"error": "Unknown error", "results": []})
    return json.dumps({"error": str(last_error), "error_type": type(last_error).__name__, "results": []})


register(_SCHEMA, _execute)
