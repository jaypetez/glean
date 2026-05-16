---
title: Common Pitfalls — Agent Runbook
description: Things AI agents get wrong on glean. Read before editing.
---

# Common Pitfalls

These are mistakes agents make on first try. Avoid them.

## 1. Using `...` in protocol stubs

CodeQL flags bare `...` as `py/empty-statement`. Always use `pass`:

```python
async def aclose(self) -> None:
    pass  # NOT ...
```

## 2. Mutating an Item

`Item` is a frozen dataclass. Use `dataclasses.replace()` to make a new one:

```python
new_item = dataclasses.replace(item, llm_summary="...")
```

## 3. Not calling `effective_*()` methods on FeedConfig

Always call `feed.effective_llm(defaults)`, never `feed.llm`. The merge logic lives in the method.

## 4. Hardcoding test env vars

Use the `_isolate_env` autouse fixture in `tests/conftest.py` — never set env vars at module import time.

## 5. Adding a new env var without updating `.env.example`

Every env var read by glean MUST appear in `.env.example` with a comment. Otherwise agents and humans can't discover it.

## 6. Skipping `validate_url()` on outbound HTTP

Every outbound HTTP from a source/sink/search plugin must call `glean.security.ssrf.validate_url(url)` first.

## 7. Not updating `_import_builtins()`

Adding a plugin file isn't enough — you must add an import to the matching `_import_builtins()` in `registry.py`. The scaffold helper should do this for you; if you're working manually, do it yourself.

## 8. Empty `except: pass` without explanation

CodeQL flags this as `py/empty-except`. Add an inline comment explaining why:

```python
except FileNotFoundError:
    pass  # State file not present yet — first boot, will be created below.
```
