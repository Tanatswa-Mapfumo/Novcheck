# ADR-024: Provenance independence and conservative lineage collapse

Status: Accepted for Phase 5 implementation

## Decision

Provenance relations are directed (`subject RELATION object`) and always carry
the evidence that established them:

- `CITES` — subject cites object (structured reference lists);
- `DERIVES_FROM` — subject derives from object (derivative coverage, extends/based-on);
- `REPOSTS` — subject reposts/mirrors object;
- `VERSION_OF` — subject is a version of object (preprint/journal, `vN`, releases);
- `PATENT_FAMILY_OF` — subject shares a patent family with the object used as family primary;
- `IMPLEMENTS` — subject implements object;
- `DOCUMENTS` — subject documents object;
- `FOUND_BY` — subject was discovered through the object as expansion seed (retrieval record).

Lineage confidence is categorical: `CONFIRMED` only when structured metadata
(citation lists, explicit version/DOI links, patent-family identifiers,
retrieval records, repository metadata) states the relation; textual hints,
credits and inferred similarity stay `POSSIBLE`. Model speculation never
creates `CONFIRMED` lineage. Multiple relations between the same pair are
allowed and retained.

Independence accounting treats these relations as dependency edges:
`VERSION_OF`, `PATENT_FAMILY_OF`, `DERIVES_FROM`, `REPOSTS`, `IMPLEMENTS`,
`DOCUMENTS`. Citation (`CITES`) and discovery (`FOUND_BY`) are association
edges only: shared citations never collapse two works.

Only `CONFIRMED` dependency edges collapse lineage. `POSSIBLE` edges are
retained and reported as unresolved ambiguities; uncertainty blocks forced
collapse. A source with no outgoing confirmed dependency edge inside its
connected component is an independent root; `independent_roots` counts roots,
never raw sources.

Consequences:

- a press release plus fifty confirmed derivatives counts as one root even
  though fifty-one sources exist;
- patent-family members keep distinct publication identities while counting
  as one family lineage by default;
- two genuinely independent implementations that merely cite the same
  predecessor remain separate roots;
- a single source discovered through many queries/providers remains one
  source with many discovery paths;
- circular derivation is detected separately (`evidence/provenance/circularity.py`)
  and marks the cluster ambiguous instead of producing a fabricated root count;
- when provenance is merely possible, the system prefers a visible over-count
  of independent lineages over a silent false merge.
