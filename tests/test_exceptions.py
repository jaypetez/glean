"""Smoke tests for the typed exception hierarchy."""

from __future__ import annotations

import pytest

from glean.exceptions import (
    ConfigError,
    FeedConfigError,
    GleanError,
    LLMError,
    LLMRateLimitError,
    SecurityError,
)


def test_all_inherit_from_glean_error() -> None:
    for cls in (ConfigError, FeedConfigError, LLMError, LLMRateLimitError, SecurityError):
        assert issubclass(cls, GleanError)


def test_subclass_specificity() -> None:
    assert issubclass(FeedConfigError, ConfigError)
    assert issubclass(LLMRateLimitError, LLMError)


def test_can_be_raised_and_caught() -> None:
    with pytest.raises(GleanError):
        raise SecurityError("test")


def test_llm_rate_limit_caught_as_llm_error() -> None:
    with pytest.raises(LLMError):
        raise LLMRateLimitError("test")
