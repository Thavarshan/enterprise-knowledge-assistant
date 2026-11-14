# Assessment implementation roadmap

This roadmap follows the ordered phases in the final sprint request.
External behavior is marked verified only after a live service response
or remote readback has been checked.

## Phase 1: Live model workflows

**Status: implemented and live verified on 2026-11-15.**

- OpenAI structured output selects small talk, Retrieval, Research, and
  supported numeric Analysis without controlling authorization.
- Live Retrieval, multi-subtask Research, grounded response, and arithmetic
  Analysis passed. Mock routing remains deterministic.
- The live workflow test asserts the selected route, retrieved incident
  identities, research counters, response validation, and numeric result.

## Phase 2: Pinecone hybrid retrieval

**Status: implemented and live verified on 2026-11-15.**

- The configured document-schema index and installed Pinecone SDK were
  inspected before implementation. Existing schema was not changed.
- The Documents API ingests eighteen synthetic incidents with stable
  document/chunk identities. It uses an explicit configured namespace.
- Dense `EmbedQuery` and BM25 `TextQuery` searches apply trusted access,
  department, type, and date filters before RRF. Returned metadata is
  checked again before content is exposed.
- Live retrieval and a separate four-case evaluation verified exact IDs,
  semantic paraphrase, access filtering, date filtering, and empty results.
  The small synthetic set is not a production relevance benchmark.

## Phase 3: Bounded recursive investigation

**Status: implemented and live verified on 2026-11-15.**

- Research uses structured OpenAI subtasks and a bounded executor. The live
  test verified multiple subtasks, authorized searches, evidence aggregation,
  and a grounded cited response.
- Shared budgets cap depth at two, searches at four, returned chunks at
  twenty, and elapsed time at thirty seconds. Duplicate expansion is
  suppressed; partial failures preserve successful branches.
- Incident aggregate questions use validated source metadata and trusted
  Python analysis in batches of five. The test verifies an inclusive rolling
  year, root-cause recurrence, count, and source validation.
- No arbitrary model-generated Python is executed. Questions outside the
  supported metadata vocabulary remain unknown rather than inferred.

## Phase 4: Tools and security

**Status: core controls implemented and tested; semantic coverage is partial.**

- The arithmetic tool validates finite numeric literals. Incident analysis
  validates source metadata. Analyst and Administrator roles are checked by
  server-side ToolRegistry before either handler runs.
- Complete document/chunk pairs gate answer citations. OpenAI and Pinecone
  timeouts, cancellation, errors, malformed fields, oversized messages,
  returned access metadata, and role-denied tool use have tests.
- The input guard rejects representative override and secret-exfiltration
  prompts before persistence. Model instructions keep document text
  untrusted. These checks are defense in depth and do not detect every
  injection technique.

## Phase 5: Demonstration and tracing

**Status: implemented and live verified on 2026-11-15.**

- Recent owner-scoped conversation turns are passed to the Supervisor and
  Response provider context, with length and history limits.
- SSE reports execution-accurate agent/tool lifecycle events, retrieval
  progress, analysis counters, validation, memory updates, and safe errors.
  Response chunks are emitted only after citation validation.
- Seven real LangSmith trace trees were remotely read back for Retrieval,
  Research, incident analysis, numeric Analysis, Viewer denial, retrieval
  failure, and OpenAI failure. Destination, parent/child relationships, and
  input/output redaction were checked.
- The guides document exact startup steps, demonstration questions,
  expected evidence, traces, and limitations. A recording is not included.

## Phase 6: Reliability and security hardening

**Status: implemented for the local demonstration; production scaling is
partial.**

- SQLite remains the persistence adapter, with API request operations
  offloaded to worker threads. Tests cover event-loop responsiveness and
  cancellation at the async boundary.
- Provider deadlines, no-retry behavior, safe failure events, fixture mode,
  and Compose startup remain available.
- User tokens and rate buckets are process-local. Fixture retrieval scans
  in-memory data in the event loop. Production identity, shared rate limits,
  and storage are not implemented.

## Phase 7: Optional MCP

**Status: deferred.**

The assessment marks MCP as lower priority. No MCP server or executable
handler is included. The dormant policy entry is not a working integration.

## Phase 8: Automated and live checks

**Status: local verification passed; push verification is reported separately.**

- Local lint, format, type, docblock, comments, line-length, syntax, package
  build, and offline tests are run before commit.
- CI config has separate jobs for quality checks, build, type, dependency
  audit, tests, and a Docker Compose smoke test. Pytest covers Python 3.12,
  3.13, and 3.14.
- The live test requires OpenAI, Pinecone, and LangSmith access. A skipped
  test is not counted as live verification.

## Phase 9: Documentation and demo

**Status: documentation synchronized with verified behavior.**

Architecture, agent, retrieval, security, observability, assumptions,
roadmap, evaluation, lifecycle, ADR, and demo documentation state current
behavior and limits. `docs/assignment.md` remains authoritative. The local
planning and assignment files are not included in commits.
