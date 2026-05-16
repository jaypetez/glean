Cut a release: $ARGUMENTS (e.g., `0.5.0`).

Follow `docs/agents/release.md` exactly. Verify:
1. All required CI checks green on main
2. Bump version in `pyproject.toml` and `src/glean/__init__.py`
3. Run `uv lock`
4. Open `chore/release-$ARGUMENTS` PR with `chore: release v$ARGUMENTS`
5. After merge, tag `v$ARGUMENTS` and push
6. Watch the release workflow

Stop and report any failures — never force or skip steps.
