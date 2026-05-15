---
title: Item Reference — glean
description: Field-by-field reference for the Item dataclass passed through the pipeline.
---

# Item Reference

This reference is for source authors and pipeline contributors who need the exact `Item` shape. `Item` is a frozen, slotted dataclass defined in `src/glean/sources/base.py`, and pipeline stages attach new data with `dataclasses.replace()`.

```python
@dataclass(frozen=True, slots=True)
class Item:
    """One piece of content surfaced by a Source."""

    canonical_url: str
    title: str
    body: str = ""
    summary: str | None = None
    source_type: str = ""
    source_name: str = ""
    published_at: datetime | None = None
    score: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    llm_summary: str | None = None
    relevance: float | None = None
    llm_key: str | None = None
    structured: dict[str, Any] = field(default_factory=dict)
```

| Field | Type | Filled by | Description |
|---|---|---|---|
| `canonical_url` | `str` | Source | URL used for the dedup hash; the state store hashes it with SHA-256. If empty, dedup falls back to `title + body[:512]`. |
| `title` | `str` | Source | Item title shown in rendered digests and LLM prompts. |
| `body` | `str` | Source | Main item content. Use plain text when possible because LLM prompts consume this field. |
| `summary` | `str \| None` | Source | Upstream-provided summary or excerpt before LLM processing. |
| `source_type` | `str` | Source | Plugin type, such as `rss`, `reddit`, or `search`. |
| `source_name` | `str` | Source | Human-readable source label, such as a feed title or configured name. |
| `published_at` | `datetime \| None` | Source | Publication or update timestamp when the upstream provides one. Use timezone-aware values when available. |
| `score` | `float \| None` | Source | Upstream score, rank, vote count, or confidence value before LLM ranking. |
| `raw` | `dict[str, Any]` | Source | Original upstream record for debugging or provider-specific prompts. Do not put secrets here. |
| `llm_summary` | `str \| None` | `summarize` stage | Per-item LLM summary. The renderer prefers this over `summary` when present. |
| `relevance` | `float \| None` | `rank` stage | `0.0`-`1.0` relevance score used for filtering and sorting. |
| `llm_key` | `str \| None` | Runner | Per-source LLM routing key when a source config overrides the feed LLM. Format matches the runner cache key. |
| `structured` | `dict[str, Any]` | `apply_skill` stage | Structured extraction output keyed by skill schema fields. Empty dict means no extraction output. |

## Mutation rule

Do not mutate an `Item` in place. Create a replacement instead:

```python
from dataclasses import replace

updated = replace(item, relevance=0.92)
```

Expected result:

```text
updated.relevance == 0.92
item.relevance is None
```
