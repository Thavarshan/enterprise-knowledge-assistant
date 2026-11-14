FROM ghcr.io/astral-sh/uv:0.13.7 AS uv-bin
FROM python:3.13-slim

COPY --from=uv-bin /uv /uvx /bin/
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY apps ./apps
COPY data ./data
RUN uv sync --locked --no-dev

EXPOSE 8000 8501

CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
