---
title: "Dedup and bootstrap — glean Concepts"
description: "Understand how glean remembers seen items and why the default first run may send nothing."
---

# Dedup and bootstrap

Dedup is how glean remembers old items; bootstrap is how a new feed avoids dumping its whole backlog.

*Who reads this: everyone configuring a feed, especially when the first run appears to send nothing.*

*This page is Explanation — read it to understand the model. For task-focused steps, see the [How-to guides](../how-to/index.md).*

See also: [Semantic dedup](./semantic-dedup.md), which suppresses near-duplicates after ordinary URL/content dedup.

This is the most common surprise in glean: **the default first run may send nothing on purpose**. That is not a broken Telegram bot, not a bad RSS URL, and not necessarily an LLM failure. It is bootstrap protection.

Dedup starts with an identity. For each item, glean computes a SHA-256 hash of `canonical_url`. If `canonical_url` is empty, it hashes `title + body[:512]` instead. The hash is stored in SQLite's `seen_items` table with feed name and send status. The `sent=1` marker means the item has been treated as delivered for that feed's history, even if the delivery was a bootstrap mark rather than a visible message.

```mermaid
flowchart TD
    Item[Fetched item] --> Key{canonical_url?}
    Key -->|yes| UrlHash[sha256(canonical_url)]
    Key -->|no| BodyHash[sha256(title + body[:512])]
    UrlHash --> Seen[(seen_items)]
    BodyHash --> Seen
    Seen --> Decision{seen before?}
    Decision -->|yes| Drop[Do not send]
    Decision -->|no| Pipeline[Continue pipeline]
```

Bootstrap is the rule for an unbootstrapped feed's first non-dry run. The default mode is `skip-and-mark`. In that mode, glean fetches current items, writes them to `seen_items` with `sent=1`, marks the feed bootstrapped in `feed_runs`, and sends no digest. The next tick only sends items that appeared after that baseline.

The analogy is subscribing to a newspaper. You usually want tomorrow's paper, not every issue the publisher still has in a stack. `skip-and-mark` creates that subscription boundary.

The other modes exist for different expectations. `send-last-N` sends a small initial digest using `bootstrap_count` and then marks the feed bootstrapped. It is useful for demos and first-contact setup, because users see proof immediately without receiving the entire backlog. `send-all` sends everything currently fetched, which is appropriate only when the backlog itself is valuable or tightly bounded.

Dry-runs add one more wrinkle: a dry-run does not write state. If `glean test-feed` reports `skipped: bootstrap`, running the same dry-run again can show the same result because SQLite was not changed. A scheduled run or a sending run establishes the baseline. When a new feed seems quiet, bootstrap is the first concept to check.
