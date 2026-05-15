# Per-source LLM models

Reference for the `sources[].llm` override. For setup steps, see [How to set up per-source LLM dispatch](../how-to/llm/per-source.md).

## Field location

`llm` is valid inside any source spec:

```yaml
sources:
  - type: rss
    url: https://example.com/feed.xml
    llm:
      provider: anthropic
      model: claude-haiku-4-5
```

## Fields

The source-level `llm` block accepts the same fields as `defaults.llm` and
`feeds[].llm`.

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | no | Built-in provider name: `ollama`, `openai`, or `anthropic`. |
| `model` | no | Provider model name. |
| `base_url` | no | Provider API base URL override. |
| `api_key` | no | Inline API key. Prefer environment variables for secrets. |
| `timeout_s` | no | LLM request timeout in seconds. |

## Precedence

For `rank`, `summarize`, and LLM-generated `digest` stages:

1. `sources[].llm`
2. `feeds[].llm`
3. `defaults.llm`

For `apply_skill` stages:

1. `skills[].llm`
2. `sources[].llm`
3. `feeds[].llm`
4. `defaults.llm`

Sources without `llm` use the feed-level LLM or the default LLM.

## Runtime behavior

- The runner tags items with the LLM config from the source that produced them.
- `rank`, `summarize`, and `apply_skill` dispatch each item to its tagged provider.
- Sources with identical provider, model, and `base_url` values share a cached provider instance.
- `max_llm_calls_per_run` still caps calls across all providers in the feed.

## Example

```yaml
defaults:
  llm:
    provider: ollama
    model: qwen2.5:7b

feeds:
  - name: tech
    schedule: "every 1h"
    sinks:
      - type: file
        path: /data/tech.md
        format: markdown
    sources:
      - type: rss
        url: https://example.com/noisy.xml
      - type: reddit
        subreddit: programming
        sort: top
        timeframe: hour
        llm:
          provider: anthropic
          model: claude-haiku-4-5
    pipeline:
      - dedup
      - rank: { prompt: "Score relevance to software builders", min_relevance: 0.6 }
      - summarize
      - digest
```

## Related

- [feeds.yaml per-source LLM reference](feeds.md#per-source-llm)
- [LLM provider reference](feeds.md#llm-providers)
