---
name: report
description: Generate a structured Markdown research report from arXiv search results
tags: output, formatting
---

The Markdown report must follow this exact structure:

# Research Report: {topic}

**Generated:** {current_date} | **Papers found:** {n}

## Summary

2-4 sentences giving an overview of the current research landscape on this topic based on the papers found.

## Papers

Use **one of the two layouts** below based on whether the topic spans multiple paradigms.

---

### Layout A — Single paradigm (flat list)

Use this when all papers belong to the same research paradigm or the topic has no clear paradigm split.

#### {number}. {Title}

- **Authors:** {author1}, {author2}, ... (et al. if more than 5)
- **Published:** {YYYY-MM-DD}
- **arXiv:** [{arxiv_id}]({full_arxiv_url})
- **Categories:** {categories}
- **Type:** one of: `Survey` | `Method` | `Empirical` | `Application`

**Contribution:** One sentence on the core novelty — what this paper proposes that prior work did not.

**Advance:** One sentence on how it differs from or improves upon existing approaches (e.g. faster, more accurate, fewer assumptions, new setting).

---

### Layout B — Multi-paradigm (grouped)

Use this when the search strategy identified distinct paradigms (e.g. "LLM as ranker" vs "LLM as generator"). Group papers under paradigm headers. Papers within a group share a common approach or vocabulary cluster.

### {Paradigm Name}

1-2 sentences explaining what this paradigm is and how it differs from the others.

#### {number}. {Title}

- **Authors:** {author1}, {author2}, ... (et al. if more than 5)
- **Published:** {YYYY-MM-DD}
- **arXiv:** [{arxiv_id}]({full_arxiv_url})
- **Categories:** {categories}
- **Type:** one of: `Survey` | `Method` | `Empirical` | `Application`

**Contribution:** One sentence on the core novelty — what this paper proposes that prior work did not.

**Advance:** One sentence on how it differs from or improves upon existing approaches (e.g. faster, more accurate, fewer assumptions, new setting).

*(repeat for each paradigm group)*

---

## Field Overview & Connections

Provide a domain-level overview and how this topic connects to adjacent areas. Focus on:
- What this field is trying to solve and why it matters (as reflected by the papers found)
- How the field relates to neighboring domains (e.g., IR / NLP / CV / systems), grounded in the paper categories and title/abstract keywords
- 3-6 bullet points or a short paragraph; keep it evidence-backed and non-speculative

- Evidence constraint: each claim must cite either a keyword from paper titles in this report, a paper category label (e.g., cs.IR), or an abstract cue present in the tool-provided abstract snippet. If you cannot cite such evidence, use cautious language ("may", "might") or omit the claim.

## Key Themes

A bulleted list of 3-6 recurring themes or trends observed across these papers.
- Evidence constraint: each theme must cite at least one supporting title keyword or abstract cue from papers in this report; otherwise phrase it cautiously or omit it.

## Suggested Next Searches

2-3 alternative search queries the user might try for deeper exploration.

---
IMPORTANT:
- Only include papers actually returned by the search tool. Never invent titles, authors, or links.
- arxiv_id format: XXXX.XXXXX (e.g. 2301.12345)
- full_arxiv_url: the complete URL from search results (e.g. https://arxiv.org/abs/2301.12345)
- Sort papers by relevance within each group (paradigm or flat list), most relevant first.
- Choose Layout A or B based on whether the search strategy used paradigm decomposition.
- For Contribution and Advance: if the abstract does not contain enough information to infer one of these, write "N/A" rather than guessing.
- Language: keep paper titles and metadata lines (Authors/Published/arXiv/Categories/Type) as-is; write all other content in Chinese (简体中文).
- For Type, use these signals:
  - `Survey` — abstract uses "we survey / overview / summarize the literature / provide a comprehensive review"
  - `Method` — abstract introduces a named technique, model, or framework ("we propose/introduce/present [Name]")
  - `Empirical` — abstract focuses on studying, analyzing, or benchmarking existing approaches without proposing a new one ("we study / analyze / benchmark / investigate / evaluate")
  - `Application` — abstract applies existing methods to a new domain or task ("we apply / adapt [existing method] to [domain/task]")
  - When a paper matches multiple types, pick the primary contribution.
