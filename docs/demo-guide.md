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

- “Investigate CS001245. Settlement records go missing when the worker
  retries.”
- Follow up with “The customer reports LedgerSync version 5.8.1.” Then try
  “The customer reports version 5.8.3.” Keep each reported version as a
  conversation observation; neither version alone confirms the cause.
- “What caused the payment webhook delay, and how was it resolved?”
- “Compare the recovery steps for delayed settlement and duplicate
  notifications.”
- “How many incidents were caused by certificate expiry?”
- “What should a viewer know about the incident reports?”

## Authorization demonstration

Use the same query under each role to show that the backend filters evidence
before the model sees it:

1. As Viewer, ask “What does case CS001288 say?” The restricted case should
   not appear in results or citations.
2. As Analyst, ask the same question. CS001288 is available with a source
   citation because its access level is `analyst`.
3. As Viewer or Analyst, ask “What does case CS001297 say?” It should remain
   unavailable. As Administrator, it is available because its access level
   is `administrator`.
4. Return to “Investigate CS001245. Settlement records go missing when the
   worker retries.” The six core Aurelion records remain Viewer-accessible.

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

The hosted Pinecone assessment namespace uses a separate 40-record fictional
Aurelion corpus: 24 ServiceNow-style cases, 8 Jira-style issues, 4 release
notes, and 4 knowledge articles. Its anchor case has no direct Jira link;
two earlier cases do link to ENG-421. The version and root cause for the
anchor case remain unknown until the user supplies more evidence.
