---
title: Process the Dependabot Backlog — Agent Runbook
description: Triage, validate, and merge the open Dependabot PRs safely, then recommend a release.
---

# Process the Dependabot backlog

Run this when Dependabot's weekly batch is waiting. It works through every open Dependabot PR:
discover → triage by risk → validate → squash-merge the good ones → recommend a release when one is
warranted. Merges are **sequential** — branch protection requires branches to be up to date, so each
merge pushes the other PRs behind and triggers a rebase. Only discovery fans out; never merge in
parallel.

`/dependabot` invokes this runbook. Flags (all optional) come from `$ARGUMENTS`:

| Flag | Effect |
|------|--------|
| `PR#` | Process only that one PR (still runs the full decision tree). |
| `--auto` | Auto-merge the LOW-RISK batch without confirming each. HIGH-SCRUTINY PRs still need explicit go. |
| `--release` | After a clean batch, chain into the `/release` flow. |
| `--dry-run` | Run phases 1–3, print the commands it *would* run, mutate nothing. Overrides `--auto` / `--release`. |
| `--deep` | Force local `make check` (+ `e2e` / `ui-test`) on every PR, not just high-scrutiny ones. |
| `--ecosystem NAME` | Restrict to one ecosystem: `pip`, `github-actions`, `docker`, or `npm`. |
| `--include-human` | Also process human-authored `deps`-labelled PRs (default: report only). |

A bare `/dependabot` is interactive over all ecosystems, Dependabot-only, confirms every merge, and
cuts no release.

## Step 1 — Preflight (hard gate)

Stop and report if any check fails — do not continue to the merge logic.

```bash
# Auth: operate as the maintainer. An EMU account won't see the right PRs.
gh auth status
gh auth switch --user jaypetez            # only if the active account isn't jaypetez

# Confirm the target repo and that you can merge.
gh repo view jaypetez/glean --json nameWithOwner,defaultBranchRef,viewerPermission

# main must be green before stacking merges onto it.
gh run list --repo jaypetez/glean --branch main --limit 5

# Derive the REQUIRED checks live — don't trust committed docs, they drift.
gh api repos/jaypetez/glean/branches/main/protection \
  --jq '{checks: .required_status_checks.contexts, enforce_admins: .enforce_admins.enabled}'
```

`enforce_admins` is on for this repo: there is **no `--admin` bypass**. Every required check must be
green for any merge to go through — that is the bar.

Only if a local deep-dive will be needed (a major bump is present, or `--deep`): sync a clean tree.

```bash
git fetch origin
git checkout main && git pull --ff-only
git status --porcelain          # must be empty — never stash silently
test -f Makefile && test -f uv.lock && test -f pyproject.toml && echo ok
```

## Step 2 — Discover and triage

```bash
# Every open Dependabot PR (the author login is app/dependabot).
gh pr list --repo jaypetez/glean --author "app/dependabot" --state open --limit 100 \
  --json number,title,headRefName,labels,createdAt,mergeStateStatus,mergeable,url

# Cross-check by label to catch human-authored deps PRs (report only unless --include-human).
gh pr list --repo jaypetez/glean --state open --label deps --limit 100 \
  --json number,title,author
```

For each PR `N`, gather the evidence bundle:

```bash
gh pr view N --repo jaypetez/glean \
  --json number,title,body,headRefName,labels,files,mergeStateStatus,mergeable,state,statusCheckRollup,autoMergeRequest,headRepositoryOwner,url
gh pr checks N --repo jaypetez/glean       # do NOT pass --watch in a batch; it blocks
```

Classify each PR:

- **Ecosystem** — from the label: `python` (pip), `github-actions`, `docker`, `npm` (the `/ui` app).
- **Grouped vs single** — grouped titles read "Bump the *group* group with N updates". The pip group
  (`python-minor-patch`) and the actions group are **minor+patch only**, so a major always arrives as
  its own single PR.
- **Bump magnitude** — parse the title (`Bump X from A to B`, or `Update X requirement from >=A to >=B`).
  Strip `>=`, `^`, `~`, `v` and compare semver. A major bump where A's major is ≥ 1 is **MAJOR**; a
  `0.x` minor (e.g. `0.4` to `0.6`) is **MAJOR-equivalent**; a pre-release tag (e.g. `4.0.0a6`) gets
  MAJOR scrutiny; everything else is MINOR/PATCH.
- **Files-touched sanity** — pip changes `pyproject.toml` + `uv.lock`; actions change
  `.github/workflows/*`; docker changes `Dockerfile`; npm changes `ui/package*.json`. A mismatch is a
  red flag → HIGH-SCRUTINY.
- **CI rollup** — are all required checks green? **mergeStateStatus** — `CLEAN` / `BEHIND` / `DIRTY` /
  `BLOCKED` / `UNSTABLE`.

Bucket each PR:

- **LOW-RISK** — patch/minor or grouped, all required checks green, `mergeStateStatus=CLEAN`, not a
  docker base-image bump, no security advisory in the body.
- **HIGH-SCRUTINY** — any of: MAJOR (or `0.x` minor on a runtime dep); a docker base-image (`FROM`)
  bump; red or pending CI; `BEHIND` / `DIRTY` / `BLOCKED`; a GHSA/CVE referenced in the body; a
  files-touched mismatch.

Print a triage table, then stop for confirmation (skip the stop only under `--auto`, and even then
auto-proceed only the LOW-RISK rows):

```
#    ecosystem        grp  bump   CI     mergeState  bucket          proposed
196  github-actions   yes  minor  green  CLEAN       LOW-RISK        MERGE
195  python (dev)     no   MAJOR  green  CLEAN       HIGH-SCRUTINY   read changelog, then MERGE
199  npm              no   MAJOR  -      -           HIGH-SCRUTINY   CLOSE (superseded by #202)
```

## Step 3 — Validate

CI-green is the authoritative signal. Local `make` targets reproduce only a subset
(`check` = ruff/mypy/pytest, `e2e` = docker compose, `ui-test` = Playwright); CodeQL, Trivy, Bandit,
Secret scan, Dependency review, and Docs build run only on GitHub. Use local runs to *investigate*
high-scrutiny PRs, never to substitute for CI.

- **LOW-RISK, green, CLEAN** → verdict **MERGE**. No local run.
- **CI red** → read why:
  ```bash
  gh pr checks N --repo jaypetez/glean
  gh run view RUN_ID --repo jaypetez/glean --log-failed
  ```
  - A deterministic break (a mypy-strict error, a failing unit test, an e2e assertion) → reproduce with
    `make check` / `make e2e` / `make ui-test`. If it reproduces, it is real → **HOLD** (or
    FIX-THEN-MERGE for a trivial fix; see Step 4).
  - Flaky/infra (timeout, runner or registry 5xx, a transient GitHub-only check) → rerun **once**, then
    escalate. Never loop reruns.
    ```bash
    gh run rerun RUN_ID --repo jaypetez/glean --failed
    ```
- **BEHIND / DIRTY** → ask Dependabot to rebase, then revisit on a later sweep (do not block):
  ```bash
  gh pr comment N --repo jaypetez/glean --body "@dependabot rebase"    # or "@dependabot recreate" on conflicts
  ```
- **HIGH-SCRUTINY** → read the change and the changelog Dependabot embeds in the PR body:
  ```bash
  gh pr diff N --repo jaypetez/glean
  gh pr checkout N --repo jaypetez/glean
  make check                                  # majors and dev-tool bumps (ruff, mypy, pytest plugins)
  make e2e                                     # docker base-image bumps
  cd ui && npm ci && cd .. && make ui-test     # npm /ui bumps
  git checkout main                            # never leave the tree on a PR branch
  ```
  Local green and no relevant breaking change in the changelog → **MERGE** (still confirm explicitly).
  Local red, or a breaking change glean actually uses → **HOLD**, and report exactly what.

Record a verdict per PR — **MERGE / FIX-THEN-MERGE / HOLD / CLOSE (superseded) / REBASE** — each with a
one-line reason and an evidence pointer (a check name, a log excerpt, or the changelog line).

## Step 4 — Merge (sequential, squash only)

```bash
# If auto-merge is already enabled on the PR and it's green/CLEAN, let it fire — don't race it.
# Otherwise merge it yourself, squash only:
gh pr merge N --repo jaypetez/glean --squash --delete-branch

# --auto mode: queue the green LOW-RISK PRs so GitHub merges them as checks pass:
gh pr merge N --repo jaypetez/glean --squash --auto --delete-branch
```

Rules:

- **Squash only.** Never `--merge`, `--rebase`, `--admin`, or `--force`, and never edit branch
  protection.
- **One at a time.** After each merge the other PRs go `BEHIND`; re-check and `@dependabot rebase` the
  next before merging it. Expect to re-rebase the tail of the queue after every merge.
- **Order:** security (GHSA) first, then low-risk grouped/patch bumps, then majors and base-image bumps
  last (or split into follow-ups).
- **Superseded PRs** — a newer bump or a human PR already covers the same package. Confirm it is truly
  dominated, then close:
  ```bash
  gh pr comment N --repo jaypetez/glean --body "@dependabot close"
  ```
- **A risky member inside a group** — groups are all-or-nothing. Kick the one package out and let the
  group recreate without it, then handle that package on its own:
  ```bash
  gh pr comment N --repo jaypetez/glean --body "@dependabot ignore PACKAGE VERSION"
  ```
- **A major bump that needs a code change** (FIX-THEN-MERGE) — confirm `headRepositoryOwner` is
  `jaypetez` (a same-repo branch, not a fork) before considering a push. Prefer a separate follow-up PR
  that does the bump *and* the fix together. Only push onto the Dependabot branch for a trivial one-liner
  you will merge immediately, and **surface it to the user first** — never silently. (Pushing makes
  Dependabot stop auto-managing that branch.)

`@dependabot rebase` and `recreate` take minutes (force-push plus a full CI re-run). Issue the comment,
move on to other PRs, and revisit on the next sweep — never `sleep`-wait on Dependabot.

## Step 5 — Summarize and (maybe) release

Print the outcome — merged / held / closed / awaiting-rebase, each with its reason — then confirm main
is still green:

```bash
gh run list --repo jaypetez/glean --branch main --limit 5
gh pr list --repo jaypetez/glean --author "app/dependabot" --state open --limit 100 \
  --json number,title,mergeStateStatus
```

Every merge to main already publishes `ghcr.io/jaypetez/glean:latest` and `sha-SHORT` via CI, so a
tagged release is **not** required just to ship a bump. Recommend a release only when:

- a merged bump fixes a GHSA/CVE in a **runtime** dependency (pinned-version users won't pull `:latest`),
- a **base-image major** changed the runtime contract, or
- enough has accumulated that a clean version boundary is worthwhile.

Pure dev-tool or patch bumps do not warrant a release.

When a release is warranted, hand off — do not reinvent the release steps. Recommend `v<next>` with the
reason and tell the user to run `/release <next>`. With `--release`, chain straight into the
[Cut a release](release.md) flow. This runbook never bumps the version, tags, or pushes a tag itself.

## Safety rails

1. Never merge with a red or pending required check — all required checks green is the bar
   (`enforce_admins` is on; there is no `--admin` bypass).
2. Never bypass checks, never push directly to `main`, **squash-merge only**.
3. Confirm before every irreversible action — a merge, a close, the release hand-off. `--auto` confirms
   the LOW-RISK batch as a group but still confirms each HIGH-SCRUTINY merge individually.
4. Stop and report on ambiguity: an unparseable title, a files-touched mismatch, an unresolved conflict,
   an unclear major changelog, main red at preflight, the wrong auth account, or `viewerPermission` other
   than `ADMIN`.
5. Never hand-resolve a Dependabot conflict silently — prefer `@dependabot rebase` / `recreate`, else
   HOLD.
6. Don't touch human-authored PRs unless `--include-human`. Never leave the working tree on a PR branch.

## Reference — `@dependabot` comment commands

- `@dependabot rebase` — rebase on the latest base (use when `BEHIND`).
- `@dependabot recreate` — rebuild the PR from scratch (rebase conflicts, or to force fresh CI).
- `@dependabot close` — close the PR and delete its branch (superseded).
- `@dependabot ignore PACKAGE VERSION` — drop one package (e.g. from a group), then recreate without it.
