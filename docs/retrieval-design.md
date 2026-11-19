# Retrieval and evidence design

## Retrieval modes

MOCK_MODE=true selects InMemoryRetriever over
data/samples/documents.json. It filters by access, department, type, and
date before deterministic lexical-overlap ranking. It makes no provider
calls.

MOCK_MODE=false selects HybridRetriever over the configured Pinecone
Documents API index. EmbedQuery supplies dense semantic ranking;
TextQuery supplies Pinecone full-text BM25 ranking. Reciprocal rank fusion
combines both ordered lists by position, not by raw score. Both component
queries are required; live mode does not fall back silently.

## Pinecone schema and ingestion

The existing index schema has a 1024-dimensional cosine embedding on
chunk_text using llama-text-embed-v2 and English full-text search on
chunk_text and title. The Documents API is required for this schema. The
adapter validates the existing schema and never creates or changes an index.

The repository keeps an 18-record generic incident corpus for the existing
retrieval smoke set. The hosted assessment namespace uses the separate
`data/samples/aurelion_case_corpus.json` corpus: 40 fictional records across
24 ServiceNow-style cases, 8 Jira-style issues, 4 release notes, and 4
knowledge articles. Its anchor case CS001245, earlier cases CS001101 and
CS001118, issue ENG-421, release note RN-5.8.3, and superseded article KB-017
preserve the Aurelion POC scenario. No real customer information is used.

Ingestion is explicit and idempotent:

    uv run --env-file .env python scripts/ingest_pinecone.py \
      --source data/samples/aurelion_case_corpus.json \
      --delete-source data/samples/incident_corpus.json

The source JSON already contains one chunk per record. IDs are stable across
re-ingestion; raw PDF, DOCX, and arbitrary source splitting are not
implemented. The command writes only to the configured existing index and
namespace. With `--delete-source`, it removes only IDs found in that prior
corpus and absent from the new corpus, after the upsert succeeds. It never
deletes a namespace or creates an index.

The live workflow verification upserts only this synthetic corpus to the
configured namespace before testing. It does not change schema or delete
records.

## Search filters and authorization

The API resolves the role from its bearer token. Retrieval maps roles to
access labels:

| Role | Allowed document levels |
|---|---|
| Viewer | viewer |
| Analyst | viewer, analyst |
| Administrator | viewer, analyst, administrator |

The server applies that access set before Pinecone exposes fields and checks
returned metadata again before constructing a chunk. User and model text
cannot select roles or access labels.

Validated optional filters include exact department, document type, and
inclusive source dates. Recognized department names narrow the search. The
source-type parser recognizes incidents, runbooks, policies, architecture
notes, and product specifications. Relative phrases "last year", "past
year", and "last 12 months" mean a rolling calendar-year window ending on
the injected current date. On 2026-11-15, the range is 2025-11-15 through
2026-11-15, inclusive.

The index stores created_date_ordinal as a numeric metadata field so
Pinecone can apply date bounds in provider filters. The adapter also checks
the returned ISO date, department, type, and access label before it returns
content. Authorization always comes from the backend role policy.

## Hybrid ranking

For each stable document/chunk identity, RRF adds one reciprocal-rank
contribution per ranking list:

    score = sum(1 / (rank_constant + one_based_position))

The default rank constant is 60. The result is a fusion score, not a
probability. Duplicates are combined by the full document/chunk pair; ties
sort by both IDs. Pinecone requests up to three times the final result limit,
capped at twenty candidates, from each ranking mode.

## Reproducible evaluation

The labeled dataset is data/evaluation/retrieval_cases.json. It includes an
exact incident-ID query, a semantic paraphrase, a Viewer access-boundary
case, and a date-filtered empty-result case. Run:

    make evaluate-retrieval

The script requires the configured Pinecone index and namespace. It reports
dense, BM25, and hybrid RRF metrics separately and emits IDs, not source
content. On 2026-11-15, the previous 18-record generic corpus produced:

| Mode | Recall@5 | MRR | Source attribution | Access leakage | Empty accuracy |
|---|---:|---:|---:|---:|---:|
| Dense | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |
| BM25 | 1.00 | 0.67 | 1.00 | 0.00 | 1.00 |
| Hybrid RRF | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |

Recall is averaged over labeled positive queries. MRR is the mean reciprocal
rank of the first expected document. Source attribution checks every returned
document/chunk pair against the checked-in corpus. Access leakage counts
unexpected access levels and explicitly forbidden document IDs. Empty
accuracy uses only cases with a labeled empty or non-empty outcome; the
Viewer boundary case measures leakage without assuming other accessible
results are absent.

Those scores describe the earlier corpus and do not measure the current
40-record Aurelion demo corpus. Four synthetic queries are a smoke evaluation,
not evidence of production relevance. The dense embedding and BM25 index may
change over time. The scores must not be generalized to an approved
enterprise corpus.

## Timeouts, failures, and evidence

Pinecone SDK timeouts and an outer async deadline use the configured
PINECONE_TIMEOUT_SECONDS. SDK retries are disabled. Synchronous SDK calls
run in worker threads; caller cancellation propagates, although it cannot
stop an HTTP request already running in a worker. Provider errors are
sanitized at the adapter boundary.

The response model may cite only complete document and chunk IDs from the
authorized result set. The graph copies title and source from those chunks
and withholds claims with unknown identities. Incident-analysis summaries
use source-classified metadata and include each supporting source pair.
Provenance validation does not prove semantic entailment.

## Remaining limits

Searchable content is synthetic. The current ingestion source is pre-chunked
JSON, the local scoring function is lexical overlap, and the four-query
evaluation set is intentionally small. Production use needs an approved
content pipeline, relevance labels, privacy review, and broader evaluation.
