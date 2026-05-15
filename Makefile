.PHONY: help dev check test test-cov e2e ui-test ui-build lint format coverage clean

help:
	@echo "Glean — common targets"
	@echo "  dev         Install all deps (Python + UI)"
	@echo "  check       Lint + type-check + unit tests (fast pre-push gate)"
	@echo "  test        Unit tests only"
	@echo "  test-cov    Unit tests with coverage report"
	@echo "  e2e         Docker e2e suite (mock services)"
	@echo "  ui-test     Playwright e2e suite"
	@echo "  ui-build    Build the Svelte SPA"
	@echo "  lint        Ruff + format check"
	@echo "  format      Ruff autofix + format"
	@echo "  coverage    Open coverage HTML report"
	@echo "  clean       Remove caches"

dev:
	uv venv
	uv sync --locked --all-extras
	cd ui && npm ci

check:
	uv run ruff check src tests
	uv run mypy src
	uv run pytest -q

test:
	uv run pytest -q

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

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
