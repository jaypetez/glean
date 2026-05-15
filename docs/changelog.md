---
title: "Changelog — glean Changelog"
description: Release highlights for recent glean versions with links to full GitHub release notes.
---

# Changelog

Release notes are maintained on [GitHub Releases](https://github.com/jaypetez/glean/releases).

## v1.3.0 — 2026-05-15

[Full release notes](https://github.com/jaypetez/glean/releases/tag/v1.3.0)

### Highlights

- E2E + agent-friendliness initiative (PRs #134-140): agent docs, DST regression coverage, property tests, API fuzzing, developer workflow, E2E stability, trace IDs, and richer health output.
- SQLite schema migrations via yoyo (PR #139); operators can run `glean migrate --db /data/state.db` explicitly after upgrade.
- Dependency maintenance for UI and Python packages, including Svelte, devalue, ruff, pytest-cov, ruamel.yaml, structlog, and GitHub Actions updates.

## v1.2.0 — 2026-05-15

[Full release notes](https://github.com/jaypetez/glean/releases/tag/v1.2.0)

### Highlights

- Security audit complete: API key disclosure fix, auth warnings, verifier permissions, secret scrubbing, SSRF protections, prompt-injection defenses, response caps, and sink URL/path validation.
- Runtime hardening: SQLite safety PRAGMAs, HTTP security headers, body limits, rate limiting, Swagger gating, SSE token hardening, subscriber caps, and origin checks.
- Supply-chain and deployment hardening: digest-pinned containers, reduced container privileges, read-only mounts, SearXNG hardening, vulnerable curl removal, CI hardening, Trivy gates, cosign verification docs, and LLM call budgets.

## v1.1.0 — 2026-05-14

[Full release notes](https://github.com/jaypetez/glean/releases/tag/v1.1.0)

### Highlights

- Full management Web UI: live dashboard, feed editor, skill editor, setup wizard, settings page, theme/density controls, and API key rotation.
- FastAPI foundation with REST config/status/run routes, shared CLI/API service layer, SSE live updates, health checks, and API key persistence across restarts.
- Playwright E2E coverage with axe-core accessibility checks and visual snapshots, plus README screenshots and updated v1.1 feature documentation.
