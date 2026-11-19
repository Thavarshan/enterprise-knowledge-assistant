# Production deployment

Viridian uses three hosted components:

| Component | Host | Role |
|---|---|---|
| User interface | Streamlit Cloud | Streamlit presentation app. |
| FastAPI | Vercel | OpenAI, Pinecone, LangGraph, and LangSmith integration. |
| Session storage | Cloudflare D1 | D1 database accessed through an authenticated Worker gateway. |

The API origin is `https://viridian-api.vercel.app`. The D1 gateway is
`https://viridian-d1-gateway.thavarshan.workers.dev`; the database is named
`viridian-sessions`. API credentials and provider keys stay in Vercel's
production environment. The D1 service token is also configured as a secret
on the gateway and in Vercel.

## Release flow

The single `.github/workflows/ci.yml` workflow deploys only after the full
`ci-gate` succeeds on the current `main` commit:

1. Confirm the CI-approved commit is still the tip of `main`.
2. Validate the dedicated D1 database, apply approved forward-only
   migrations, and deploy the D1 gateway.
3. Smoke the gateway's authentication and D1 read/write behavior.
4. Pull Vercel production settings, build the API from the approved commit,
   and deploy it to production.
5. Check API health, D1 readiness, and the configured OpenAI and Pinecone
   providers.
6. Report success only when each deployment and smoke step succeeds.

`vercel.json` disables automatic Vercel Git deployments so they cannot go
live before the GitHub gate passes. CI uses the pinned Vercel CLI and requires
`VERCEL_TOKEN` in the GitHub `production` environment.

Streamlit Cloud watches its configured Git branch and deploys UI changes
independently. It is not invoked by GitHub Actions. The current CI release
controls the D1 gateway and Vercel API.

## GitHub production environment

Create a `production` environment restricted to `main`. Set these variables:

| Variable | Value |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account that owns the gateway. |
| `CLOUDFLARE_D1_DATABASE_ID` | UUID for `viridian-sessions`. |
| `CLOUDFLARE_D1_GATEWAY_URL` | `https://viridian-d1-gateway.thavarshan.workers.dev`. |
| `VERCEL_ORG_ID` | Vercel team ID. |
| `VERCEL_PROJECT_ID` | Vercel project ID. |
| `VERCEL_API_URL` | `https://viridian-api.vercel.app`. |

Set these secrets:

| Secret | Purpose |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Deploy the D1 gateway and apply migrations. |
| `D1_SERVICE_TOKEN` | Authenticate API requests to the D1 gateway. |
| `VERCEL_TOKEN` | Pull production settings and deploy the Vercel project. |

OpenAI, Pinecone, LangSmith, signing, and demo account credentials are read
from Vercel's production environment; do not duplicate them into the
repository or print them in CI logs. The demo accounts are synthetic and
must not be reused for other services.

## Local development

```bash
uv sync --all-groups --all-extras
make setup
make dev
```

For the disposable local Cloudflare D1 gateway simulation, use
`make cloud-sim`. It does not access the remote Cloudflare account or
production D1. The Streamlit app remains available locally as well as on
Streamlit Cloud.
