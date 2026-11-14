# Assumptions

- `docs/assignment.md` is the authoritative specification. Its evaluation
  table supplies the weights reproduced in `docs/evaluation-matrix.md`.
- Python 3.13.9 is selected and verified locally. Project metadata declares Python `>=3.12,<3.15`; CI is configured for 3.13, so other minor versions have not been verified here.
- All fixture documents are synthetic examples for an invented enterprise and product. They do not contain real banking customer data or claim affiliation with a real bank.
- Development roles are configured in ignored `.env`. `make setup` generates random local passwords and prints them once to the operator; application logs do not print credentials or bearer tokens.
- `MOCK_MODE=true` uses fixture retrieval. `MOCK_MODE=false` uses dense and
  full-text BM25 queries against the configured Pinecone document schema and
  fuses their rankings. It does not create or change indexes.
- The backend is intended to run as one API process while using local in-memory tokens and rate buckets. Production multi-instance deployment needs shared identity and rate-limit state.
- `LANGSMITH_TRACING` controls agent-addressed LangSmith tracing. The example
  configuration selects the existing assessment agent. Inputs and outputs
  are hidden, metadata is allowlisted, and trace errors are anonymized. Run
  `make verify-langsmith` to check external delivery; CI needs no key.
- `LLM_PROVIDER=mock` is the default and requires no model credentials.
  `LLM_PROVIDER=openai` enables the structured OpenAI adapter; live provider
  behavior remains unverified until a configured key receives a response.

## Configuration reference

The API's Settings model reads process environment variables and then the
repository .env file. Empty values are ignored. Secret-bearing fields are
excluded from the Pydantic model representation. Mock mode needs no model,
LangSmith, or Pinecone credentials.

| Variable | Default | Use and limits |
|---|---|---|
| APP_NAME | Enterprise Knowledge Assistant | FastAPI title. |
| APP_ENV | development | Environment label; does not itself enable production controls. |
| MOCK_MODE | true | Selects fixture retrieval. False selects Pinecone dense and BM25 hybrid retrieval. |
| API_PREFIX | /api/v1 | Prefix for authentication and chat routes. |
| API_HOST | 0.0.0.0 | Settings field only; launch commands currently bind 0.0.0.0 directly. |
| API_PORT | 8000 | Read by run_dev and Compose host-port mapping; make api currently uses 8000. |
| UI_PORT | 8501 | Read by run_dev and Compose host-port mapping. |
| API_BASE_URL | http://localhost:8000 | Read by Streamlit from its process environment; Compose overrides it to api:8000. |
| SQLITE_PATH | data/sessions.sqlite3 | Local synchronous SQLite store path. |
| CORS_ORIGINS | http://localhost:8501 | JSON list of browser origins accepted by FastAPI. |
| LOG_LEVEL | INFO | Root application log level. |
| RATE_LIMIT_CAPACITY | 30 | Initial token capacity per user in this process. |
| RATE_LIMIT_REFILL_PER_SECOND | 0.5 | Token refill rate per user. |
| DEV_USERS_JSON | empty | Inline account JSON or file path; setup writes data/users/default.json. |
| LLM_PROVIDER | mock | Selects deterministic mock or configured OpenAI. |
| OPENAI_API_KEY | empty | Secret required only when `LLM_PROVIDER=openai`. |
| OPENAI_MODEL | gpt-4.1-mini | Model used for structured outputs; live suitability is not yet evaluated. |
| LLM_TIMEOUT_SECONDS | 30 | Per-request model timeout from 1 to 120 seconds. |
| LANGSMITH_TRACING | false | Opt-in; see `observability.md` for verification. |
| LANGSMITH_ENDPOINT | api.smith.langchain.com | LangSmith Cloud API endpoint. |
| LANGSMITH_API_KEY | empty | Secret required with tracing enabled. |
| LANGSMITH_AGENT_ID | enterprise-knowledge-assistant | Existing agent identifier. |
| LANGSMITH_AGENT_ENVIRONMENT | local | Destination environment for agent traces. |
| PINECONE_API_KEY | empty | Secret used by the Documents API adapter. |
| PINECONE_INDEX_NAME | empty | Existing document-schema index; the app never creates it. |
| PINECONE_NAMESPACE | empty | Explicit namespace selected by server configuration. |
| PINECONE_EMBEDDING_MODEL | llama-text-embed-v2 | Must match the model declared on the existing `chunk_text` field. |
| PINECONE_EMBEDDING_DIMENSION | 1024 | Must match the existing dense schema dimension. |
| PINECONE_TIMEOUT_SECONDS | 15 | Per-operation timeout for Pinecone SDK calls. |
| PINECONE_DOCUMENTS_PATH | data/samples/incident_corpus.json | Pre-chunked JSON source used by the ingestion command. |

The UI reads API_BASE_URL directly from its process environment and falls
back to localhost:8000. The API_HOST and Settings.api_port fields do not
currently control Uvicorn's bind address or port. The local launcher reads
API_PORT and UI_PORT from the process environment; Docker Compose also uses
them for host port mappings. These launcher values are not a replacement
for checking the effective runtime environment.

The API and UI may use different configuration sources: the API Settings
model reads .env, while run_dev reads port variables from os.environ and the
UI reads API_BASE_URL from os.environ. Compose injects .env values and
overrides the UI's internal service URL.
