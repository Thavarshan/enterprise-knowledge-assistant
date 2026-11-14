.PHONY: setup dev api ui test lint format format-check typecheck audit check docker-up docker-down

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

lint:
	uv run ruff check .

format:
	uv run autopep8 --in-place --recursive src apps tests scripts

format-check:
	uv run autopep8 --diff --recursive --exit-code src apps tests scripts

typecheck:
	uv run mypy src apps

audit:
	uv run pip-audit --local --skip-editable --progress-spinner off

check: lint format-check typecheck test

docker-up:
	docker compose up --build

docker-down:
	docker compose down
