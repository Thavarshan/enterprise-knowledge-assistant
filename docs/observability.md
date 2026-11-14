# Observability

## Four distinct signals

- **Application logs:** Python logging and request middleware emit allowlisted
  operational fields and request IDs for API and graph diagnosis.
- **LangSmith traces:** The redacting client exposes run names and graph
  structure while hiding inputs, outputs, metadata, runtime details, and
  errors. Inspect graph execution when tracing is enabled and accepted.
- **Graph state:** LangGraph holds identity, questions, routes, plans,
  results, responses, citations, and events during one run.
- **Activity events:** Graph nodes, ChatService, and the API emit coarse
  transitions, evidence references, validation, and failures for the UI.

Activity events are not an application log, LangSmith trace, or full state
dump. They describe selected behavior and evidence; they do not expose hidden
model chain-of-thought. There is no model in the current graph.

## Request and log correlation

RequestIdMiddleware accepts an incoming X-Request-ID only when it matches
the bounded safe-character expression. Otherwise it creates a UUID. It
stores the value on request state, sets a context variable for logs, attaches
the value to the response header, and resets the context variable in a
finally block.

JsonFormatter emits timestamp, level, logger name, message, request ID,
and a small allowlist of fields such as method, path, status, duration,
error type, tracing-enabled state, and mock mode. It does not serialize
arbitrary log-record attributes. Chat and request bodies, access tokens,
passwords, and document contents are not part of the configured log schema.
Unexpected API and graph failures log exception type, not exception text.

The activity schema carries both request ID and session ID. The request ID
also appears in the HTTP response header. An evaluator can compare the
header, SSE event IDs, and structured API logs for one request. The graph
adds request and session IDs to local run metadata, but the LangSmith client
removes metadata before export; those IDs are not available in remote traces.

## Graph events and UI activity

Nodes add typed event dictionaries to AgentState.events. The operator.add
reducer appends them across node updates. ChatService consumes the graph
using update streaming, validates event payloads with ActivityEvent, and the
API encodes each as an SSE event whose name is the event type and whose data
is JSON.

Current event categories include agent transition, tool execution,
retrieval, validation, response chunk, memory update, completion, and
failure. Retrieval metadata includes source IDs, chunk IDs, titles, and
scores. Response chunks are emitted after citation validation in
80-character slices of the completed deterministic answer; they are not
model tokens. Node events arrive after node execution completes.

The Streamlit sidebar renders the latest agent and node, retrieval/tool
activity, validation, and errors. The conversation area assembles response
chunks. The UI does not display raw graph state or LangSmith internals.

## LangSmith configuration and limitations

LangSmith tracing requires the explicit opt-in and an API key. The optional
LANGSMITH_WORKSPACE_ID must be a UUID, not the workspace display name. The
application leaves implicit SDK tracing disabled and passes a dedicated
client into LangGraph's tracing context for each graph run.

Before export, the client removes all run inputs, outputs, and metadata,
omits runtime details, and replaces error strings with a fixed redaction
marker. The SDK's environment flags also hide graph inputs, outputs, and
metadata. Run names and graph structure remain visible for inspection.
Remote trace correlation metadata is intentionally unavailable.

Configuration alone does not confirm delivery. Run `make langsmith-check`
to submit a graph invocation containing only synthetic content, locate the
exact root run, and verify that inputs, outputs, and the synthetic marker
were not exported. This command requires valid credentials and network
access; it is not run in CI.

## Failure behavior

If tracing is absent or disabled, the application continues without trace
export. Graph execution and activity events do not depend on LangSmith.
Provider or graph errors are represented by generic failure events and
correlated logs; the client does not receive provider exception details.
There is no trace-delivery health check, retry policy, or persisted activity
event store.

## Verification checklist

Before reporting LangSmith as connected:

1. Use a dedicated test project and synthetic request content.
2. Confirm tracing is enabled, the API key is set, and the optional
   workspace selector is a UUID.
3. Run `make langsmith-check` and require a successful exit.
4. Inspect the matching run ID and expected graph node spans in the workspace.
5. Confirm run inputs, outputs, and metadata are empty in the remote trace.
6. Record the observed result and any rejected credentials or permissions.

Until these steps succeed, treat LangSmith as an optional configured
integration boundary rather than a verified observability backend.
