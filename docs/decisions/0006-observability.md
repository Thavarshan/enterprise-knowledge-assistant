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
validation; they are not live model tokens. LangSmith delivery has been
verified on synthetic mock and model-backed runs.

## Consequences

The UI displays activity and validated response chunks. In OpenAI mode,
structured provider calls have `llm` child spans beneath their graph nodes.
The LangSmith client includes run inputs and outputs, metadata, runtime
details, and errors while anonymizing recognized credential patterns. The
standalone check distinguishes submission from remote readback and verifies
visible synthetic content. Seven live workflow and failure traces were
remotely read back on 2026-11-15 under the former hidden-payload settings.

## Security and Operational Implications

Tracing sends run inputs, outputs, metadata, runtime details, and errors to
LangSmith after recognized credential patterns are anonymized. This does not
filter arbitrary personal or confidential content. Use tracing only for data
whose transfer is permitted; local synthetic verification does not establish
a production data-retention policy.

## Revisit Conditions

Revisit event fields and tracing policy when the corpus, trace retention,
compliance, or operational requirements change.
