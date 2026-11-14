# Roadmap

## Phase 0: Foundation

- One-repository Python modular monolith with FastAPI and Streamlit processes.
- Deterministic LangGraph and retrieval flow, typed contracts, SSE activity events, SQLite sessions, development RBAC, and rate limiting.
- Docker/Compose, CI, smoke tests, architecture, and assessment evidence.

## Phase 1: Retrieval evidence slice

- Implement synthetic-document ingestion, chunking, dense embeddings, Pinecone metadata schema, and namespace handling.
- Add server-side access metadata filters and test them before retrieved text reaches graph state.
- Add a sparse/BM25 provider and RRF integration, then citation lineage and retrieval evaluation.
- Validate a real LangSmith trace against an approved test corpus.

## Phase 2: Model-backed assistant

- Add provider configuration, prompt/version governance, response grounding, bounded retries, and output guardrails.
- Add streamed graph custom events for incremental model tokens and structured tool outcomes.
- Move authentication and distributed rate limits to shared production services.

## Phase 3: Controlled research and operations

- Add bounded recursive investigation and batch analysis with cost, time, depth, document, and call budgets.
- Implement approval-gated MCP integrations and human interruption/resume.
- Add production persistence, deployment hardening, security review, quality evaluation, and operational dashboards.

The next high-value milestone is the Phase 1 retrieval evidence slice. It tests the assessment's core enterprise requirement—permission-safe, attributable hybrid knowledge retrieval—before investing in more autonomous agent behavior.
