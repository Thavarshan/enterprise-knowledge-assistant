# ADR-0003: Keep Pinecone behind a hybrid retrieval boundary

## Status

Proposed for provider integration; rank fusion utility exists.

## Context

Enterprise knowledge search needs semantic matching for paraphrases and
exact-term recall for incident identifiers, error codes, and service names.
Dense similarity and sparse ranking use different numerical scales. The
current application searches synthetic fixture data only.

## Decision

Keep loading, chunking, embedding, sparse indexing, retrieval, and fusion
behind separate contracts. Use reciprocal-rank fusion over ranked positions
if dense and sparse providers are connected. Keep Pinecone configuration
separate from the search contract.

The current Pinecone adapter is a scaffold. It has no SDK client, ingestion,
metadata filter, or query implementation. Its search raises an explicit
not-configured error. The RRF helper is implemented but is not wired into
the graph.

## Alternatives Considered

- Dense-only retrieval.
- Sparse-only retrieval.
- Direct score normalization and weighted score addition.
- A provider-managed hybrid index.

These are analytical alternatives, not recorded historical evaluations.

## Rationale

Semantic and lexical retrieval cover different query patterns. Rank fusion
avoids assuming an embedding score and a BM25 score are calibrated to the
same scale. Separate contracts allow deterministic tests before provider
credentials or indexing exist.

## Trade-offs

Hybrid retrieval can improve recall across varied language, but requires
ingestion, index operations, access metadata, ranking evaluation, and
provider failure policy. RRF discards score magnitude and depends on the
quality and limits of each input ranking.

## Consequences

Before production use, choose embedding and chunk versions, index dimensions
and metric, namespace mapping, metadata schema, top-k limits, retry and
timeout behavior, and source update/deletion semantics. Evaluate dense,
sparse, and fused ranking against labeled queries.

## Security and Operational Implications

The server must derive namespace and metadata filters from authenticated
identity and apply them before returning text. Namespace isolation does not
replace per-document access checks. The current adapter makes no security
claim because it performs no provider operation.

## Revisit Conditions

Revisit the ranking design after real ingestion and a labeled retrieval
evaluation show whether dense, sparse, or hybrid search meets recall,
precision, latency, and cost requirements.
