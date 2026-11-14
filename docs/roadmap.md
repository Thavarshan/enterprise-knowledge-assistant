# Assessment implementation roadmap

This roadmap follows the ordered execution phases in the assessment task.
External behavior is marked verified only when an opt-in integration check
has received and validated a real service response.

## Phase 1: Real LLM-powered workflow

**Status: implemented locally; live verification blocked.**

- OpenAI Responses adapter parses structured supervisor routes and grounded
  answer claims and recursive research subtasks.
- Mock mode remains deterministic and is covered by offline tests.
- The live integration test skips because this workspace has no
  `OPENAI_API_KEY`. Do not call the phase complete until the live test passes.

## Phase 2: Pinecone hybrid retrieval

**Status: implemented and live verified for the synthetic corpus.**

- The existing document-schema index was inspected before integration. Its
  `chunk_text` field uses a 1024-dimensional cosine embedding and full-text
  BM25 search.
- The Documents API ingests stable synthetic document/chunk identities in
  the configured namespace.
- Dense `EmbedQuery` and BM25 `TextQuery` calls apply access and department
  filters before RRF fusion.
- The opt-in live test verifies a semantic incident query, exact incident ID,
  and viewer access filtering. The small corpus is not a relevance benchmark.

## Phase 3: Simplified recursive investigation

**Status: implemented with deterministic provider; live-model behavior pending.**

- The Research node recursively expands validated model subtasks up to depth
  two and runs at most four authorized searches and retrieves at most twenty
  documents within thirty seconds.
- Leaf findings retain their task and source identities, then aggregate by
  reciprocal rank fusion over complete document/chunk identities.
- Partial branch failures preserve successful findings. Cancellation is
  propagated. The executor never runs model-generated Python.
- Unit and graph tests verify a synthetic incident question runs three
  subtasks and aggregates attributed evidence.
- A live OpenAI decomposition remains unverified because the local workspace
  has no `OPENAI_API_KEY`.

## Phase 4: Tools and security

**Status: pending.**

- Implement strict analysis inputs and backend tool dispatch.
- Add practical injection and exfiltration controls around enabled tools.
- Add timeout, cancellation, failure, and security tests.
- Preserve server-side role policy and complete citation identity checks.

## Phase 5: Demonstration readiness

**Status: pending.**

- Verify a live model-backed LangSmith trace and parent-child spans.
- Load owner-scoped session history into graph context.
- Emit execution-accurate SSE activity for nodes, tools, and failures.
- Update architecture, security, assumptions, and evaluation evidence.
- Provide exact reproducible startup and demonstration instructions.

The modular monolith, API, UI, SQLite persistence, RBAC, CI, Compose smoke
test, Pinecone hybrid retrieval, and redacted LangSmith tracing foundation
are already present. Their remaining limits are documented in the relevant
architecture and security guides.
