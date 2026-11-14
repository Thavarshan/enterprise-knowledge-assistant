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
session IDs in graph metadata and activity events. Keep tracing disabled by
default.

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

The logging allowlist limits diagnostic detail. Events arrive when their
graph node completes, not as a live model-token stream. LangSmith setup only
sets environment variables; it does not validate delivery.

## Consequences

The UI displays activity and response chunks. The current graph has no model
spans or live model tokens. No redaction layer or trace health check is
implemented. External tracing has not been verified as successful.

## Security and Operational Implications

Enabling tracing may export questions, retrieved evidence, graph state, and
responses. Use synthetic data until a redaction and retention policy is
reviewed. Application logs currently omit request bodies, tokens, passwords,
and document contents.

## Revisit Conditions

Revisit event fields and tracing policy when a model provider or sensitive
corpus is added, or when trace retention, compliance, or operational
requirements change.
