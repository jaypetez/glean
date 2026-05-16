"""Shared service layer used by both the CLI and the REST API.

Functions in this module take pre-built Config + StateStore (do not
load files or open DBs themselves), return typed dataclasses, and never
print to stdout. The CLI and API layers are responsible for I/O concerns
(formatting output, error reporting, exit codes).
"""

from glean.api_service.config_service import (
    ConfigSummary,
    FeedSummary,
    validate_config_summary,
    write_config,
)
from glean.api_service.run_service import (
    FeedStatus,
    get_feed_status,
    list_feeds_with_status,
    run_feed_once,
)

__all__: list[str] = [
    "ConfigSummary",
    "FeedStatus",
    "FeedSummary",
    "get_feed_status",
    "list_feeds_with_status",
    "run_feed_once",
    "validate_config_summary",
    "write_config",
]
