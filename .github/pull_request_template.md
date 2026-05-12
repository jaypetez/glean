<!--
Thanks for the PR. One concern per PR keeps reviews fast.
Fill in the sections below; write "n/a" if a section truly doesn't apply.
-->

## Summary

<!-- What does this change, and why? Link the issue: "Closes #123" or "Refs #123". -->

## Type of change

- [ ] Bug fix
- [ ] New source / LLM provider / sink
- [ ] New pipeline stage
- [ ] Refactor (no behavior change)
- [ ] Docs / examples
- [ ] CI / build / infra
- [ ] Other

## How I tested this

<!-- Commands you ran, manual checks, the feed you pointed it at. -->
- [ ] `ruff check src tests`
- [ ] `mypy src`
- [ ] `pytest -q`
- [ ] Ran the daemon locally / against a test feed

## User-visible changes

<!-- README / DESIGN.md / docs/* updates? New config keys? Breaking changes? -->

## Checklist

- [ ] No secrets, `.env` contents, or real chat IDs in the diff or tests.
- [ ] New behavior has at least one test.
- [ ] Touched `feeds.example.yaml` if I added a new source / provider / sink.
- [ ] Branch is rebased on latest `main`.
