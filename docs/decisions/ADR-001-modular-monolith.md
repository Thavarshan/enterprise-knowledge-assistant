# ADR 001: Keep API, UI, and domain in one modular monolith

- **Status:** Accepted
- **Decision:** Maintain one repository, package, lockfile, and container image. Run FastAPI and Streamlit as separate processes but keep retrieval, security, memory, tools, and agents as internal modules.
- **Reason:** The assessment requires enterprise boundaries without independent microservices. One codebase reduces local setup and deployment coordination while keeping interfaces replaceable.
- **Consequences:** Module dependencies need review to avoid cycles. Split a service only when measured scaling or ownership requires it.
