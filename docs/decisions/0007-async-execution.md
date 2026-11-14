# ADR-0007: Keep async API boundaries with local adapters

## Status

Accepted for the current local foundation.

## Context

FastAPI and LangGraph expose asynchronous request and graph APIs. SQLite,
the local fixture retriever, Pinecone SDK calls, and the Streamlit API client
have synchronous components.

## Decision

Keep async FastAPI and graph contracts. Offload blocking SQLite calls from
API request paths and synchronous Pinecone SDK calls to worker threads.
Retain the synchronous Streamlit client and the in-memory fixture scan.
Preserve cancellation at async boundaries and use configured provider
timeouts where supported.

## Alternatives Considered

- Replace SQLite with an asynchronous database driver.
- Replace fixture scanning with a background retrieval service.
- Use an asynchronous HTTP client inside the Streamlit script.
- Make the entire API and graph execution synchronous.

These alternatives are future options, not recorded historical evaluations.

## Rationale

Thread offloading avoids blocking the API event loop during local database
operations without replacing the simple SQLite persistence architecture.
The same boundary accommodates the installed synchronous Pinecone SDK.

## Trade-offs

Thread offloading does not make SQLite itself asynchronous and cannot stop an
already-running synchronous provider call when its awaiting task is
cancelled. The Pinecone SDK timeout bounds that work. Fixture search still
scans in memory in the event loop, and Streamlit holds its execution thread
while consuming SSE.

## Consequences

API lifecycle, health, chat, and session operations call SQLite through
`asyncio.to_thread`. Tests check event-loop responsiveness and cancellation
at the coroutine boundary. Pinecone calls use worker threads, bounded
timeouts, and no automatic retries. Production concurrency needs measurement
and may justify async-native storage and retrieval adapters.

## Security and Operational Implications

Thread offloading does not change owner checks or role policy. SQLite remains
a local database without shared multi-instance coordination or a production
retention and encryption policy.

## Revisit Conditions

Revisit the adapters when measured latency, database contention, or
concurrent-user requirements justify additional operational complexity.
