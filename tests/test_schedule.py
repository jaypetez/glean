from __future__ import annotations

import pytest

from glean.config.schedule import CronSchedule, IntervalSchedule, parse_schedule


@pytest.mark.parametrize(
    "raw,seconds",
    [
        ("every 30s", 30),
        ("every 5m", 300),
        ("every 1h", 3600),
        ("EVERY 2d", 172800),
        ("  every 1h  ", 3600),
    ],
)
def test_interval_strings(raw: str, seconds: int) -> None:
    s = parse_schedule(raw)
    assert isinstance(s, IntervalSchedule)
    assert s.seconds == seconds


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("daily 09:00", "0 9 * * *"),
        ("daily 23:45", "45 23 * * *"),
        ("@hourly", "0 * * * *"),
        ("@daily", "0 0 * * *"),
        ("midnight", "0 0 * * *"),
        ("0 */2 * * *", "0 */2 * * *"),
    ],
)
def test_cron_strings(raw: str, expected: str) -> None:
    s = parse_schedule(raw)
    assert isinstance(s, CronSchedule)
    assert s.expression == expected


@pytest.mark.parametrize("bad", ["", "every", "every 0s", "daily 25:00", "every -1h", "nonsense"])
def test_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_schedule(bad)
