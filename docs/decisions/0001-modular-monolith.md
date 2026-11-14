# ADR-0001: Keep API, UI, and domain in one modular monolith

## Status

Accepted for the current foundation.

## Context

The application has a Streamlit presentation, a FastAPI service, and
capabilities for retrieval, memory, security, tools, agents, and
observability. It also needs an external persistence adapter for cloud D1,
without moving AI or business logic out of FastAPI.

## Decision

Keep one repository and one authoritative Python backend. Run FastAPI and
Streamlit as separate processes and deploy them independently when needed.
Keep backend capabilities as internal modules with replaceable adapter
contracts. The Cloudflare Worker may translate the narrow session contract
to D1 but owns no chat or authorization policy.

## Alternatives Considered

- A microservice per capability, which adds network and deployment
  boundaries.
- One process for the UI and API, which couples their runtime lifecycle.

These are analytical alternatives, not recorded historical proposals.

## Rationale

Separate processes isolate the web server and Streamlit runtime while
preserving a simple local install and coordinated container build. Internal
contracts let tests inject deterministic adapters without deploying each
backend capability independently. A dedicated persistence adapter keeps
serverless storage concerns outside the graph and UI.

## Trade-offs

The repository and runtime are simpler to operate locally. Module-level
boundaries rely on code review and tests rather than independent service
ownership or network isolation.

## Consequences

The API and UI share a repository and release history. The UI can install
only its own Python dependencies; the API and local Docker image continue to
use the backend package. New providers can replace adapters behind their
contracts. Avoid cross-layer imports that create cycles.

## Security and Operational Implications

Separate processes are not a security boundary. The UI must use the API for
identity and data access. Compose builds one image for both Python services
and waits for API readiness before starting the UI. The Worker receives only
session requests from the authenticated API and does not run model calls.

## Revisit Conditions

Split a capability into a service when independent scaling, ownership,
failure isolation, or regulatory controls justify the extra operational
surface.
