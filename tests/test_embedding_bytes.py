from __future__ import annotations

import pytest

from glean.state.embedding_bytes import cosine_similarity, pack_embedding, unpack_embedding


def test_pack_and_unpack_round_trip_with_fp16_tolerance() -> None:
    original = [0.1, 0.5, -0.3]

    packed = pack_embedding(original)
    unpacked = unpack_embedding(packed)

    assert len(packed) == 6
    assert unpacked == pytest.approx(original, abs=0.001)


def test_cosine_similarity_for_identical_vectors() -> None:
    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_for_orthogonal_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_handles_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_similarity_returns_zero_for_different_lengths() -> None:
    assert cosine_similarity([1.0], [1.0, 0.0]) == pytest.approx(0.0)
