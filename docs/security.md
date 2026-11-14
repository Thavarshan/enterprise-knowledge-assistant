# Security foundation

## Identity and roles

The local token endpoint accepts credentials loaded from `DEV_USERS_JSON`; it assigns the role from server configuration and keeps opaque bearer tokens in process memory. Client request bodies cannot set a role. Unknown users and incorrect passwords have the same response. Missing credentials disable token issuance without preventing health checks. Use a real identity provider before production.

The `ToolRegistry` enforces the role matrix in backend execution paths: Viewer can search, Analyst can search and use planned analytics/MCP tools, and Administrator has all registered permissions. The graph calls the registry before `KnowledgeSearchTool` runs. Unimplemented tools have policy entries but no handler and cannot be executed.

## Document isolation

The retriever receives a server-derived set of allowed access levels. The fixture adapter applies this metadata filter before it scores or returns chunk text. The graph's model context is assembled only from authorized search results. A production Pinecone adapter must preserve this ordering in server-side metadata filters and must fail closed when the authorization filter cannot be applied.

Every session read/write checks `owner_id` in SQLite queries. A session belonging to another user appears as not found. No user-supplied owner or role is accepted by chat endpoints.

## Request and tool safety

Request IDs are validated or replaced with a UUID and attached to API responses and logs. Request bodies, credentials, access tokens, and document contents are not included in application logs. Tool arguments are validated at their service boundary. RLM plans are structured data interpreted by approved functions; no generated Python is executed.

Guardrail protocols exist for prompt injection, output validation, and unsafe tool checks, but policy implementations are deferred. Do not connect unrestricted tools until those checks are implemented and tested.

## Local infrastructure limitations

`.env` is ignored and generated demo passwords are local-only. Rotate them by replacing `.env` and rerunning setup. API tokens and rate-limit buckets are in memory, so run one API worker locally. SQLite is appropriate for this phase, not an HA deployment.

LangSmith is disabled by default. Enabling tracing may transmit graph inputs and outputs to the configured LangSmith project. Review the organization's data policy and add redaction before using confidential documents or production identities. External trace delivery has not been validated here.
