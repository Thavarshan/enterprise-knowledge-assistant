# ADR-0003: Use Pinecone dense and BM25 retrieval with rank fusion

## Status

Accepted and verified for the synthetic assessment corpus.

## Context

Enterprise search needs semantic matching for paraphrases and exact-term
recall for incident identifiers, error codes, and service names. The
configured Pinecone index is a document-schema index with a 1024-dimensional
cosine embedding on `chunk_text` and English full-text search on `chunk_text`
and `title`. The installed Pinecone SDK is 10.3.0.

## Decision

Use the Pinecone Documents API for this index. Store stable document/chunk
identities and validated metadata in its configured namespace. Run one
`EmbedQuery` search and one `TextQuery` BM25 search with server-derived
access, department, type, and date filters. Combine both rankings with
reciprocal rank fusion keyed by the complete document/chunk pair.

The adapter validates the existing embedding and full-text schema before
use. It does not create, configure, or delete indexes. The ingestion command
accepts pre-chunked JSON records and uses deterministic IDs so repeat runs
update the same synthetic chunks. The assessment corpus contains eighteen
fictional incident records.

## Alternatives Considered

- Dense-only retrieval.
- Sparse-only retrieval.
- Direct score normalization and weighted score addition.
- Local BM25 fusion with Pinecone dense results.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Dense and BM25 rankings cover different query patterns and have unrelated
score scales. RRF uses their positions without assuming score calibration.
Using the index's declared document schema avoids a parallel vector API or
separate embedding configuration.

## Trade-offs

Hybrid retrieval needs two requests and the quality of both ranked lists
matters. A four-case evaluation produced Recall@5 of 1.00 for dense, BM25,
and RRF. BM25 MRR was 0.67; dense and RRF MRR were 1.00. These results are
only a smoke evaluation on synthetic records. The corpus is pre-chunked; no
general PDF/DOCX loader or source chunker is included.

## Consequences

`MOCK_MODE=false` requires valid Pinecone credentials, the matching index
schema, and an explicit namespace. Provider timeouts and retries are bounded.
If either ranking request fails, the graph fails the turn rather than
silently switching to a different retrieval mode.

## Security and Operational Implications

The server derives access labels from the authenticated role and sends them
as provider-side metadata filters. The adapter checks access and department
again before returning chunk content. Namespace selection comes from server
configuration and does not replace per-document access filters.

## Revisit Conditions

Revisit model, schema, candidate limits, and fusion strategy after a broader
labeled evaluation compares recall, precision, latency, and cost on an
approved corpus.
