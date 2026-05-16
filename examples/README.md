# glean examples

Self-contained quickstart scenarios. Pick the one closest to your goal, run its setup script, and you have a working glean stack in minutes.

## Available examples

| # | Name | Stack | Time to first digest |
|---|------|-------|----------------------|
| 01 | [web-search-local-llm](01-web-search-local-llm/) | Glean + Ollama (qwen2.5:7b) + SearXNG → file sink | ~10 min (mostly model pull) |

## How to use

```bash
cd examples/01-web-search-local-llm
./setup.sh        # Linux / macOS
# or
./setup.ps1       # Windows PowerShell
```

The setup script:

1. Verifies prerequisites (Docker, openssl, curl).
2. Generates required secrets into a local `.env`.
3. Brings up the compose stack.
4. Pulls the LLM model.
5. Runs a dry-run of the first feed and prints next steps.

Every example is **self-contained**: it has its own `docker-compose.yml`, `feeds.yaml`, and `.env.example`. It will not interfere with a glean install elsewhere on your machine (different container names, separate `data/` volume).

## Conventions for new examples

If you add an example, follow this layout:

```
NN-short-slug/
├── README.md                # What this demonstrates + manual steps if curious
├── setup.sh                 # POSIX setup (≤100 lines, idempotent)
├── setup.ps1                # Windows setup (same behavior)
├── teardown.sh              # docker compose down -v + cleanup
├── docker-compose.yml       # All services this example needs
├── feeds.yaml               # The feed(s)
├── .env.example             # Copied to .env by setup.sh
└── (optional) config/       # Sidecar config files (e.g. searxng-config/)
```

Rules:

- **Container names** must be prefixed `glean-ex<NN>-*` so they don't collide with each other or a real install.
- **Volumes** must use a relative `./data` directory (gitignored), not a named Docker volume — easier to inspect and delete.
- **Setup script is idempotent**: re-running must not break a working stack.
- **No real secrets**: every credential is either generated locally (e.g. `SEARXNG_SECRET`) or a placeholder the user replaces.
- **Output** goes to `./data/digests/` so users can immediately see results.

## Removing an example

```bash
cd examples/NN-short-slug
./teardown.sh
```

This stops the compose stack, removes its volumes, and deletes the local `data/` directory for that example only.
