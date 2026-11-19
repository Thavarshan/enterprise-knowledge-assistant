# Viridian demonstration guide

The hosted demonstration uses Streamlit Cloud for the UI, Vercel for the
FastAPI backend, and Cloudflare D1 for session history. It uses synthetic
demo accounts and data while connecting to the configured OpenAI, Pinecone,
and LangSmith services.

## Online reviewer access

Open the active Viridian app on Streamlit Cloud and sign in:

| User | Role | Public demo password |
|---|---|---|
| `viewer` | Viewer | `viewer-demo-2026` |
| `analyst` | Analyst | `analyst-demo-2026` |
| `admin` | Administrator | `admin-demo-2026` |

These passcodes work only with the synthetic Viridian demo. Do not reuse
them. Ask the app owner before storing non-synthetic data in the demo.

## Local development

Requirements: Python 3.12–3.14, `uv`, and GNU Make.

```bash
uv sync --all-groups --all-extras
make setup
make dev
```

The local Streamlit client and FastAPI service use independent local demo
accounts. `make setup` creates passwords only when the ignored
`data/users/default.json` file is absent and prints newly generated values
once. Open <http://localhost:8501> and sign in.

The default local profile uses SQLite, fixture search, and mock answers.
OpenAI, Pinecone, and LangSmith credentials are optional local integrations.
Review account usage before running `make verify-live` or
`make verify-langsmith`.

To run containers instead, use:

```bash
docker compose up --build
```

For a local Cloudflare D1 gateway simulation with disposable local state,
run `make cloud-sim`. It does not write to the production D1 database.

## Example questions

- “What caused the payment webhook delay, and how was it resolved?”
- “Compare the recovery steps for delayed settlement and duplicate
  notifications.”
- “How many incidents were caused by certificate expiry?”
- “What should a viewer know about the incident reports?”

The activity panel shows structured graph transitions, retrieval, tool use,
validation, and response status. It does not expose private model
chain-of-thought.

## What the demo demonstrates

- Backend-assigned roles and owner-scoped conversation history.
- Pinecone retrieval and source-backed response claims.
- LangGraph bounded research and structured incident analysis.
- Server-sent event streaming and activity visibility.
- Cloudflare D1 persistence through the authenticated gateway.

The corpus is synthetic and intentionally small. The demo is an assessment
application, not a production identity or data-isolation service.
