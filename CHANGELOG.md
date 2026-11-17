# Changelog

All notable changes to the Enterprise Knowledge Assistant are recorded here.

This project uses Semantic Versioning and follows the Keep a Changelog format.

## [1.0.0] - 2026-11-17

### Added

- Streamlit chat interface backed by a FastAPI service and server-sent events.
- LangGraph workflows for greetings, knowledge questions, investigations,
  and supported numeric analysis.
- Configurable OpenAI responses with structured routing and grounded answers;
  deterministic mock mode remains available for development and tests.
- Pinecone dense and BM25 retrieval with metadata authorization filters and
  reciprocal rank fusion.
- Role-based access control, owner-scoped conversation history, and SQLite or
  Cloudflare D1 session storage.
- Bounded incident research with source attribution and trusted Python
  aggregation.
- Citation identity validation and redacted LangSmith tracing.
- Synthetic incident data and a small retrieval evaluation suite.
- Docker Compose support and automated CI checks with gated deployment
  workflows.
- User, operator, architecture, security, evaluation, and deployment guides.

### Notes

- The included incident corpus is synthetic and the retrieval evaluation is
  intentionally small; neither represents performance on customer data.
- Live OpenAI, Pinecone, and LangSmith features require credentials supplied
  through deployment configuration.
