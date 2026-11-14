# Assessment evaluation matrix

The assessment PDF was not available at planning time, but the supplied
Markdown assignment includes the evaluation criteria and weights. This table
copies those weights, which total 100%.

| Evaluation area | Weight | Phase 0 status | Evidence and remaining work |
|---|---:|---|---|
| Agent Architecture | 20% | In progress | Structured model routing and grounded response generation are wired; live provider verification and recursive research remain. |
| RAG Design | 15% | Scaffolded | Fixture retrieval and an RRF utility exist. Pinecone ingestion, dense embeddings, BM25, and connected hybrid search remain. |
| LangGraph Usage | 15% | In progress | A compiled graph executes and emits node updates. OpenAI structured routing and response calls are wired; mock mode remains deterministic and live calls are unverified. |
| RLM Implementation | 10% | Scaffolded | Structured plan and budget contracts exist. Recursive execution, batching, aggregation, and timeout enforcement remain. |
| Security & Guardrails | 10% | In progress | Development authentication, backend role checks, request validation, and full document/chunk citation matching work. Model-facing defenses need additional coverage. |
| Observability | 10% | In progress | Structured logs and graph activity events work. A redacted LangSmith trace has been verified; real model-backed parent-child traces remain blocked on model credentials. |
| Async Engineering | 5% | Scaffolded | API routes and graph nodes are async. SQLite, fixture scanning, and the Streamlit HTTP client still perform blocking work. |
| RBAC | 5% | Implemented | Server-assigned roles are enforced for the active knowledge-search tool. Analytics and MCP tools are not executable yet. |
| Code Quality | 5% | Implemented | Ruff, formatting, type, docstring, comment, line-length, syntax, build, test, and dependency-audit checks run in CI. |
| Documentation | 5% | Implemented | Architecture, lifecycle, security, assumptions, decisions, and implementation limits are documented. |

## Phase 0 implementation evidence

| Requirement area | Status | Evidence and remaining work |
|---|---|---|
| Modular monolith and shared Python environment | Implemented | `pyproject.toml`, `uv.lock`, `src/enterprise_assistant/`; Compose services share one image. |
| Async FastAPI, versioned API, contracts, health, request IDs, JSON logs, CORS | Implemented | `api/application.py`, `api/middleware.py`, `api/routes/`, `observability/logging.py`. |
| SSE event contract and structured graph activity | Implemented | `observability/events.py`, `chat/service.py`, `api/routes/chat.py`; events come from LangGraph updates. |
| Streamlit chat, session selection, login, activity and error feedback | Implemented | `apps/ui/`; the API client consumes SSE and renders activity and validation. |
| Executable Supervisor/Retrieval/Research/Response/Validate graph | Implemented | `agents/graph.py`; deterministic routing, fixture search, response, citations, and actual graph updates. |
| Session ownership and persistent turns | Implemented | `memory/sqlite.py`; owner identity is included in session queries. Recent owner-scoped turns are now included in graph state. |
| Development authentication and backend RBAC | Implemented | `security/authentication.py`, `security/authorization.py`, `tools/registry.py`; identity comes from API token state. |
| In-memory per-user token bucket | Implemented | `security/rate_limiting.py`; state is not shared between processes or instances. |
| Fictional banking sample documents and citation checks | Implemented | `data/samples/documents.json`, `agents/graph.py`, unit and integration tests. |
| Retrieval interfaces and local deterministic adapter | Implemented | `retrieval/interfaces.py`, `retrieval/in_memory.py`; search uses lexical matching only. |
| Pinecone-backed dense retrieval and ingestion | Scaffolded | `retrieval/pinecone.py` and settings define the boundary; no SDK client, indexing, embeddings, or provider query exists. |
| Sparse/BM25 and hybrid retrieval | Scaffolded | `retrieval/sparse.py`, `retrieval/hybrid.py`; RRF is implemented but no dense or sparse source is connected. |
| RLM planning, batching, depth and execution budgets | Scaffolded | `rlm/contracts.py`; one query and result limit are used. Timeout is not enforced; decomposition and batching are unused. |
| LangSmith conversations, graph, tool, retrieval, and failure traces | In progress | `observability/langsmith.py` and a redacted external trace verify the existing path; model-backed parent-child trace evidence remains. |
| Prompt injection, exfiltration, unsafe tools, output policies | In progress | Fixed model instructions treat user/history/document content as untrusted; complete citation pairs are checked. Tool validation and automated injection tests remain. |
| Docker Compose, reproducible lock, and CI | Implemented | `Dockerfile`, `compose.yaml`, `uv.lock`, `.github/workflows/ci.yaml`; CI builds and starts both Compose services and checks API/UI connectivity. |
| Recursive research, MCP server, semantic memory, approval flow | Deferred | Remaining implementation milestones are documented in `docs/roadmap.md`. |
| Repository-wide Python documentation enforcement | Implemented | Ruff Google pydocstyle rules, AST coverage validation, Makefile, pre-commit, CI, and validator tests. |

## Status meanings

- **Implemented:** the Phase 0 behavior exists and is covered by local
  verification where applicable.
- **Scaffolded:** the contract or integration boundary exists, but the
  production capability is not complete.
- **Planned:** a defined next milestone exists without a complete interface
  or behavior.
- **Deferred:** intentionally outside Phase 0 scope.
