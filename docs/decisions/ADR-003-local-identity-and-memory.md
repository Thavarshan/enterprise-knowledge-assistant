# ADR 003: Use server-resolved local roles and SQLite sessions in Phase 0

- **Status:** Accepted
- **Decision:** Keep local demo accounts in ignored `.env`, issue process-local opaque bearer tokens, enforce session ownership in SQLite, and use an in-memory per-user token bucket.
- **Reason:** The local mock should run without external identity, database, or cache services while exercising backend access boundaries.
- **Consequences:** Tokens and rate limits do not survive API restarts or coordinate across multiple instances. Replace them before production use.
