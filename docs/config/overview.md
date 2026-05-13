# Configuration Overview

glean uses two files:

- **`.env`** — secrets (bot tokens, API keys, chat IDs). Never committed.
- **`feeds.yaml`** — feeds, sources, prompts, schedules. Safe to commit. References `${ENV_VARS}`.

## feeds.yaml structure

```yaml
defaults:          # inherited by all feeds unless overridden
  llm: { ... }
  render: { ... }
  bootstrap: skip-and-mark
  failure: { ... }

feeds:
  - name: my-feed
    schedule: "every 1h"
    chat_id: ${TELEGRAM_CHAT_ID}
    sources: [...]
    pipeline: [...]
```

See [feeds.yaml Reference](feeds.md) for the full schema.
