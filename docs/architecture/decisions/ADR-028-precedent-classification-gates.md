# ADR-028: Constrained precedent classification and anti-stitching

Status: Accepted for Phase 6 implementation

## Decision

Precedent classification is a deterministic stage over two earlier stages: the
passage-grounded mapping (dimension comparison) and the independent support
verification (commitment states). It never receives quality tiers, retrieval
ranks, provider scores or any novelty verdict, and it never re-runs mapping.

Every classification is single-source by construction
(`single_source: Literal[True]`) and explicitly local
(`scope="LOCAL_SOURCE_MCU"`, `global_absence_claim_permitted: Literal[False]`).
`NO_DIRECT_PRECEDENT_IDENTIFIED` therefore means only "this source did not
establish direct precedent for this MCU", never a global absence claim.

Relation rules, in priority order:

1. verified contradiction -> `CONTRADICTORY_EVIDENCE`;
2. exhausted insufficient context -> `UNRESOLVED` with the needed context;
3. no supported material commitment -> `SUPERFICIAL_SIMILARITY` when any
   dimension matched, otherwise `NO_DIRECT_PRECEDENT_IDENTIFIED`;
4. every material commitment supported and decisive (pre-cutoff) ->
   `DIRECT_PRECEDENT`; if chronology is post-cutoff or uncertain the same
   evidence stays `UNRESOLVED` and cannot be decisive;
5. partial support: functional match with an unsupported mechanism and
   configuration -> `ANALOGOUS_PRECEDENT`; claimed configuration unsupported
   while ingredients are supported -> `COMPONENT_PRECEDENT_ONLY`; more than
   half of the material commitments supported -> `STRONG_PARTIAL_PRECEDENT`;
   otherwise structural partial support -> `COMPONENT_PRECEDENT_ONLY`, and
   only soft/unsupported overlap -> `SUPERFICIAL_SIMILARITY`.

Direct precedent requires every material commitment of one source/version,
including contribution-bearing relationships and configuration. Merging
sources is structurally impossible in a classification: multi-source support is
summarized by `summarize_multi_source`, which reports
`MULTI_SOURCE_COMBINATION_ONLY` and `stitched_direct_forbidden=True` whenever
two or more independent lineage roots contribute without any single source
being direct-eligible. Sources sharing one lineage root (versions, mirrors,
patent family) count once.

The counterfactual-removal diagnostic (FR-EQ-004) removes one recorded
differentiating element and reports the remaining distinction. It is
explicitly `diagnostic_only` and never mutates a classification.

## Consequences

Combination claims cannot be satisfied by accumulating partial sources, and
relationship loss defeats direct equivalence even when feature overlap is
high. Quality is attached to edges after classification and cannot change the
relation. The cost is a conservative bias toward partial/component states when
a human might accept a combination argument; that is intentional, because
stitching is the failure mode that fabricates false direct precedent.
