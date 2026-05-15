---
title: Publishing Plugins — glean
description: Share plugin ideas today and upstream plugins through focused pull requests.
---

# Publishing Plugins

This page is for authors who want to share a plugin beyond a local fork. Glean does not load third-party plugin packages at runtime yet, so production plugins must be merged into this repository.

## Package names for informal sharing

If you publish an experiment as its own repository, use a pip-style prefix that names the plugin layer:

| Layer | Suggested package name |
|---|---|
| Source | `glean-source-myname` |
| Sink | `glean-sink-myname` |
| LLM provider | `glean-llm-myname` |
| Search backend | `glean-search-myname` |

This mirrors conventions such as the `pytest-` prefix. It also makes the layer clear in package indexes and GitHub search.

## Share informally

For experiments that are not ready to upstream, create a GitHub repository with:

- The plugin file.
- A short `feeds.yaml` snippet.
- Test instructions and expected output.
- The glean version or commit you tested against.

Then link the repository in [GitHub Discussions](https://github.com/jaypetez/glean/discussions). Mention whether you want feedback, users, or upstream review.

## Upstream through a PR

Open an issue before writing a non-trivial plugin. The issue can be short: name the service, link the API docs, describe auth needs, and note any rate limits.

Keep the PR focused:

1. Add one plugin file under `src/glean/sources/`, `src/glean/sinks/`, `src/glean/llm/`, or `src/glean/search/`.
2. Add one test file that uses `respx` or fakes instead of real services.
3. Add a `feeds.example.yaml` entry that shows the YAML users need.
4. Update the relevant docs page under `docs/plugins/`.

Run the docs and lint checks before pushing:

```bash
uv run mkdocs build --strict
uv run ruff check src tests
```

Expected output:

```text
INFO    -  Documentation built in ...
All checks passed!
```

## Future third-party loading

A third-party loading model is a roadmap item. When PR5 adds the roadmap page, this section should link to [roadmap.md](https://github.com/jaypetez/glean/blob/main/docs/roadmap.md) for the design and tracking issue.
