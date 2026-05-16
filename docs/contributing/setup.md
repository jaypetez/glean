---
title: Development Setup Notes — glean Contributing
description: Platform-specific setup notes for local glean development.
---

# Development Setup Notes

This page collects small setup notes that are useful during local development but too detailed for the top-level contributor docs.

## Windows

If you want to use the `make` shortcuts, install `make` with Chocolatey:

```powershell
choco install make
```

If you do not want to install `make`, use WSL or run the underlying commands directly (`uv run ...`, `npm ...`, and `docker compose ...`).

## Python + UI dependencies

For a full local setup, install Python and UI dependencies from the repo root:

```bash
uv sync --locked --all-extras
cd ui && npm ci
```

## Conventional commits

We use [conventional commits](https://www.conventionalcommits.org/). PR titles become commit messages on squash-merge, so PR titles must follow the convention:

```text
<type>(<scope>): <subject>
```

Allowed types: `feat`, `fix`, `docs`, `chore`, `ci`, `test`, `refactor`, `perf`, `build`, `style`, `revert`.

Locally, install the commit-msg hook so your individual commits are checked too:

```bash
uv run pre-commit install --hook-type commit-msg
```

`make dev` does this automatically.
