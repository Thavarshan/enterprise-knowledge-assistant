# Assumptions

- `docs/assignment.md` is the authoritative specification. Its scoring
  weights are copied into `docs/evaluation-matrix.md`.
- The default profile is a local assessment demonstration. A D1-backed cloud
  profile is available, but it is not a production identity or
  data-isolation service.
- All fixture documents are synthetic examples for an invented enterprise.
  They contain no real customer data or claim affiliation with a real bank.
- Development roles are configured in server-only `.env` or an ignored
  local user file. Demo passwords are plain strings, `make setup` prints
  generated values once, and credentials are not logged.
- `MOCK_MODE=true` selects local fixture retrieval. `MOCK_MODE=false` selects
  Pinecone dense and full-text BM25 search with reciprocal rank fusion. The
  application uses the configured existing index and does not manage its
  schema or lifecycle.
- `LLM_PROVIDER=mock` is deterministic. `LLM_PROVIDER=openai` independently
  enables model-backed routing, research decomposition, and response claims.
  On 2026-11-15, live verification exercised Retrieval, multi-subtask
  Research, incident aggregation, numeric Analysis, and Viewer denial.
- LangSmith tracing is optional for normal application use. The live
  verification confirmed the configured agent destination, seven workflow
  and failure span trees, parent-child links, and hidden run inputs/outputs.
- Incident-analysis fields come from validated source metadata. Trusted
  Python counts records and source-classified root causes; missing or
  conflicting causes remain unknown. It does not infer causes from prose.
- The input guard blocks selected override and secret-exfiltration patterns.
  It is defense in depth, not a general prompt-injection classifier.
- The async storage contract selects SQLite by default or D1 for cloud
  deployment. The SQLite adapter offloads synchronous operations to worker
  threads; D1 uses bounded async HTTP requests. Fixture retrieval still scans
  in the event loop; the Streamlit client is synchronous.
- Stateless bearer tokens work across API instances with the same signing
  configuration. They cannot be revoked individually before expiration.
- The fresh `viridian-sessions` D1 database is empty until the deployment
  workflow applies its initial migration. The `viridian` and
  `viridian-d1-gateway` Workers are created and smoke-checked by the release
  workflow.

## Configuration reference

The API Settings model reads process environment variables and then `.env`.
Empty values are ignored. Secret fields are excluded from Settings model
representations. Mock mode needs no provider credentials.

| Variable | Default | Use and limits |
|---|---|---|
| APP_NAME | Viridian | FastAPI title. |
| APP_ENV | development | Environment label; not a production control. |
| MOCK_MODE | true | Fixture retrieval; false selects Pinecone hybrid search. |
| API_PREFIX | /api/v1 | Prefix for authentication and chat routes. |
| API_HOST | 0.0.0.0 | Settings field; launcher currently binds directly. |
| API_PORT | 8000 | Launcher and Compose host-port mapping. |
| UI_PORT | 8501 | Launcher and Compose host-port mapping. |
| API_BASE_URL | localhost:8000 | Streamlit client API origin. |
| MEMORY_BACKEND | sqlite | `sqlite` locally or `d1` via the Worker. |
| SQLITE_PATH | data/sessions.sqlite3 | Local SQLite database path. |
| D1_API_URL | empty | Dedicated Worker origin; HTTPS in production. |
| D1_SERVICE_TOKEN | empty | Shared backend/Worker secret; minimum 32 chars. |
| D1_TIMEOUT_SECONDS | 5 | D1 request timeout between 1 and 30 seconds. |
| AUTH_SIGNING_SECRET | empty | Shared JWT key; production requires 32+ chars. |
| AUTH_ISSUER | viridian | Expected token issuer. |
| AUTH_AUDIENCE | viridian-api | JWT audience check. |
| AUTH_TOKEN_TTL_SECONDS | 900 | Token lifetime from 60 to 86400 seconds. |
| CORS_ORIGINS | http://localhost:8501 | Browser origin allowlist. |
| LOG_LEVEL | INFO | Root application log level. |
| RATE_LIMIT_CAPACITY | 30 | Initial per-user token count in this process. |
| RATE_LIMIT_REFILL_PER_SECOND | 0.5 | Per-user token refill rate. |
| DEV_USERS_JSON | empty | Inline demo accounts or local user-file path. |
| LLM_PROVIDER | mock | Deterministic mock or configured OpenAI. |
| OPENAI_API_KEY | empty | Required only when the provider is OpenAI. |
| OPENAI_MODEL | gpt-4.1-mini | Structured-output model; not benchmarked. |
| LLM_TIMEOUT_SECONDS | 30 | Per-request deadline from 1 through 120 seconds. |
| LANGSMITH_TRACING | false | Optional; see observability guide. |
| LANGSMITH_ENDPOINT | api.smith.langchain.com | LangSmith Cloud API endpoint. |
| LANGSMITH_API_KEY | empty | Secret required when tracing is enabled. |
| LANGSMITH_AGENT_ID | viridian | Optional local agent destination. |
| LANGSMITH_AGENT_ENVIRONMENT | local | Agent destination environment. |
| PINECONE_API_KEY | empty | Secret used by the Documents API adapter. |
| PINECONE_INDEX_NAME | empty | Existing index; the app never creates it. |
| PINECONE_NAMESPACE | empty | Explicit namespace selected by server config. |
| PINECONE_EMBEDDING_MODEL | llama-text-embed-v2 | Must match index schema. |
| PINECONE_EMBEDDING_DIMENSION | 1024 | Must match the index's dense schema. |
| PINECONE_TIMEOUT_SECONDS | 15 | Pinecone SDK operation deadline. |
| PINECONE_DOCUMENTS_PATH | data/samples/incident_corpus.json | Ingest source. |

`make setup` creates `data/users/default.json` when it is missing. The local
Streamlit client reads `API_BASE_URL` from its process environment or
Streamlit secrets and defaults to the Viridian Cloudflare API. Local `.env`
and Compose override that default; Compose supplies `http://api:8000`. The
production browser frontend is served as static assets by the Viridian
Cloudflare Worker. The existing Streamlit Cloud deployment remains active by
request and is outside the Cloudflare release workflow.

The local API and UI can use different configuration sources. API Settings
reads `.env`; the launcher reads process environment variables; the local UI
reads its own `API_BASE_URL`. Check the effective environment when changing
local ports or starting the processes outside Compose.
