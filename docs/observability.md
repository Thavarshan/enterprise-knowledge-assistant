# Observability

## Signals

- **Application logs:** Python logging emits allowlisted operational fields
  and request IDs for API and graph diagnosis.
- **LangSmith traces:** The explicit client records run names and graph
  structure. Inputs and outputs are hidden; metadata is allowlisted.
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
validation operations.

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

LangSmith is an optional integration for local experiments. The hosted
Cloudflare Worker sets `LANGSMITH_TRACING=false` and does not send traces to
LangSmith. Its logical agent ID is `viridian`; configure an accessible
LangSmith destination and credentials locally before enabling tracing.

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
the client or LangGraph workflow. Test settings and the Cloudflare
production deployment disable tracing and need no key.

Agent-based addressing replaces the older project destination. The setup
removes `LANGSMITH_PROJECT`, `LANGCHAIN_PROJECT`, and `LANGCHAIN_SESSION`
from the process environment to prevent mixed routing. Do not configure a
project name for this agent-based workspace. A workspace ID is not the
agent ID and is not required unless the API key's scope requires it.

## Privacy and metadata

The SDK client applies these protections before export:

- All run inputs and outputs are hidden, including questions, retrieved
  evidence, graph state, assistant responses, and persisted message text.
- Runtime details are omitted.
- Metadata is restricted to safe values such as request ID, session ID,
  agent ID, environment, graph node, tool name, workflow, and status.
- Trace error text is replaced with `[REDACTED]`; logs include only the
  exception type.

The metadata filter accepts only known keys with short, safe string values;
request, session, and verification identifiers must also be UUIDs. It
discards arbitrary metadata, content, credentials, and future fields by
default. These identifiers are correlation labels, not authorization tokens.
The app does not record passwords, bearer tokens, private document text, or
confidential personal information in traces.

The LangSmith spans describe observable operations and outcomes. They do not
expose hidden model reasoning. OpenAI request inputs and outputs are hidden,
and error text is redacted before export.

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
environment, hierarchy, and payload redaction.

Results have distinct meanings:

- **Configuration PASS:** Required settings are present; this alone does not
  prove that the service accepted a trace.
- **Trace submission PASS:** SDK flush completed without reported errors;
  this is not remote readback verification.
- **VERIFIED:** Remote readback confirmed destination, spans, hierarchy, and
  hidden inputs and outputs.
- **FAILED:** Trace execution, submission, or a remote assertion failed.
- **BLOCKED:** Required configuration or remote read permission is
  unavailable. The command exits with status 2.

The command never prints the API key, question payload, evidence, or answer.
It prints a unique verification ID. In LangSmith Cloud, open the
`Viridian` agent, select the `Local` environment, and
find the trace with that ID. If submission passed but readback is BLOCKED,
use the UI to inspect that verification ID; do not call it verified until
the remote trace is visible and its payload is checked.

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
destination, expected graph/model/tool spans, parent-child links, and hidden
inputs and outputs. The Viewer-denial trace did not contain
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

These runs use synthetic assessment data. They verify current trace routing
and redaction, not a production data-transfer or retention policy.

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
The current configured key and destination have remotely verified model
workflows, tool behavior, failure traces, and redaction. See
`docs/demo-guide.md` for the reproducible procedure and limits.
