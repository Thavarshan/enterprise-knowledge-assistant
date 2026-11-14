# ADR-0008: Execute structured Research tasks within shared budgets

## Status

Accepted and implemented with deterministic-provider verification. Live
model-backed decomposition remains unverified until provider credentials
are available.

## Context

The assessment calls for multi-step investigations. Unrestricted recursion,
model-generated code, or unbounded retrieval would be difficult to contain
and explain. The application now has a structured `ModelProvider` and a
trusted knowledge-search tool guarded by server-side RBAC.

## Decision

The Research node invokes `BoundedResearchExecutor`. It accepts validated
`TaskDecomposition` output and can expand subtasks to depth two. All child
tasks share a maximum of four retrieval calls, twenty returned chunks, and
thirty seconds. Each search goes through the authenticated role policy.
Findings retain task/source attribution and aggregate with reciprocal rank
fusion by full document/chunk identity.

The executor preserves completed sibling findings when a branch fails,
reports safe failure codes, and propagates caller cancellation. If a
decomposition call fails, it searches that objective as a bounded leaf. It
never executes generated Python, shell commands, or filesystem operations.

## Alternatives Considered

- Unbounded recursive model calls.
- Model-generated Python search plans.
- A single direct retrieval call with no planning contract.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Validated plans and shared counters make recursion inspectable and testable.
The deterministic provider allows the complete decomposition and
aggregation path to run without external credentials. Live OpenAI behavior
is tracked separately from local functional verification.

## Trade-offs

The fixed limits may truncate broad investigations. Decomposition errors
fall back to searching the current objective, while search errors retain
other successful branches. The executor does not yet invoke a Python
analysis tool or execute batch computations.

## Consequences

The graph's Research path now performs multiple queries and recursive
sub-investigations. It exposes per-task source identities in graph state and
passes fused authorized evidence to the Response agent. Tests cover nested
plans, budgets, partial failures, and an incident question that triggers
three subtask searches.

## Security and Operational Implications

Plans do not grant permissions. Role-derived filters are applied before
retrieval content reaches the model. Provider subtasks are bounded strings;
no untrusted program text is executed. External provider calls are
time-limited and exceptions are represented with safe failure codes.

## Revisit Conditions

Revisit the budget values after labeled relevance and latency evaluation.
Require a credential-backed model run before claiming live model-driven
decomposition has been verified.
