---
title: "Skills — glean Configuration"
description: Define reusable structured extraction skills for the apply_skill pipeline stage.
---

# Skills

A **skill** is a reusable, named LLM extraction template. Each skill defines a
prompt, an output schema, and (optionally) which LLM to use. Skills are referenced
by name from the `apply_skill` pipeline stage.

Skills shine when you want **structured output** — fields like
`{title, sale_price, deal_quality, summary}` instead of a free-form sentence.

## When to use a skill

| Want | Use |
|------|-----|
| One-line summary string per item | `summarize` stage |
| Structured fields (price, severity, tags, etc.) | `apply_skill` stage |
| Both — structured fields *and* a clean summary | `apply_skill` (it auto-populates `llm_summary` from the `summary`/`one_liner`/`tldr` field) |

## Defining skills

Skills are declared at the top of `feeds.yaml`:

```yaml
skills:
  - name: deal-finder
    description: "Extract structured deal information"
    system_prompt: |
      You are a deal analysis assistant. Extract factual deal details only.
      Never guess prices that aren't explicitly stated.
    prompt: |
      Extract deal information from:

      Title: {title}
      Content: {body}
    output_schema:
      item_title: str
      original_price: "str | None"
      sale_price: "str | None"
      discount_percent: "float | None"
      deal_quality: str
      summary: str

feeds:
  - name: r-buildapcsales
    schedule: "every 30m"
    chat_id: ${TELEGRAM_CHAT_DEALS}
    sources:
      - type: reddit
        subreddit: buildapcsales
        sort: new
    pipeline:
      - dedup
      - apply_skill:
          skill: deal-finder
      - digest:
          intro: "🛒 <b>PC sales</b>"
```

## Field reference

### Top-level skill fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique identifier. Lowercase, alphanumeric + `._-`. |
| `version` | no | Informational version string (default `"1"`). |
| `description` | no | Human-readable description. |
| `system_prompt` | no | Optional system message sent to the LLM. |
| `prompt` | yes | Per-item prompt template. May reference `{title}`, `{body}`, `{summary}`, `{url}`, `{source_name}`, `{source_type}`. |
| `output_schema` | yes | Map of field-name → type-string (or full `SkillOutputField` object). |
| `llm` | no | Skill-level LLM override. Highest precedence (overrides source and feed LLMs). |

### Output schema field types

These are the supported types (validated at config-load time):

| Type | Example value |
|------|---------------|
| `str` | `"hello"` |
| `int` | `42` |
| `float` | `3.14` |
| `bool` | `true` |
| `str | None` | `null` or string |
| `int | None`, `float | None`, `bool | None` | nullable numerics |
| `list[str]` | `["a", "b"]` |
| `list[int]` | `[1, 2]` |
| `list[float]` | `[1.5, 2.5]` |

For richer descriptions, use the verbose form:
```yaml
output_schema:
  summary:
    type: str
    description: "≤25 word one-liner for the digest"
    required: true
  tags:
    type: "list[str]"
    required: false
```

### Template variables

The `prompt` field is rendered with Python's `str.format_map`. Only these
variables are available:

| Variable | Source |
|----------|--------|
| `{title}` | `Item.title` |
| `{body}` | `Item.body` |
| `{summary}` | `Item.summary` (source-provided) |
| `{url}` | `Item.canonical_url` |
| `{source_name}` | `Item.source_name` |
| `{source_type}` | `Item.source_type` |

Referencing any other variable causes a config-load error so typos are caught
early.

## Using skills in pipelines

The `apply_skill` stage is independent of `summarize` and `rank` — you can
use it alongside, instead of, or before either:

```yaml
pipeline:
  - dedup
  - apply_skill:                  # extract structured fields
      skill: deal-finder
  - rank:                         # rank using the structured fields
      prompt: |
        Score 0-1: is this a great deal? Use the structured.deal_quality
        and structured.discount_percent fields if present.
      min_relevance: 0.5
  - digest:
      intro: "🛒 <b>Today's deals</b>"
```

The extracted fields land on `Item.structured` (a dict). If the schema includes
a `summary`, `one_liner`, or `tldr` field, it's also copied to `Item.llm_summary`
so existing renderers Just Work.

## LLM precedence

When `apply_skill` runs, the LLM is chosen by this precedence:

1. **Skill-level `llm:`** — highest priority. The skill knows what model it needs.
2. **Source-level `llm:`** — set on the source spec, applies to all items from that source.
3. **Feed-level `llm:`** — `FeedConfig.llm`.
4. **Defaults** — `defaults.llm` (always present).

```yaml
defaults:
  llm: { provider: ollama, model: qwen2.5:7b }   # 4. fallback

skills:
  - name: needs-claude
    prompt: "Extract complex CVE details from {body}"
    output_schema:
      cve_id: "str | None"
      severity: str
    llm: { provider: anthropic, model: claude-haiku-4-5 }   # 1. wins for this skill

feeds:
  - name: cves
    chat_id: ${OPS_CHAT}
    llm: { provider: openai, model: gpt-4o-mini }   # 3. feed default
    sources:
      - type: rss
        url: https://nvd.nist.gov/feeds/...
        llm: { provider: ollama, model: llama3:70b }   # 2. for this source
    pipeline:
      - dedup
      - apply_skill: { skill: needs-claude }   # uses Claude (skill override)
      - summarize: { prompt: "..." }            # uses llama3:70b (source override)
```

## Failure handling

If the LLM call fails, the item passes through unchanged with `structured: {}`.
The pipeline does not abort. Errors are logged with `feed`, `skill`, and `url`.

If the LLM doesn't implement `extract()` (e.g., a third-party provider), items
also pass through unchanged with a logged warning.

## Built-in example skills

Four ready-to-use skills are shipped in `feeds.example.yaml`:

- **`deal-finder`** — for shopping/sale RSS feeds (extracts price, discount, quality)
- **`cve-extractor`** — for security advisory feeds (extracts CVE ID, severity, packages)
- **`paper-digest`** — for arXiv/academic feeds (extracts contributions, methodology, GPU requirement)
- **`job-posting`** — for job board feeds (extracts role, salary, tech stack, remote-ok)

Copy whichever you need into your own `feeds.yaml`.
