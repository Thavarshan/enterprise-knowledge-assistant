# ADR-0002: Use a deterministic LangGraph workflow for chat turns

## Status

Accepted for the current foundation.

## Context

Chat execution has route selection, retrieval, response construction,
validation, and activity events. The workflow must expose explicit
transitions and keep failures from continuing into later steps.

## Decision

Compile a LangGraph state graph with Supervisor, Research, Retrieval,
Response, and Validate nodes. Use a deterministic keyword route and consume
node updates with asynchronous update streaming. The graph ends after
validation and compiles without a checkpointer.

## Alternatives Considered

- A direct Python pipeline with explicit function calls.
- A model-selected supervisor or a model-backed agent loop.

These are analytical alternatives; the record does not claim they were
formally evaluated before implementation.

## Rationale

Named nodes and graph updates provide observable transitions and a clear
termination point. A deterministic supervisor and one-pass workflow keep
the foundation testable without model credentials or open-ended tool loops.

## Trade-offs

Graph state and event reducers add framework concepts. The current graph
does not use model reasoning, retries, recursion, checkpointing, or
conversational history, so it is not a multi-agent LLM system yet.

## Consequences

Each node returns partial state updates. The events field uses an append
reducer. The route is based on fixed substrings; retrieval and response run
once, then citation validation completes the graph.

## Security and Operational Implications

The API creates role and user identity in graph state. ToolRegistry applies
backend policy before handler dispatch. Activity events expose decisions and
evidence references, not hidden chain-of-thought. A graph failure becomes a
generic event and prevents assistant-response persistence.

## Revisit Conditions

Revisit routing, graph persistence, retry policy, and checkpointing when
model-backed reasoning, user-visible long-running tasks, or resumable
approval flows are implemented.
