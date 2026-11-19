# 🌿 Viridian

Viridian is an explainable enterprise knowledge assistant. The hosted
platform uses Streamlit Cloud for the UI, Vercel for the FastAPI backend,
and Cloudflare D1 for session storage through an authenticated gateway.

## Live demo

Open the [Viridian live demo](https://viridian.streamlit.app/). The FastAPI
health endpoint is
[viridian-api.vercel.app/health](https://viridian-api.vercel.app/health).
The public demo accounts use synthetic data; do not reuse their passwords.

| Account | Password |
|---|---|
| Viewer (`viewer`) | `viewer-demo-2026` |
| Analyst (`analyst`) | `analyst-demo-2026` |
| Administrator (`admin`) | `admin-demo-2026` |

Streamlit Cloud deploys UI changes from its configured Git branch. GitHub
Actions gates the D1 gateway and Vercel API deployments on `ci-gate`.

### Aurelion case-intelligence walkthrough

The hosted Pinecone namespace contains 40 fictional records spanning
ServiceNow-style cases, Jira issues, release notes, and knowledge articles.
Try the main investigation prompt:

> Investigate CS001245. Settlement records go missing when the worker retries.

The answer should treat ENG-421 as a candidate, cite the two earlier cases
and release note, and ask which LedgerSync version and build is installed.
Follow up with “The customer reports LedgerSync version 5.8.1,” then try
5.8.3. A reported version is an observation; it does not prove the cause.

To demonstrate document authorization, use a fresh conversation for each
role:

1. As Viewer, ask “What does case CS001288 say?” It should not return that
   Analyst-only case.
2. As Analyst, ask the same question. CS001288 should be available with a
   source citation.
3. As Analyst, ask “What does case CS001297 say?” It should remain
   unavailable.
4. As Administrator, ask the same question to retrieve CS001297.

All Aurelion example records are synthetic and pre-seeded. The demo does not
connect to live ServiceNow, Jira, or SharePoint systems.

## Architecture

```mermaid
flowchart LR
    B[Browser] --> UI[Streamlit Cloud]
    UI --> API[FastAPI on Vercel]
    API --> AUTH[Authentication and RBAC]
    API --> CHAT[LangGraph assistant]
    CHAT --> RET[Pinecone retrieval]
    CHAT --> LLM[OpenAI]
    API --> LS[LangSmith tracing]
    API -->|Authenticated HTTPS| G[Cloudflare D1 gateway]
    G --> D1[(Cloudflare D1: viridian-sessions)]
```

The FastAPI backend runs on Vercel with the configured OpenAI, Pinecone,
LangGraph, and LangSmith integrations. Cloudflare hosts the narrow D1 gateway
and database; the API reaches them with a server-side service token.

## Local development

Requirements: Python 3.12–3.14, `uv`, and GNU Make. Docker Compose is
optional.

```bash
uv sync --all-groups --all-extras
make setup
make dev
```

`make setup` creates local demo users if no user file exists. It prints
generated passwords once and stores them in ignored
`data/users/default.json`. The local Streamlit client uses the local FastAPI
service. Run `docker compose up --build` to use containers instead.

Local OpenAI, Pinecone, and LangSmith integrations are optional. They are
disabled by default; configure them through `.env` for local provider use.
For local Cloudflare-style D1 development, use `make cloud-sim`; the
simulation uses a disposable local D1 database.

## Verification

```bash
make check
make audit
```

`make verify-live` and `make verify-langsmith` explicitly contact optional
external providers and are not required for the hosted release.
Review their configuration and account usage before running them.

GitHub Actions runs lint, formatting, package build, tests, type checks,
dependency audits, D1 Worker checks, and deployment configuration checks.
After the full CI gate passes on `main`, it applies forward-only migrations
to `viridian-sessions`, deploys the D1 gateway, then deploys the FastAPI
backend to Vercel. It smoke-checks the gateway and API health, readiness, and
provider configuration. See [CI/CD operations](docs/ci-cd.md) and the
[deployment guide](docs/deployment.md).

## Implemented behavior

- Server-assigned Viewer, Analyst, and Administrator roles protect tools and
  document access.
- Local Python runs use LangGraph to route greetings, knowledge questions,
  bounded investigations, and supported numeric calculations.
- The hosted API uses LangGraph to route knowledge questions, bounded
  investigations, and supported numeric calculations.
- Server-sent events report workflow and tool activity without exposing
  private chain-of-thought.
- D1 stores owner-scoped conversation history. The API holds the D1 gateway
  credential; browser requests never receive it.
- LangSmith tracing redacts inputs and outputs before sending traces.

## Limits

The hosted assessment namespace contains 40 fictional Aurelion records across
cases, Jira issues, release notes, and knowledge articles. Ingestion accepts
pre-chunked JSON rather than arbitrary PDF or DOCX documents. The existing
four-query retrieval measurements apply to an earlier synthetic corpus and
do not establish relevance on this Aurelion set. Prompt-injection checks are
defense in depth. Production identity, distributed rate limits, semantic
memory, and a human approval flow are not implemented.

## Guides

- [Architecture](docs/architecture.md) and
  [request lifecycle](docs/request-lifecycle.md)
- [Agent design](docs/agent-design.md),
  [retrieval design](docs/retrieval-design.md), and
  [model provider](docs/model-provider.md)
- [Security](docs/security.md),
  [observability](docs/observability.md), and
  [evaluation matrix](docs/evaluation-matrix.md)
- [Production deployment](docs/deployment.md)
- [CI/CD and release operations](docs/ci-cd.md)
- [Demonstration guide](docs/demo-guide.md) and
  [architecture decisions](docs/decisions/README.md)

The authoritative assessment is `docs/assignment.md`. Planning files are
kept local and ignored by Git.
