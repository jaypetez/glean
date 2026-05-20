"""Embedding provider abstraction for semantic operations.

Mirrors the LLMProvider Protocol but is scoped to single-text-to-vector
operations. Used by the semantic_dedup pipeline stage.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Produces dense vector embeddings for individual strings.

    Implementations must be stateless across calls (or manage their own
    connection pooling). Models should produce vectors of consistent
    dimensionality within a single instance.
    """

    name: ClassVar[str]
    model: str

    async def embed(self, text: str) -> list[float]:
        """Return the embedding for `text` as a list of floats."""
        pass

    async def aclose(self) -> None:
        """Release any held resources."""
        pass
