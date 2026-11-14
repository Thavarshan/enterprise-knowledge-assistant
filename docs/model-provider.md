# Model provider

The graph accepts a `ModelProvider` contract. `LLM_PROVIDER=mock` is the
default and uses deterministic intent selection and extractive, cited claims.
`LLM_PROVIDER=openai` selects the asynchronous OpenAI Responses API adapter.
The adapter parses Pydantic structured output for supervisor decisions,
grounded answer claims, and bounded research decomposition. The Supervisor
may select direct retrieval, research, or explicit numeric analysis; the
analysis handler independently parses and validates the numeric values.

OpenAI is the first provider because its official asynchronous Python SDK
supports schema-validated output without replacing the existing LangGraph
orchestration. `gpt-4.1-mini` is the configurable initial model default; the
project has not benchmarked model quality, latency, or cost. Set
`OPENAI_MODEL` to another model that supports Structured Outputs when using
the live provider.

The supervisor schema only contains a `route`. It cannot assign roles,
permissions, access labels, departments, tool arguments, or retrieval
filters. The response schema requires every claim to cite complete document
and chunk IDs from already-authorized retrieval results. Retrieved document
text and user content are treated as untrusted data by fixed system
instructions.

The adapter enforces a request timeout, disables implicit retries, and
propagates cancellation. Provider failures become a generic user-facing
failure; mock output is not used as a silent live-provider fallback. Unit
tests use stalled mocked SDK calls to verify timeout and cancellation
behavior without network access.

## Verification

Unit tests exercise deterministic provider behavior, recursive research,
analysis routing, and graph integration without network access. The live
integration test uses synthetic evidence:

```bash
uv run pytest tests/integration/test_llm_live.py -q
```

That test skips when `OPENAI_API_KEY` is absent. No live response has yet
been verified in this workspace because the local environment has no OpenAI
credential. The adapter must remain marked unverified until the test receives
and validates actual provider output.
