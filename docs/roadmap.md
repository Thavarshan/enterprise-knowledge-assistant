# Assessment implementation roadmap

This roadmap follows the ordered execution phases in the assessment task.
External behavior is marked verified only after a live integration or
operational check receives and validates an actual service response.

## Phase 1: Real LLM-powered workflow

**Status: implemented and live verified for routing and grounded response.**

- OpenAI Responses adapter parses structured supervisor routes and grounded
  answer claims and recursive research subtasks.
- Mock mode remains deterministic and is covered by offline tests.
- The live integration test received valid structured route and grounded
  answer output on 2026-11-14. A model-backed API conversation also
  completed successfully.

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
- Live decomposition has not yet been exercised through the research route;
  current multi-subtask verification uses the deterministic provider.

## Phase 4: Tools and security

**Status: implemented for the active tool surface; broader adversarial
evaluation remains.**

- Python analysis supports count, sum, and average over explicit bounded
  numeric literals; the registry allows analysts and administrators only.
- A deterministic input guard blocks clear instruction-override and
  credential-exfiltration requests before message persistence.
- OpenAI and Pinecone boundaries have timeout/cancellation tests; security
  tests cover validation, role denial, prompt patterns, and citation identity.
- The guard is intentionally a small pattern-based control, not a complete
  injection classifier. Expand tests if tools or data sources expand.

## Phase 5: Demonstration readiness

**Status: implemented; model-backed trace verified on 2026-11-14.**

- Owner-scoped prior conversation history is supplied to model context and
  covered by an API integration test.
- LangGraph custom stream events report agent and tool starts/completions and
  safe failures during execution; API tests cover event counts and ordering.
- OpenAI structured requests have explicit LangSmith `llm` child spans. A
  model-backed chat was read back with its supervisor and response child
  spans, matching agent destination, and hidden inputs and outputs.
- Architecture, security, assumptions, observability, evaluation evidence,
  and reproducible demonstration instructions describe current behavior.

The modular monolith, API, UI, SQLite persistence, RBAC, CI, Compose smoke
test, Pinecone hybrid retrieval, and redacted LangSmith tracing foundation
are already present. Their remaining limits are documented in the relevant
architecture and security guides.
