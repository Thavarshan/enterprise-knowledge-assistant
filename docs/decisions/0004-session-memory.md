# ADR-0004: Preserve owner-scoped SQLite for local persistence

## Status

Accepted for the local default; see
[ADR-0009](0009-multi-cloud-deployment.md) for cloud persistence.

## Context

The UI needs stored user and assistant messages across API restarts. Local
development should not require a managed database, while cloud runtimes
cannot depend on a persistent local filesystem.

## Decision

Keep SQLite as the default local store. The async `SessionStore` contract
also supports the authenticated D1 Worker adapter in cloud mode. Include
owner identity in session reads and message appends; return the same missing
result for absent and foreign-owned sessions.

## Alternatives Considered

- Process-memory-only sessions.
- A managed relational database.
- A separate graph checkpointer for workflow state.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

SQLite keeps the local demo self-contained. A provider-neutral async
contract lets FastAPI use D1 without changing graph or route behavior. Owner
checks exercise a backend data boundary. Conversation history and LangGraph
state have different responsibilities and are not conflated.

## Trade-offs

The API can restore messages after restart, but graph state does not persist.
SQLite calls remain synchronous and run in worker threads. D1 requests add
network latency and depend on Worker availability.

## Consequences

The UI renders saved history. ChatService also loads bounded recent turns
into graph context. SQLite creates parent directories for file-backed paths
and enables foreign keys. Its async adapter uses `asyncio.to_thread` so the
synchronous driver does not block FastAPI's event loop.

## Security and Operational Implications

All session access must retain owner predicates. The local database file
should not be committed. The Worker requires a private service token and
applies owner predicates to every operation. Neither adapter implements
production retention, auditing, or multi-region replication.

## Revisit Conditions

Move to managed storage or add a checkpointer when concurrency, availability,
retention, audit, or resumable-workflow requirements exceed local SQLite.
