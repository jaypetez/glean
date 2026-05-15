from __future__ import annotations

import socket
import textwrap
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from glean.config import load_config
from glean.config.loader import ConfigError
from glean.llm.anthropic_provider import AnthropicProvider
from glean.llm.ollama_provider import OllamaProvider
from glean.llm.openai_provider import OpenAIProvider
from glean.search.searxng import SearXNGBackend
from glean.security.ssrf import SSRFValidationError, validate_url
from glean.security.ssrf_transport import SSRFGuardedTransport
from glean.sources._fetch import follow_with_validation


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com",
        "https://api.openai.com",
        "https://example.com:8443/path?q=1",
        "https://user:pass@example.com/feed",
    ],
)
def test_validate_url_allows_public_http_and_https(url: str) -> None:
    assert validate_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://x",
        "gopher://x",
        "ldap://x",
        "javascript:alert(1)",
    ],
)
def test_validate_url_blocks_non_http_schemes(url: str) -> None:
    with pytest.raises(SSRFValidationError, match="scheme"):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/",
        "http://169.254.1.1/",
        "http://10.0.0.1/",
        "http://127.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:10.0.0.1]/",
    ],
)
def test_validate_url_blocks_internal_ip_literals(url: str) -> None:
    with pytest.raises(SSRFValidationError):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://metadata.google.internal/",
        "http://metadata.google/",
        "http://metadata/",
        "http://instance-data/",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_validate_url_blocks_cloud_metadata_hostnames(url: str) -> None:
    with pytest.raises(SSRFValidationError, match="metadata|cloud"):
        validate_url(url)


@pytest.mark.parametrize("url", ["", "https:///path", "http://"])
def test_validate_url_rejects_empty_or_hostless_urls(url: str) -> None:
    with pytest.raises(SSRFValidationError):
        validate_url(url)


def _fake_getaddrinfo(address: str) -> Callable[..., list[tuple[Any, ...]]]:
    def fake_getaddrinfo(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, 443))]

    return fake_getaddrinfo


def test_validate_url_rejects_hostname_that_resolves_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.1"))

    with pytest.raises(SSRFValidationError, match="10.0.0.0/8"):
        validate_url("https://attacker.example")


def test_validate_url_allows_hostname_that_resolves_to_public_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))

    assert validate_url("https://example.com") == "https://example.com"


def test_validate_url_lets_http_client_report_dns_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_getaddrinfo(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        raise OSError("dns unavailable")

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)

    assert validate_url("https://does-not-resolve.invalid") == "https://does-not-resolve.invalid"


def test_allow_private_allows_internal_service_hostnames_without_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_getaddrinfo(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        raise AssertionError("single-label internal hosts should not require DNS")

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)

    assert validate_url("http://ollama:11434", allow_private=True) == "http://ollama:11434"


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/",
        "http://169.254.1.1/",
        "http://[fe80::1]/",
        "http://metadata.google.internal/",
    ],
)
def test_allow_private_still_blocks_metadata_and_link_local(url: str) -> None:
    with pytest.raises(SSRFValidationError):
        validate_url(url, allow_private=True)


def test_env_allowlist_allows_named_internal_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLEAN_SSRF_ALLOWED_HOSTS", "mock-rss,mock-ollama")
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("172.18.0.7"))

    assert validate_url("http://mock-rss:8002/feed") == "http://mock-rss:8002/feed"


def test_env_allowlist_does_not_override_metadata_blocklist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLEAN_SSRF_ALLOWED_HOSTS", "metadata.google.internal")

    with pytest.raises(SSRFValidationError):
        validate_url("http://metadata.google.internal/")


async def test_ssrf_guarded_transport_blocks_internal_ip_before_network() -> None:
    async with httpx.AsyncClient(transport=SSRFGuardedTransport()) as client:
        with pytest.raises(httpx.RequestError, match="SSRF blocked"):
            await client.get("http://127.0.0.1/")


@respx.mock
async def test_follow_with_validation_follows_safe_redirects() -> None:
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(302, headers={"Location": "https://example.org/feed"})
    )
    final = respx.get("https://example.org/feed").mock(return_value=httpx.Response(200, text="ok"))

    async with httpx.AsyncClient(follow_redirects=False) as client:
        resp = await follow_with_validation(client, "https://example.com/feed")

    assert resp.status_code == 200
    assert final.called


@respx.mock
async def test_follow_with_validation_blocks_unsafe_redirect_target() -> None:
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
    )

    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(SSRFValidationError):
            await follow_with_validation(client, "https://example.com/feed")


@respx.mock
async def test_follow_with_validation_raises_on_too_many_redirects() -> None:
    for index in range(3):
        respx.get(f"https://example.com/r{index}").mock(
            return_value=httpx.Response(302, headers={"Location": f"/r{index + 1}"})
        )

    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(httpx.TooManyRedirects, match="Exceeded maximum redirects"):
            await follow_with_validation(client, "https://example.com/r0", max_hops=2)


def test_searxng_backend_rejects_metadata_base_url() -> None:
    with pytest.raises(ValueError):
        SearXNGBackend(base_url="http://169.254.169.254/")


def test_ollama_provider_rejects_metadata_base_url() -> None:
    with pytest.raises(ValueError):
        OllamaProvider(base_url="http://169.254.169.254/")


def test_openai_provider_rejects_insecure_external_base_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAIProvider(api_key="sk-test", base_url="http://api.openai.com/v1")


def test_openai_provider_allows_explicit_localhost_base_url() -> None:
    provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:8080/v1")
    assert str(provider._client.base_url).startswith("http://localhost:8080")


def test_anthropic_provider_rejects_metadata_base_url() -> None:
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="sk-ant-test", base_url="http://169.254.169.254/")


def test_config_validation_rejects_malicious_source_url(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          telegram:
            bot_token: test-token
            chat_id: -1001
        feeds:
          - name: ssrf
            schedule: "every 1h"
            sources:
              - type: rss
                url: http://169.254.169.254/latest/meta-data/
            pipeline:
              - dedup
        """
    )

    with pytest.raises(ConfigError, match="SSRF|blocked|metadata"):
        load_config(write_yaml(yaml))


def test_config_validation_rejects_malicious_sink_url(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: ssrf
            schedule: "every 1h"
            sinks:
              - type: webhook
                url: http://10.0.0.1/hook
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )

    with pytest.raises(ConfigError, match="blocked"):
        load_config(write_yaml(yaml))


def test_config_validation_rejects_malicious_default_sink_url(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          sinks:
            - type: webhook
              url: http://10.0.0.1/hook
        feeds: []
        """
    )

    with pytest.raises(ConfigError, match="blocked"):
        load_config(write_yaml(yaml))


def test_config_validation_allows_searxng_private_base_url(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          telegram:
            bot_token: test-token
            chat_id: -1001
        feeds:
          - name: search
            schedule: "every 1h"
            sources:
              - type: search
                query: llms
                engine: searxng
                base_url: http://searxng:8080
            pipeline:
              - dedup
        """
    )

    cfg = load_config(write_yaml(yaml))
    assert cfg.feeds[0].sources[0]["base_url"] == "http://searxng:8080"
