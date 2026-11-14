# Architecture Decision Records

These records describe decisions evidenced by the current source or explicit
roadmap. They do not imply that the named alternatives were discussed by a
historical team. Where alternatives are listed, they are analytical options
for future review.

Accepted records describe the current foundation. Proposed records describe
an identified design boundary whose production implementation is incomplete.
The status does not imply that a provider connection or control has been
verified.

## Index

| ADR | Decision | Status |
|---|---|---|
| 0001 | Modular monolith with separate API and UI processes | Accepted |
| 0002 | Deterministic LangGraph workflow and structured events | Accepted |
| 0003 | Pinecone dense and BM25 hybrid retrieval | Accepted |
| 0004 | Owner-scoped SQLite session persistence | Accepted |
| 0005 | Local identity and backend role policy | Accepted |
| 0006 | Logs, graph events, and optional LangSmith tracing | Accepted |
| 0007 | Async API boundaries with local and remote adapters | Accepted |
| 0008 | Structured Research executor with shared budgets | Accepted |
| 0009 | Multi-cloud modular monolith: Vercel, Streamlit, D1 | Accepted |

## Record template

Each ADR uses this structure:

1. Status
2. Context
3. Decision
4. Alternatives Considered
5. Rationale
6. Trade-offs
7. Consequences
8. Security and Operational Implications
9. Revisit Conditions
