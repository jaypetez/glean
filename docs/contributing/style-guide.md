---
title: "Documentation Style Guide  glean Contributing"
description: Writing standards for clear, task-focused, and consistent glean documentation.
---

# Documentation Style Guide

This guide is for contributors writing or reviewing glean documentation. Use it to make pages consistent, task-focused, and respectful of readers who may be blocked.

## Voice rules

- Write in second person: "Configure the feed", not "The user configures the feed".
- Use active voice: "Run the command", not "The command should be run".
- Keep paragraphs to 3 sentences or fewer; reference entries can be shorter.
- Avoid these banned words: "easy", "simple", "just", and "simply".
- Lead every page with what it is and who it is for.
- Show expected output after every command.

## Diátaxis page types

Glean uses [Diátaxis](https://diataxis.fr/) to keep each page focused. Choose one type and optimize for that reader need.

| Type | Reader need | Page shape |
|---|---|---|
| Tutorial | Learn by doing | Guided path, known starting point, complete result. |
| How-to | Solve a task | Goal, prerequisites, steps, verification. |
| Reference | Look up facts | Exact fields, options, defaults, contracts. |
| Concept | Understand an idea | Context, trade-offs, mental model, links to tasks. |

## Commands

Every command needs an expected output block. Use realistic snippets instead of full logs when the output is long.

```bash
uv run mkdocs build --strict
```

Expected output:

```text
INFO    -  Documentation built in ...
```

If a command writes a file, show the path or the confirmation message. If the command can fail for a common reason, add a short troubleshooting note after the expected output.

## Links and names

Use relative links for docs pages in the same site. Use repository links only when the target is outside the docs site, such as root `CONTRIBUTING.md`.

Write project terms consistently: `glean` for the project, `feeds.yaml` for config, `Item` for the dataclass, and `respx` for HTTP mocks.

## Code examples

Keep examples focused on the page goal. Include imports when the reader is likely to copy the snippet into a test or plugin file.

Use `pass` for empty async methods in Python examples. Avoid placeholder bodies that hide required behavior.
