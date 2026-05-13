from __future__ import annotations

import logging
from typing import Any

import glean.logging as logging_module


def test_configure_logging_uses_console_renderer_by_default(
    monkeypatch,
) -> None:
    configured: dict[str, Any] = {}
    basic_config: dict[str, Any] = {}

    monkeypatch.setattr(
        logging_module.structlog,
        "configure",
        lambda **kwargs: configured.update(kwargs),
    )
    monkeypatch.setattr(
        logging_module.logging,
        "basicConfig",
        lambda **kwargs: basic_config.update(kwargs),
    )
    monkeypatch.setattr(logging_module.sys.stderr, "isatty", lambda: True)

    logging_module.configure_logging()

    assert basic_config["level"] == "INFO"
    assert basic_config["format"] == "%(message)s"
    assert basic_config["stream"] is logging_module.sys.stderr
    assert configured["processors"][-1].__class__.__name__ == "ConsoleRenderer"


def test_configure_logging_honors_env_and_json_mode(monkeypatch) -> None:
    configured: dict[str, Any] = {}
    basic_config: dict[str, Any] = {}

    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setattr(
        logging_module.structlog,
        "configure",
        lambda **kwargs: configured.update(kwargs),
    )
    monkeypatch.setattr(
        logging_module.logging,
        "basicConfig",
        lambda **kwargs: basic_config.update(kwargs),
    )

    logging_module.configure_logging()

    assert basic_config["level"] == "DEBUG"
    assert configured["processors"][-1].__class__.__name__ == "JSONRenderer"


def test_get_logger_returns_structlog_logger(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(logging_module.structlog, "get_logger", lambda name=None: sentinel)

    assert logging_module.get_logger("cli") is sentinel


def test_configured_logger_can_emit_named_event(caplog) -> None:
    logging_module.structlog.reset_defaults()
    try:
        logging_module.configure_logging("INFO", json_logs=True)

        with caplog.at_level(logging.INFO, logger="smoke"):
            logging_module.get_logger("smoke").info("health_listening", port=19090)

        assert any("health_listening" in record.getMessage() for record in caplog.records)
    finally:
        logging_module.structlog.reset_defaults()
