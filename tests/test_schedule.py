from __future__ import annotations

from datetime import UTC, datetime

import pytest
import time_machine
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from glean.config.schedule import CronSchedule, IntervalSchedule, parse_schedule
from glean.scheduler import _trigger_from_schedule


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


def _next_fires_utc(raw: str, count: int) -> list[datetime]:
    trigger = _trigger_from_schedule(parse_schedule(raw))
    assert isinstance(trigger, CronTrigger)
    fires: list[datetime] = []
    for _ in range(count):
        next_fire = trigger.next()
        assert next_fire is not None
        fires.append(next_fire.astimezone(UTC))
    return fires


def _next_fire_utc(raw: str) -> datetime:
    return _next_fires_utc(raw, 1)[0]


@time_machine.travel("2026-03-08 05:00:00+00:00", tick=False)
def test_daily_schedule_handles_spring_forward_missing_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing 02:30 New York wall time maps to the first real post-jump instant."""
    monkeypatch.setenv("TZ", "America/New_York")

    assert _next_fire_utc("daily 02:30") == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)


@time_machine.travel("2026-11-01 04:00:00+00:00", tick=False)
def test_daily_schedule_can_fire_both_fall_back_instants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeated 01:30 New York wall time can produce both UTC instants."""
    monkeypatch.setenv("TZ", "America/New_York")

    assert _next_fires_utc("daily 01:30", 2) == [
        datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
    ]


@time_machine.travel("2026-03-08 06:00:00+00:00", tick=False)
def test_daily_schedule_fires_correctly_before_us_dst_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At 06:00 UTC, New York is 01:00 EST before the spring-forward."""
    monkeypatch.setenv("TZ", "America/New_York")

    # The 09:00 wall-clock fire is after the 02:00 -> 03:00 jump, so it is EDT.
    assert _next_fire_utc("daily 09:00") == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)


@time_machine.travel("2026-03-08 12:00:00+00:00", tick=False)
def test_daily_schedule_fires_correctly_after_us_dst_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At 12:00 UTC on 2026-03-08, New York is 08:00 EDT."""
    monkeypatch.setenv("TZ", "America/New_York")

    assert _next_fire_utc("daily 09:00") == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)


@time_machine.travel("2026-03-29 00:30:00+00:00", tick=False)
def test_daily_schedule_handles_european_dst_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paris springs forward from 02:00 CET to 03:00 CEST on 2026-03-29."""
    monkeypatch.setenv("TZ", "Europe/Paris")

    assert _next_fire_utc("daily 09:00") == datetime(2026, 3, 29, 7, 0, tzinfo=UTC)


@time_machine.travel("2026-03-08 06:00:00+00:00", tick=False)
def test_every_1h_unaffected_by_dst(monkeypatch: pytest.MonkeyPatch) -> None:
    """'every 1h' is interval-based; DST changes wall clock but not interval."""
    expected_first = datetime(2026, 3, 8, 6, 0, tzinfo=UTC)
    expected_second = datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    actual: list[tuple[datetime, datetime]] = []

    for tz_name in ("UTC", "America/New_York", "Europe/Paris"):
        monkeypatch.setenv("TZ", tz_name)
        trigger = _trigger_from_schedule(parse_schedule("every 1h"))
        assert isinstance(trigger, IntervalTrigger)
        first_fire = trigger.next()
        second_fire = trigger.next()
        assert first_fire is not None
        assert second_fire is not None
        actual.append((first_fire.astimezone(UTC), second_fire.astimezone(UTC)))

    assert actual == [
        (expected_first, expected_second),
        (expected_first, expected_second),
        (expected_first, expected_second),
    ]
