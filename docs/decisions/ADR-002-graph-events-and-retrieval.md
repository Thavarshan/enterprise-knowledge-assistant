# ADR 002: Stream actual graph updates and fuse retrieval by rank

- **Status:** Accepted
- **Decision:** Derive visible activity from LangGraph `astream` node updates and serialize it as a stable SSE schema. Use reciprocal-rank fusion for future dense and sparse retrieval lists.
- **Reason:** The activity panel must describe executed graph transitions, and raw dense/sparse scores may not share a comparable scale.
- **Consequences:** A node's current deterministic events are emitted when that node completes. The mock response chunks are streamed as events; a future model adapter should use LangGraph custom streaming for token-by-token output.
