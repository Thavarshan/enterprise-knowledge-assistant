# Assessment evaluation matrix

The assessment PDF was not available at planning time, but the supplied
Markdown assignment includes the evaluation criteria and weights. This table
copies those weights, which total 100%.

| Evaluation area | Weight | Current status | Evidence and remaining work |
|---|---:|---|---|
| Agent Architecture | 20% | In progress | Structured model routing, bounded recursive research, and grounded response generation are wired; live provider verification remains blocked on credentials. |
| RAG Design | 15% | Implemented for the synthetic corpus | Pinecone Documents API ingestion, integrated dense search, BM25 full-text search, role filters, and RRF pass the live synthetic test. Broader labeled evaluation remains. |
| LangGraph Usage | 15% | In progress | A compiled graph executes and emits node updates. OpenAI structured routing and response calls are wired; mock mode remains deterministic and live calls are unverified. |
| RLM Implementation | 10% | Implemented with mock; live-model verification pending | The executor recursively decomposes, authorizes each leaf search, enforces depth/call/document/time budgets, preserves partial findings, and fuses source identities. |
| Security & Guardrails | 10% | In progress | Server role checks, strict numeric tool inputs, full citation identities, and a pre-persistence override/exfiltration guard are tested. Pattern coverage is intentionally limited and needs adversarial evaluation. |
| Observability | 10% | In progress | Structured logs and graph activity events work. A redacted LangSmith trace has been verified; real model-backed parent-child traces remain blocked on model credentials. |
| Async Engineering | 5% | In progress | API routes, graph nodes, and provider/retrieval adapters are async. SQLite, local fixture scanning, and the Streamlit HTTP client still perform blocking work. |
| RBAC | 5% | Implemented for active tools | Server-assigned roles control knowledge search and Python analysis; MCP has no executable handler. |
| Code Quality | 5% | Implemented | Ruff, formatting, type, docstring, comment, line-length, syntax, build, test, and dependency-audit checks run in CI. |
| Documentation | 5% | Implemented | Architecture, lifecycle, security, assumptions, decisions, and implementation limits are documented. |

## Implementation evidence

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
| Pinecone-backed dense retrieval and ingestion | Implemented | `retrieval/pinecone.py`, `scripts/ingest_pinecone.py`; the configured existing document schema accepts stable synthetic source IDs. |
| Sparse/BM25 and hybrid retrieval | Implemented | Pinecone `TextQuery` runs BM25 full-text ranking; `EmbedQuery` returns dense ranking; `HybridRetriever` fuses both through RRF. |
| Pinecone metadata authorization and retrieval quality | Verified | Opt-in live integration test checks provider filters, viewer restrictions, semantic paraphrase, and exact incident-ID ranking in `assessment-demo`. |
| Recursive research and execution budgets | Implemented with mock | `rlm/executor.py`; tests verify nested decomposition, multi-subtask incident search, source attribution, partial failures, and depth/call/document/time limits. No model-generated code is executed. |
| Python analysis tool | Implemented for bounded arithmetic | `tools/analysis.py`; count, sum, and average accept only explicit finite numeric literals, with analyst/administrator authorization. |
| LangSmith conversations, graph, tool, retrieval, and failure traces | In progress | `observability/langsmith.py` and a redacted external trace verify the existing path; model-backed parent-child trace evidence remains. |
| Prompt injection, exfiltration, unsafe tools, output policies | In progress | Fixed model instructions treat user/history/document content as untrusted. Clear override/exfiltration requests are rejected before persistence; arbitrary code execution is absent; broader adversarial coverage remains. |
| Docker Compose, reproducible lock, and CI | Implemented | `Dockerfile`, `compose.yaml`, `uv.lock`, `.github/workflows/ci.yaml`; CI builds and starts both Compose services and checks API/UI connectivity. |
| MCP server, semantic memory, approval flow | Deferred | These capabilities are outside the current implementation milestone. |
| Repository-wide Python documentation enforcement | Implemented | Ruff Google pydocstyle rules, AST coverage validation, Makefile, pre-commit, CI, and validator tests. |

## Status meanings

- **Implemented:** the behavior exists and is covered by local
  verification where applicable.
- **In progress:** functioning behavior exists, with identified verification
  or integration gaps remaining.
- **Scaffolded:** the contract or integration boundary exists, but the
  production capability is not complete.
- **Planned:** a defined next milestone exists without a complete interface
  or behavior.
- **Deferred:** intentionally outside the current milestone.
