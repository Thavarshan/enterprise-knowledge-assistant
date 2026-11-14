# Assumptions

- The referenced `Lead AI Assignment.pdf` was not present in the workspace or available attachments during implementation. The pasted task is treated as the fallback specification. Numeric evaluator weightings are therefore unavailable and are not invented in the evaluation matrix.
- Python 3.13.9 is selected and verified locally. Project metadata declares Python `>=3.12,<3.15`; CI is configured for 3.13, so other minor versions have not been verified here.
- All fixture documents are synthetic examples for an invented enterprise and product. They do not contain real banking customer data or claim affiliation with a real bank.
- Development roles are configured in ignored `.env`. `make setup` generates random local passwords and prints them once to the operator; application logs do not print credentials or bearer tokens.
- Local mode uses a fixture-backed retriever. `MOCK_MODE=false` selects the explicit Pinecone boundary, which currently returns an actionable not-configured failure rather than silently choosing another production database.
- The backend is intended to run as one API process while using local in-memory tokens and rate buckets. Production multi-instance deployment needs shared identity and rate-limit state.
- `LANGSMITH_TRACING` controls agent-addressed LangSmith tracing. The example
  configuration selects the existing assessment agent. Inputs and outputs
  are hidden, metadata is allowlisted, and trace errors are anonymized. Run
  `make verify-langsmith` to check external delivery; CI needs no key.

## Configuration reference

The API's Settings model reads process environment variables and then the
repository .env file. Empty values are ignored. Secret-bearing fields are
excluded from the Pydantic model representation. Mock mode needs no model,
LangSmith, or Pinecone credentials.

| Variable | Default | Use and limits |
|---|---|---|
| APP_NAME | Enterprise Knowledge Assistant | FastAPI title. |
| APP_ENV | development | Environment label; does not itself enable production controls. |
| MOCK_MODE | true | Selects fixture retrieval. False selects the unimplemented Pinecone adapter. |
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
| LANGSMITH_TRACING | false | Opt-in; see `observability.md` for verification. |
| LANGSMITH_ENDPOINT | api.smith.langchain.com | LangSmith Cloud API endpoint. |
| LANGSMITH_API_KEY | empty | Secret required with tracing enabled. |
| LANGSMITH_AGENT_ID | enterprise-knowledge-assistant | Existing agent identifier. |
| LANGSMITH_AGENT_ENVIRONMENT | local | Destination environment for agent traces. |
| PINECONE_API_KEY | empty | Secret retained in settings; no client consumes it yet. |
| PINECONE_INDEX_NAME | empty | Reserved for the future Pinecone adapter. |
| PINECONE_NAMESPACE | empty | Reserved for the future Pinecone adapter. |

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
