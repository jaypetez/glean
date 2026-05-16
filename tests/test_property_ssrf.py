from __future__ import annotations

from contextlib import suppress
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from glean.exceptions import SecurityError
from glean.security.ssrf import validate_url


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=200))
@settings(max_examples=200, deadline=1000)
def test_validate_url_never_panics(url: str) -> None:
    """Must raise SecurityError or ValueError, never anything else."""
    with (
        patch("glean.security.ssrf._resolve", return_value=[]),
        suppress(SecurityError, ValueError),
    ):
        validate_url(url)
