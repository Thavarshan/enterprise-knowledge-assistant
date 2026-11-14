# ADR-0002: Use LangGraph for bounded chat workflows

## Status

Accepted and implemented with deterministic and live-provider paths.

## Context

Chat execution has route selection, retrieval, research, analysis, response
generation, validation, and activity events. The workflow must expose
transitions, preserve authorization, and stop safely after failures.

## Decision

Compile a LangGraph graph with Supervisor, Research, Retrieval, Analysis,
Response, and Validate nodes. The Supervisor uses validated OpenAI
structured output in live mode and deterministic routing in mock mode. A
small-talk route goes directly to Response. Research delegates recursion to
`BoundedResearchExecutor` and an authorized search tool. The graph has no
open-ended model tool-selection loop or checkpointer.

## Alternatives Considered

- A direct Python pipeline with explicit function calls.
- A model-driven agent loop with unrestricted tool selection.
- Persisting graph state with a separate checkpointer.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Named nodes and graph updates expose decisions and actions. Structured model
output supports live routing while keeping the selected route separate from
server-side roles, filters, and tool permissions. Shared Research budgets
bound recursion without model-generated code.

## Trade-offs

Graph state and event reducers add framework concepts. Research may truncate
broad investigations at fixed limits. Session history is passed as bounded
context, but graph state itself is not persisted across restarts.

## Consequences

Each node returns partial state updates and appends typed activity events.
Small talk avoids retrieval. Direct questions use authorized Retrieval.
Research decomposes, searches, and aggregates attributed evidence. Numeric
Analysis uses a validated Python tool. Response claims are checked against
complete document/chunk identities before output is streamed.

## Security and Operational Implications

The API creates role and user identity in graph state. ToolRegistry applies
backend policy before handler dispatch. Activity events expose selected
decisions and evidence references, not hidden chain-of-thought. A graph
failure becomes a generic event and prevents answer persistence.

## Revisit Conditions

Revisit budgets, persistence, and retry policy after broader evaluation or
when resumable workflow requirements justify checkpointing.
