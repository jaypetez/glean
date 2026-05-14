from __future__ import annotations

from glean.logging import get_logger

logger = get_logger(__name__)

_SUSPICIOUS = (
    "ignore previous",
    "ignore all previous",
    "ignore all instructions",
    "system:",
    "assistant:",
    "you are now",
    "<script>",
    "<iframe>",
    "javascript:",
)


def filter_llm_output(text: str, *, max_len: int = 1000) -> str:
    text = text[:max_len]
    lower = text.lower()
    hits = [s for s in _SUSPICIOUS if s in lower]
    if hits:
        logger.warning("llm_output_filtered", phrases=hits)
        return "[output filtered: suspected prompt injection]"
    return text
