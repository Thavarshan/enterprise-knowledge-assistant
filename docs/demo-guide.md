# Assessment demonstration guide

This guide runs the local FastAPI and Streamlit application with the
structured OpenAI provider, synthetic fixture documents, and optional
LangSmith tracing. It uses the existing modular monolith and does not
provision new services.

## Prerequisites

- Python 3.13, `uv`, and GNU Make.
- An OpenAI API key for model-backed routing and response generation.
- A LangSmith API key for trace verification.
- Optional: access to the already configured Pinecone index and namespace
  for the hybrid retrieval variant.

The repository does not contain provider credentials. Configure existing
accounts and observe their usage and billing policies before running live
provider requests. Fixture mode works without Pinecone credentials.

## Startup

From the repository root, install dependencies and prepare local users:

```bash
uv sync --all-groups
make setup
```

`make setup` keeps an existing account file. If it creates one, it prints
generated passwords once in the terminal and stores them under the ignored
`data/users/default.json` path with restrictive file permissions. The demo
usernames and roles are `viewer` / viewer, `analyst` / analyst, and `admin` /
administrator. Passwords are intentionally not recorded in this guide or
Git; use the locally saved credentials.

Set these values in the ignored `.env` file. Keep the actual key values
local:

```dotenv
MOCK_MODE=true
LLM_PROVIDER=openai
OPENAI_API_KEY=<your-local-key>
OPENAI_MODEL=gpt-4.1-mini
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<your-local-key>
LANGSMITH_AGENT_ID=enterprise-knowledge-assistant
LANGSMITH_AGENT_ENVIRONMENT=local
```

`MOCK_MODE=true` selects the checked-in synthetic fixture corpus. It does
not turn off the OpenAI provider. Start both local processes:

```bash
make dev
```

Open <http://localhost:8501>, sign in with one of the locally configured
accounts, and use the Streamlit chat. `make dev` runs the API and UI in one
foreground process group; Ctrl+C stops both.

Before the conversation, the standalone trace check can confirm LangSmith
delivery and redaction independently of OpenAI:

```bash
make verify-langsmith
```

To check the real model provider with synthetic evidence:

```bash
uv run --env-file .env pytest tests/integration/test_llm_live.py -q
```

That command skips when `OPENAI_API_KEY` is missing. The connectivity check
above sends a synthetic trace, not a model-backed conversation.

### Optional Pinecone retrieval

To run the same UI against the existing Pinecone index, set `MOCK_MODE=false`
and configure `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, and
`PINECONE_NAMESPACE` in `.env`. The default assessment namespace is
`assessment-demo`. Ingest the synthetic incident corpus before starting the
app:

```bash
uv run --env-file .env python scripts/ingest_pinecone.py
make dev
```

The command upserts synthetic records into the configured existing index; it
does not create an index. Pinecone retrieval uses the backend role filters,
dense and BM25 queries, then RRF. Return `MOCK_MODE=true` to use local
fixtures again.

## Representative questions

Try these prompts. The first and second use the knowledge corpus. Use a
viewer for the direct runbook question and an administrator for the
investigation so the latter can search every synthetic access level.

| Question | Expected route | Expected evidence or result |
|---|---|---|
| “What does the gateway timeout response runbook require before replaying a payment?” | Retrieval | `doc-runbook-gateway-timeout` / `doc-runbook-gateway-timeout-001`; check regional health and latency, shift traffic if needed, verify recovery, record the incident reference, and confirm idempotency before replay. |
| “Investigate payment incidents and compare symptoms, causes, and mitigations.” | Research | Multiple bounded subtasks, authorized searches, and aggregated citations. Fixture mode should surface the payment incident, gateway timeout runbook, and authorization-path architecture note when relevant. The Pinecone synthetic incident set includes stable IDs such as `incident-2026-041`, `incident-2026-057`, and `incident-2026-124`. |
| “Calculate average of 10, 20, 30.” | Analysis | The analyst/admin-only Python tool returns an average of `20`; no retrieved citations are needed. |

The real Supervisor selects the route from structured model output. The
expected route is the intended demonstration behavior, not a claim that a
live model has already been run in this workspace. The deterministic mock
uses a fixed route rule and decomposition, so it is useful for repeatable
offline checks.

## LangSmith trace to inspect

For an OpenAI-backed turn, open the existing `Enterprise Knowledge
Assistant` agent and its `local` environment. Locate the latest
`chat_request` parent for the chat. The expected tree contains:

```text
chat_request
├── LangGraph execution
│   ├── supervisor
│   │   └── openai_supervisor (llm)
│   ├── research (when selected)
│   │   ├── openai_decomposition (llm, decomposition)
│   │   └── knowledge_search (tool, per search)
│   ├── retrieval (when selected)
│   │   └── knowledge_search (tool)
│   ├── analysis (when selected)
│   │   └── python_analysis (tool)
│   ├── response
│   │   └── openai_response (llm, when evidence exists)
│   └── validate
└── assistant_memory_append (tool)
```

Mock mode creates no OpenAI request spans. With tracing configured, model
and tool run inputs/outputs are hidden, metadata is allowlisted, and trace
error text is redacted. Verify the model request spans are children of the
corresponding graph/node operation and that no question, evidence, or answer
text appears in the exported payload.

The repository has verified LangSmith redaction on a synthetic
fixture-backed chat and on one OpenAI-backed retrieval chat. On 2026-11-14,
trace `3d657959-195c-4256-a4ab-1bf410074c7e` read back with eleven runs;
`openai_supervisor` was nested under the Supervisor node and
`openai_response` under Response. The agent destination matched, all run
inputs and outputs were hidden, and the question text was absent. Live
Research decomposition and trace hierarchy remain to be verified.

## Limitations and fallback

- `LLM_PROVIDER=mock` keeps local chat deterministic when no model key is
  available. OpenAI failures return a generic failure event; the app does
  not silently replace a failed live request with mock output.
- `MOCK_MODE=true` uses a five-document fixture corpus and lexical overlap
  scoring, not embeddings or BM25. Pinecone mode requires the configured
  existing index and network access.
- The Pinecone demonstration corpus has six synthetic incidents. It is not
  a statistically meaningful retrieval benchmark.
- Research is bounded to depth two, four searches, twenty documents, and
  thirty seconds. Partial findings may be returned when a branch fails.
- Python analysis supports count, sum, and average over validated numeric
  literals. It does not execute model-generated code.
- The prompt guardrail catches selected obvious override and credential
  exfiltration patterns; it does not detect every prompt injection.
- Development tokens and rate limits are process-local. The local demo is
  not a production identity or multi-instance deployment.
