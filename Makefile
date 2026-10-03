UV_CACHE_DIR ?= /private/tmp/centeralign-uv-cache
export UV_CACHE_DIR

.PHONY: test lint smoke sandbox dev eval eval-live
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
	uv run python -m evals.run --live
	uv run python -m scripts.update_readme_metrics
