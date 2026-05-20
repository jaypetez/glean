"""FP16 pack/unpack for embedding storage in SQLite BLOB columns."""

from __future__ import annotations

import struct


def pack_embedding(vec: list[float]) -> bytes:
    """Pack a float embedding into FP16 bytes (2 bytes per dim)."""
    return struct.pack(f"{len(vec)}e", *vec)


def unpack_embedding(data: bytes) -> list[float]:
    """Reverse of pack_embedding."""
    n = len(data) // 2
    return list(struct.unpack(f"{n}e", data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Returns 0.0 if either vector is all zeros."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))
