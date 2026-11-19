# Security model and known limits

## Threat boundary

The assessment application uses synthetic documents and local development
accounts. It demonstrates input validation, role checks, retrieval filters,
bounded tools, citation checks, and redacted tracing. These controls do not
make the application a production identity or data-isolation system.

- **Environment and local users:** Operator-controlled. Settings validate
  values; secret values are hidden in representations.
- **Bearer token:** Untrusted until AuthService verifies its signature,
  issuer, audience, expiry, subject, and backend-assigned role.
- **Request body:** Untrusted. Pydantic caps text; the input guard runs before
  persistence.
- **Retrieved document:** Untrusted. Backend filters precede model context;
  prompts treat content as data.
- **Model output and citations:** Untrusted. Schemas and complete identity
  checks gate answers.
- **LangSmith payload:** External transfer. When enabled, run inputs,
  outputs, metadata, runtime details, and errors are sent after common
  credential patterns are anonymized.

## Authentication and authorization

DEV_USERS_JSON accepts inline JSON or a path to data/users/default.json.
The local file contains plaintext development passwords and is ignored by
Git. The bootstrap script creates it with restrictive permissions and
prints generated passwords once.

AuthService validates configured demo credentials and issues short-lived
HS256 bearer tokens. Roles come from backend configuration; login input
cannot choose a role. Production must set an explicit signing key of at least
32 characters. API instances configured with the same key, issuer, and
audience can verify the same token without shared process state.

Stateless tokens cannot be individually revoked before expiry. Rotating the
signing key invalidates every token. Demo passwords are plain strings in
server-only configuration and local development files; this is not password
storage for real users. Replace demo login with a reviewed identity provider
before production use.

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

The async SessionStore contract selects the local SQLite adapter or the D1
HTTP adapter. SQLite still uses synchronous operation-scoped connections,
offloaded to threads so API requests do not block the event loop. D1 requests
use a reused async HTTP client, a bounded timeout, and no automatic retries.
The FastAPI backend sends a service token and the authenticated owner's ID
only after it verifies the user's bearer token.

The Cloudflare Worker checks the service token before accessing D1. It
validates the owner ID and payload, uses prepared SQL statements, and scopes
every session read and append by both session and owner. Missing and foreign
sessions both return 404. D1 credentials are never sent to the browser. Worker
errors are reduced to safe 4xx/5xx responses; D1 does not provide a general
SQL route. The local simulation uses a separate disposable D1 database.

## Logging, traces, and secrets

Structured logs omit request bodies, passwords, bearer tokens, and source
content. Request IDs are validated or replaced with UUIDs. LangSmith receives
run inputs and outputs, metadata, runtime details, and error text; its secret
anonymizer replaces recognized credential patterns before upload. The
anonymizer is not a general personal-data filter. Verification commands
distinguish delivery from remote readback; a trace without read permission is
reported as BLOCKED.

LangSmith receives prompts, retrieved evidence, tool arguments and results,
model outputs, and errors when tracing is enabled. Synthetic assessment data
was used for earlier live verifications. Do not enable tracing for data whose
transfer is not permitted.

SSE events contain status text, counts, source IDs, and stable error codes.
Research events do not expose model-proposed query text. Response chunks
are emitted only after validation.

Never commit .env, local account JSON, provider keys, or customer data.
Root ignore rules exclude docs/plan.md and docs/assignment.md. The
data/users directory has its own ignore rule for development accounts. The
Docker build context also excludes local account JSON and environment files.
The online assessment demo intentionally displays fixed public passcodes for
its synthetic demo accounts. Never reuse them or store confidential documents
in the assessment index. Replace these accounts before using real data.
The cloud simulation uses only synthetic hard-coded local accounts.

## Deployment workflow boundary

Pull requests and scheduled CI runs do not receive production secrets. A
deployment can start only after the complete `ci-gate` passes for a push to
`main`, or after a manual run invokes the same CI workflow successfully.
No deployment opt-in variable is required. Deployment smoke checks use
synthetic accounts and do not call model providers. Production deployment
credentials belong to the GitHub `production` environment. The Cloudflare
token is limited to the D1 gateway and database; the Vercel token is used
only by the API deployment job. Deployment jobs use read-only repository
access.

The deployment workflow serializes production releases and rechecks the
approved Git SHA before deployment. It verifies the exact Cloudflare D1 name
and ID, rejects destructive SQL migrations, and deploys the authenticated D1
gateway. After the gateway smoke succeeds, GitHub Actions builds and deploys
the FastAPI API to Vercel, then checks its health, D1 readiness, and provider
configuration. Provider and application secrets are loaded from Vercel's
production environment. Streamlit Cloud continues to deploy from its
configured Git branch outside this workflow.

This automation does not replace repository rules. Restrict the production
environment to `main` and configure the secret inventory in
[`ci-cd.md`](ci-cd.md).

## Automated security coverage

Unit and API tests cover:

- Direct and paraphrased override and credential-exfiltration patterns.
- Untrusted retrieved-document prompt handling.
- Viewer denial for arithmetic and incident-analysis tools.
- Access filtering before graph/model use and returned-metadata rechecks.
- Invalid tool fields, calculation bounds, and complete citation identities.
- Provider failures, timeouts, and cancellation without raw error leakage.
- Oversized request validation and pre-persistence rejection.
- Signed-token expiry, tampering, wrong audience, and cross-instance use.
- D1 Worker authentication, owner isolation, input limits, and local migrations.

The tests exercise defined examples. They do not prove robustness against
all prompt-injection styles, real confidential data, or future tools.
