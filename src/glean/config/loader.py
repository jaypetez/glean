from __future__ import annotations

import os
import re
from io import StringIO
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML

from glean.config.schedule import parse_schedule
from glean.config.schema import Config

_ENV_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


class ConfigError(Exception):
    """Raised when feeds.yaml is invalid."""


def _interpolate(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            var = m.group(1)
            return os.environ.get(var, m.group(0))

        return _ENV_RE.sub(repl, value)
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    return value


def _strip_unresolved(value: Any) -> tuple[Any, list[str]]:
    """Walk the structure; record any remaining ${VAR} placeholders."""
    missing: list[str] = []

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            for m in _ENV_RE.finditer(v):
                missing.append(m.group(1))
            return v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(val) for k, val in v.items()}
        return v

    walk(value)
    return value, sorted(set(missing))


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"YAML parse error in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"top-level of {path} must be a mapping")

    interpolated = _interpolate(raw)
    _, missing = _strip_unresolved(interpolated)

    try:
        cfg = Config.model_validate(interpolated)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc, path)) from exc

    for feed in cfg.feeds:
        try:
            parse_schedule(feed.schedule)
        except ValueError as exc:
            raise ConfigError(f"feed {feed.name!r}: {exc}") from exc

    if missing:
        raise ConfigError(
            "unresolved environment variables in config: "
            + ", ".join(f"${{{v}}}" for v in missing)
        )

    return cfg


def _format_validation_error(exc: ValidationError, path: Path) -> str:
    out = StringIO()
    out.write(f"config validation failed for {path}:\n")
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        out.write(f"  - {loc}: {err['msg']}\n")
    return out.getvalue().rstrip()
