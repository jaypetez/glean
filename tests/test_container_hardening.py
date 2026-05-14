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

    assert re.search(rf"^FROM node:22-alpine{SHA256_PIN.pattern} AS ui-builder$", dockerfile, re.M)
    assert re.search(
        rf"^FROM python:3\.13-slim-trixie{SHA256_PIN.pattern} AS builder$",
        dockerfile,
        re.M,
    )
    assert re.search(
        rf"^FROM python:3\.13-slim-trixie{SHA256_PIN.pattern} AS runtime$",
        dockerfile,
        re.M,
    )
    assert re.search(
        rf"^COPY --from=ghcr\.io/astral-sh/uv:0\.5\.13{SHA256_PIN.pattern} "
        r"/uv /usr/local/bin/uv$",
        dockerfile,
        re.M,
    )


def test_runtime_image_keeps_curl_for_local_health_probe() -> None:
    dockerfile = ROOT.joinpath("Dockerfile").read_text(encoding="utf-8")

    assert "tzdata ca-certificates curl" in dockerfile


def test_production_compose_hardens_glean_and_support_services() -> None:
    _assert_hardened(_service("docker-compose.yml", "glean"), read_only=True)
    _assert_hardened(_service("docker-compose.yml", "ollama"), read_only=True)


def test_e2e_compose_hardens_all_services() -> None:
    compose = _load_compose("docker-compose.e2e.yml")

    for service in compose["services"].values():
        assert isinstance(service, dict)
        _assert_hardened(service, read_only=True)
