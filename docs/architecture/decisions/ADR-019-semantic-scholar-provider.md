# ADR-019: Semantic Scholar graph retrieval

Status: Accepted for Phase 4 implementation

Use the existing HTTP runtime and async ports for Graph v1 relevance search, paper
metadata, directional citations/references and explicit author-paper traversal.
Provider code remains under providers/ alongside the accepted Phase 3 adapters.
No SDK or new dependency is introduced. Optional SEMANTIC_SCHOLAR_API_KEY is resolved
only at request time through CredentialRef and supplied as x-api-key, with recursive
known-secret/key redaction. All used wire fields are schema-validated.

Relevance results are limited to the provider's 1000-result window; graph offsets
are separate. Every graph discovery retains its seed and direction. Author traversal
has explicit author/offset cursors rather than recursively expanding every author.
Requests are conservatively paced at one per second, with explicit retries/failures.

SPECTER embeddings may be retained as provider-local features. Relevance search is
not advertised as a native semantic-query operation: OpenAlex supplies that capability
in this phase. Scores and embeddings cannot become cross-provider probabilities.
Partial/year-only publication dates stay provisional/uncertain; Phase 5 resolves truth.

Official contracts checked 2026-09-27:
- https://api.semanticscholar.org/api-docs/graph
- https://api.semanticscholar.org/api-docs/snippets
- https://webflow.semanticscholar.org/product/api
