# Observability

## Four distinct signals

| Signal | Produced by | Contains | Purpose |
|---|---|---|---|
| Application logs | Python logging and request middleware | Allowlisted operational fields and request ID | Diagnose API and graph failures. |
| LangSmith traces | LangGraph environment integration | Potentially graph inputs and outputs | Inspect traced graph execution when enabled and accepted. |
| Graph state | LangGraph during one run | Identity, question, route, plan, results, response, citations, events | Carry data and partial updates between nodes. |
| Activity events | Graph nodes, ChatService, and API | Coarse transitions, evidence references, validation, failures | Show execution progress and outcomes to the UI. |

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
header, SSE event IDs, and structured API logs for one request. LangSmith
trace metadata includes the request and session IDs when native tracing
works.

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

configure_langsmith enables environment-based native tracing only when
LANGSMITH_TRACING is true in settings and an API key is present. It sets
the project name and optional workspace ID. When tracing is disabled, it
removes the API key and workspace ID from the process environment.

This is configuration, not a connection test. The factory reports whether
tracing is configured, but it does not submit a probe trace or confirm that
credentials, workspace selection, network access, or project permissions
work. The project documentation does not claim a successful external trace.
The application defines no custom trace root or span instrumentation.
LangGraph's native integration may create graph and child spans when the
configured SDK sends a trace, but span completeness is not verified here.

The application does not redact LangSmith payloads. Native graph tracing may
include questions, retrieved evidence, state values, and responses. Keep it
disabled for sensitive data until an explicit data policy and redaction
strategy are in place. Use synthetic test content for a connection check.

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
2. Confirm configured tracing, API key, and optional workspace ID.
3. Run one graph request and inspect the matching trace in the workspace.
4. Verify request/session correlation metadata and expected node spans.
5. Record the observed result and any rejected credentials or permissions.

Until these steps succeed, treat LangSmith as an optional configured
integration boundary rather than a verified observability backend.
