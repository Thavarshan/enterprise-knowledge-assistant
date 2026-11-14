# ADR-0006: Separate application logs, graph events, and tracing

## Status

Accepted for the current foundation.

## Context

Operators need request correlation and failure diagnostics. The UI needs
execution status and evidence references. Optional graph tracing may help
inspect execution, but may transfer sensitive input and output externally.

## Decision

Use allowlisted JSON application logs, typed activity events transported as
SSE, and optional LangGraph native LangSmith tracing. Carry request and
session IDs in graph metadata and activity events. Export traces only when
tracing is enabled and valid credentials are configured.

## Alternatives Considered

- Logs alone with no UI activity stream.
- Persist every graph state snapshot.
- Always-on external tracing.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Logs, events, and traces serve different audiences and have different data
needs. Structured event metadata can explain route choice and cite evidence
without exposing hidden reasoning. Explicit trace opt-in reduces accidental
external transfer.

## Trade-offs

The logging allowlist limits diagnostic detail. Agent and tool lifecycle
events stream while operations run. Response chunks follow citation
validation; they are not live model tokens. External LangSmith delivery and
redaction have been verified for synthetic mock and model-backed chat runs.

## Consequences

The UI displays activity and validated response chunks. In OpenAI mode,
structured provider calls have `llm` child spans beneath their graph nodes.
The LangSmith client hides run inputs and outputs, allowlists metadata, and
redacts trace errors. A synthetic trace check reports submission and remote
readback separately; a live model-backed retrieval trace has also been
verified.

## Security and Operational Implications

Tracing sends run structure and allowlisted metadata to LangSmith. The
configured client hides inputs and outputs, filters metadata, and replaces
trace error text. Continue to use synthetic assessment data; the local
verification does not establish a production data-retention policy.

## Revisit Conditions

Revisit event fields and tracing policy when the corpus, trace retention,
compliance, or operational requirements change.
