# Enterprise Knowledge Assistant

An explainable, multi-agent enterprise assistant foundation, delivered as one Python modular monolith. This phase provides deterministic mock conversations, API and Streamlit processes, session persistence, role-aware retrieval, and an executable LangGraph workflow.

## Architecture

```mermaid
flowchart LR
    UI[Streamlit UI] -->|HTTP + SSE| API[FastAPI]
    API --> AUTH[Authentication and RBAC]
    API --> LIMIT[Per-user rate limiter]
    API --> MEM[(SQLite sessions)]
    API --> GRAPH[LangGraph]
    GRAPH --> SUP[Supervisor]
    SUP -->|direct question| RET[Retrieval]
    SUP -->|investigation| RES[Research plan]
    RES --> RET
    RET --> MOCK[Fixture-backed retrieval]
    RET -. planned adapter .-> PINE[Pinecone dense + sparse]
    RET --> RESP[Grounded response]
    RESP --> VAL[Citation validation]
    GRAPH -. optional tracing .-> LS[LangSmith]
```

FastAPI and Streamlit run as separate processes because they have different runtime needs. They share one repository, package, lockfile, and Compose build. Internal capabilities remain in one deployable Python package.

## Requirements and quick start

- Python 3.13 (3.12+ is supported), `uv`, and GNU Make.
- Docker and Docker Compose are optional for containerized startup.

```bash
uv sync
make setup   # creates ignored .env and prints one-time demo credentials
make dev     # starts FastAPI on :8000 and Streamlit on :8501
```

Use the displayed `viewer`, `analyst`, or `admin` credentials in the UI. `make dev` keeps both processes in the foreground; Ctrl+C stops them. Alternatively, run `make api` and `make ui` in separate terminals after setup.

Open [http://localhost:8501](http://localhost:8501). The UI logs in through the API, creates an owned session, and consumes the API's SSE stream. The mock graph returns synthetic, cited evidence without paid provider keys.

## VS Code Python tooling

The workspace formats Python files on save with Autopep8 at an 80-character
line limit. Ruff enforces the same limit in editor diagnostics and CI; Pylint
is disabled for this workspace to avoid duplicate linter output. Install the
recommended VS Code extensions from `.vscode/extensions.json`.

## Docker

Run `make setup` once to create the local ignored `.env`, then:

```bash
docker compose up --build
```

The API and UI containers use the same image and environment file. SQLite data is persisted in the local `data/` directory. `docker compose down` stops the services; it does not remove that local database.

## Development commands

```bash
uv sync --all-groups
make test
make lint
make format-check
make typecheck
make audit
make check
```

`uv.lock` pins the resolved dependency graph. Autopep8 formats Python files; Ruff handles linting and import fixes. GitHub Actions checks Python 3.12 through 3.14, audits installed dependencies weekly and on each change, and builds and starts both Docker services. No CI job requires external credentials.

## Configuration

Copy `.env.example` to `.env`, or let `make setup` generate local-only
credentials. `.env` is ignored by Git. The mock system works without
model-provider keys. `LANGSMITH_TRACING` is off by default and can be enabled
with a valid `LANGSMITH_API_KEY` and project name. Set
`LANGSMITH_WORKSPACE_ID` when your LangSmith credentials require an explicit
workspace. Pinecone settings are reserved for the future production adapter.

Important settings include `MOCK_MODE`, `API_BASE_URL`, `SQLITE_PATH`, CORS origins, rate-limit capacity/refill, LangSmith tracing, and Pinecone index/namespace configuration. Never commit `.env` or real provider credentials.

## What is implemented

- Async FastAPI app factory, lifespan, request IDs, JSON logs, CORS, health/readiness, typed routes, and SSE contracts.
- Development authentication with server-side role assignment, backend tool permission checks, and in-memory per-user token buckets.
- SQLite session ownership and turn history.
- A compiled LangGraph graph that streams actual node updates from Supervisor, optional Research planning, Retrieval, Response, and citation validation nodes.
- Deterministic fixture retrieval with access filtering before evidence enters graph state. Citations resolve to actual synthetic chunks.
- Streamlit login/session controls, chat history, response streaming, and graph activity display.
- LangSmith tracing hook through the supported LangChain/LangGraph environment integration; no live trace has been claimed or verified.

## Boundaries and limitations

Pinecone indexing, embedding, sparse ranking, and live hybrid retrieval are interfaces/plans only. The mock adapter uses deterministic lexical matching. The documented production merge strategy is reciprocal-rank fusion so dense and sparse scores are not treated as directly comparable.

Research currently produces a restricted structured plan and permits one bounded retrieval pass. It does not execute generated code or recurse. There is no live LLM, MCP server, production identity provider, distributed rate limiter, semantic memory, or human approval flow. The token registry and event schema are extension points, not evidence that those integrations are complete. In-memory rate limits and login tokens do not coordinate across API processes.

LangSmith auto-tracing is configured when enabled and credentials are present; validation against the external service remains outstanding. The Streamlit UI makes a synchronous HTTP call while consuming the streamed response, which is suitable for local demonstration.

## Assessment status

See [the evaluation matrix](docs/evaluation-matrix.md) for requirement weights, implementation status, evidence locations, and remaining work. Architecture and assumptions are documented in `docs/`; concise decisions are in `docs/decisions/`.

## Next milestone

Implement a real Pinecone ingestion and hybrid retrieval slice with role-filtered metadata, citation checks, and LangSmith traces. This validates the highest-risk retrieval and observability assumptions before adding model-driven recursive research.
