# Assessment evaluation matrix

The authoritative assignment provides these evaluation weights. They total
100%.

| Evaluation area | Weight | Status |
|---|---:|---|
| Agent Architecture | 20% | Verified |
| RAG Design | 15% | Verified |
| LangGraph Usage | 15% | Verified |
| RLM Implementation | 10% | Verified |
| Security & Guardrails | 10% | Partial |
| Observability | 10% | Verified |
| Async Engineering | 5% | Partial |
| RBAC | 5% | Verified for active tools |
| Code Quality | 5% | Local checks passed |
| Documentation | 5% | Synchronized |

## Evidence and limits

- **Agent Architecture:** Live OpenAI routing, Retrieval, Research, numeric
  Analysis, and citation validation passed. No production model benchmark.
- **RAG Design:** Pinecone dense, BM25, filters, IDs, and RRF passed on
  synthetic data. Four evaluation cases are only a smoke test.
- **LangGraph Usage:** Routing, bounded Research, analysis, validation, and
  SSE lifecycle passed deterministic and live checks.
- **RLM Implementation:** Live Research decomposed tasks, searched authorized
  evidence, aggregated findings, and preserved attribution under budgets.
- **Security:** Role policy, filters, schemas, citations, timeout/cancel,
  and representative prompt attacks are tested. Pattern checks do not
  detect every attack.
- **Observability:** Seven remote LangSmith trees confirmed destination,
  expected spans and parents, and hidden inputs/outputs. Synthetic data only.
- **Async Engineering:** SQLite calls are thread-offloaded and tested.
  Fixture search and Streamlit's synchronous HTTP client remain blocking.
- **RBAC:** Server roles control retrieval and active analysis tools. MCP
  has no executable server or handler.
- **Code Quality:** Local lint, format, build, type, docblock, comment, line
  length, syntax, tests, and dependency audit passed. CI runs on each push.
- **Documentation:** Architecture, security, retrieval, observability,
  evaluation, ADR, and demo guides describe behavior and known limits.

## Core implementation and verification map

### Live OpenAI workflows

- **Implementation:** `src/enterprise_assistant/llm/providers.py` and
  `src/enterprise_assistant/agents/graph.py`.
- **Tests:** `tests/unit/test_llm.py` and
  `tests/integration/test_live_workflows.py`.
- **Method/result:** Real OpenAI requests routed Retrieval, Research, and
  numeric Analysis on 2026-11-15; citations and results passed.
- **Limit:** No broad model-quality, latency, or cost benchmark.

### Pinecone retrieval and evaluation

- **Implementation:** `src/enterprise_assistant/retrieval/` and
  `scripts/ingest_pinecone.py`, `scripts/evaluate_retrieval.py`.
- **Tests:** `tests/unit/test_pinecone.py`,
  `tests/unit/test_retrieval_evaluation.py`, and the live workflow suite.
- **Method/result:** Existing index; 18 synthetic records; dense, BM25, and
  RRF checked for exact IDs, semantic retrieval, filters, and empty results.
- **Limit:** Four evaluation queries; ingestion accepts pre-chunked JSON.

### Recursive Research and incident analysis

- **Implementation:** `src/enterprise_assistant/rlm/`,
  `tools/incident_analysis.py`, and `agents/graph.py`.
- **Tests:** `tests/unit/test_rlm.py`, `tests/unit/test_graph.py`,
  `tests/unit/test_incident_analysis.py`, and
  `tests/integration/test_live_workflows.py`.
- **Method/result:** OpenAI decomposed a real investigation into multiple
  Pinecone searches; trusted Python aggregated classified incident data.
- **Limit:** Depth 2, 4 searches, 20 chunks, 30 seconds, batches of 5.

### Authorization and source integrity

- **Implementation:** `src/enterprise_assistant/security/`,
  `tools/registry.py`, `tools/knowledge.py`, and `agents/graph.py`.
- **Tests:** `tests/unit/test_security.py`, `test_pinecone.py`,
  `test_retrieval.py`, `test_graph.py`, and API integration tests.
- **Method/result:** Verified role-derived filters, metadata postchecks,
  full citation pairs, and Viewer denial of analysis.
- **Limit:** Local demo accounts and tokens are process-local.

### Prompt, input, and tool defenses

- **Implementation:** `src/enterprise_assistant/security/guardrails.py`,
  `llm/providers.py`, Pydantic contracts, and tool handlers.
- **Tests:** `tests/unit/test_security.py`, `test_llm.py`,
  `tests/integration/test_api.py`, `tests/unit/test_analysis.py`, and
  `test_incident_analysis.py`.
- **Method/result:** Representative alternate overrides and secret requests
  are rejected; retrieved instructions stay in the untrusted data payload.
- **Limit:** Pattern checks do not detect every attack.

### LangSmith observability

- **Implementation:** `src/enterprise_assistant/observability/langsmith.py`,
  `chat/service.py`, `llm/providers.py`, and `scripts/verify_langsmith.py`.
- **Tests:** `tests/unit/test_langsmith.py` and the live workflow suite.
- **Method/result:** Seven remote trace trees confirmed the agent,
  environment, expected parents, and hidden inputs/outputs.
- **Limit:** Verification used synthetic data and current workspace access.
  Trace IDs are listed in `docs/observability.md`.

### Memory, activity stream, and async reliability

- **Implementation:** `src/enterprise_assistant/memory/`, `chat/service.py`,
  API routes, `agents/graph.py`, and `apps/ui/`.
- **Tests:** `tests/unit/test_async_memory.py`,
  `tests/integration/test_api.py`, and
  `tests/integration/test_failures.py`.
- **Method/result:** Bounded history, concurrent SQLite operations,
  event-loop responsiveness, cancellation, and SSE ordering passed.
- **Limit:** SQLite is local; fixture scans and the UI HTTP client are
  synchronous. LangGraph state has no checkpointer.

### Build, CI, and operations

- **Implementation:** `.github/workflows/ci.yaml`, `compose.yaml`,
  `Dockerfile`, `Makefile`, and `uv.lock`.
- **Tests:** Local `make check` and `make audit`; CI runs tests on Python
  3.12, 3.13, and 3.14, plus Compose smoke.
- **Method/result:** Local checks passed. CI is configured to build and run
  the Compose API/UI pair; final Actions status is reported after push.
- **Limit:** Live provider verification is opt-in and has no CI secrets.

### Deferred and external requirements

- **MCP:** No server or executable tool is implemented; deferred as optional.
- **PDF/DOCX ingestion:** Missing; current ingestion consumes JSON chunks.
- **Production services:** Shared identity, quotas, and persistence are
  outside the local demonstration scope.
- **Recording:** Not included; it is handled separately.

## Retrieval evaluation result

The opt-in four-query Pinecone evaluation on 2026-11-15 returned:

| Mode | Recall@5 | MRR | Attribution | Leakage | Empty accuracy |
|---|---:|---:|---:|---:|---:|
| Dense | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |
| BM25 | 1.00 | 0.67 | 1.00 | 0.00 | 1.00 |
| Hybrid RRF | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |

The cases are few and synthetic. These scores verify the evaluator and
current fixture behavior; do not interpret them as production quality.

## Status definitions

- **Verified:** Behavior passed the stated local or live verification.
- **Partial:** Working behavior exists, with a material limit listed above.
- **Configured:** A workflow exists, but its latest external run is pending.
- **Missing/deferred:** No executable capability is included in this scope.
