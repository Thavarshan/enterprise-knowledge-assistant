# Assumptions

- The referenced `Lead AI Assignment.pdf` was not present in the workspace or available attachments during implementation. The pasted task is treated as the fallback specification. Numeric evaluator weightings are therefore unavailable and are not invented in the evaluation matrix.
- Python 3.13 is selected for the local environment; project metadata supports Python 3.12 through 3.14.
- All fixture documents are synthetic examples for an invented enterprise and product. They do not contain real banking customer data or claim affiliation with a real bank.
- Development roles are configured in ignored `.env`. `make setup` generates random local passwords and prints them once to the operator; application logs do not print credentials or bearer tokens.
- Local mode uses a fixture-backed retriever. `MOCK_MODE=false` selects the explicit Pinecone boundary, which currently returns an actionable not-configured failure rather than silently choosing another production database.
- The backend is intended to run as one API process while using local in-memory tokens and rate buckets. Production multi-instance deployment needs shared identity and rate-limit state.
- LangSmith integration uses LangGraph's native environment-based tracing and is disabled by default. No external trace was tested as part of the foundation.
