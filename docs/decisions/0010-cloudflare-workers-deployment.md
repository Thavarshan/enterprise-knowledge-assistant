# ADR-0010: Deploy Viridian on Cloudflare Workers and D1

## Status

Accepted. This record supersedes ADR-0009's Vercel API and separately hosted
Streamlit frontend proposal.

## Context

The repository and product have been renamed Viridian. The Vercel deployment
was deleted, and the previous Cloudflare D1 gateway Worker and database were
deleted. The user requested a fresh deployment of the complete stack on
Cloudflare, including the frontend, while keeping the Cloudflare deployment
on the Free plan and leaving paid features disabled.

## Decision

Deploy the static browser UI and existing FastAPI application together on one
Python Worker named `viridian`. Deploy the authenticated D1 gateway as
`viridian-d1-gateway` and persist sessions in the newly created
`viridian-sessions` database. CI applies forward-only migrations and deploys
both Workers only after the required gate succeeds on the current `main`
commit.

Keep `MOCK_MODE=true`, `LLM_PROVIDER=mock`, and `LANGSMITH_TRACING=false` in
the Cloudflare configuration. No OpenAI, Pinecone, or LangSmith credentials
are included in the Cloudflare release. The Streamlit client remains
available locally and through its active Streamlit Cloud deployment, outside
this release workflow.

## Alternatives considered

- Keep the API on Vercel and the UI on Streamlit Community Cloud.
- Use Cloudflare Containers for the FastAPI API.
- Move API logic into the TypeScript D1 gateway.
- Bind D1 directly to the Python API Worker.

## Rationale

Workers Static Assets and the Python Workers ASGI adapter allow the browser
UI and existing FastAPI routes to share one origin. The separate D1 gateway
preserves the existing session-store interface and owner-scoped SQL policy.
Cloudflare Containers require a paid Workers plan, so they do not meet the
free deployment constraint. The mock provider and fixture corpus keep the
hosted assessment demo independent of paid inference and vector services.

## Trade-offs

Python Workers use the Workers runtime rather than ordinary Python sockets.
The D1 adapter therefore uses Workers `fetch` through a custom HTTPX
transport. API requests and D1 operations are subject to the Free plan's
resource limits. The Pyodide package index does not provide LangGraph's
`ormsgpack` dependency, so the hosted Worker uses role-filtered extractive
fixture chat while local Python runs retain the full graph workflow. The demo
is not a capacity benchmark and cannot silently upgrade the account to a paid
plan.

## Consequences

- Production origins are `viridian.thavarshan.workers.dev` and
  `viridian-d1-gateway.thavarshan.workers.dev`.
- Static assets are served from `apps/web/public` by the `viridian` Worker.
- D1 state is fresh; no data is copied from the deleted database.
- CI checks the frontend, FastAPI API, authentication, ownership, streaming,
  gateway security, and D1 persistence after deployment.
- The production release does not contact model, vector, or tracing
  providers.

## Security and operational implications

The D1 service token is held only by the backend Worker and D1 gateway. The
JWT signing secret and demo credentials are configured as Worker secrets and
GitHub Environment secrets. The public browser receives only the short-lived
user bearer token. Production deployments are restricted to the `main`
branch and use a current-SHA gate.

## Revisit conditions

Revisit this decision if the demo outgrows the free Workers or D1 limits, if
the app needs production identity or confidential customer data, or if
Cloudflare no longer supports the required Python runtime and ASGI behavior.
