Add a new Source plugin named $ARGUMENTS.

Steps:
1. Run `make new-plugin LAYER=source NAME=$ARGUMENTS`
2. Read `docs/plugins/source.md` to understand the protocol
3. Implement the TODOs in the scaffolded `src/glean/sources/$ARGUMENTS.py`
4. Implement the test in `tests/test_source_$ARGUMENTS.py` using respx
5. Run `make check` until clean
6. Add a row to the Sources table in README.md
7. Commit `feat(sources): add $ARGUMENTS source` and open a PR

Always validate outbound URLs via `glean.security.ssrf.validate_url`.
