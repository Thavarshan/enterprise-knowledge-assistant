# ADR-0001: Keep API, UI, and domain in one modular monolith

## Status

Accepted for the current foundation.

## Context

The application has a Streamlit presentation, a FastAPI service, and
capabilities for retrieval, memory, security, tools, agents, and
observability. The assessment needs clear internal boundaries without
requiring separately deployed microservices.

## Decision

Keep one repository, Python package set, lockfile, and container image. Run
FastAPI and Streamlit as separate processes. Keep backend capabilities as
internal modules with protocols where adapter replacement is useful.

## Alternatives Considered

- A microservice per capability, which adds network and deployment
  boundaries.
- One process for the UI and API, which couples their runtime lifecycle.

These are analytical alternatives, not recorded historical proposals.

## Rationale

Separate processes isolate the web server and Streamlit runtime while
preserving a simple local install and coordinated container build. Internal
contracts let tests inject deterministic adapters without deploying each
capability independently.

## Trade-offs

The repository and runtime are simpler to operate locally. Module-level
boundaries rely on code review and tests rather than independent service
ownership or network isolation.

## Consequences

The API and UI share dependency management and releases. New providers can
replace adapters behind their contracts. Avoid cross-layer imports that
create cycles.

## Security and Operational Implications

Separate processes are not a security boundary. The UI must use the API for
identity and data access. Compose builds one image for both services and
waits for API readiness before starting the UI.

## Revisit Conditions

Split a capability into a service when independent scaling, ownership,
failure isolation, or regulatory controls justify the extra operational
surface.
