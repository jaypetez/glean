---
title: "Schedule Syntax — glean Configuration"
description: Supported interval, daily, preset, and cron schedule formats.
---

# Schedule Syntax

glean supports friendly schedule strings:

| Format | Example | Meaning |
|--------|---------|---------|
| `every <N><unit>` | `every 1h` | Interval (s/m/h/d) |
| `daily HH:MM` | `daily 09:00` | Daily at time (uses `$TZ`) |
| `@preset` | `@hourly` | Cron preset |
| Cron | `0 */2 * * *` | 5-field cron expression |

All times use the `TZ` environment variable (default: `UTC`).

## Timezone behavior

`daily HH:MM` schedules use `$TZ` as an IANA timezone name, such as
`Europe/Paris` or `America/New_York`. The container defaults to UTC, so set
`TZ=Europe/Paris` in `.env` when wall-clock schedules should follow another
region.

DST transitions are resolved with Python `zoneinfo` and APScheduler cron
semantics. Wall-clock times after a transition use the new UTC offset. Times
inside a spring-forward gap run at the corresponding first real instant after
the jump. Times inside a fall-back repeated hour can produce both UTC instants,
so avoid repeated-hour schedules if duplicate wall-clock runs are a concern.
