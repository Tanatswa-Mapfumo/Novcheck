# Phase 5 completion record

Scope: Source Normalization, Provenance, and Evidence Graph only. Accepted
baseline: `ba92895`. Worktree: `/private/tmp/novcheck-phase5.WORKTREE`, branch
`phase-5-evidence-graph`. Phase 6 has not started. No merge or push performed.

Status: Tasks 1-15 complete and all 29 Phase 5 acceptance gates pass. 1259
deterministic tests pass with 5 opt-in network cases deselected; Ruff, format
and strict Pyright are clean. The vertical slice reaches REPORTED/COMPLETED
with real Phases 2-5 and visibly fixture-backed Phase 6+ mapping/adjudication.
The branch remains isolated and unmerged for the user; this is not
authorization for Phase 6.

## 1. Tasks completed

| Task | Scope | Commit |
| --- | --- | --- |
| prereq | Baseline `uv sync`/verify/`git diff --check` on `ba92895`; plan copy committed | `b445b27` |
| 1 | Canonical source/version/passage/provenance/quality contracts | `b7a3f11` |
| 2 | Canonical identifier normalization and ADR-023 | `55eed25` |
| 3 | Phase 4 cluster -> canonical source/version normalization | `ca73058` |
| 4 | Version linking and deterministic content hashing + ADR-025 | `ca73058` |
| 5 | Exact passage extraction with locator preservation | `a73175a` |
| 6 | Provenance lineage relations + ADR-024 | `27f163d` |
| 7 | Conservative lineage clustering and independence groups | `27f163d` |
| 8 | Circular provenance/dependency diagnostics | `27f163d` |
| 9 | Evidence quality separate from relevance | `27f163d` |
| 10 | Storage-independent graph domain and repository protocol + ADR-022 | `1321d80` |
| 11 | SQLAlchemy 2.x + SQLite persistence | `1321d80` |
| 12 | Retrieval/query/search-run discovery provenance mapping | `f90d8d4` |
| 13 | Phase 5 pipeline and real slice integration | `4298ecb` |
| 14 | Mandatory 18-case adversarial suite | `0982f8d` |
| 15 | Guards, traceability, README and this record | final commit |
| fix | Reserved `confidence` name kept banned from production code | `1043f70` |

Tasks 3 and 4 share commit `ca73058` because the normalizer needs version
construction. Commit `27f163d` briefly left the pre-existing Phase 1
reserved-name guard red; `1043f70` fixed it immediately and the branch has
been green since.

## 2. Commits created

`b445b27`, `b7a3f11`, `55eed25`, `ca73058`, `a73175a`, `27f163d`, `1043f70`,
`1321d80`, `f90d8d4`, `4298ecb`, `0982f8d`, plus the Task 15 commit recorded
by `git log` on `phase-5-evidence-graph`.

## 3-4. Files and requirements

59 paths differ from `ba92895`. New production packages:
`evidence/normalization/{models,identifiers,versions,source_normalizer}.py`,
`evidence/passages/{models,hashing,extraction}.py`,
`evidence/provenance/{models,lineage,clustering,circularity,_components}.py`,
`evidence/quality/{models,assessment}.py`,
`evidence/graph/{models,repository,retrieval_mapping,migrations,sqlalchemy_models,sqlalchemy_repository}.py`,
`evidence/pipeline.py`, `application/evidence_phase5.py`. Modified production:
`application/vertical_slice.py`, `domain/ids.py`, `pyproject.toml`.
Documentation: ADR-022..025, `docs/traceability/phase-5.yaml`, README section,
this record, plan copy. Tests: 169 new deterministic tests (137 unit, 10
architecture guards, 19 adversarial, 2 pipeline integration, 1 slice
integration) and `tests/fixtures/phase5.py`.

Requirement mapping: FR-SRC-001/002, FR-PROV-001/002; sections 23-26, 27 as a
downstream boundary, 24, 44, 46, 49, 54, 60 Phase 5; INV-07 (independent
evidence count), INV-08/14 (claims vs evidence and citation fidelity) guarded
architecturally. Details in `docs/traceability/phase-5.yaml`. Phase 6
equivalence/support semantics are explicitly deferred there.

## 5-7. Verification

Run after the final change in the implementation worktree:

```text
uv sync --dev                  PASS; sqlalchemy 2.1.1 added, lock updated
uv run python scripts/verify.py
  Ruff check                  PASS
  Ruff format --check         PASS; 241 files formatted
  Pyright                     PASS; 0 errors, 0 warnings, 0 informations
  Pytest                      PASS; 1259 passed, 5 opt-in network cases deselected
git diff --check               PASS; no whitespace errors
```

Baseline before changes was 1090 deterministic tests; Phase 5 adds 169. A
fresh-checkout verification of the final commit is recorded below once the
final commit exists.

## 6. Adversarial tests and results

`tests/adversarial/test_phase5_provenance_attacks.py` (19 tests, all pass):

| # | Attack | Result |
| --- | --- | --- |
| 1 | Same DOI via OpenAlex/Crossref/S2 | one source, all three discovery paths retained |
| 2 | Preprint + journal | one source, two linked versions, one independent root |
| 3 | 50 derivatives of one press release | 51 sources, one independent root |
| 4 | Title-similar distinct papers | no merge, two sources |
| 5 | Patent-family duplication | three publications, one family lineage |
| 6 | Deleted/archived project | retained, BLOCKED, access limitation recorded |
| 7 | Abstract-only closest source | ABSTRACT_ONLY passage, completeness MEDIUM, limitations |
| 8 | Metadata-only candidate | no passages, Tier D |
| 9 | Search snippet | discovery-only; no passage created |
| 10 | Circular derivation | MATERIAL cycle, one lineage, ambiguity recorded |
| 11 | Mutual citation | not collapsed, two roots, INFO severity |
| 12 | Highly relevant marketing page | relevance HIGH while quality Tier D |
| 13 | Conflicting chronology | conflict + unresolved field, no guess |
| 14 | Changed content | new version/hash with predecessor |
| 15 | Prompt injection in text | inert data; identical tier to neutral content |
| 16 | One source via many queries | one source, three query/search-run paths |
| 17 | Duplicate versions | independence unchanged (one root) |
| 18 | Independent implementations | separate roots despite shared citations |
| + | No reserved adjudication edge kinds | guard passes |

## 8. ADRs created

- ADR-022 evidence graph storage (SQLAlchemy 2.x over SQLite, schema, idempotence);
- ADR-023 canonical source identity (identifier ranking and conflict rules);
- ADR-024 provenance independence (collapse vs association, confidence);
- ADR-025 passage storage and hashing (exact text, normalization, versioning).

## 9. SQLAlchemy/SQLite schema decisions

`graph_nodes(node_id PK, kind, label, document_json)`,
`graph_edges(edge_id PK, kind, source_node_id FK, target_node_id FK, document_json)`,
`lineage_clusters(cluster_id PK, document_json)`,
`lineage_cluster_members(source_id PK/FK, cluster_id FK)`,
`schema_version(version PK, applied_at)`. `document_json` is canonical JSON of
the domain model; `kind`/`label` are denormalized for queries. Foreign keys are
enforced with `PRAGMA foreign_keys=ON` per connection and dangling edges are
also rejected before flush. Canonical edge uniqueness is content-addressed via
deterministic `gedge_` identities, so identical canonical edges cannot be
persisted twice while genuinely distinct evidence remains distinct. Batch
`upsert` is one transaction; identical re-persistence is idempotent;
different content under an existing identity raises rather than overwriting.
In-memory databases use `StaticPool`; schema version 1 is created and
verified, and newer/older versions are refused. Column types stay
PostgreSQL-compatible (string keys, ISO timestamps, JSON text).

## 10. Canonical source identity

Stable identifier ranking: DOI, patent numbers, GitHub `owner/repository`,
arXiv base id, OpenAlex id, Semantic Scholar id, other identifiers, canonical
URL, then a conservative fallback over discovery identities. The source id is
`src_` + SHA-256 of the first available level's canonical value. Titles,
snippets and provider ranks never participate. Same DOI across providers yields
one source id; each provider/query/strategy/seed path stays on the record.

## 11. Conflicting identities/metadata

Every identifier observation is kept separate and merged conflict-aware. A
disagreeing field is left unset, reported as an `IdentifierConflict` with the
observed values, and listed in `unresolved_fields`; identity falls back to a
lower ranking level rather than merging. Title, author, date and source-type
disagreements are recorded as `conflicts` with unresolved field names. A
cluster with conflicting DOIs cannot establish DOI identity and never merges on
a weaker shared identifier alone.

## 12. Source versions

`SourceVersionRecord` keeps `version_id` derived from source, label and content
hash. arXiv `vN`, preprint/journal and repository releases are version-aware;
content hashes use documented Unicode/newline normalization; changed content
creates a new version linked by `predecessor_version_id` and flagged
`chronology_certain=false` when dates are missing, tied or contradicted by
observation order. Hash equality means only that normalized content is
identical; it is never treated as conceptual equivalence.

## 13. Independent evidence roots

`build_lineage_clusters` connects sources only through `CONFIRMED` dependency
relations (`VERSION_OF`, `PATENT_FAMILY_OF`, `DERIVES_FROM`, `REPOSTS`,
`IMPLEMENTS`, `DOCUMENTS`). Roots are the source-SCCs of the dependency DAG
with no outgoing dependency edges; `independent_roots` is the root-set size and
summing it is the only independence count. `CITES` and `FOUND_BY` are
association edges and never collapse lineage. `POSSIBLE` dependency edges are
retained as ambiguities and do not collapse.

## 14. Press-release/citation flooding prevention

Confirmed derivation/repost lineage collapses a press release plus any number
of derivatives into one root (51 sources -> 1 root). Shared citations leave
independent works in separate clusters (3 works citing one predecessor -> 3
roots). Deterministic `path_key` deduplication keeps one source with many
queries/providers without inflating either source or root counts.

## 15. Patent families

Patent publications keep distinct source identities (`PATENT_FAMILY_OF` is a
lineage relation, not a source collapse), but family lineage collapses them to
one independent root by default, so family members cannot inflate independence.

## 16. Relevance vs quality separation

`EvidenceQualityAssessment` (tier + seven dimensions) and
`SourceRelevanceAssessment` are disjoint contracts with no shared scalar.
`assess_quality` does not accept relevance; tiers derive from explicit signals
plus access and lineage position, and source type alone never decides a tier
(identical `PAPER` records with different access resolve to A and D in tests).
Phase 5 relevance stays explicitly `UNKNOWN` with a documented basis because
retrieval rank is a discovery proxy, not verified relevance.

## 17. Passage access limitations

Access states are `FULL_TEXT`, `ABSTRACT_ONLY`, `METADATA_ONLY`, `BLOCKED`.
Resolution failures become `BLOCKED` (or `ABSTRACT_ONLY` with an explicit
provider-supplied-abstract limitation); metadata-only sources have no version
or passage. Passage records require exact hashed text and reject any access
state below abstract-only; abstract-only passages require an abstract locator.
Titles/snippets have no extraction API at all.

## 18. Retrieval discovery path survival

Each canonical source keeps every `DiscoveryPath` (provider, provider-local id,
strategy, mechanism, family, query, seed, MCU, best rank, earliest time) as
record data. The graph maps each unique path to `DISCOVERED_BY` edges to
`Query` and deterministic logical `SearchRun` nodes, and expansion seeds become
`FOUND_BY`/`CITES` relations with the correct direction. Identical repeated
paths collapse by deterministic identity; different queries/strategies/seeds do
not. Physical provider run IDs will replace logical run identities when
providers expose them.

## 19. Circular provenance detection

`detect_provenance_cycles` finds SCCs over all non-discovery relations and
classifies them: citation-only cycles are `INFO` (ordinary mutual citation and
explicitly not dependency), confirmed dependency loops are `MATERIAL`, and
loops relying on `POSSIBLE` edges are `WARNING`. Clusters containing a
dependency cycle count as one lineage with the cycle recorded as an
unresolved ambiguity.

## 20. Deviations from the plan

- Phase 5 canonical artifacts are written under `phase5/` (matching the
  accepted `phase4/` prefix convention) so they cannot overwrite the legacy
  root `sources.jsonl`/`passages.jsonl` compatibility records.
- `SourceNormalizationResult` conflicts/unresolved fields use tuples rather
  than the plan sketch's mutable lists, preserving frozen immutability.
- Logical search-run identities are introduced (deterministic per
  provider/strategy/query/seed branch) because Phase 4 candidates carry no
  physical run IDs; this is documented in README/traceability.
- `EvidenceNormalizationResult` adds cycles/conflicts/unresolved/limitations/
  relevance beyond the plan sketch for audit completeness.
- `REPOSTS` maps to the graph's `DERIVES_FROM` edge kind because the master
  graph edge set has no separate repost kind; the relation itself is kept in
  the provenance substrate and edge attributes.
- An internal `_components.py` SCC helper module was added (not in the plan's
  file list) and is shared by clustering and circularity.

## 21. Remaining fixture-backed stages

Phase 6 mapping/equivalence, support verification, direct/partial/component/
analogy precedent, chronology validation, `SUPPORTS`/`CHALLENGES`/`CONTRADICTS`
edges; Phase 7 prosecutor/defender and adjudication gates; Phase 8 narrative
reporting. In the accepted slice these remain visibly fixture-backed
(`PHASE6_FIXTURE_BOUNDARY`, fixture provenance) over real Phase 5 sources and
passages. Patent-family/web/archive providers likewise remain unimplemented.

## 22. Acceptance gates

| Gate | Evidence | Result |
| --- | --- | --- |
| 1 | Baseline `ba92895`: sync/verify/diff-check PASS (1090 tests) | PASS |
| 2 | Final full verification: 1259 pass, Ruff/format/Pyright clean | PASS |
| 3 | Canonical source round-trip contract + artifact tests | PASS |
| 4 | Identifier normalization deterministic tests | PASS |
| 5 | Same-DOI three-provider test retains all paths | PASS |
| 6 | Similar-title/different-DOI stays distinct | PASS |
| 7 | Versions linked; arXiv/preprint/journal/release tests | PASS |
| 8 | Changed content -> new version/hash tests | PASS |
| 9 | Four access states enforced | PASS |
| 10 | Passage exactness/locator/hash tests | PASS |
| 11 | Snippet/metadata cannot become passages | PASS |
| 12 | Provenance relations and confidence tests | PASS |
| 13 | Raw source count never independence count | PASS |
| 14 | Press-release/repost flooding -> one root | PASS |
| 15 | Patent family -> one root | PASS |
| 16 | Independent works with shared citations stay separate | PASS |
| 17 | Circular dependency detectable with severities | PASS |
| 18 | Relevance/quality disjoint types and behavior | PASS |
| 19 | Tiers respect access/primaryness without type shortcuts | PASS |
| 20 | SQLite reopen/rollback/idempotence/version tests | PASS |
| 21 | Domain models storage-independent; no ORM leakage | PASS |
| 22 | Retrieval/query/run provenance survives normalization | PASS |
| 23 | All 18 adversarial cases pass | PASS |
| 24 | Slice REPORTED/COMPLETED with real Phases 2-5 | PASS |
| 25 | No Phase 6 equivalence/support adjudication | PASS (guards) |
| 26 | No `DIRECT_PRECEDENT`-style adjudicated edge creation | PASS (guards) |
| 27 | No prosecutor/defender/adjudication logic | PASS (guards) |
| 28 | README/traceability distinguish implemented/deferred | PASS |
| 29 | Phase 6 has not started | PASS |

## 23. Phase 6 status

Not started. No source-to-MCU equivalence reasoning, support verification,
precedent states, contradiction adjudication, prosecutor/defender, novelty
scores/probabilities or Phase 7+ behavior was implemented. Reserved graph edge
kinds are rejected by the domain if a Phase 5 component ever tried to create
them.
