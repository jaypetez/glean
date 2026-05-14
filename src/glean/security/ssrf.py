from __future__ import annotations

import ipaddress
import os
import socket
from functools import lru_cache
from urllib.parse import urlparse

_BLOCKED_NETWORKS_V4 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
]
_BLOCKED_NETWORKS_V6 = [
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]
_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.google",
    "metadata",
    "instance-data",
}
_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_HOSTS_ENV = "GLEAN_SSRF_ALLOWED_HOSTS"
_LINK_LOCAL_V4 = ipaddress.ip_network("169.254.0.0/16")
_LINK_LOCAL_V6 = ipaddress.ip_network("fe80::/10")
_METADATA_V4 = ipaddress.ip_network("169.254.169.254/32")
_LOCALHOST_HOSTS = {"localhost"}

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class SSRFValidationError(ValueError):
    pass


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Validate `url` is safe to fetch. Raises SSRFValidationError on bad URL.

    With allow_private=True, internal Docker hosts and loopback are allowed, but
    cloud-metadata and link-local addresses are still blocked.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFValidationError(
            f"URL scheme {parsed.scheme!r} not allowed (only http/https)"
        )
    host = _normalize_host(parsed.hostname)
    if not host:
        raise SSRFValidationError(f"URL has no host: {url}")
    if host in _BLOCKED_HOSTS:
        raise SSRFValidationError(f"Host {host!r} is in cloud-metadata blocklist")

    effective_allow_private = allow_private or host in _allowed_hosts()
    literal = _parse_ip(host)
    if literal is not None:
        _check_ip(literal, host=host, allow_private=effective_allow_private)
        return url
    if effective_allow_private and _is_unqualified_hostname(host):
        return url

    addrs = _resolve(host)
    for addr in addrs:
        _check_ip(addr, host=host, allow_private=effective_allow_private)
    return url


def validate_provider_base_url(provider: str, base_url: str) -> str:
    """Validate an LLM provider base URL using provider-specific policy."""
    normalized_provider = provider.lower()
    if normalized_provider == "ollama":
        return validate_url(base_url, allow_private=True)
    if normalized_provider in {"openai", "anthropic"}:
        local = is_localhost_url(base_url)
        if urlparse(base_url).scheme != "https" and not local:
            raise SSRFValidationError(
                f"{provider} base_url must use HTTPS unless host is localhost"
            )
        return validate_url(base_url, allow_private=local)
    return validate_url(base_url)


def is_localhost_url(url: str) -> bool:
    host = _normalize_host(urlparse(url).hostname)
    if not host:
        return False
    if host in _LOCALHOST_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_external_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "http" or is_localhost_url(url):
        return False
    host = _normalize_host(parsed.hostname)
    if not host or host in _allowed_hosts() or _is_unqualified_hostname(host):
        return False
    literal = _parse_ip(host)
    if literal is not None:
        return not _is_private_or_local(literal)
    addrs = _resolve(host)
    return bool(addrs) and all(not _is_private_or_local(addr) for addr in addrs)


def _resolve(host: str) -> list[IPAddress]:
    """Resolve host to addresses."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    addrs: list[IPAddress] = []
    seen: set[IPAddress] = set()
    for info in infos:
        sockaddr = info[4]
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if addr not in seen:
            addrs.append(addr)
            seen.add(addr)
    return addrs


def _check_ip(addr: IPAddress, *, host: str, allow_private: bool) -> None:
    mapped = addr.ipv4_mapped if isinstance(addr, ipaddress.IPv6Address) else None
    check_addr: IPAddress = mapped or addr

    if isinstance(check_addr, ipaddress.IPv4Address) and check_addr in _METADATA_V4:
        raise SSRFValidationError(f"{host} resolves to cloud metadata IP {addr}")
    if isinstance(check_addr, ipaddress.IPv4Address) and check_addr in _LINK_LOCAL_V4:
        raise SSRFValidationError(f"{host} resolves to blocked link-local range ({addr})")
    if isinstance(addr, ipaddress.IPv6Address) and addr in _LINK_LOCAL_V6:
        raise SSRFValidationError(f"{host} resolves to blocked link-local range ({addr})")

    if allow_private:
        return

    if isinstance(check_addr, ipaddress.IPv4Address):
        for net in _BLOCKED_NETWORKS_V4:
            if check_addr in net:
                raise SSRFValidationError(f"{host} resolves to blocked range {net} ({addr})")
        return

    for net in _BLOCKED_NETWORKS_V6:
        if addr in net:
            raise SSRFValidationError(f"{host} resolves to blocked range {net} ({addr})")


def _is_private_or_local(addr: IPAddress) -> bool:
    try:
        _check_ip(addr, host=str(addr), allow_private=False)
    except SSRFValidationError:
        return True
    return False


def _parse_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_unqualified_hostname(host: str) -> bool:
    return "." not in host


def _allowed_hosts() -> frozenset[str]:
    return _parse_allowed_hosts(os.environ.get(_ALLOWED_HOSTS_ENV, ""))


@lru_cache(maxsize=16)
def _parse_allowed_hosts(raw: str) -> frozenset[str]:
    return frozenset(_normalize_host(part) for part in raw.split(",") if _normalize_host(part))


def _normalize_host(host: str | None) -> str:
    return (host or "").strip().rstrip(".").lower()
