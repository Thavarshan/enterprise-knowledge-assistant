# Retrieval and evidence design

## Current scope

Only the fixture adapter performs end-to-end search. The repository contains
protocols for loading, chunking, dense embedding, sparse indexing, and fusion,
plus a Pinecone configuration boundary. There is no ingestion pipeline,
embedding model, Pinecone SDK client, BM25 index, or provider query in the
current application.

`MOCK_MODE=true` selects `InMemoryRetriever` over
`data/samples/documents.json`. With mock mode disabled, the API factory
selects `PineconeRetriever`, whose `search` raises
`PineconeNotConfigured`. It does not silently switch providers.

## Fixture data and metadata

Each fixture chunk has text and validated metadata:

| Field | Purpose |
|---|---|
| `document_id` | Stable parent source identifier. |
| `chunk_id` | Stable evidence identifier used in citation markers. |
| `title` | Human-readable source title and searchable text. |
| `department` | Optional exact department filter. |
| `document_type` | Source classification label. |
| `access_level` | `viewer`, `analyst`, or `administrator`. |
| `created_date` | Source date validated as a date value. |
| `source` | Attribution URI or source reference. |

The Pydantic models are frozen and reject unknown fields. They validate
shape, not authorization. Source documents are synthetic examples and are
loaded from the repository fixture; production ingestion and provenance
generation are deferred.

## Access filtering and local ranking

The API creates a trusted role from the bearer token. The knowledge tool
maps it to allowed access labels:

| Role | Allowed document levels |
|---|---|
| Viewer | viewer |
| Analyst | viewer, analyst |
| Administrator | viewer, analyst, administrator |

The retriever filters access level and optional department before examining
content for ranking. This order prevents disallowed fixture text from
entering graph state. Future adapters must apply authorization server-side;
client-supplied filters are not evidence of permission.

The in-memory score is lexical token overlap:

1. Lowercase and extract alphanumeric tokens from the query.
2. Deduplicate query tokens.
3. Count matching occurrences in each title and chunk body.
4. Drop chunks with no overlap.
5. Sort by descending count, then document ID.
6. Divide each count by the highest count and assign one-based ranks.

This is a deterministic fixture heuristic. It is neither BM25 nor semantic
similarity. Repeated terms in document text add to the count, but repeated
query tokens do not. A non-positive limit returns an empty result list.
The async method performs a synchronous scan, which is acceptable only for
the small local corpus.

## Dense, sparse, and hybrid retrieval

Dense semantic retrieval compares query and passage embeddings. It can find
paraphrases and concepts with different wording, but may miss exact
identifiers or conflate similar operational terms. Sparse retrieval uses
term overlap or sparse vectors; BM25 is a common scoring method. Exact-term
retrieval is useful for incident IDs, error codes, service names, and
organizational vocabulary.

The current `SparseRetriever` is only a protocol. No BM25 implementation or
indexing process exists. The `reciprocal_rank_fusion` utility is implemented
but not called by the graph. Given ranked result lists, it adds
`1 / (rank_constant + position)` for each appearance, using one-based
positions and a default constant of 60. Repeated chunk IDs accumulate rank
evidence; tied scores sort by chunk ID. The first matching result supplies
the chunk payload. The output score is a fusion score, not provider
relevance.

RRF compares positions rather than raw scores because embedding similarity
and BM25 scores have unrelated scales. It can merge independently tuned
retrievers without assuming that a score of 0.8 has the same meaning in both.
Its utility status does not imply a working hybrid pipeline.

## Pinecone boundary and planned filter design

`PineconeConfig` holds an API key, index name, and namespace. The current
adapter creates no SDK client, reads no index schema, sends no request, and
applies no metadata filter. No claim is made about SDK behavior, index
configuration, timeout support, or network concurrency.

A real implementation must decide and document:

- Embedding model, vector dimension, normalization, and versioning.
- Index metric, deployment mode, namespaces, and tenant mapping.
- Stable document/chunk IDs and metadata types.
- Ingestion, chunk size/overlap, update, and deletion behavior.
- Provider-side access and department filters before returning text.
- Dense and sparse result limits and partial failure policy.
- Network timeouts, cancellation, retries, and blocking SDK offload.

Namespace isolation can reduce accidental cross-tenant search only when the
server selects namespaces from trusted identity and the provider's query is
constrained correctly. It is not a replacement for per-document access
filters. Metadata fields must not be trusted when supplied by a user or
retrieved from unvalidated ingestion input.

## Empty results and provider failures

No matching fixture result produces a fixed response stating that no
accessible document was found. A production provider failure currently
propagates from `PineconeRetriever` into graph execution. ChatService emits a
generic failure event; the client does not receive the provider exception.
There are no retries, fallback adapter, timeout enforcement, or partial
results.

## Attribution and citation validation

The Response node selects at most two ranked chunks. It copies each
`SourceCitation` from the chunk metadata and writes markers in the form
`[document_id#chunk_id]` beside the corresponding text. The language-model
path does not generate citations because no model is used.

The graph validation helper checks that markers equal the citation markers
whose chunk IDs occurred in the retrieved result set. This works for the
current path because Response constructs citations directly from those
results. The helper does not compare a full document/chunk tuple against the
retrieved tuple set. A future model-backed response should validate exact
pairs, reject duplicate or malformed IDs, and avoid trusting model-created
citation metadata.

The marker pattern currently permits only ASCII letters, digits, underscore,
and hyphen in each identifier. If ingestion introduces other characters,
the marker grammar and validator must change together.

## Evaluation before production use

Measure recall and ranking quality against a labeled query set that includes
paraphrases, exact incident identifiers, access-level boundaries, empty
results, and department filters. Verify that denied chunks never leave the
retriever. Test provider timeouts and partial failures before connecting the
graph. A live LangSmith trace should be checked only with an approved test
corpus and an explicit redaction decision.
