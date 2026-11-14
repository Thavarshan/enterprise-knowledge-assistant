# Assessment evaluation matrix

The source PDF containing evaluator weightings was not available in the supplied environment. The pasted fallback contains requirements but no numeric scores, so the weighting column is recorded transparently as unavailable rather than estimated. Provide the assessment PDF to map exact weights.

| Requirement area | Evaluator weighting | Status | Evidence and remaining work |
|---|---|---|---|
| Modular monolith and shared Python environment | Not supplied | Implemented | `pyproject.toml`, `uv.lock`, `src/enterprise_assistant/`, Compose services share one image. |
| Async FastAPI, versioned API, contracts, health, request IDs, JSON logs, CORS | Not supplied | Implemented | `api/application.py`, `api/middleware.py`, `api/routes/`, `observability/logging.py`. |
| SSE event contract and structured graph activity | Not supplied | Implemented | `observability/events.py`, `chat/service.py`, `api/routes/chat.py`; events come from LangGraph updates. |
| Streamlit chat, session selection, login, activity and error feedback | Not supplied | Implemented | `apps/ui/`; API client consumes SSE and renders current node, tools, retrieval, and validation. |
| Executable Supervisor/Retrieval/Research/Response/Validate LangGraph | Not supplied | Implemented | `agents/graph.py`; deterministic route, fixture search, response, citations, actual graph stream. Model reasoning remains deferred. |
| Session ownership and persistent turns | Not supplied | Implemented | `memory/sqlite.py`; owner is part of each session query. |
| Development authentication and backend RBAC | Not supplied | Implemented | `security/authentication.py`, `security/authorization.py`, `tools/registry.py`; identity comes from API token state. |
| In-memory per-user token bucket | Not supplied | Implemented | `security/rate_limiting.py`; not shared between processes or instances. |
| Fictional banking sample documents and citation checks | Not supplied | Implemented | `data/samples/documents.json`, `agents/graph.py`, unit/integration tests. |
| Retrieval interfaces and local deterministic adapter | Not supplied | Implemented | `retrieval/interfaces.py`, `retrieval/in_memory.py`; lexical mock search only. |
| Pinecone-backed dense retrieval and ingestion | Not supplied | Scaffolded | `retrieval/pinecone.py` and settings define the adapter boundary; live SDK, indexing, embeddings, and queries remain. |
| Sparse/BM25 and hybrid retrieval | Not supplied | Scaffolded | `retrieval/sparse.py`, `retrieval/hybrid.py`; RRF fusion is implemented, but no live dense/sparse sources are connected. |
| RLM planning, batching, depth and execution budgets | Not supplied | Scaffolded | `rlm/contracts.py`; one query, depth, call count, and result limit are used. Timeout is not enforced; decomposition and batching are unused. |
| LangSmith conversations, graph, tool, retrieval, and failure traces | Not supplied | Scaffolded | `observability/langsmith.py` configures native tracing when enabled; no successful external trace has been verified. |
| Prompt injection, exfiltration, unsafe tools, output policies | Not supplied | Scaffolded | `security/guardrails.py` contracts; concrete model-facing protections remain. Backend role checks and citation-marker validation exist; full document/chunk pair validation is a known gap. |
| Docker, Compose, reproducible lock, CI | Not supplied | Implemented | `Dockerfile`, `compose.yaml`, `uv.lock`, `.github/workflows/ci.yaml`; exact local build/start results are reported in the final verification. |
| Production model provider, full research, MCP server, semantic memory, approval flow | Not supplied | Deferred | Roadmap milestones documented in `docs/roadmap.md`. |
| Repository-wide Python documentation enforcement | Not supplied | Implemented | Ruff Google pydocstyle rules, AST coverage validation, Makefile, pre-commit, CI, and validator tests. |

## Status meanings

- **Implemented:** the Phase 0 behavior exists and is covered by local verification where applicable.
- **Scaffolded:** the contract or integration boundary exists, but the production capability is not complete.
- **Planned:** a defined next milestone exists without a complete interface or behavior.
- **Deferred:** intentionally outside Phase 0 scope.
