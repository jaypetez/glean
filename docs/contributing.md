---
title: "Contributing to the Docs — glean Contributing"
description: Contribute tutorials, how-to guides, reference pages, and copy to the glean documentation site.
---

# Contributing to the Docs

This page is for contributors who want to improve tutorials, how-to guides, reference pages, or copy in the documentation site. For code changes, plugin implementation, dev setup, and PR rules, read the root [CONTRIBUTING.md](https://github.com/jaypetez/glean/blob/main/CONTRIBUTING.md).

## Choose the right page type

Glean docs follow [Diátaxis](https://diataxis.fr/): tutorials teach, how-to guides solve tasks, reference pages describe facts, and concepts explain ideas. Pick one type before you write so the page has a clear job.

Use the [style guide](contributing/style-guide.md) for voice, structure, and command examples.

## Add a how-to guide

Write a how-to when the reader has a goal, such as adding a sink or configuring web search. Start with who the guide is for, then list prerequisites, steps, expected output, and a verification command.

Preview the docs locally:

```bash
uv run mkdocs serve
```

Expected output:

```text
INFO    -  [..] Serving on http://127.0.0.1:8000/
```

## Add a tutorial

Write a tutorial when the reader should learn by building a complete path from start to finish. Keep it runnable on a clean checkout, prefer fixture data over real accounts, and show the output after each command.

Before you open the PR, run the strict build:

```bash
uv run mkdocs build --strict
```

Expected output:

```text
INFO    -  Documentation built in ...
```

## Fix typos or stale copy

Small copy fixes are welcome. Keep the PR limited to the page you are improving, unless the same typo appears across related pages.

If you change a command, run it and paste the expected output into the page. If you cannot run it, say why in the PR description.

## Screenshots and GIFs

Store docs images under `docs/assets/`. Prefer SVG or compressed GIF/PNG assets that are small enough for a fast docs build.

Add alt text that describes the purpose of the image. If the image shows UI state, mention the state and the action the reader should take next.

## PR checklist for docs

- The page starts with what it is and who it is for.
- Commands include expected output.
- Links work in `uv run mkdocs build --strict`.
- New pages are added to `mkdocs.yml` navigation.
- The PR description explains the reader problem the page solves.
