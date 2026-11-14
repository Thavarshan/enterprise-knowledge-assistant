# ADR-0007: Keep async API boundaries with synchronous local adapters

## Status

Accepted for the current local foundation.

## Context

FastAPI and LangGraph expose asynchronous request and graph APIs. Local
SQLite and fixture search are small and simple, while the Streamlit client
is a synchronous script.

## Decision

Use async FastAPI routes and async graph node/search contracts. Keep SQLite
operations synchronous and use the synchronous httpx client in Streamlit.
Do not infer that an async signature makes a dependency non-blocking.

## Alternatives Considered

- Offload SQLite calls to a thread pool.
- Use an async database driver and async HTTP client.
- Make the entire API and graph execution synchronous.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

The current single-process local demo avoids additional connection pools
and concurrency abstractions. Explicit adapter contracts leave room for
async-native or offloaded implementations when workload requires them.

## Trade-offs

SQLite operations and fixture scans can block the API event loop. Streamlit
holds its execution thread during SSE consumption. These constraints limit
throughput and are not suitable for assuming production concurrency.

## Consequences

No retrieval or persistence timeout is currently enforced. Pinecone has no
SDK code, so there is no provider offload or cancellation behavior to
document. Measure blocking latency before adding concurrent workloads.

## Security and Operational Implications

Blocking work can reduce service availability under load but does not
change the role or owner checks. A future provider adapter must document
timeouts, cancellation, thread safety, retry scope, and failure mapping.

## Revisit Conditions

Offload or replace synchronous adapters when observed event-loop latency,
database contention, or concurrent-user requirements justify the added
complexity.
