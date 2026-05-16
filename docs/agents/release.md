---
title: Cut a Release — Agent Runbook
description: Step-by-step for bumping the version and tagging a glean release.
---

# Cut a release

## Step 1 — Verify all CI checks green on main

```bash
gh run list --branch main --limit 5
```

## Step 2 — Bump version

Edit `pyproject.toml` and `src/glean/__init__.py` to the new version. Run `uv lock`.

## Step 3 — Open release PR

If GitHub CLI is authenticated with an EMU account, switch first:

```bash
gh auth switch --user jaypetez
```

Then open and queue the release PR:

```bash
git checkout -b chore/release-<version>
git add pyproject.toml src/glean/__init__.py uv.lock
git commit -m "chore: bump version to <version>" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
gh pr create --base main --head chore/release-<version> --title "chore: release v<version>"
gh pr merge --auto --squash --delete-branch
```

## Step 4 — Tag after merge

```bash
git checkout main && git pull
git tag -a v<version> -m "Release v<version>"
git push origin v<version>
```

## Step 5 — Watch the release workflow

```bash
gh run watch
```

The `release.yml` workflow will publish to `ghcr.io`, build standalone binaries, and create the GitHub release.
