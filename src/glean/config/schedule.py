from __future__ import annotations

import re
from dataclasses import dataclass

_INTERVAL_RE = re.compile(r"^\s*every\s+(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_DAILY_RE = re.compile(r"^\s*daily\s+(\d{1,2}):(\d{2})\s*$", re.IGNORECASE)
_AT_RE = re.compile(r"^\s*@?(hourly|daily|weekly|midnight)\s*$", re.IGNORECASE)
_CRON_PRESETS = {
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "midnight": "0 0 * * *",
    "weekly": "0 0 * * 0",
}


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    """Fire every N seconds."""

    seconds: int


@dataclass(frozen=True, slots=True)
class CronSchedule:
    """Standard 5-field cron expression."""

    expression: str


Schedule = IntervalSchedule | CronSchedule


def parse_schedule(raw: str) -> Schedule:
    """Parse a friendly schedule string.

    Accepted forms:
      - "every <N>(s|m|h|d)"        -> IntervalSchedule
      - "daily HH:MM"               -> CronSchedule
      - "@hourly" / "hourly", "daily", "weekly", "midnight" -> CronSchedule
      - 5-field cron                -> CronSchedule
    """
    if not raw or not isinstance(raw, str):
        raise ValueError(f"schedule must be a non-empty string: {raw!r}")

    s = raw.strip()

    if m := _INTERVAL_RE.match(s):
        n = int(m.group(1))
        unit = m.group(2).lower()
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        if n <= 0:
            raise ValueError(f"interval must be > 0: {raw!r}")
        return IntervalSchedule(seconds=n * mult)

    if m := _DAILY_RE.match(s):
        hh, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"invalid time: {raw!r}")
        return CronSchedule(expression=f"{mm} {hh} * * *")

    if m := _AT_RE.match(s):
        return CronSchedule(expression=_CRON_PRESETS[m.group(1).lower()])

    parts = s.split()
    if len(parts) == 5 and all(p for p in parts):
        return CronSchedule(expression=s)

    raise ValueError(
        f"unrecognized schedule {raw!r}. "
        "examples: 'every 1h', 'every 15m', 'daily 09:00', '@hourly', '0 */2 * * *'"
    )
