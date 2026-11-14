# Retrieval and evidence design

## Retrieval modes

`MOCK_MODE=true` selects `InMemoryRetriever` over
`data/samples/documents.json`. It applies access and department filters before
deterministic lexical overlap scoring and makes no provider calls.

`MOCK_MODE=false` selects `HybridRetriever` over the configured Pinecone
adapter. The adapter runs separate semantic and full-text BM25 searches in
the same namespace; `HybridRetriever` fuses both ranked lists with reciprocal
rank fusion. It does not fall back silently if Pinecone fails.

## Pinecone schema and ingestion

The configured index is a document-schema index. Inspection showed a
1024-dimensional cosine embedding on `chunk_text` using the
`llama-text-embed-v2` model, plus English full-text search on `chunk_text` and
`title`. The SDK's Documents API is required for this schema; vector API
upserts are rejected by the service. The adapter validates the existing
schema before use and never creates or changes an index.

The source corpus at `data/samples/incident_corpus.json` contains six
synthetic payment incidents. Each source record is already one chunk and
contains stable document and chunk IDs, title, department, type, access
level, date, source, and content. Ingestion is explicit:

```bash
uv run python scripts/ingest_pinecone.py
```

The script calls `documents.upsert` with `_id` derived from the complete
document/chunk pair and stores content in `chunk_text`. Repeating ingestion
updates the same records. It does not create namespaces or indexes and does
not split arbitrary source documents into chunks.

The live verification used the configured `assessment-demo` namespace, which
was empty before the test. The test upserts only the synthetic corpus and
checks semantic retrieval, exact incident-ID retrieval, and viewer filtering.
It is opt-in because it writes to the configured Pinecone namespace:

```bash
PINECONE_RUN_LIVE_TESTS=true \
  uv run pytest tests/integration/test_pinecone_live.py -q
```

## Dense and BM25 searches

Dense retrieval sends `EmbedQuery(field="chunk_text", query=...)` to the
Documents API. The index schema embeds the query with its configured model.
Sparse retrieval sends `TextQuery(fields=["chunk_text"], query=...)`, which
uses Pinecone full-text BM25 scoring. Exact incident IDs and service terms
are therefore ranked separately from semantic similarity. See the
[Pinecone SDK scoring reference](https://sdk.pinecone.io/python/_modules/pinecone/models/documents/score_by.html).

The repository also contains a local `BM25Retriever` for deterministic tests
and local corpus evaluation. Live application hybrid search uses Pinecone's
BM25 full-text query so both production rankings come from the indexed
corpus.

## Authorization and metadata

The API resolves the user's role from the bearer token. The knowledge tool
maps it to allowed labels:

| Role | Allowed document levels |
|---|---|
| Viewer | viewer |
| Analyst | viewer, analyst |
| Administrator | viewer, analyst, administrator |

Both Pinecone queries receive an `access_level` filter and the optional
department filter before fields are returned. The adapter checks the returned
access level and department again before it constructs a `DocumentChunk`.
Client input, model output, and retrieved metadata never choose a role or
access label. The namespace comes from server configuration and is not
treated as a substitute for document-level authorization.

`DocumentChunk` and `DocumentMetadata` reject extra fields and validate
provenance types. Pinecone source content is capped at 30,000 UTF-8 bytes per
chunk before ingestion. The current corpus is synthetic; connecting real
documents requires a reviewed source and retention policy.

## Hybrid ranking

`reciprocal_rank_fusion` combines dense and BM25 lists by one-based position:

```text
RRF(document, chunk) = sum(1 / (rank_constant + position))
```

The default `rank_constant` is 60. The score is a fusion score, not a
probability or direct provider relevance value. Duplicate candidates use the
full `(document_id, chunk_id)` identity, and ties sort by both identifiers.
The live adapter requests up to three times the final result limit, capped at
twenty candidates, from each ranking method.

The live synthetic checks confirmed that a paraphrase about a saturated
webhook queue ranked `incident-2026-057` first, an exact `INC-2026-099`
query ranked `incident-2026-099` first, and viewer search omitted analyst
and administrator incidents.

## Timeouts and failures

The Pinecone SDK client timeout and an enclosing async timeout both use the
configured `PINECONE_TIMEOUT_SECONDS` value. SDK retries are disabled so one
operation stays within its deadline. Synchronous SDK calls run in worker
threads. Cancellation propagates, while other provider errors are logged by
type and returned to ChatService as a generic assistant failure.

Hybrid retrieval requires both ranked lists. If either Pinecone query fails,
the graph fails the turn; there is no deterministic or BM25-only fallback in
live mode. Empty rankings are valid and produce the no-accessible-evidence
response when both searches complete without matches.

## Attribution and citation validation

The response model returns claims with complete document and chunk IDs.
Graph code resolves each identity against the current authorized result set,
constructs citations from canonical metadata, and renders markers as
`[document_id#chunk_id]`. Citation validation compares the complete identity
pair before answer chunks are emitted. Unknown model identities cause the
answer to be withheld.

The marker grammar allows ASCII letters, digits, underscore, and hyphen in
each ID. Ingestion must preserve those characters unless the marker grammar
and validator are changed together.

## Evaluation limits

The live test covers six synthetic incidents, one paraphrased semantic
query, one exact incident ID, and one viewer access boundary. It is a useful
smoke check, not a labeled retrieval benchmark. Production evaluation needs
broader queries, multiple departments, empty-result checks, and recall and
ranking measures over an approved corpus.
