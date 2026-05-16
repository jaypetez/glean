Add a new LLM provider named $ARGUMENTS.

Steps:
1. Run `make new-plugin LAYER=llm NAME=$ARGUMENTS`
2. Read `docs/plugins/llm.md` to understand the `rank` / `summarize` / `digest` / `extract` / `aclose` protocol
3. Implement the TODOs in the scaffolded `src/glean/llm/$ARGUMENTS.py`
4. Implement the test in `tests/test_llm_$ARGUMENTS.py`
5. Run `make check` until clean
6. Add a row to the LLM Providers table in README.md
7. Commit `feat(llm): add $ARGUMENTS provider` and open a PR
