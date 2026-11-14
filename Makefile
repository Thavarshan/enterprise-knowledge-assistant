.PHONY: setup dev api ui test lint comments-check line-length-check \
	format format-check build typecheck docs-check syntax-check audit check \
	docker-up docker-down langsmith-check

setup:
	uv sync --all-groups
	uv run python scripts/bootstrap_dev_env.py

dev:
	uv sync --all-groups
	uv run python scripts/run_dev.py

api:
	uv run uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	uv run streamlit run apps/ui/main.py

test:
	uv run pytest -q

langsmith-check:
	uv run python scripts/check_langsmith.py

lint:
	uv run ruff check .

comments-check:
	uv run ruff check --select ERA001 .

line-length-check:
	uv run ruff check --select E501 .

format:
	uv run autopep8 --in-place --recursive src apps tests scripts

format-check:
	uv run autopep8 --diff --recursive --exit-code src apps tests scripts

build:
	uv build

typecheck:
	uv run mypy src apps

docs-check:
	uv run python scripts/check_docstrings.py

syntax-check:
	uv run python -m compileall -q src apps scripts tests

audit:
	uv run pip-audit --local --skip-editable --progress-spinner off

check: lint comments-check line-length-check format-check build typecheck \
	docs-check syntax-check test

docker-up:
	docker compose up --build

docker-down:
	docker compose down
