Work through the open Dependabot PR backlog: $ARGUMENTS (flags optional; a bare run is interactive over every ecosystem).

Follow `docs/agents/dependabot.md` exactly.

Usage: `/dependabot [PR#] [--auto] [--release] [--dry-run] [--deep] [--ecosystem NAME] [--include-human]`

Phases:
1. Preflight — `gh auth status` (switch to `jaypetez` if needed), confirm the repo + ADMIN access, confirm `main` CI is green, derive the required checks from the live branch-protection API. Stop if any fail.
2. Discover & triage — list `app/dependabot` open PRs; classify each by ecosystem, bump magnitude, CI status, and merge state into LOW-RISK or HIGH-SCRUTINY; print the triage table.
3. Validate — CI-green is authoritative; deep-dive locally (`make check` / `make e2e` / `make ui-test`) only for major bumps, base-image bumps, or red CI. Rerun a flaky check at most once.
4. Merge — squash only, one at a time, confirming each (or auto-merge the LOW-RISK batch with `--auto`). Rebase / recreate / close via `@dependabot` comments. Never `--admin`.
5. Summarize & release — recommend a release only when warranted (GHSA fix, base-image major, meaningful accumulation) and hand off to `/release`; `--release` chains it. Never tag or push a tag directly.

Default (no flags): interactive, confirm every merge, no release.

Stop and report any failures — never force, bypass checks, push to `main`, or skip steps.
