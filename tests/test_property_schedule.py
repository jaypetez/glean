from __future__ import annotations

from contextlib import suppress

from hypothesis import given, settings
from hypothesis import strategies as st

from glean.config.schedule import parse_schedule


@given(st.text(min_size=1, max_size=100))
@settings(max_examples=200, deadline=1000)
def test_parse_schedule_never_panics(s: str) -> None:
    """parse_schedule must raise ValueError on bad input, never an internal error."""
    with suppress(ValueError):
        parse_schedule(s)
