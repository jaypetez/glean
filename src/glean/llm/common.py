from __future__ import annotations

import re

from glean.sources.base import Item

_NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%?")
_WORD_SCORES = {
    "irrelevant": 0.0, "no": 0.0, "skip": 0.0, "drop": 0.0,
    "low": 0.2, "weak": 0.2,
    "medium": 0.5, "mid": 0.5, "neutral": 0.5,
    "high": 0.8, "strong": 0.8, "yes": 0.9, "relevant": 0.85,
    "very": 0.9, "critical": 1.0, "essential": 1.0,
}


def parse_score(raw: str) -> float:
    """Coerce model output to a float in [0, 1]. Lenient by design."""
    if not raw:
        return 0.0
    s = raw.strip().lower()

    if m := _NUM_RE.search(s):
        n = float(m.group(1))
        if "%" in s:
            n /= 100.0
        return max(0.0, min(1.0, n))

    for word, score in _WORD_SCORES.items():
        if word in s:
            return score

    return 0.0


def item_as_prompt_context(item: Item, *, max_chars: int = 2000) -> str:
    """Format an item for inclusion in an LLM prompt."""
    parts: list[str] = [f"TITLE: {item.title}"]
    if item.source_name:
        parts.append(f"SOURCE: {item.source_name}")
    if item.canonical_url:
        parts.append(f"URL: {item.canonical_url}")
    body = (item.body or item.summary or "").strip()
    if body:
        if len(body) > max_chars:
            body = body[:max_chars] + "…"
        parts.append(f"BODY:\n{body}")
    return "\n".join(parts)


def items_as_prompt_context(items: list[Item], *, max_chars: int = 6000) -> str:
    blocks: list[str] = []
    used = 0
    for i, item in enumerate(items, 1):
        snippet = (item.body or item.summary or "")[:400]
        block = f"[{i}] {item.title} — {item.source_name}\n{snippet}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
