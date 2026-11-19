# ADR-0009: Keep cloud deployment within the modular monolith

## Status

Superseded by [ADR-0010](0010-cloudflare-workers-deployment.md). This record
documents the earlier Vercel API and Streamlit UI proposal and is retained
for decision history.

## Context

The assessment needs to preserve FastAPI, Streamlit, LangGraph, OpenAI,
Pinecone, LangSmith, and local SQLite while preparing for request-scoped
serverless API instances and an independently hosted UI. Vercel Functions
cannot rely on a persistent local filesystem or process-local token map.

## Decision

Keep FastAPI as the only application and business-logic backend. Expose the
existing application through a thin root Vercel entrypoint. Keep Streamlit
as the independently installable frontend and configure only its public API
URL there.

Use an async `SessionStore` contract. SQLite remains the local default and
uses thread offloading. Cloud mode selects a D1 HTTP adapter that talks only
to a small authenticated Cloudflare Worker. The Worker owns the D1 binding,
enforces owner-scoped prepared queries, and contains no chat, AI, or
authorization policy.

Use short-lived signed tokens so separate API instances can verify identity
with one configured signing key. Configure cloud-only requirements through
environment settings and fail closed when production values are missing.
Keep a local simulation and tests independent of remote accounts.

## Alternatives Considered

- Put SQLite on serverless local disk or use process memory for sessions.
- Move AI and business logic into the Cloudflare Worker.
- Replace the existing Streamlit UI with a web frontend framework.
- Add a hosted identity or relational database platform for this assessment.

These alternatives would add state, services, or a new application stack
without improving the assessment's core architecture.

## Rationale

The API stays the single place for authentication, role enforcement,
retrieval, model calls, citation validation, streaming, and tracing. A narrow
Worker lets D1 serve persistent sessions without creating another backend.
SQLite and deterministic mock mode continue to support local work and
offline tests.

## Trade-offs

The API-to-Worker request adds network latency and a shared service secret.
The stateless token cannot be individually revoked before it expires. The
in-process rate limiter does not coordinate between Vercel instances. The
Worker and D1 need separate account setup and migration management. Free-tier
limits and platform capabilities can change.

## Consequences

- `MEMORY_BACKEND=sqlite` remains the default.
- `MEMORY_BACKEND=d1` selects the async Worker adapter.
- The Vercel entrypoint exposes the same `create_app()` used locally.
- Streamlit receives `API_BASE_URL` only; backend keys remain server-side.
- Local Wrangler and D1 tests require no Cloudflare credentials.
- Remote database IDs and provider credentials stay outside Git.

## Security and Operational Implications

Create a dedicated D1 database for this assessment. Never point its binding
at another user database. Set the same high-entropy D1 service token on the
Worker and FastAPI, and keep the JWT signing key only on FastAPI. Do not
commit `.env`, `.dev.vars`, actual account-specific IDs, or user data.

The included tests verify local boundaries. A Cloudflare Worker and D1
release has also passed authenticated health and read/write smoke checks.
Verify the API, UI, current migrations, secrets, quotas, function duration,
and provider credentials before claiming full-stack live readiness.

## Revisit Conditions

Revisit the design when real identity, higher throughput, stronger token
revocation, data retention, regional availability, or production audit
requirements arise.
