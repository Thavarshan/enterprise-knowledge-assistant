# Security model and known limits

## Threat boundary

The assessment application uses synthetic documents and local development
accounts. It demonstrates input validation, role checks, retrieval filters,
bounded tools, citation checks, and redacted tracing. These controls do not
make the application a production identity or data-isolation system.

- **Environment and local users:** Operator-controlled. Settings validate
  values; secret values are hidden in representations.
- **Bearer token:** Untrusted until AuthService resolves its local identity
  and role.
- **Request body:** Untrusted. Pydantic caps text; the input guard runs before
  persistence.
- **Retrieved document:** Untrusted. Backend filters precede model context;
  prompts treat content as data.
- **Model output and citations:** Untrusted. Schemas and complete identity
  checks gate answers.
- **LangSmith payload:** External transfer. Inputs/outputs are hidden;
  metadata is allowlisted and errors are redacted.

## Authentication and authorization

DEV_USERS_JSON accepts inline JSON or a path to data/users/default.json.
The local file contains plaintext development passwords and is ignored by
Git. The bootstrap script creates it with restrictive permissions and
prints generated passwords once.

AuthService validates credentials and issues opaque bearer tokens. Roles
come from server configuration; login input cannot choose a role. Tokens
are process-local and disappear after restart. Use a reviewed identity
provider before production.

The backend roles are Viewer, Analyst, and Administrator. Knowledge search
is available to all roles. Python arithmetic and structured incident
analysis are limited to Analysts and Administrators. ToolRegistry checks
permissions before it invokes a handler. The model cannot assign roles,
access labels, departments, or tool permissions.

## Retrieval and data boundaries

The knowledge tool derives allowed access labels from authenticated role
state. Pinecone receives those trusted filters before returning fields, and
the adapter checks returned metadata again before making content available
to the graph. Department, document type, and date filters can narrow that
scope; none can widen it. Namespace selection is server configuration and
does not replace document-level access checks.

Incident analysis accepts only validated structured fields copied from
already-authorized incident report chunks. The tool cannot fetch documents.
It counts explicit source labels, treats conflicts as unknown, and retains
complete document/chunk source references. It does not infer facts from
free text or execute model-authored Python.

The Response agent receives only authorized chunks. Each claim must cite
complete document and chunk IDs returned this turn. Canonical citation
metadata comes from those chunks. Citation validation proves identity and
provenance, not semantic entailment.

## Prompt injection and tool abuse

PromptInjectionGuardrail rejects selected direct instruction overrides and
credential-exfiltration requests before a user message is stored or sent to
a model. Rejections return fixed messages and do not echo input. OpenAI
system instructions treat user text, conversation history, and retrieved
documents as untrusted data.

Pattern checks are defense in depth, not the security boundary. They can
miss paraphrased attacks and can reject benign wording. Actual controls are
backend role policy, role-filtered retrieval, strict Pydantic tool schemas,
the arithmetic literal parser, bounded Research budgets, and citation
validation. The model has no shell, filesystem, network, or arbitrary-code
tool.

## External calls, timeouts, and cancellation

OpenAI requests use a configured deadline and disabled retries. Caller
cancellation propagates through its async SDK adapter. Pinecone has an SDK
timeout, disabled retries, an outer async deadline, and worker-thread
offloading. Cancelling cannot stop a synchronous HTTP request already
running in a worker; its SDK timeout bounds that request. Errors are
sanitized before reaching users and activity events.

## Rate limits and storage

TokenBucketRateLimiter keeps one bucket per user in the API process. Its
default capacity is 30 and refill rate is 0.5 token per second. Buckets do
not coordinate across processes and login attempts are not rate-limited.

SQLite remains synchronous, with operation-scoped connections. API lifespan,
health checks, history reads, and message writes use asyncio.to_thread so
they do not block the request event loop. SQLite is a local demo store, not
shared or high-latency production storage.

## Logging, traces, and secrets

Structured logs omit request bodies, passwords, bearer tokens, and source
content. Request IDs are validated or replaced with UUIDs. LangSmith hides
run inputs and outputs, keeps allowlisted metadata, omits runtime details,
and redacts error text. Verification commands distinguish delivery from
remote readback; a trace without read permission is reported as BLOCKED.

LangSmith receives external trace metadata when enabled. Only synthetic
assessment data was used for the live verification. Do not enable tracing
for data whose transfer is not permitted.

SSE events contain status text, counts, source IDs, and stable error codes.
Research events do not expose model-proposed query text. Response chunks
are emitted only after validation.

Never commit .env, local account JSON, provider keys, or customer data.
Root ignore rules exclude docs/plan.md and docs/assignment.md. The
data/users directory has its own ignore rule for development accounts.

## Automated security coverage

Unit and API tests cover:

- Direct and paraphrased override and credential-exfiltration patterns.
- Untrusted retrieved-document prompt handling.
- Viewer denial for arithmetic and incident-analysis tools.
- Access filtering before graph/model use and returned-metadata rechecks.
- Invalid tool fields, calculation bounds, and complete citation identities.
- Provider failures, timeouts, and cancellation without raw error leakage.
- Oversized request validation and pre-persistence rejection.

The tests exercise defined examples. They do not prove robustness against
all prompt-injection styles, real confidential data, or future tools.
