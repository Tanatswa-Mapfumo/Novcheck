# ADR-016: Retrieval perspectives and independent mechanisms

Status: Accepted for Phase 4 implementation

Phase 4 adds versioned retrieval-candidate-v1 and retrieval-batch-v1 artifacts.
Accepted Phase 3 plans, screening artifacts and async SearchProvider contracts remain
unchanged. Candidates preserve provider identity, local rank/score, query, UTC discovery
time, metadata, cursor and expansion seed. Retrieval is not verified evidence.

Nine strategy labels distinguish lexical, semantic, relational, backward citations,
forward citations, related work, entity lineage, historical terms and adjacent domains.
Directional expansion always retains its seed. Provider metadata stays local/untrusted.

Saturation uses a separate conservative mechanism taxonomy. Lexical, relational,
historical and adjacent-domain text queries share TEXT_SEARCH; paraphrase/query count
cannot manufacture diversity. Native semantic search is SEMANTIC_SEARCH. Backward,
forward and related-work neighborhoods share GRAPH_EXPANSION. Explicit author/project/
owner traversal is ENTITY_LINEAGE. Direction and perspective labels are never erased.

This grouping is an operational diversity safeguard, not an independence/provenance
judgment, evidence equivalence or calibrated confidence. Phase 5 resolves source truth
and evidence lineage; Phase 4 preserves all observations for that later work.
