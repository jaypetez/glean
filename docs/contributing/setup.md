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
