Add a new Sink plugin named $ARGUMENTS.

Steps:
1. Run `make new-plugin LAYER=sink NAME=$ARGUMENTS`
2. Read `docs/plugins/sink.md` to understand the protocol
3. Implement the TODOs in the scaffolded `src/glean/sinks/$ARGUMENTS.py`
4. Implement the test in `tests/test_sink_$ARGUMENTS.py` using respx when network I/O is involved
5. Run `make check` until clean
6. Add a row to the Sinks table in README.md
7. Commit `feat(sinks): add $ARGUMENTS sink` and open a PR

Always validate outbound URLs via `glean.security.ssrf.validate_url` when the sink makes HTTP requests.
