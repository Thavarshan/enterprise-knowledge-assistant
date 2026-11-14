# ADR-0007: Keep async API boundaries with local adapters

## Status

Accepted for the current local foundation.

## Context

FastAPI and LangGraph expose asynchronous request and graph APIs. SQLite,
the local fixture retriever, Pinecone SDK calls, and the Streamlit API client
have synchronous components. A remote D1 adapter performs network I/O.

## Decision

Keep async FastAPI, graph, and `SessionStore` contracts. Offload blocking
SQLite calls from API request paths and synchronous Pinecone SDK calls to
worker threads. Use async HTTP for D1. Retain the synchronous Streamlit
client and in-memory fixture scan. Preserve cancellation at async boundaries
and use configured provider timeouts where supported.

## Alternatives Considered

- Replace SQLite with an asynchronous database driver.
- Replace fixture scanning with a background retrieval service.
- Use an asynchronous HTTP client inside the Streamlit script.
- Make the entire API and graph execution synchronous.

These alternatives are future options, not recorded historical evaluations.

## Rationale

Thread offloading avoids blocking the API event loop during local database
operations without replacing the simple SQLite persistence architecture.
The same boundary accommodates the installed synchronous Pinecone SDK;
async HTTP accommodates D1 without blocking FastAPI.

## Trade-offs

Thread offloading does not make SQLite itself asynchronous and cannot stop an
already-running synchronous provider call when its awaiting task is
cancelled. The Pinecone SDK timeout bounds that work. Fixture search still
scans in memory in the event loop, and Streamlit holds its execution thread
while consuming SSE.

## Consequences

API lifecycle, health, chat, and session operations use async adapters.
SQLite uses `asyncio.to_thread`; D1 uses a reusable async HTTP client.
Pinecone calls use worker threads, bounded timeouts, and no automatic
retries. Production concurrency still needs measurement.

## Security and Operational Implications

Thread offloading does not change owner checks or role policy. SQLite remains
a local database without shared multi-instance coordination or a production
retention and encryption policy.

## Revisit Conditions

Revisit the adapters when measured latency, database contention, or
concurrent-user requirements justify additional operational complexity.
