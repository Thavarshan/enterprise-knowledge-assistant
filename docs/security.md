# Security model and known limits

## Threat boundary

This is an assessment application with synthetic documents and local
development accounts. It has active request validation, role checks,
retrieval filters, a narrow arithmetic tool, and a deterministic input
guardrail. These controls are useful for the demonstrated paths but do not
make the application a production identity or data-isolation system.

| Input or state | Trust level | Current handling |
|---|---|---|
| Environment and local account file | Operator-controlled | Settings validate configuration; secret fields are hidden from model repr. |
| Bearer token | Untrusted until resolved | AuthService maps it to process-owned identity and role. |
| Request body | Untrusted | Pydantic bounds text and rejects extra fields; input guardrail runs before storage. |
| Retrieved document | Untrusted content with validated metadata | Backend role filters run before content reaches the model. Prompt rules treat it as data. |
| Model answer and citations | Untrusted generated output | Structured schemas and full document/chunk identity validation gate the response. |
| LangSmith payload | External transfer when tracing is enabled | Configured client hides inputs and outputs and filters metadata. |

## Authentication and identity

`DEV_USERS_JSON` accepts inline JSON or a path to a JSON file. The local
workflow uses `data/users/default.json`. That file contains plaintext
development passwords and must remain ignored by Git. The bootstrap script
creates it with restrictive permissions and prints generated passwords
once.

AuthService validates credentials and issues random opaque bearer tokens.
Roles are loaded from server configuration; login input cannot choose a
role. Tokens have no expiry, are not persisted, and are stored in process
memory. They disappear at restart and are not shared between workers. Use
an established identity provider before production.

Missing or invalid bearer credentials receive HTTP 401. Health and readiness
endpoints are public. The identity endpoint returns the role associated
with the token.

## Role policy and authorization boundaries

The role vocabulary is viewer, analyst, and administrator. Knowledge search
is available to all roles, while Python analysis and MCP policies permit
analysts and administrators only.

ToolRegistry checks role policy on the backend before awaiting a handler.
The model returns only a workflow route; it cannot assign roles, access
labels, departments, tool permissions, or retrieval filters. The graph
creates identity from the authenticated API user. A request body, prompt,
or UI control is not authorization.

The Python analysis handler accepts only a validated count, sum, or average
over explicit finite numeric values. It has no filesystem, network, shell,
or dynamic-code interface. Its chat grammar accepts commands such as
`calculate average of 10, 20, 30`; it does not parse Python expressions.
Viewers who reach the analysis route are rejected by ToolRegistry before
the handler runs.

SQLite reads and writes include owner identity. Foreign-owned sessions use
the same 404 response as missing sessions. The chat route verifies ownership
before input inspection, rate consumption, or message persistence.

## Document filtering and citation handling

The fixture retriever applies access-level and optional department filters
before ranking. Pinecone receives the same trusted metadata filters in its
query and rechecks returned metadata before exposing chunk content. Viewer
may search viewer documents; analysts may search viewer and analyst
documents; administrators may search all three levels.

The response provider receives only authorized retrieved chunks. Every
claim must include a citation with a complete document ID and chunk ID.
The graph resolves those identities against the current turn's evidence,
copies citation metadata from the source chunk, and withholds answers whose
markers do not validate. Citation identity proves provenance, not semantic
entailment; response quality still needs evaluation.

## Prompt injection and exfiltration controls

`PromptInjectionGuardrail` blocks clear requests to override prior/system
instructions and requests to reveal or export credentials. The API applies
it before persisting a user message, so rejected text is not stored or sent
to the model. Decisions use safe codes and do not echo the input.

This is a small pattern-based check, not a general injection classifier.
It can miss paraphrased attacks and can reject some benign wording. The
model's fixed system instructions separately tell it to treat user input,
history, and retrieved documents as untrusted data. The model has no direct
tool-call or arbitrary-code interface. The only active tools are role-gated
knowledge search and bounded numeric arithmetic.

Retrieval authorization is independent of prompts. An injection cannot
change the server-derived role filter. The response schema requires exact
source identities, and the arithmetic parser accepts only literal numbers.
These controls reduce risk for the implemented surface but are not a
security proof for arbitrary future tools or real customer data.

## External calls, timeouts, and cancellation

OpenAI requests use configured deadlines and disable automatic retries.
Caller cancellation propagates through the asynchronous SDK adapter.
Pinecone operations have an SDK request timeout, retries disabled, and an
outer async deadline; cancellation propagates to the awaiting coroutine.
Pinecone's SDK is synchronous, so cancellation cannot stop a worker thread
already inside an HTTP request. Its SDK timeout bounds that request.
Errors are sanitized before they reach users or activity events.

## Rate limiting and storage

`TokenBucketRateLimiter` keeps one bucket per user in the API process.
Defaults are capacity 30 and refill 0.5 token per second. The buckets do not
coordinate across processes, have no shared backing store, and do not limit
login attempts.

SQLite operations are synchronous and run from async routes. Production use
needs a shared identity provider, distributed rate limits, managed
persistent storage, and a reviewed lifecycle for credentials and sessions.

## Logging, traces, and secrets

Structured application logs use an allowlist and omit request bodies,
passwords, bearer tokens, and document contents. Request IDs are validated
or replaced with UUIDs and used for correlation. Authentication decisions
are not logged with user identifiers; safe error categories are logged.

Settings fields for secrets are excluded from their model representation.
`DevUserConfig`, `IssuedToken`, and `PineconeConfig` representations may
include sensitive fields; current code does not log those objects.

LangSmith tracing is disabled by default. When enabled, the configured
client hides run inputs and outputs and restricts metadata to an allowlist.
The synthetic connectivity check confirms the redacted trace path. Never
enable tracing for data whose transfer is not permitted by the operator.

SSE lifecycle events use fixed status messages, counts, source identities,
and stable error codes. Research events omit the model-proposed query text;
tool exceptions do not cross the stream boundary. Response chunks are emitted
only after citation validation.

Never commit `.env`, local account JSON, real provider keys, or customer
data. Root ignore rules exclude `plan.md` and `assignment.md`; the
`data/users` directory has a local ignore rule for development credentials.

## Automated security coverage

Unit and API tests verify that:

- Viewer users cannot run Python analysis.
- Numeric tool inputs reject extra fields, non-finite numbers, oversized
  values, and executable expressions.
- The input guard blocks representative override and credential-exfiltration
  prompts before persistence.
- Retrieval filters remove unauthorized documents before graph/model use.
- Citation validation compares complete source identities.
- Provider failures and caller cancellation do not expose exception text.

These tests cover implemented controls, not adversarial robustness against
all prompt-injection styles.
