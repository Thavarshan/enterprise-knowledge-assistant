# Observability

## Signals

- **Application logs:** Python logging emits allowlisted operational fields
  and request IDs for API and graph diagnosis.
- **LangSmith traces:** The explicit client records run names and graph
  structure. Inputs and outputs are hidden; metadata is allowlisted.
- **Graph state:** LangGraph holds identity, questions, routes, plans,
  evidence, responses, citations, and events while one run executes.
- **Activity events:** Graph nodes, ChatService, and the API send coarse
  transitions, retrieval details, validation, and failures to the UI.

Activity events are not LangSmith traces or a graph-state dump. They show
selected operations and evidence references. There is no model in the
current graph, and hidden model chain-of-thought is never an explainability
feature.

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
│   ├── research (investigation questions only)
│   ├── retrieval
│   │   └── knowledge_search
│   ├── response
│   └── citation validation
└── assistant_memory_append
```

The user message is persisted by the API route before the stream starts; that
write is outside the current `chat_request` trace. Assistant persistence is
inside the trace. Failures from graph execution or assistant persistence
mark the parent run as failed while the API returns a generic activity event.
Trace export errors are logged by exception type, without exception text,
and do not prevent normal chat requests from running.

Only implemented operations are traced. The current workflow uses synthetic
in-memory retrieval and deterministic response construction. It has no live
LLM call, Pinecone dense retrieval, sparse/BM25 ranking, hybrid ranking, MCP
tool, or recursive RLM operation to trace.

## Agent-based destination

This workspace uses LangSmith Cloud's agent-based observability. The app
routes traces to the already registered agent by pairing its identifier with
an environment:

- Agent display name: `Enterprise Knowledge Assistant`
- Agent ID: `enterprise-knowledge-assistant`
- Environment: `local`
- API endpoint: `https://api.smith.langchain.com`

The **Agent ID** is the registered identifier, not the display name. Agent
addressing is `agent ID + environment`. It is neither a tracing project ID
nor a workspace ID. Do not create a replacement agent or tracing project.
`LANGSMITH_WORKSPACE_ID` is omitted unless a credential's scope requires an
explicit workspace selector.

The Python SDK requirement is `langsmith>=0.14.9`; `uv.lock` fixes the
resolved version used by this repository. The SDK's agent-addressing API
receives the explicit agent address for each trace. The environment
variables are also set before the client and compiled graph are created so
SDK integrations in the API process share the same destination.

## Configuration and local setup

Copy `.env.example` to the ignored local `.env`, then set the LangSmith key.
The required values are:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<your-secret-key>
LANGSMITH_AGENT_ID=enterprise-knowledge-assistant
LANGSMITH_AGENT_ENVIRONMENT=local
```

Keep the API key in local `.env` or the deployment secret store. It is
loaded by `Settings`, passed only to the backend SDK client, and never sent
to the Streamlit process. The API loads settings and configures LangSmith
before it constructs the client or LangGraph workflow. Test settings disable
tracing and need no key.

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
expose hidden model reasoning. The deterministic graph currently has no
model reasoning to record.

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

- **VERIFIED:** Remote readback confirmed the run, destination metadata,
  expected nested spans, and hidden inputs and outputs.
- **SUBMITTED:** The SDK flush completed without reporting export errors,
  but remote readback was unavailable or incomplete. This may be normal for
  a tracing-only API key.
- **FAILED:** Trace execution, submission, or a remote redaction check failed.
- **BLOCKED:** Required configuration is missing or invalid.

The command never prints the API key, question payload, evidence, or answer.
It prints a unique verification ID. In LangSmith Cloud, open the
`Enterprise Knowledge Assistant` agent, select the `Local` environment, and
find the trace with that ID. If the result is `SUBMITTED`, use this UI check
to confirm receipt when the API key cannot read traces.

## Application verification

The standalone script validates agent addressing and nested SDK tracing. To
exercise the actual API with the local fixture graph, start the normal
development server and use the existing Streamlit UI:

```bash
make api
make ui
```

Sign in with a configured demo user and submit a synthetic question. The
backend sends the chat trace to the same agent and environment. The sidebar
continues to display application activity events; those events are a UI
progress feed, not LangSmith spans. For automated repository checks, ordinary
tests use mock settings and never require LangSmith credentials.

### Live verification record

On 2026-11-14, a synthetic chat was sent through the local FastAPI service
and the fixture-backed graph. LangSmith readback found trace
`7dea0ced-4176-47c5-b153-4f3456adb31c` under the existing agent's `local`
environment. The trace contained nine runs. Every run had empty inputs and
outputs, and the synthetic chat text was absent from the serialized trace.

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
- **Result is SUBMITTED:** The key may have trace-write permission without
  run-read permission. Confirm the verification ID in the LangSmith UI.
- **No model spans:** The current graph is deterministic and does not call
  an LLM. No model spans are expected.

LangSmith availability is optional. A missing key, rejected request, or
network failure is reported without stopping ordinary chat execution.
Pinecone, live LLM calls, sparse search, and recursive research are not
implemented and are outside the current trace hierarchy.
