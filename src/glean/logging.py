import logging
import os
import sys

import structlog


def configure_logging(level: str | None = None, *, json_logs: bool | None = None) -> None:
    log_level = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    use_json = json_logs if json_logs is not None else os.environ.get("LOG_FORMAT") == "json"

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    level_int = getattr(logging, log_level, logging.INFO)
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stderr)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[return-value]
