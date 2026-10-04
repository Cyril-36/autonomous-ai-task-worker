UV_CACHE_DIR ?= /private/tmp/centeralign-uv-cache
export UV_CACHE_DIR

.PHONY: setup test lint smoke sandbox dev eval eval-live reset-demo
setup:
	uv sync --locked
	uv run playwright install chromium
	npm --prefix console ci
	npm --prefix console run build
test:
	uv run pytest
lint:
	uv run ruff check .
smoke:
	uv run python scripts/smoke_llm.py
sandbox:
	uv run python -m scripts.serve_sandbox
dev:
	uv run python -m scripts.dev
eval:
	uv run python -m evals.run
	uv run python -m scripts.update_readme_metrics
eval-live:
	uv run python -m evals.run --live --suite dev --out LIVE_DEV_AFTER.md
	uv run python -m scripts.update_readme_metrics
# Fresh sandbox data for a demo; keeps the evaluation spending ledger.
reset-demo:
	rm -rf data/portal.db data/register.db data/worker.db data/artifacts data/traces
