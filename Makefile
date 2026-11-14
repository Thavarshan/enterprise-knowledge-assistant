.PHONY: setup dev api ui test lint format format-check typecheck check docker-up docker-down

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
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy src apps

check: lint format-check typecheck test

docker-up:
	docker compose up --build

docker-down:
	docker compose down
