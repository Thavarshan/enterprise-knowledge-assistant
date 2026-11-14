# ADR-0005: Use server-resolved local identity and role policy

## Status

Accepted for the current development foundation.

## Context

The assessment requires viewer, analyst, and administrator behavior without
external identity services. Authorization must not depend on prompt
instructions or UI controls.

## Decision

Load demo accounts from inline JSON or a local JSON file. Issue short-lived
HS256 tokens containing a configured subject and server-assigned role, plus
issuer, audience, and expiry claims. Verify tokens statelessly with a shared
signing key. Enforce tool role policy in ToolRegistry and derive document
access labels from authenticated graph state.

## Alternatives Considered

- An external identity provider with short-lived signed tokens.
- Database-backed user and role assignments.
- Model-directed tool access based on prompt policy.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Local accounts avoid external setup while exercising a server-side identity
boundary. Signed tokens work across API instances without process-local
token state. A backend policy check remains authoritative even if prompts or
UI affordances change.

## Trade-offs

Development is simple, but demo passwords are plain strings in server-only
configuration. Tokens expire, but cannot be individually revoked before
expiry. Role policies are tool-level and do not implement a production
identity lifecycle.

## Consequences

Viewer can chat and search viewer-level documents. Analyst can also access
analyst-level material and use Python arithmetic and incident aggregation.
Administrator is allowed by all active tool policies and may access every
document level. The MCP policy entry has no executable server or handler;
policy permission alone does not create an integration.

## Security and Operational Implications

Keep local account JSON ignored and permissions restricted. Do not accept
client-supplied roles or access labels. Production must configure a high
entropy signing key consistently across API instances. A production system
still needs an identity provider, token revocation, audit decisions, and
reviewed authorization lifecycle.

## Revisit Conditions

Replace demo authentication before real users or whenever account
provisioning, individual revocation, federation, or audit requirements arise.
