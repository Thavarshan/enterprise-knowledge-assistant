# Observability

## Signals

- **Application logs:** Python logging emits allowlisted operational fields
  and request IDs for API and graph diagnosis.
- **LangSmith traces:** The explicit client records run inputs and outputs,
  metadata, runtime details, errors, and graph structure. Recognized
  credential patterns are anonymized before export.
- **Graph state:** LangGraph holds identity, questions, routes, plans,
  evidence, responses, citations, and events while one run executes.
- **Activity events:** Graph nodes, ChatService, and the API send agent and
  tool lifecycle, retrieval details, validation, and failures to the UI.

Activity events are not LangSmith traces or a graph-state dump. They show
selected operations and evidence references. In OpenAI mode the graph calls
a real model through the structured Responses adapter; in mock mode its
model-shaped decisions are deterministic local code. Neither mode treats
hidden chain-of-thought as an explainability feature.

## LangSmith architecture

The API creates one process-scoped LangSmith client when tracing is enabled
and valid configuration is present. ChatService creates a `chat_request`
parent span around graph execution and assistant-message persistence.
LangGraph automatically traces its graph and node execution inside that
parent. The `KnowledgeSearchTool.run` wrapper adds a child tool span. The
graph node names identify supervisor, research, retrieval, response, and
validation operations. The parent input includes the current question,
conversation history, role, and correlation IDs; its output includes the
validated answer, citations, route, and validation status.

The expected trace shape is:

```text
chat_request
├── LangGraph execution
│   ├── supervisor
│   │   └── openai_supervisor (OpenAI mode)
│   ├── research (investigation questions only)
│   │   ├── openai_decomposition (decomposition, OpenAI mode)
│   ├── retrieval
│   │   └── knowledge_search
│   ├── analysis (analysis questions only)
│   │   └── python_analysis
│   ├── response
│   │   └── openai_response (OpenAI mode)
│   └── citation validation
└── assistant_memory_append
```

The user message is persisted by the API route before the stream starts; that
write is outside the current `chat_request` trace. Assistant persistence is
inside the trace. Failures from graph execution or assistant persistence
mark the parent run as failed while the API returns a generic activity event.
Trace export errors are logged by exception type, without exception text,
and do not prevent normal chat requests from running.

The structured OpenAI provider creates an `llm` child span for each actual
provider request. Mock mode creates no model-request span. The live suite
verified model-backed Supervisor, decomposition, and Response calls, plus
Pinecone search, incident analysis, numeric tool use, and failure traces.
MCP has no executable handler.

## Agent-based destination

The FastAPI service enables LangSmith tracing in its Vercel production
environment when the agent destination and credentials are configured. The
Cloudflare D1 gateway does not run the agent and does not send traces. The
logical LangSmith agent ID is `viridian`; its production environment is
`production`.

The Python SDK requirement is `langsmith>=0.14.9`; `uv.lock` fixes the
resolved version used by this repository. The SDK receives an explicit
agent address when tracing is enabled. The environment variables are set
before the client and compiled graph are created so SDK integrations in the
API process share the same destination.

## Configuration and local setup

Copy `.env.example` to the ignored local `.env` only if you intend to use
LangSmith locally. Set `LANGSMITH_TRACING=true` and provide a key:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<your-secret-key>
LANGSMITH_AGENT_ID=viridian
LANGSMITH_AGENT_ENVIRONMENT=local
```

Keep the API key in local `.env`; it is loaded by `Settings` and passed only
to the backend SDK client. The API configures LangSmith before it constructs
the client or LangGraph workflow. Test settings and the Cloudflare D1
gateway disable tracing and need no key. Production settings live in
Vercel's environment; GitHub Actions does not pull Vercel's protected
provider credentials into the deployment job. The standalone connectivity
verifier can use a local `.env` without calling OpenAI or Pinecone.

Agent-based addressing replaces the older project destination. The setup
removes `LANGSMITH_PROJECT`, `LANGCHAIN_PROJECT`, and `LANGCHAIN_SESSION`
from the process environment to prevent mixed routing. Do not configure a
project name for this agent-based workspace. A workspace ID is not the
agent ID and is not required unless the API key's scope requires it.

## Privacy and metadata

The SDK client applies these protections before export:

- Run inputs and outputs are included: questions, retrieved evidence,
  graph state, tool arguments and results, model responses, and persisted
  assistant message text.
- Runtime details, metadata, and useful error text are included.
- LangSmith's secret anonymizer replaces recognized credential patterns
  with `[SECRET_DETECTED]` in inputs, outputs, metadata, and errors.
- Application logs still omit request bodies and exception text; they keep
  safe correlation fields and error types.

The anonymizer recognizes common API keys, bearer credentials, passwords,
private keys, and other credential-like patterns. This is credential
scrubbing, not broad personal-data filtering. Prompts, retrieved document
text, and generated answers are transferred to LangSmith whenever tracing is
enabled, so only use tracing for data whose transfer is permitted.

The LangSmith spans describe observable operations and outcomes. They do not
expose hidden model reasoning.

## Verification

Run the standalone connectivity check with the existing local environment:

```bash
make verify-langsmith
```

The equivalent direct command is:

```bash
uv run --env-file .env python scripts/verify_langsmith.py
```

The script executes a traceable parent operation and three nested,
deterministic operations using fictional PAY-504 data. It flushes the SDK's
background trace queue and checks SDK export callbacks. If read permissions
allow it, the script reads the exact run back and checks the agent,
environment, hierarchy, visible synthetic input/output, and credential
anonymization.

Results have distinct meanings:

- **Configuration PASS:** Required settings are present; this alone does not
  prove that the service accepted a trace.
- **Trace submission PASS:** SDK flush completed without reported errors;
  this is not remote readback verification.
- **VERIFIED:** Remote readback confirmed destination, spans, hierarchy,
  visible synthetic content, and replacement of a fake API key.
- **FAILED:** Trace execution, submission, or a remote assertion failed.
- **BLOCKED:** Required configuration or remote read permission is
  unavailable. The command exits with status 2.

The command never prints the API key, question payload, evidence, or answer.
It prints a unique verification ID. In LangSmith Cloud, open the
`Viridian` agent, select the `Local` environment, and
find the trace with that ID. The synthetic question, mock evidence, answer,
and anonymized credential probe should appear. If submission passed but
readback is BLOCKED, use the UI to inspect that verification ID; do not call
it verified until the remote trace is visible and its payload is checked.

## Application verification

The standalone script validates agent addressing and nested SDK tracing. To
exercise the actual API with the local fixture graph, start the normal
development server and use the existing Streamlit UI:

```bash
make api
make ui
```

Sign in with a configured demo user and submit a synthetic question. With
`LLM_PROVIDER=openai`, the backend sends the chat and its model child spans
to the configured agent and environment. The sidebar displays application
activity events; those events are a UI progress feed, not LangSmith spans.
For automated repository checks, ordinary tests use mock settings and never
require LangSmith credentials.

### Live verification record

The trace IDs below predate the current content-visibility setting. Their
inputs and outputs remain empty; newly created traces include run payloads
and apply the secret anonymizer before upload.

On 2026-11-14, a synthetic chat was sent through the local FastAPI service
and the fixture-backed graph. LangSmith readback found trace
`7dea0ced-4176-47c5-b153-4f3456adb31c` under the existing agent's `local`
environment. The trace contained nine runs. Every run had empty inputs and
outputs, and the synthetic chat text was absent from the serialized trace.

On 2026-11-14, an OpenAI-backed direct retrieval chat was sent through the
local FastAPI service. Trace
`3d657959-195c-4256-a4ab-1bf410074c7e` read back with eleven runs under the
same agent and environment. Its hierarchy placed `openai_supervisor` beneath
the Supervisor node and `openai_response` beneath the Response node. The
agent destination matched, every run had empty inputs and outputs, and the
question text was absent from the serialized trace.

On 2026-11-15, `make verify-live` completed seven real chat turns and read
each trace tree back from the same agent environment. It confirmed the
destination, expected graph/model/tool spans, parent-child links, and the
former hidden-input/output settings. The Viewer-denial trace did not contain
`python_analysis`. The trace IDs are:

| Workflow | Trace ID |
|---|---|
| Retrieval | `107153f4-40a6-4afd-aab1-f2f52c01e071` |
| Multi-subtask Research | `7f74e6d9-be91-4272-bc48-e3e5a38d2ce2` |
| Incident analysis | `00325724-ffb8-406b-afa3-22b11f6d6257` |
| Numeric Analysis | `1e2e9ec1-3d98-4bd5-a5e6-32d08eebe52d` |
| Viewer denial | `0ac7a031-0bf7-499b-8124-4d7ed00ceecd` |
| Retrieval failure | `da1607ab-30f0-46fb-a988-c228f2d2a881` |
| OpenAI failure | `bdcecb0d-3127-41e2-9867-15b3f8f0c8a2` |

These runs use synthetic assessment data. They are historical checks of trace
routing and hierarchy under the prior hidden-payload configuration. The
standalone verifier now checks visible payloads and credential anonymization.

## Troubleshooting and limitations

- **Configuration reports missing settings:** Check the five values in the
  local `.env`; never paste the API key into a terminal command or report.
- **Authentication or submission fails:** Confirm the key is active and
  scoped to the target workspace, the endpoint matches the LangSmith region,
  and network access to the endpoint is available.
- **No agent destination:** Confirm the Agent ID from the agent's Overview
  page and use an existing environment such as `local`. The display name is
  not a substitute for the ID.
- **Agent not found or archived:** Confirm the exact ID and that the
  registered agent is active in the selected workspace.
- **Submission passed but readback is BLOCKED:** The key may have trace-write
  permission without run-read permission. Confirm the ID in the LangSmith UI.
- **No model spans:** `LLM_PROVIDER=mock` makes deterministic local
  decisions and emits no model-request spans. In OpenAI mode, check that
  `LLM_PROVIDER=openai` and the key were set before starting the API.

LangSmith availability is optional for ordinary chat. A missing key,
rejected request, or network failure is reported without stopping the turn.
See `docs/demo-guide.md` for the reproducible procedure and limits.
