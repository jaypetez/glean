"""Typed exception hierarchy for glean.

All glean-raised exceptions inherit from GleanError so callers can catch
the whole family with one except. Specific subclasses let callers
differentiate by failure mode.
"""

from __future__ import annotations


class GleanError(Exception):
    """Base for all glean-raised errors."""


class ConfigError(GleanError):
    """Invalid or missing configuration."""


class FeedConfigError(ConfigError):
    """Per-feed config invalid (bad schedule, missing source, etc.)."""


class SourceError(GleanError):
    """A source plugin failed to fetch."""


class SourceTimeoutError(SourceError):
    """Source request exceeded its timeout budget."""


class SourceFetchError(SourceError):
    """Source returned an HTTP error or unparseable payload."""


class SinkError(GleanError):
    """A sink plugin failed to deliver."""


class SinkRateLimitError(SinkError):
    """Sink rejected with 429."""


class LLMError(GleanError):
    """LLM provider call failed."""


class LLMRateLimitError(LLMError):
    """LLM provider returned 429."""


class LLMOutputInvalidError(LLMError):
    """LLM returned text that didn't match the requested schema/format."""


class StateError(GleanError):
    """SQLite store failure."""


class SecurityError(GleanError, ValueError):
    """Security boundary violation (SSRF block, prompt injection, etc.)."""
