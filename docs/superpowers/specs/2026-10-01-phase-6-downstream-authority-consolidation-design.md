# Phase 6 downstream authority consolidation design

**Status:** Proposed design for approval; no implementation authorized by this document.
**Baseline:** `phase-6-evidence-verification` at `750917734fbed622f785f96e3d1d443dea166fe7`.
**Scope:** Phase 6 downstream reads, the real Phase 6 vertical slice bridge, and the future Phase 7 input contract. Phase 7 adjudication itself remains unstarted.

## 1. Context and intent

Phase 6 produces evidence grounded local comparisons. The master design spec requires exact source passages, version awareness, relationship-level comparison, chronology, scoped uncertainty, anti-stitching, and traceable findings (sections 23–30, 31–38, 44–45, and Phase 6/7 exit criteria). R10–R14 established immutable content ancestry, committed semantic artifacts, post-commit publication, manifest resolution, and schema-v6 graph membership. The intended outcome is **one repository authority with rich downstream views**, preserving every useful Phase 6 fact and a clear future input for prosecutor, defender, and neutral adjudicator agents.

The user has chosen to retire `project_verified_edges()` from the trusted Phase-6-to-future-stage boundary if capability is preserved. This design treats that choice as direction for the architecture, not approval to delete code or implement Phase 7.

## 2. R15 problem statement

R15 is valid. At the reviewed commit, removing `phase6_graph_edge_memberships` and `phase6_graph_node_memberships` hides a direct relation and proposition from graph readers, but `resolve_phase6_commit(receipt)` and `project_verified_edges(result, repository)` still export a `DIRECT_PRECEDENT` legacy edge. The semantic commit resolver checks persisted chain and classification, while the adapter never asks whether the corresponding graph projection remains authorized. The same stored state therefore has two conflicting downstream answers about graph authority.

R15 remains open until an implemented boundary removes this trusted adapter path, preserves its useful output, and passes independent review. No existing FAIL record is revised by this design.

## 3. Existing architecture and authority locations

```text
Phase 5 source/version and passage records
  -> Phase 6 mapping, claim, verifier, chronology, classification
  -> repository upsert: verified edge + chain + classification + graph projection
  -> manifest + v6 edge/proposition memberships (one transaction)
  -> graph readers: membership and semantic-chain checks

Parallel legacy route at the reviewed commit:
  Phase6EvidenceResult + receipt -> resolve_phase6_commit
  -> project_verified_edges -> EvidenceEdge -> fixture adjudicator/report
```

The SQL repository stores `verified_edges`, `verified_chains`, `verified_classifications`, observations, `phase6_commits`, graph rows, graph memberships, and lineage clusters. A `VerifiedEvidenceChain` embeds the source, optional exact version, proposition, mapping, support bundle and passages, verification, context passages, and verified edge. A `ClassifiedComparison` binds that chain to the classification. The manifest identifies the committed pair. The graph row is a derived projection whose *graph authority* requires its v6 membership and current read validation. `Phase6CommitReceipt` is a locator, never proof.

The pipeline also writes profiles, failed candidate outcomes, coverage, context expansion attempts, multi-source summaries, patent screenings, and limitations into `Phase6EvidenceResult`, JSON/JSONL artifacts, and selected trace events. Those assessment-wide records are **not all reconstructible from the current SQL semantic tables**. File presence or a trace event is audit data; neither grants a Phase 6 relation authority.

## 4. Capability-parity audit

`L` describes the actual `project_verified_edges()` output, not every optional value that an unrelated Phase 1 `EvidenceEdge` fixture could set. `S` means the current committed chain/classification or repository graph. `A` means a Phase 6 result or run artifact outside the current semantic repository. “Gap” names work needed for a complete repository-derived Phase 6 assessment view. A graph node's `attributes` alone are not accepted as a substitute for the validated chain.

| Semantic capability | Legacy adapter `L` | Current source | Equivalent or richer? | Gap for canonical downstream view |
| --- | --- | --- | --- | --- |
| Relation/class | `relation_type` | `ClassifiedComparison.classification.relation`; some classes project graph edges | S richer: full basis and nine local classes | Graph has no dedicated relation edge for every class; retain committed status separately from graph relation authority |
| MCU/combination target | `mcu_id` only | Chain proposition; MCU graph node has `target_kind`/`combination_id`; full profile in A | S/A richer | Persist or bind the full combination profile, members, and topology in the repository assessment ledger |
| Source ID | `source_id` | Chain source and graph source node | S richer | None for committed comparison |
| Exact source version | absent | Chain version, disclosure, version node | S richer | None for committed comparison |
| Passage IDs | `passage_ids` | Verified edge and cited commitment records | S richer | None for committed comparison |
| Passage text, locator, attestation | absent | Chain bundle/context passages, attested parent digest and span | S richer | Expose exact cited passages, access state and limitations in view |
| Mapping identity and dimensions | absent except flattened comparison | Chain mapping ID, dimension mappings, directed relationships and passage links | S richer | None for committed comparison |
| Proposition/claim identity | proposition text only | Proposition ID, commitments, claim ID/digest, bundle | S richer | None for committed comparison |
| Commitment-level verification | aggregate `support_verification` | Verification records, citation IDs, supported/unsupported portions | S richer | None for committed comparison |
| Five verifier states | one aggregate state | Verification aggregate and per-commitment states | S richer | Keep all five, including negative and insufficient, in view |
| Scoped partial support | absent | Verification subset/remainder; classification `scoped_coverage` | S richer | None for committed comparison |
| Chronology/cutoff | tri-state `predates_cutoff` | `CitedDisclosure`, `ChronologyAssessment`, eligibility | S richer | Show date basis, cutoff and uncertainty, not a Boolean alone |
| Decisiveness/eligibility | implicit in relation and tri-state date | Edge `decisive` and `eligibility` | S richer | None for committed comparison |
| Verification/classification IDs and basis | absent | Chain and classification; manifest pairs IDs | S richer | Include IDs and classification basis explicitly |
| Relationship/control-flow semantics | flattened strings in `comparison` | Proposition commitments, structured mapping, classification coverage | S richer | Bind full target profile for combination topology |
| Multi-passage evidence | IDs only | Cited and context passages with separate attestations | S richer | None for committed comparison |
| Multi-source/lineage context | absent | Lineage clusters in repository; summary in A | S/A richer | Store input-bound summary or derive it from a complete assessment ledger and current lineage snapshot |
| Patent-specific distinctions | absent | Patent screening and locators/dates in A; source/version in chain | A richer | Persist screening and its exact committed input IDs, or deterministically reconstruct and version it |
| Unresolved/no-direct/contradiction | `relation_type` only when adapter receives a chain | Full classification in S; failed unassessable candidate in A | S/A richer | Preserve unchained failures and distinguish local no-direct from global absence |
| Coverage and failed candidates | absent | `Phase6EvidenceResult`, `coverage.json`, candidate failures, trace | A richer | Persist bounded selection ledger, exclusions, reasons, and failure states in repository |
| Access and evidence quality | `evidence_quality`; `access_limitations=()` | Edge quality tier; passage/source access and limitations; Phase 5 quality artifact | S/A richer | Resolve full quality record if needed; do not repeat the adapter's empty limitation field |
| Relevance strength | optional class field, adapter leaves `None` | Mapping dimensions/relevance are distinct from verification | No loss from retiring actual adapter | Do not invent a scalar strength; define a separate versioned metric only if later required |
| Audit provenance and prompt versions | fixed `PHASE6_PROVENANCE` | Per-artifact provenance, prompts/rubrics, observation rows, traces | S/A richer | Link read view to trace/artifact IDs without trusting files as semantic authority |
| Commit identity and graph endpoints | absent | Manifest/receipt, graph nodes, graph edges, membership | S richer | Carry commit and validated graph IDs; verify both on read |

### Exact parity conclusions

**A.** The SQL repository contains every nonconstant fact that the *actual adapter output* uses for a committed comparison: edge/source/target IDs, proposition, passages, flattened mapping comparison, relation, support state, chronology state, and quality tier. It does **not** yet contain all assessment-wide Phase 6 facts needed for a rich future consumer: bounded coverage, failed/unassessable candidates, full target profiles, all expansion attempts, and patent/multi-source result snapshots currently live in `Phase6EvidenceResult` and run artifacts. The adapter omits these too, so retiring it does not itself cause their absence; the recommended interface must close the gap.

**B.** The committed chain and classification are substantially richer than `EvidenceEdge`: exact version, passage text and attestation, material commitments, mapping dimensions, per-commitment verifier judgments, scoped partials, disclosure dates, eligibility, classification basis, and lineage joins.

## 5. Legacy adapter lossiness analysis

**C.** The adapter flattens or drops source version, passage provenance and limitations, scope and subset/remainder, combination topology, detailed chronology, context completeness, uncertainty reasons, commit identity, and graph authority. It maps chronology to `True`/`False`/`None`, sets `access_limitations=()`, and replaces artifact-specific provenance with a constant. The optional legacy `relevance_strength` is not populated. The old adapter must not define Phase 7's semantic ceiling.

## 6. Consumer and call-graph inventory

Repository-wide search covered `project_verified_edges`, `EvidenceEdge`, `evidence_phase6`, `resolve_phase6_commit`, `evidence_edges.jsonl`, and their protocol/report callers.

| Caller or surface | Current role | Authority needed | Design disposition |
| --- | --- | --- | --- |
| `evidence/phase6_pipeline.py::_commit_candidate` | Production Phase 6 write; resolves receipt before semantic publication | Semantic commit, then graph projection for graph-facing success | Keep repository commit; require the new downstream view to validate graph membership before relation publication |
| `application/evidence_phase6.py::Phase6EvidenceComponents` | Production Phase 6 orchestration | Repository write authority | Keep; return run metadata/locator, not a caller-owned authority token |
| `application/evidence_phase6.py::project_verified_edges` | Legacy conversion | Currently claims downstream authority from semantic receipt alone | Remove from trusted real-Phase-6 path; retain temporarily only as labeled diagnostic export, or remove after migration |
| `application/vertical_slice.py` real Phase 6 branch | Sole production call to adapter; writes `evidence_edges.jsonl`, feeds fixture adjudicator and minimal report | Graph-authorized relations plus rich committed facts and coverage | Switch to repository-derived assessment view; preserve visible fixture boundary and lifecycle test |
| `application/ports.py::EvidenceMapper/EvidenceVerifier/AdjudicationEngine` | Earlier-phase generic `EvidenceEdge` ports | Fixture/legacy contract, not Phase 6 authority | Keep for earlier phase fixtures; do not make it the future Phase 7 input |
| `reporting/minimal.py` | Existing fixture-era report compiler consumes `EvidenceEdge` | Frozen finding plus authorized evidence for real Phase 6 slice | Real Phase 6 branch should use a rich-view-aware fixture report path; Phase 1 fixture path may stay |
| `tests/fixtures/phase1.py`, Phase 1/4 integration | Deterministic earlier-phase fixtures | No Phase 6 authority | Retain their `EvidenceEdge` contract and tests |
| Phase 5/6 integration and R11/R13/R14 tests | Exercise bridge, receipts, graph and lifecycle | Test exact authority boundaries | Replace trusted-adapter assertions with rich-view and fail-closed regressions; retain historical negative reproductions |
| README, traceability, plans, ADR-036 | Describe current bridge/contract | Documentation accuracy | Amend when implementation changes, preserving historical records |
| `phase6/*.jsonl`, `coverage.json`, `evidence_edges.jsonl`, trace | Audit/export artifacts | No independent authority | Preserve or version exports; mark canonical authority as repository read model and commit/snapshot references |

No real Phase 7 module currently consumes the adapter. The current `AdjudicationEngine` and `FrozenAdjudication` are fixture-era interfaces. `resolve_phase6_commit` is also called by the Phase 6 pipeline and graph reader internals; those calls still have legitimate semantic-commit uses, but a semantic receipt alone must not be interpreted as graph authority.

## 7. Semantic authority and graph authority

**Semantic commit authority** means the repository has revalidated and committed an exact `VerifiedEvidenceChain` plus `ClassifiedComparison`, source/version content ancestry, observations and manifest. Such a record can be shown for audit, including an unresolved or negative verifier outcome. It does not automatically create an authorized graph relation.

**Graph projection authority** additionally means the repository finds the expected derived graph relation(s) and evidence-proposition node, their exact schema-v6 membership to that manifest and classification, and current chain/graph field validation. Graph-facing consumers must fail closed or receive an explicit unavailable status when any required membership or projection is absent or corrupt. A missing `DIRECT_PRECEDENT` membership cannot become an absence finding; it is an authority/integrity failure.

The read model must use separate, typed fields for `committed_comparisons`, `authorized_graph_relations`, and `candidate_failures`/coverage. It must never silently convert a semantic-only comparison to a graph relation. A receipt supplied by a caller selects a possible commit; the repository resolves it and independently checks membership. All reads for one assessment snapshot happen under one consistent database snapshot/transaction to avoid a time-of-check/time-of-use split.

## 8. Candidate architectures

| Approach | Strength | Limitation and authority risk | Decision |
| --- | --- | --- | --- |
| A. Repository graph only | One graph read path; useful topology and lineage traversal | Raw `GraphEdge.attributes` omit much of the chain, scoped support and failed/coverage context; some valid committed classifications have no precedent graph edge | Insufficient as Phase 7's only input |
| B. Repository-backed rich Phase 6 read model | One authority, typed full semantic chain plus graph membership and assessment ledger; direct provenance to exact passage | Requires repository query/ledger work, versioned view contract and careful graph-vs-semantic status distinction | **Recommended** |
| C. Keep legacy adapter as nonauthoritative export | Maintains existing fixture/debug format temporarily | Easy to misuse; omits important facts; duplicated trusted conversion if real Phase 6 still calls it | Transitional export only, never a Phase 7 or real-Phase-6 authority input |

## 9. Trade-off analysis

Approach A preserves topology but makes Phase 7 rebuild semantic context from low-level rows and still needs a separate place for failed candidates and bounded coverage. Approach C preserves the familiar DTO for existing fixtures but leaves future agents with less evidence and a tempting bypass. Approach B requires more explicit repository query and ledger contracts, but it minimizes lossy translation, retains provenance, gives Phase 7 one ergonomic typed input, and permits later semantic additions without creating another authority store. Its main risk is accidentally treating a committed status as a graph relation; typed authority states and membership validation address that risk.

## 10. Recommended architecture

The recommendation is B, with authoritative graph queries available alongside the rich view for specialist consumers. This is one repository authority with multiple derived reads, not multiple persisted truth sources.

## 11. Canonical downstream interface

Conceptual repository port (names are design-level, not an implementation prescription):

```text
load_phase6_assessment(assessment_id, snapshot_id?) -> Phase6AssessmentView

Phase6AssessmentView:
  assessment_id; cutoff; schema/view version; snapshot/commit IDs
  authorized_graph_relations: typed relation + endpoints + graph IDs + commit ID
  committed_comparisons: exact classified chain + authority/status marker
  cited_passages: resolved text, locator, attestation, source/version, limitations
  targets: MCU/combination profile and member topology
  candidate_outcomes: assessed, unassessable, excluded, rejected, reason
  coverage: bounded sources/versions/evidence families, limits, gaps
  lineage; multi_source_context; patent_screenings
  audit references: observations, trace IDs, artifact IDs, method versions
```

The repository constructs the immutable view from its own persisted rows. The view is not separately persisted as a new authority. It carries stable IDs and may be serialized as a labeled derived export, but callers cannot deserialize an export and gain authority. Reads must validate manifest/chain, content ancestry, classification, graph field derivation, both relation and proposition membership, source/version ownership, and the assessment/cutoff join. For each committed comparison, the view explicitly reports whether a graph projection is authorized, absent by defined nonrelational state, or invalid. An invalid projection is an integrity failure, not an ordinary no-match.

The current SQL tables suffice for the committed comparison portion and for graph-backed relations. To build the complete assessment view, add repository-owned, versioned **assessment ledger records** for the eligible source/version candidate universe, target profiles, bounded selection/exclusions, failed or unassessable candidates, context expansion attempts and limitations, and the input identities/method version behind multi-source and patent outputs. These records are append-only or superseded by explicit versions; they are validated against committed comparison IDs and source/version/target identities, including immutable references for unassessed candidates. Multi-source and patent summaries may be recomputed from committed inputs and lineage or stored as validated derived snapshots; either way, their exact dependencies and cutoff are retained. No file, trace, or caller-supplied list can supply missing authoritative coverage.

For classes with no present graph relation (`SUPERFICIAL_SIMILARITY`, `UNRESOLVED`, and any unprojected unassessable state), the view preserves the committed classification or failure as a typed *status*, with its basis and uncertainty, without claiming a graph precedent relation. A future graph schema may add explicit projections for these classes; it must do so through the same manifest/membership path. Existing `NO_MATCH` remains local only. For a class that requires a graph projection, missing or corrupt relation/proposition membership makes the entire trusted assessment read fail closed; its committed classification remains accessible only through a separately labeled audit query. Such a source cannot be counted as assessed for a no-direct conclusion merely because a semantic row exists.

## 12. Phase 7 consumption contract

Future prosecutor, defender, and neutral adjudicator agents receive the immutable repository-derived view plus the idea/MCU input and explicit role-specific instructions. They can inspect every classified comparison, commitment judgment, exact cited passage, supported subset/remainder, context limit, chronology, source/version and lineage, combination profile, coverage gap, and patent distinction. They may use committed nonrelational statuses to formulate uncertainty or follow-up research; they may cite a graph relation as an established Phase 6 relation only when `authorized_graph_relations` contains it. No agent may promote a missing projection, file export, receipt, or mapper proposal to verified support.

The eventual adjudicator must bind its structured challenges and decisive-edge references to authorized Phase 6 IDs and revalidate at the frozen-finding boundary. The report compiler uses those frozen findings and repository-resolvable citations; it never re-decides precedent. Phase 7 verdict gates, agent prompts, calibration and report behavior are deferred to their own approved phase.

The fixture adjudicator used to keep the current real-Phase-6 vertical slice running should accept the new view or a narrow repository-derived fixture input. Its `fixture` provenance and lack of real Phase 7 authority remain visible. Earlier Phase 1/4 fixture paths may continue using `EvidenceEdge`; they are not an alternate real Phase 6 entry point.

## 13. Capability-preservation guarantees

Retirement is safe **only after** the rich view and ledger expose at least all adapter fields, with the actual adapter's empty/constant fields replaced by real limitations and provenance. A per-field parity test must compare the existing adapter output with the new view for valid direct, partial, component, analogy, contradiction, no-direct, unresolved, combination, and multi-passage cases. Additional tests must show the new view retains the information the adapter discarded. Failed mapping, all five verifier states, scoped partial support, multi-source lineage, patent dates/locators, and bounded coverage must remain visible even though not all produce graph relation edges.

## 14. Future extensibility

Use versioned typed contracts and extension records rather than a fixed collection of `GraphEdge.attributes` strings. New relation types and semantic states can add projections through the same commit/membership mechanism; new provenance, calibrated confidence, robustness, expert annotation, domain and patent metadata can join by stable assessment/comparison/commit IDs. New read views or exports derive from the repository and declare their schema version. A future confidence model remains separate from novelty and cannot bypass deterministic eligibility gates.

## 15. R10–R14 invariant preservation

The new read must recheck R10 immutable stored source/version authority and passage ancestry; R11/R12 publication only after committed authority for every semantic polarity; R13 receipt-as-reference and exact manifest resolution; and R14 v6 membership, derived graph fields, orphan/migration quarantine, and ordinary Phase 5 graph independence. Post-commit trace publication should carry the new read's commit/snapshot identity. Missing view publication is an explicit run failure or recoverable delivery state, not an invented semantic result.

## 16. R15 disposition

R15's reproduction remains valid at `7509177`. The proposed disposition is to retire the legacy compatibility projection from the trusted Phase 6 downstream path. A repository-derived rich view becomes canonical. The old adapter's inconsistent authority answer then cannot reach real Phase 6 or future Phase 7. R15 is **not closed** by this document; implementation and independent re-review must prove the replacement and verify that no production caller still trusts the old adapter.

ADR-036 currently says the legacy projection resolves semantic artifacts directly without graph rows. That rule conflicts with the chosen downstream graph-authority contract. An implementation must amend ADR-036 or add a superseding ADR: semantic-only commits remain useful for audit, while graph-backed downstream relations require membership. This is an explicit contract change, not a silent reinterpretation of historical artifacts.

## 17. Migration and deprecation strategy

1. Introduce the versioned repository read-model contract and assessment ledger, retaining existing SQL semantic rows and audit files. Populate ledger records only from validated pipeline outcomes; preserve failed and excluded work.
2. For current assessments, produce graph projections, proposition nodes and v6 memberships atomically with the semantic commit. Keep semantic-only commits for internal/audit use, marked so downstream relation queries cannot treat them as graph backed.
3. Make the real Phase 6 vertical-slice fixture consumer use the rich repository view. Update its identity checks, frozen fixture finding and minimal report path to resolve authorized citations from that view. Keep earlier-phase fixture ports unchanged.
4. Stop calling `project_verified_edges()` in production real Phase 6 and future-stage interfaces. Keep the existing `evidence_edges.jsonl` contract for earlier-phase fixtures and historical runs. If a real-Phase-6 legacy-format export remains useful, derive it only from the authorized rich view, label it nonauthoritative and retain a link to its authoritative snapshot. Retain `project_verified_edges()` temporarily only as an isolated diagnostic helper, or remove it after dependent tests and documentation have migrated. Do not delete historical review tests; replace their positive bridge assertions with new authority/parity tests while keeping reproductions of rejected states.
5. Treat v4/v5 migrated semantic rows and schema-v6 rows lacking membership as audit-only until exact validated replay establishes graph authority. Do not backfill membership from IDs alone. Preserve raw records and explicit migration status.
6. Update README, traceability, ADR, export labels and run-artifact schema. Keep existing Phase 1 fixture outputs functional. Do not start actual Phase 7 adjudication as part of this change.

## 18. Test strategy

Meaningful deterministic tests should exercise repository reads through public interfaces and use no live providers. Required cases:

- R15: valid direct relation and proposition are present in rich view; deleting either membership, graph row, or corrupting graph fields removes authority and causes the trusted read to fail closed. A still-resolvable semantic receipt cannot restore the relation. Include v5 migration and semantic-only commit cases.
- R10–R14 replay: foreign stored digest, copied chain, forged/stale receipt, trace polarity, generic graph injection, orphan nodes/edges and foreign manifest association never enter a trusted view or semantic publication.
- Full relation/status matrix: direct, strong partial, component, analogy, superficial, contradiction, no-direct, unresolved and unassessable; five verifier states; scoped subset/remainder; combination target; multiple passages; distinct and duplicate lineage roots; patent single versus multi-reference context.
- Coverage: selected, excluded, failed and authority-rejected candidates remain explicit; absent or invalid graph authority cannot be converted to no-direct or global absence. The reader uses a consistent assessment snapshot.
- Capability parity: every populated legacy field has an equal or richer value in the view, while version, passage attestation, context completeness, mapping/claim/verification IDs, classification basis and commit/graph membership are newly accessible.
- Real Phase 6 fixture slice reaches `REPORTED`/`COMPLETED` using the rich view and still labels Phase 7 as a fixture. Phase 1/4 fixture paths, ordinary Phase 5 graph relations and audit artifacts retain their contracts. A repository-wide search finds no trusted real-Phase-6 or future-stage call to `project_verified_edges()`.

## 19. Acceptance criteria

The implemented change passes only when (1) the real Phase 6 downstream path obtains at least all previous useful evidence and the richer fields in this design; (2) a caller-created object, semantic-only commit, orphan graph row, or missing membership cannot establish a Phase 6 graph relation; (3) new states and annotations can join by stable repository identities without creating a second authority; and (4) the trusted production surface has no call to the legacy adapter. A fresh independent Stage-1 review must verify the implemented boundary, followed by the separate full Gate-30 review. A green test suite alone does not close R15.

## 20. Explicit non-goals

This design does not implement R15, modify production code or tests, create an implementation commit, start Phase 7, define Phase 7 verdicts, assign novelty scores, calibrate model confidence, or erase earlier review findings. It does not treat run artifacts, traces, receipts, graph rows, or caller-created DTOs as standalone authority. It does not narrow the nine precedent states or the evidence obligations in the master spec.
