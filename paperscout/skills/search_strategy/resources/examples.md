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
