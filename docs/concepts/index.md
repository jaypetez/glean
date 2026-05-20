---
title: "Concepts — glean Concepts"
description: Core mental models for feeds, pipelines, plugins, state, and schedules.
---

# Concepts

This section is being filled out. For now, start with [What is a feed?](./feed.md), the [Architecture](./architecture.md) overview, [Semantic dedup](./semantic-dedup.md), and the [feeds.yaml reference](../config/feeds.md).

The web UI is organized around a few stable navigation concepts:

- **Home** is the operational landing page for daemon health, recent digests, and quick actions.
- **Feeds** is the index of configured feeds.
- Each **feed detail** page groups **Overview**, **Digests**, **Runs**, **Suppressed**, and **Edit** into one place.
- **Digests**, **Skills**, and **Settings** remain top-level destinations for cross-feed history, structured prompts, and system controls.

Digest history is explicit: if you want the web UI to show past rendered digests, add the `dashboard` sink to a feed. glean does not implicitly persist digests just because the UI is enabled.
