# ADR-0005: Use server-resolved local identity and role policy

## Status

Accepted for the current development foundation.

## Context

The assessment requires viewer, analyst, and administrator behavior without
external identity services. Authorization must not depend on prompt
instructions or UI controls.

## Decision

Load development accounts from inline JSON or a local JSON file. Issue
random process-local bearer tokens and resolve each token to a configured
user and role. Enforce tool role policy in ToolRegistry and derive document
access labels from authenticated graph state.

## Alternatives Considered

- An external identity provider with short-lived signed tokens.
- Database-backed user and role assignments.
- Model-directed tool access based on prompt policy.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Local accounts avoid external setup while exercising a server-side identity
boundary. A backend policy check remains authoritative even if future model
prompts or UI affordances are changed.

## Trade-offs

Development is simple, but passwords are plaintext, tokens do not expire,
and token state disappears at restart. The current policy table is small and
does not provide route-level role distinctions beyond authentication and
session ownership.

## Consequences

Viewer can chat and search viewer-level documents. Analyst can also access
analyst-level material and policy entries for analytics and MCP.
Administrator is allowed by all current policy entries. Analytics and MCP
have no installed handlers; policy permission alone does not create a tool.

## Security and Operational Implications

Keep local account JSON ignored and permissions restricted. Do not accept
client-supplied roles or access labels. Tokens and tool policies are
process-local. A production system needs an identity provider, token
lifecycle, audit decisions, and shared authorization state.

## Revisit Conditions

Replace local authentication before production or whenever account
provisioning, expiry, revocation, federation, or audit requirements arise.
