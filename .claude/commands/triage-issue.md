Triage GitHub issue $ARGUMENTS.

Steps:
1. `gh issue view $ARGUMENTS` to read the report
2. Identify type: bug | feature | question | docs
3. For bugs: try to reproduce locally (`make e2e` if needed)
4. Apply labels via `gh issue edit $ARGUMENTS --add-label <labels>`
5. Post a comment with: reproduction status, hypothesized root cause, suggested next step

Available labels: `bug`, `enhancement`, `documentation`, `question`, `good first issue`, `help wanted`, `needs-repro`, `security`.
