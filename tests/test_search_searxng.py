from __future__ import annotations

import pytest

from glean.exceptions import SecurityError
from glean.search.searxng import SearXNGBackend


def test_searxng_backend_rejects_bad_base_url_scheme() -> None:
    with pytest.raises(SecurityError, match="scheme"):
        SearXNGBackend(base_url="file:///etc/passwd")


def test_searxng_backend_allows_internal_service_base_url() -> None:
    backend = SearXNGBackend(base_url="http://searxng:8080/")

    assert backend.base_url == "http://searxng:8080"
