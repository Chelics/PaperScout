---
name: search_strategy
description: Plan multi-angle searches to get comprehensive, non-redundant paper coverage
tags: search, planning
---

## Why Multi-Angle Search

A single query misses papers that:
- Use different terminology for the same concept
- Belong to different paradigms that rarely cross-cite each other
- Don't mention the concept in their title (e.g. "Attention is All You Need" has no "transformer"; "P5" has no "recommendation")

Breaking a topic into 2-4 targeted queries from different angles gives broader and more accurate coverage.

## Step 0: Map the Topic

Before planning queries, answer two questions:

**1. What are the English terms for this concept?**
If the topic is in another language or uses informal shorthand, list all common English equivalents and synonym clusters. Different communities may use different names.

Example — "生成式推荐":
→ "generative recommendation", "LLM-based recommendation", "large language model recommender system", "generative retrieval recommendation"

**2. Does the topic span multiple paradigms?**
A paradigm split means distinct research communities with largely non-overlapping vocabulary and citation networks.

Example — "generative recommendation" spans 4 paradigms:
| Paradigm | Core vocabulary |
|----------|----------------|
| LLM as ranker | LLM reranking, scoring candidates |
| LLM as generator | item ID generation, generative retrieval |
| LLM as encoder | language model embeddings, collaborative filtering |
| RAG-based | retrieval augmented generation, recommendation |

→ Multi-paradigm: plan one query angle per paradigm.
→ Single paradigm (e.g. "diffusion models"): plan queries around terminology variants.

## Step 1: Choose Decomposition Strategy

**Strategy A — Terminology variants** (single paradigm, multiple names):
2-4 queries each targeting a different name for the same concept.
Best for: well-established fields with stable but varied terminology.

**Strategy B — Paradigm decomposition** (multi-paradigm topic):
One query angle per paradigm, each using that paradigm's specific vocabulary.
Best for: cross-cutting topics where different communities barely overlap.

Most topics benefit from a mix of both.

## Step 2: Build Targeted Queries

Use arXiv query syntax:
- `ti:term` — title only: high precision, fewer results
- `abs:term` — abstract: broader coverage
- `cat:cs.XX` — category filter: reduces noise for broad `abs:` queries
- Combined: `cat:cs.IR AND abs:large language model`

**Rule: every query plan must include at least one `abs:` query.**
Title-only queries miss papers with creative or branded titles. Use `abs:` (optionally with `cat:`) to capture them.

Typical pattern:
- `ti:` query for direct keyword matches in titles
- `abs:` or `cat: AND abs:` query for broader paradigm coverage

Foundational/seminal coverage (recommended for method-family topics):
- If the topic is a model family or well-known method class (e.g., diffusion models, transformers), include one dedicated query angle targeting seminal terms, canonical names, or widely-used aliases.
- This improves user expectation matching when they want both foundational and recent work.

## Step 3: Size Each Query

Given user limit N and number of planned queries Q:
- Set `max_results` per query to `max(5, ceil(N / Q) + 3)`
- Example: limit=10, 4 queries → max_results=6 each → ~24 candidates → pick top 10

## Step 4: Deduplicate and Select

After all searches:
- Compare `arxiv_url` across all results — this is the unique identifier
- Each paper appears only once, placed under the most relevant paradigm/angle
- Rank by relevance to the original topic and recency
- Select the top N unique papers for the report
- Record which paradigm/angle each selected paper belongs to — used for report grouping

## Examples

### Single-paradigm topic (terminology variants)

**Topic:** "diffusion models for image generation", limit=10

| Query | Search string | max_results |
|-------|---------------|-------------|
| 1 | `ti:diffusion model image generation` | 7 |
| 2 | `abs:score-based generative model image` | 7 |
| 3 | `ti:denoising diffusion probabilistic model` | 6 |
| 4 | `ti:latent diffusion` | 6 |

→ ~20 candidates, deduplicate, select top 10. Single paradigm → flat paper list in report.

### Multi-paradigm topic

**Topic:** "generative recommendation systems", limit=12

| Paradigm | Query | max_results |
|----------|-------|-------------|
| LLM as ranker | `cat:cs.IR AND abs:large language model reranking recommendation` | 6 |
| LLM as generator (title) | `ti:generative recommendation` | 6 |
| LLM as generator (broad) | `abs:item generation recommender system` | 5 |
| LLM as encoder | `cat:cs.IR AND abs:language model embedding collaborative filtering` | 5 |

→ ~22 candidates, deduplicate, select top 12. Multi-paradigm → group papers by paradigm in report.
