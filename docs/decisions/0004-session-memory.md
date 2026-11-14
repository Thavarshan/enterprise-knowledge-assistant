# ADR-0004: Use owner-scoped SQLite for local session persistence

## Status

Accepted for the current foundation.

## Context

The UI needs to list a conversation and restore stored user and assistant
messages across API restarts. The local foundation should not require a
managed database service.

## Decision

Persist sessions and messages in SQLite. Open a short-lived synchronous
connection per operation. Include owner identity in session reads and
message appends; return the same missing result for absent and foreign-owned
sessions.

## Alternatives Considered

- Process-memory-only sessions.
- A managed relational database.
- A separate graph checkpointer for workflow state.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

SQLite gives the local demo durable turns with no extra service. Owner checks
exercise a backend data boundary. Conversation history and LangGraph state
have different responsibilities and are not conflated.

## Trade-offs

The API can restore messages after restart, but graph state does not persist.
SQLite calls are synchronous and are offloaded from API request paths to
worker threads.

## Consequences

The UI renders saved history. ChatService also loads bounded recent turns
into graph context. SQLite creates parent directories for file-backed paths
and enables foreign keys. API operations use `asyncio.to_thread` so the
synchronous driver does not block the event loop while calls are running.

## Security and Operational Implications

All session access must retain owner predicates. The local database file
should not be committed. The current schema does not include data retention,
encryption-at-rest, or multi-region replication.

## Revisit Conditions

Move to managed storage or add a checkpointer when concurrency, availability,
retention, audit, or resumable-workflow requirements exceed local SQLite.
