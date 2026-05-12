from __future__ import annotations

import pytest

from glean.llm.common import parse_score


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.7", 0.7),
        ("0.85", 0.85),
        ("1", 1.0),
        ("0", 0.0),
        ("70%", 0.7),
        ("Score: 0.42", 0.42),
        ("high", 0.8),
        ("relevant", 0.85),
        ("irrelevant", 0.0),
        ("", 0.0),
        ("totally garbage answer here", 0.0),
    ],
)
def test_parse_score(raw: str, expected: float) -> None:
    got = parse_score(raw)
    assert abs(got - expected) < 0.01, f"{raw!r} -> {got}"


def test_score_clamps_above_one() -> None:
    assert parse_score("2.5") == 1.0


def test_score_clamps_negative() -> None:
    assert parse_score("-0.3") == 0.0
