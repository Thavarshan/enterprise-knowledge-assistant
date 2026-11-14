# Security model and known limits

## Threat boundary

The current system is a local assessment foundation with synthetic
documents, development-only accounts, and a deterministic graph. It is not
a production identity or data-isolation system. This guide distinguishes
controls that execute today from protocols and safeguards still planned.

| Input or state | Trust level | Current handling |
|---|---|---|
| Environment and local account file | Operator-controlled | Settings are validated; secret fields are excluded from model repr. |
| Bearer token | Untrusted until resolved | AuthService maps it to process-owned identity and role. |
| Request body | Untrusted | Pydantic schemas bound lengths and reject extra fields. |
| Retrieved document | Untrusted content with validated metadata | Role filter is applied before fixture text enters graph state. |
| Graph-generated response and citations | Internal but still validated | Citation marker gate runs before response chunks are emitted. |
| LangSmith payload | External data transfer when enabled | No redaction is implemented. |

## Authentication and identity

DEV_USERS_JSON accepts inline JSON or a path to a JSON file. The default
local workflow uses data/users/default.json. That file contains plaintext
development passwords and must remain ignored by Git. The bootstrap script
creates the file with restrictive permissions and prints generated
passwords once.

AuthService validates credentials and issues random opaque bearer tokens.
Roles are loaded from server configuration; login input cannot choose a
role. Unknown usernames use a random comparison value and receive the same
error message as a wrong password. Tokens have no expiry, are not persisted,
and are stored in process memory. They disappear at restart and are not
shared between workers. Use an established identity provider before
production.

Missing or invalid bearer credentials are rejected with HTTP 401 before
protected route work. Health and readiness endpoints are public. The
identity endpoint returns the role associated with the token.

## Role policy and authorization boundaries

The role vocabulary is viewer, analyst, and administrator. Document access
levels follow a simple hierarchy:

| Role | Chat and search | Analytics policy | MCP policy |
|---|---|---|---|
| Viewer | Allowed | Denied | Denied |
| Analyst | Allowed | Allowed | Allowed |
| Administrator | Allowed | Allowed | Allowed |

The current graph installs only a knowledge-search handler. Analytics and
MCP policy entries do not provide executable tools. Administrator access
means all tools represented by the current policy table, not unrestricted
system access.

ToolRegistry checks role policy on the backend before it awaits a handler.
Prompt text, a UI control, or a request field is not authorization. The
knowledge tool derives allowed access labels from the role in graph state
and passes them to retrieval. Graph identity is initialized by ChatService
from the authenticated API user; future entrypoints must preserve that
trusted construction.

SQLite reads and writes include owner identity. Foreign-owned sessions use
the same 404 response as missing sessions. The chat route verifies ownership
before consuming a rate token or storing the user message.

## Document filtering and citation handling

The fixture retriever applies access-level and optional exact department
filters before ranking content. Viewer may search viewer documents;
analysts may search viewer and analyst documents; administrators may search
all three levels.

This application-level filter is the only active document isolation. The
Pinecone adapter does not issue queries or filters. A future provider must
derive namespace and metadata filters from authenticated identity, apply
them server-side before returning text, and fail closed if filtering cannot
be enforced. Namespace separation alone is not a complete authorization
control.

The response node copies citations from retrieved chunk metadata. The
validator checks answer markers against citations whose chunk IDs occur in
the current retrieval result set. It does not independently compare full
document/chunk pairs. The deterministic graph does not accept client
citations, but a model-backed response should validate exact pairs and
identifier syntax.

## Prompt injection and guardrails

There is no language model in the current graph, so retrieved text is not
used as model instructions. The deterministic response includes selected
fixture text and generated source markers. Request schemas validate shape
and length; citation validation gates response chunks.

InputGuardrail and OutputGuardrail are protocol definitions only. No prompt
injection classifier, output sanitizer, data-exfiltration policy, or unsafe
tool inspection is implemented or called. Citation checks are not a general
content-safety mechanism. Treat retrieved documents as untrusted when
adding a model, and keep unrestricted tools disabled until concrete
guardrails and server-side authorization tests exist.

## Rate limiting

TokenBucketRateLimiter keeps one bucket per user in the API process.
Defaults are capacity 30 and refill 0.5 token per second. Each chat request
consumes one token. Elapsed time comes from a monotonic clock; the balance
is capped at capacity. A rejected request receives HTTP 429 and an
approximate Retry-After value rounded up to at least one second.

The bucket map has no thread lock and no shared backing store. It is not
safe as a coordinated quota across threaded or multi-worker deployments.
The configured policy does not limit login attempts or other endpoints.

## Logging, traces, and secrets

Structured application logs use an allowlist and omit request bodies,
passwords, bearer tokens, and document contents. Request IDs are validated
or replaced with UUIDs and used for correlation. Authentication decisions
are not logged with user identifiers; API status and safe error categories
are logged.

Settings fields for secrets are excluded from their model representation.
DevUserConfig, IssuedToken, and PineconeConfig use default representations
that include password or token/key fields. Current code does not log those
objects, but future diagnostics must not format or log them.

LangSmith tracing is disabled by default. Enabling it may export graph
inputs, retrieved text, state, and response content. No payload redaction or
successful external trace verification is implemented. Keep it disabled
for sensitive data until a reviewed data policy and a tested redaction
strategy exist.

Never commit .env, local account JSON, real provider keys, or customer data.
The root ignore rules exclude plan.md and assignment.md under docs. The
data/users directory has its own ignore file so local credential files do
not enter commits.

## Deployment limitations

The bearer token map and rate limiter are process-local. SQLite operations
are synchronous and run directly from async API handlers. CORS origins,
secrets, and provider configuration require deployment-specific review.
Production use requires shared authentication, distributed rate limits,
managed persistent storage, provider-side filtering, tracing redaction,
and security testing.
