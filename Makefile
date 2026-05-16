.PHONY: help dev check check-fast test test-cov e2e ui-test ui-build lint format coverage docs-cli docs-api docs-schema docs docs-serve new-plugin clean

help:
	@echo "Glean — common targets"
	@echo "  dev         Install all deps (Python + UI)"
	@echo "  check       Lint + type-check + unit tests (fast pre-push gate)"
	@echo "  check-fast  Lint + type-check (no tests)"
	@echo "  test        Unit tests only (parallel)"
	@echo "  test-cov    Unit tests with coverage report"
	@echo "  e2e         Docker e2e suite (mock services)"
	@echo "  ui-test     Playwright e2e suite"
	@echo "  ui-build    Build the Svelte SPA"
	@echo "  lint        Ruff + format check"
	@echo "  format      Ruff autofix + format"
	@echo "  coverage    Open coverage HTML report"
	@echo "  new-plugin  Scaffold a plugin (LAYER=source NAME=my_source)"
	@echo "  clean       Remove caches"

dev:
	uv venv
	uv sync --locked --all-extras
	cd ui && npm ci
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

check:
	uv run ruff check src tests
	uv run mypy src
	uv run pytest -q

check-fast:
	uv run ruff check src tests
	uv run mypy src

test:
	uv run pytest -q -n auto

test-cov:
	uv run pytest -q --cov=src/glean --cov-report=term-missing --cov-report=html

e2e:
	docker compose -f docker-compose.e2e.yml down -v
	docker compose -f docker-compose.e2e.yml up --build -d
	uv run pytest tests/e2e -v -m e2e
	docker compose -f docker-compose.e2e.yml down -v

ui-build:
	cd ui && npm run build

ui-test: ui-build
	cd ui && npx playwright install chromium
	cd ui && npx playwright test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

coverage: test-cov
	@echo "Open htmlcov/index.html in your browser"

docs-cli:
	uv run typer glean.cli.app utils docs --name glean --output docs/reference/cli.md
	uv run python scripts/normalize_utf8.py docs/reference/cli.md
	uv run python scripts/prepend_frontmatter.py docs/reference/cli.md "CLI \u2014 glean Reference" "All glean command-line subcommands and options."

docs-api:
	uv run python scripts/dump_openapi.py docs/openapi.json

docs-schema:
	uv run python scripts/dump_schema.py docs/reference/feeds-schema.json

docs: docs-cli docs-api docs-schema
	uv run mkdocs build --strict

docs-serve:
	uv run mkdocs serve

new-plugin:
	@if [ -z "$(LAYER)" ] || [ -z "$(NAME)" ]; then \
		echo "Usage: make new-plugin LAYER=source NAME=my_source"; exit 1; \
	fi
	uv run python scripts/new_plugin.py $(LAYER) $(NAME)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
