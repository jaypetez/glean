# Schedule Syntax

glean supports friendly schedule strings:

| Format | Example | Meaning |
|--------|---------|---------|
| `every <N><unit>` | `every 1h` | Interval (s/m/h/d) |
| `daily HH:MM` | `daily 09:00` | Daily at time (uses `$TZ`) |
| `@preset` | `@hourly` | Cron preset |
| Cron | `0 */2 * * *` | 5-field cron expression |

All times use the `TZ` environment variable (default: `UTC`).
