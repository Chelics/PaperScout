from __future__ import annotations

import os
from pathlib import Path

from .tools.skill_loader import _loader

_DIR = Path(__file__).parent / "prompts"


def _normalize_lang(value: str) -> str:
    v = value.strip().lower()
    if v in {"zh", "zh-cn", "zh_hans", "cn", "chinese"}:
        return "zh"
    if v in {"en", "en-us", "english"}:
        return "en"
    return v


def _normalize_mode(value: str) -> str:
    v = value.strip().lower()
    if v in {"survey", "research", "review"}:
        return "survey"
    if v in {"trending", "fresh", "recent", "new"}:
        return "trending"
    return v


def build_system_prompt(report_mode: str | None = None, mode: str | None = None) -> str:
    report_mode_norm = (report_mode or os.environ.get("PAPERSCOUT_REPORT_MODE", "strict")).strip().lower()
    if report_mode_norm not in {"strict", "light"}:
        report_mode_norm = "strict"

    mode_norm = _normalize_mode(mode or os.environ.get("PAPERSCOUT_MODE", "survey"))
    if mode_norm not in {"survey", "trending"}:
        mode_norm = "survey"

    report_lang_raw = os.environ.get("PAPERSCOUT_REPORT_LANG")
    if report_lang_raw:
        report_lang = _normalize_lang(report_lang_raw)
    else:
        contrib_lang = _normalize_lang(os.environ.get("PAPERSCOUT_CONTRIB_LANG", "zh"))
        report_lang = "zh" if contrib_lang == "zh" else "en"

    if report_lang == "zh":
        language_instruction = (
            "Language: Except for paper titles and metadata lines (Authors/Published/arXiv/Categories/Type), "
            "write all report content in Chinese (简体中文). Keep section headings and metadata labels exactly "
            "as in the report template."
        )
    else:
        language_instruction = (
            "Language: Write all report content in English. Keep section headings and metadata labels exactly "
            "as in the report template."
        )

    evidence_instruction = (
        "Evidence constraint: For Field Overview & Connections and Key Themes, every claim must explicitly cite either "
        "(a) a keyword from a paper title in this report, (b) a paper category label (e.g., cs.IR), or "
        "(c) an abstract cue present in the tool-provided abstract snippet. "
        "If you cannot cite such evidence, use cautious language (may/might) or omit the claim."
    )

    core_guidelines = (
        "Do not invent paper titles, authors, or links. Only cite papers returned by the search tool.\n"
        "Do not output any preface, planning notes, or tool traces. Output only the final Markdown report.\n"
        "Deduplicate by arxiv_url, and never list the same paper twice.\n"
        "If the report requires a section but you lack evidence, keep it brief and cautious rather than guessing."
    )

    if mode_norm == "survey":
        mode_instruction = (
            "Mode profile: Survey.\n"
            "- Goal: comprehensive understanding (landscape + paradigms + representative work).\n"
            "- Requirement: include at least one foundational/seminal angle for method-family topics (e.g., canonical names, "
            "aliases, or seminal terms such as DDPM / score-based / latent diffusion for diffusion topics).\n"
            "- Selection: prioritize relevance and representativeness; include surveys/overviews when available.\n"
        )
    else:
        mode_instruction = (
            "Mode profile: Trending.\n"
            "- Goal: recent developments and emerging directions.\n"
            "- Requirement: use search_arxiv sort_by=submittedDate or lastUpdatedDate for at least one query angle.\n"
            "- Selection: prioritize recency first, then relevance; avoid claiming historical lineage beyond abstract evidence.\n"
        )

    if report_mode_norm == "light":
        report_mode_instructions = (
            "When given a research topic:\n"
            "1. Call load_skill(\"search_strategy\") to plan your search approach.\n"
            "2. Following the search strategy, decompose the topic and run 2-4 targeted search_arxiv calls from different angles.\n"
            "3. Deduplicate results by arxiv_url and select the most relevant unique papers up to the requested limit.\n"
            "4. Generate a concise Markdown report. Keep it short and readable. You may omit Research Lineage, Key Themes, "
            "and Suggested Next Searches if they would be speculative.\n"
        )
    else:
        report_mode_instructions = (
            "When given a research topic:\n"
            "1. Call load_skill(\"search_strategy\") to plan your search approach.\n"
            "2. Call load_skill(\"report\") to load the report format instructions.\n"
            "3. Following the search strategy, decompose the topic and run 2-4 targeted search_arxiv calls from different angles.\n"
            "4. Deduplicate results by arxiv_url and select the most relevant unique papers up to the requested limit.\n"
            "5. Generate the Markdown report following the report skill instructions.\n"
        )

    return (
        (_DIR / "system.md")
        .read_text(encoding="utf-8")
        .replace("{skills_list}", _loader.get_descriptions())
        .replace("{report_mode_instructions}", report_mode_instructions)
        .replace("{mode_instruction}", mode_instruction)
        .replace("{core_guidelines}", core_guidelines)
        .replace("{language_instruction}", language_instruction)
        .replace("{evidence_instruction}", evidence_instruction)
    )


SYSTEM_PROMPT = build_system_prompt()
