Run `make check` and fix every failure systematically.

Approach:
1. Run `make check`
2. If lint errors: run `uv run ruff check --fix src tests` and re-check
3. If type errors: read each error, identify the root cause (not just the symptom), fix it, re-run mypy
4. If test failures: read the failing test, understand the contract, fix the production code (not the test) unless the test itself is wrong
5. Loop until 0 failures across all three checks

Do NOT skip steps or claim success without re-running `make check` and seeing exit code 0.
