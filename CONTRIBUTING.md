# Contributing to glean

Thanks for your interest in `glean`. This doc covers how to file good issues, get a dev environment running, and what we'll look for in a PR.

## Ground rules

- **Open an issue first** for anything non-trivial (new source, new LLM provider, new sink, architecture change). A 2-line issue is fine — the goal is to agree on direction before you spend time.
- **One concern per PR.** A new source plugin and a refactor of the pipeline are two PRs.
- **Be kind.** We follow the [Code of Conduct](./CODE_OF_CONDUCT.md).

## Reporting bugs

Use the **Bug report** issue template. The most useful bug reports include:

- `glean version`
- The smallest `feeds.yaml` snippet that reproduces it
- What you expected vs. what happened
- Relevant log lines (set `LOG_FORMAT=json` and `LOG_LEVEL=debug` if you can)

**Never include secrets** (bot tokens, API keys, chat IDs). Redact before pasting.

## Reporting security issues

Do **not** open a public issue. See [SECURITY.md](./SECURITY.md) for the private disclosure process.

## Dev setup

```bash
git clone https://github.com/jaypetez/glean.git
cd glean
uv venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

Quick checks before pushing:

```bash
ruff check src tests
mypy src
pytest -q
```

CI runs the same three steps plus a multi-arch Docker build on `main`.

## Adding plugins

The plugin author's guides are in [`docs/plugins/source.md`](./docs/plugins/source.md) and [`docs/plugins/llm.md`](./docs/plugins/llm.md). Short version:

- **Source:** subclass `Source`, implement `fetch(ctx) -> list[Item]`, decorate with `@register_source("yourtype")`. Smallest example: `src/glean/sources/rss.py`.
- **LLM provider:** implement `rank` / `summarize` / `digest`, decorate with `@register_provider("yourname")`. Smallest example: `src/glean/llm/ollama_provider.py`.
- **Sink:** the `Sink` protocol is on the roadmap; if you're keen, the design lives in [`DESIGN.md`](./DESIGN.md). Open an issue and we'll align before you start.

Every new plugin needs:

- A unit test (mock the network; `respx` is already a dep).
- A short snippet in `feeds.example.yaml` showing how it's used.
- A row in the relevant README table.

## Commit & PR style

- Branches: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`.
- Commit messages: short imperative subject (`add reddit source`), wrap the body at ~72 cols if you need one.
- We squash-merge PRs, so the PR title becomes the commit message — make it readable.
- Rebase your branch on `main` before requesting review.
- Fill in the PR template. If a section doesn't apply, write "n/a" — don't delete it.

## What "ready to merge" looks like

- CI is green (lint, type-check, tests).
- The PR description explains *why*, not just *what*.
- New behavior has at least one test.
- User-visible changes are mentioned in the README or relevant doc.
- No secrets, no large binaries, no committed `.env` or `.venv`.

## Releases

Releases are cut from `main` by maintainers. Tagging `vX.Y.Z` triggers a release workflow that publishes a multi-arch image to `ghcr.io/jaypetez/glean`. You don't need to bump versions in your PR — that happens at release time.

## Questions

Open a [Discussion](https://github.com/jaypetez/glean/discussions) for anything that isn't a bug or a concrete feature ask.
