from __future__ import annotations

import json
import os
import re
from datetime import date

import anthropic
import click

from .prompts import build_system_prompt
from .tools import dispatch, get_all_tools, load_all

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_ITERATIONS = 15


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


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _compact_arxiv_tool_result(raw: str, tool_input: dict) -> str:
    try:
        data = json.loads(raw)
    except Exception:
        return raw

    if isinstance(data, dict) and data.get("_paperscout_compact") is True:
        return raw

    query = tool_input.get("query")
    sort_by = tool_input.get("sort_by", "relevance")
    abstract_chars = _env_int("PAPERSCOUT_ARXIV_ABSTRACT_CHARS", 300)

    results = []
    for paper in (data.get("results") or []) if isinstance(data, dict) else []:
        if not isinstance(paper, dict):
            continue
        abstract = paper.get("abstract", "") or ""
        results.append({
            "title": paper.get("title", ""),
            "authors": paper.get("authors", [])[:5],
            "published": paper.get("published", ""),
            "arxiv_url": paper.get("arxiv_url", ""),
            "abstract": abstract[:abstract_chars],
            "primary_category": paper.get("primary_category", ""),
        })

    compact = {
        "_paperscout_compact": True,
        "query": query,
        "sort_by": sort_by,
        "total_found": data.get("total_found") if isinstance(data, dict) else None,
        "message": data.get("message") if isinstance(data, dict) else None,
        "results": results,
    }
    return json.dumps(compact, ensure_ascii=False)


def _micro_compact_messages(messages: list[dict]) -> None:
    keep_last_group = _env_bool("PAPERSCOUT_MICRO_COMPACT_KEEP_LAST", True)
    enabled = _env_bool("PAPERSCOUT_MICRO_COMPACT", True)
    if not enabled:
        return

    tool_use_by_id: dict[str, dict] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if getattr(block, "type", None) == "tool_use":
                tool_use_by_id[getattr(block, "id")] = {
                    "name": getattr(block, "name"),
                    "input": getattr(block, "input", {}),
                }

    last_tool_group_idx = None
    if keep_last_group:
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                last_tool_group_idx = i
                break

    for i, msg in enumerate(messages):
        if last_tool_group_idx is not None and i >= last_tool_group_idx:
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        changed = False
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = block.get("tool_use_id")
            meta = tool_use_by_id.get(tool_use_id or "")
            if not meta:
                continue
            name = meta.get("name")
            if name == "load_skill":
                if isinstance(block.get("content"), str) and len(block.get("content", "")) > 200:
                    skill_name = (meta.get("input") or {}).get("name", "")
                    block["content"] = f"(skill '{skill_name}' loaded; content elided)"
                    changed = True
            elif name == "search_arxiv":
                if isinstance(block.get("content"), str):
                    block["content"] = _compact_arxiv_tool_result(block["content"], meta.get("input") or {})
                    changed = True
        if changed:
            msg["content"] = content


def _normalize_mode(value: str | None) -> str:
    if not value:
        return "survey"
    v = value.strip().lower()
    if v in {"survey", "research", "review"}:
        return "survey"
    if v in {"trending", "fresh", "recent", "new"}:
        return "trending"
    return v


def _should_enforce_diffusion_foundational(topic: str) -> bool:
    t = topic.lower()
    return ("diffusion" in t) and any(k in t for k in ["image", "images", "text-to-image", "t2i"])


def _has_foundational_diffusion_query(arxiv_calls: list[dict]) -> bool:
    terms = [
        "denoising diffusion probabilistic model",
        "ddpm",
        "score-based",
        "score based",
        "latent diffusion",
    ]
    for call in arxiv_calls:
        q = str(call.get("query", "")).lower()
        if any(term in q for term in terms):
            return True
    return False


def run_agent(
    topic: str,
    limit: int,
    verbose: bool,
    max_iterations: int | None = None,
    report_mode: str | None = None,
    mode: str | None = None,
) -> tuple:
    load_all()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file or environment."
        )

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if max_iterations is None:
        max_iterations = _env_int("PAPERSCOUT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
    today = date.today().strftime("%Y-%m-%d")
    mode_norm = _normalize_mode(mode or os.environ.get("PAPERSCOUT_MODE"))
    system_prompt = build_system_prompt(report_mode=report_mode, mode=mode_norm)
    messages = [
        {
            "role": "user",
            "content": (
                f"Research topic: {topic}\n"
                f"Requested number of papers: {limit}\n"
                f"Today's date: {today}\n\n"
                "Please search for relevant papers and produce a Markdown report."
            ),
        }
    ]

    # Collect raw paper data from search tool results for BibTeX export.
    # Keyed by arxiv_url to deduplicate across multiple search calls.
    collected_papers: dict = {}

    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0
    arxiv_calls: list[dict] = []
    enforcements_sent: set[str] = set()

    for _ in range(max_iterations):
        _micro_compact_messages(messages)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=get_all_tools(),
            messages=messages,
        )

        iterations += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            total_input_tokens += getattr(usage, "input_tokens", 0) or 0
            total_output_tokens += getattr(usage, "output_tokens", 0) or 0

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    stats = {
                        "iterations": iterations,
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "model": model,
                    }
                    return block.text, list(collected_papers.values()), stats
            raise RuntimeError("Agent finished without producing a text report.")

        if verbose:
            click.echo(
                f"[tokens] input={response.usage.input_tokens} "
                f"output={response.usage.output_tokens}",
                err=True,
            )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if verbose:
                        click.echo(f"[tool] {block.name}({block.input})", err=True)
                    result = dispatch(block.name, block.input)
                    if block.name == "search_arxiv":
                        arxiv_calls.append({
                            "query": block.input.get("query"),
                            "sort_by": block.input.get("sort_by", "relevance"),
                        })
                        try:
                            data = json.loads(result)
                            if verbose and isinstance(data, dict):
                                query = block.input.get("query", "")
                                sort_by = block.input.get("sort_by", "relevance")
                                results_count = len(data.get("results", []) or [])
                                source = "cache-hit" if data.get("cached") is True else "network"
                                click.echo(
                                    f"[search] source={source} sort_by={sort_by} results={results_count} query={query!r}",
                                    err=True,
                                )
                            for paper in data.get("results", []):
                                url = paper.get("arxiv_url", "")
                                if url and url not in collected_papers:
                                    collected_papers[url] = paper
                        except (json.JSONDecodeError, AttributeError):
                            pass
                        if _env_bool("PAPERSCOUT_MICRO_COMPACT", True):
                            result = _compact_arxiv_tool_result(result, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

            enforcement_lines: list[str] = []
            if mode_norm == "trending":
                has_recent_sorted = any(
                    c.get("sort_by") in {"submittedDate", "lastUpdatedDate"} for c in arxiv_calls
                )
                if not has_recent_sorted and "trending_recent_sort" not in enforcements_sent:
                    enforcement_lines.append(
                        "Mode enforcement (Trending): you must call search_arxiv at least once with sort_by=submittedDate "
                        "or sort_by=lastUpdatedDate. Do this next with a broad abs: query derived from the topic."
                    )
                    enforcements_sent.add("trending_recent_sort")

            if mode_norm == "survey" and _should_enforce_diffusion_foundational(topic):
                if not _has_foundational_diffusion_query(arxiv_calls) and "survey_foundational_diffusion" not in enforcements_sent:
                    enforcement_lines.append(
                        "Mode enforcement (Survey): include at least one foundational/seminal search angle for diffusion models. "
                        "Do one of these next: "
                        "`ti:denoising diffusion probabilistic model` OR `abs:score-based generative model` OR `ti:latent diffusion`."
                    )
                    enforcements_sent.add("survey_foundational_diffusion")

            if enforcement_lines:
                messages.append({"role": "user", "content": "\n".join(enforcement_lines)})
            continue

        raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")

    raise RuntimeError(
        f"Agent did not complete within {max_iterations} iterations. "
        "Try a more specific topic."
    )
