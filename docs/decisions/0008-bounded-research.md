# ADR-0008: Keep Research plans structured and bounded

## Status

Accepted for the current deterministic scaffold.

## Context

The assessment calls for recursive research concepts, but unrestricted
recursive tasks, generated code, or unbounded tool calls would be difficult
to contain and explain. The current system has no model provider.

## Decision

Represent research plans and budgets as validated Pydantic models. The
current graph retains one query and uses one search call, one depth level,
and a five-result limit. It sends query text to an approved retrieval
handler and does not execute generated Python.

## Alternatives Considered

- Unbounded recursive model calls.
- Model-generated Python search plans.
- A single direct retrieval call with no planning contract.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Structured data and explicit limits are inspectable and testable. The
bounded route demonstrates a planning boundary without pretending a full
RLM executor exists.

## Trade-offs

The current Research node adds little beyond query wrapping. Timeout values
are validated but not enforced. Task decomposition and batch aggregation
models are unused; partial-result behavior is not implemented.

## Consequences

The graph does not recurse, batch documents, deduplicate work, or aggregate
subtask summaries. The fixed planner is a scaffold for a future executor,
not a working recursive research system.

## Security and Operational Implications

Plans do not grant permissions; retrieval filters still come from trusted
role state. Do not add eval, exec, shell, or arbitrary filesystem behavior
for model-created plans. Future work needs shared depth, call, document, and
elapsed-time limits plus cancellation and failure aggregation.

## Revisit Conditions

Revisit the scaffold when a model-backed Research executor is proposed.
Require a defined budget across child tasks, duplicate-work policy, timeout
enforcement, partial-failure behavior, and evaluation before enabling
recursion.
