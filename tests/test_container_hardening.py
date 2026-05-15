from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
SHA256_PIN = re.compile(r"@sha256:[0-9a-f]{64}")


def _load_compose(path: str) -> dict[str, Any]:
    loaded = YAML(typ="safe").load(ROOT.joinpath(path).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _service(compose_path: str, service_name: str) -> dict[str, Any]:
    services = _load_compose(compose_path)["services"]
    service = services[service_name]
    assert isinstance(service, dict)
    return service


def _assert_hardened(service: dict[str, Any], *, read_only: bool) -> None:
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service.get("read_only") is read_only
    if read_only:
        assert "/tmp:size=64m,mode=1777" in service["tmpfs"]


def test_dockerfile_pins_mutable_base_images_to_sha256_digests() -> None:
    dockerfile = ROOT.joinpath("Dockerfile").read_text(encoding="utf-8")

    # We assert *digest pinning* on every FROM/COPY --from line — not specific
    # versions. Version bumps are handled by a separate review process; the
    # security invariant we enforce here is "no mutable tags in production".
    from_lines = [
        line
        for line in dockerfile.splitlines()
        if line.startswith("FROM ") or line.startswith("COPY --from=")
    ]
    assert from_lines, "Dockerfile has no FROM or COPY --from lines"

    for line in from_lines:
        # Skip alias-only references like 'FROM builder' that have no image
        # registry component (no ':' in the image part)
        ref = line.removeprefix("FROM ").removeprefix("COPY --from=").split(" ", 1)[0]
        if ":" not in ref:
            continue  # alias to an earlier stage
        assert SHA256_PIN.search(line), (
            f"Dockerfile line is not SHA-256-pinned: {line!r}"
        )


def test_runtime_image_provides_curl_probe_without_debian_curl_package() -> None:
    dockerfile = ROOT.joinpath("Dockerfile").read_text(encoding="utf-8")
    curl_shim = ROOT.joinpath("docker", "curl")

    assert "tzdata ca-certificates curl" not in dockerfile
    assert "COPY docker/curl /usr/local/bin/curl" in dockerfile
    assert curl_shim.exists()


def test_production_compose_hardens_glean_and_support_services() -> None:
    _assert_hardened(_service("docker-compose.yml", "glean"), read_only=True)
    _assert_hardened(_service("docker-compose.yml", "ollama"), read_only=True)


def test_e2e_compose_hardens_all_services() -> None:
    compose = _load_compose("docker-compose.e2e.yml")

    for service in compose["services"].values():
        assert isinstance(service, dict)
        _assert_hardened(service, read_only=True)
