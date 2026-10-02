# Phase 6 Downstream Authority Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give real Phase 6 downstream consumers one complete, repository-derived assessment view whose graph relations have current schema-v6 authority, while preserving the full Phase 6 semantic and coverage record.

**Architecture:** Keep `ClassifiedComparison`, its verified chain, the commit manifest, and v6 graph membership as separate validated layers in the existing SQLite repository. Add a small typed assessment ledger for run facts absent from semantic tables, then assemble an immutable `Phase6AssessmentView` in one database read transaction. Migrate only the real Phase 6 slice to that view; earlier fixture `EvidenceEdge` paths remain.

**Tech Stack:** Python 3.12+, `uv`, Pydantic v2, SQLAlchemy 2.x/SQLite, pytest, Ruff, Pyright.

**Spec:** `docs/superpowers/specs/2026-10-01-phase-6-downstream-authority-consolidation-design.md`; governing requirements in `docs/specs/master-design-spec.md` §§23–30, 44–45 and Phase 6/7 gates; approved Phase 6 plan `docs/superpowers/plans/2026-09-28-phase-6-evidence-mapping-support-verification-precedent-classification-implementation-plan.md`.

## Global Constraints

- Baseline is `phase-6-evidence-verification` at `750917734fbed622f785f96e3d1d443dea166fe7`. Preserve the existing R15 review modification and historical FAIL records.
- Phase 6 only. No prosecutor, defender, neutral adjudicator, Phase 7 prompts, novelty verdict, novelty score, confidence model, or global absence claim.
- Reduce trusted pathways, not model expressiveness: preserve all nine `PrecedentState` classes, five `SupportVerificationState` states, exact passages, scoped support, chronology, source/version identity, coverage, lineage and patent distinctions.
- `Phase6AssessmentView` is a derived read model, never a separately persisted authority. A receipt, trace, artifact file, or serialized view is not proof of authority.
- A semantic commit may exist without a graph projection. A graph-backed class with missing/corrupt required projection is an integrity failure; it cannot become `NO_MATCH` or `NO_DIRECT_PRECEDENT_IDENTIFIED`.
- Preserve R10 stored content authority, R11/R12 post-commit publication for every verifier polarity, R13 receipt-as-reference, and R14 graph membership/generic-write protection.
- Use immutable/versioned Pydantic contracts with `extra="forbid"`, canonical IDs, timezone-aware UTC observation times, append-only ledger snapshots, and no live network in deterministic tests.
- Keep Phase 1/4 `EvidenceEdge` fixtures and historical `evidence_edges.jsonl` files working. The real Phase 6 trusted path must stop calling `project_verified_edges()`.
- Do not rewrite prior review decisions. Implementation evidence is not independent Stage-1 acceptance; R15 and Gate 30 remain open through implementation.

## Review Focus

1. Revoked graph-edge or proposition membership after a valid semantic commit must make the trusted view fail closed (`test_r15_*`, Task 7).
2. A bounded-out source/version or failed candidate must remain visible in the snapshot, including runs with no committed comparison (`test_ledger_*`, Tasks 3–4).
3. A semantic-only commit must remain a typed status and never enter `authorized_graph_relations` (`test_semantic_only_*`, Tasks 6–7).
4. A concurrent membership change during assessment loading must yield one coherent snapshot or an explicit failure (`test_snapshot_*`, Task 6).
5. No real Phase 6 production caller may reach the legacy adapter after migration (`test_real_phase6_*` and architecture guard, Tasks 10–11).

---

## File map and locked boundaries

| File | Responsibility |
| --- | --- |
| `src/novelty_harness/evidence/graph/assessment_view.py` (new) | Frozen, versioned read contracts: semantic comparison, authorized relation, citation, target, candidate, derived context, coverage and audit references. No SQL or decisions. |
| `src/novelty_harness/evidence/graph/assessment_ledger.py` (new) | Typed snapshot/target/candidate/derived ledger contracts and canonical ledger IDs; factual recording only. Define these alongside the view types in Task 1. |
| `src/novelty_harness/evidence/graph/sqlalchemy_models.py`, `migrations.py` | Schema v7 ledger tables and safe v4/v5/v6 migration; no authority backfill. |
| `src/novelty_harness/evidence/graph/repository.py` | `record_phase6_assessment(...)` and `load_phase6_assessment(...)` protocol; existing `resolve_phase6_commit` remains semantic-only. |
| `src/novelty_harness/evidence/graph/sqlalchemy_repository.py` | Atomic ledger write, one-transaction assessment load, semantic/content and current graph membership validation. |
| `src/novelty_harness/evidence/phase6_pipeline.py` | Record target universe, candidate outcomes, expansions, coverage, derived-input dependencies; keep result and audit artifacts as nonauthority outputs. |
| `src/novelty_harness/application/evidence_phase6.py` | Return snapshot locator from real Phase 6; isolate or remove legacy adapter only after parity and consumer migration. |
| `src/novelty_harness/application/phase6_fixture.py` (new) | Fixture-only protocol taking `Phase6AssessmentView` and yielding `FrozenAdjudication`; no verdict logic in production. |
| `src/novelty_harness/application/vertical_slice.py`, `reporting/minimal.py` | Real Phase 6 branch consumes rich view and renders from authorized citations; earlier fixture branch retains `EvidenceEdge`. |
| `tests/adversarial/test_phase6_r15_assessment_authority.py`, `tests/unit/evidence/graph/test_assessment_ledger.py`, `test_assessment_view.py`, `tests/integration/test_phase6_assessment_view.py`, `tests/integration/test_phase5_slice_with_phase6_evidence.py` | R15, ledger, parity, and full-slice proof. Keep existing R10–R14 negative tests. |

**Concrete contract choice:** Use `snapshot_id: str` as an explicit locator. `load_phase6_assessment(assessment_id: AssessmentId, *, snapshot_id: str) -> Phase6AssessmentView` does not select a possibly ambiguous “latest” run. A successfully returned `Phase6EvidenceResult.snapshot_id: str` locates the completed ledger snapshot but never grants authority. `Phase6AssessmentView.view_version` is `1`; graph schema becomes `7` solely for ledger storage. Existing v6 membership remains the graph-authority mechanism.

**Identity choice:** Compute `snapshot_id = "p6snap_" + canonical_hash(...)` over assessment ID, cutoff, method/limit versions, canonical target/candidate/derived facts and committed IDs, excluding observation clocks and ledger record IDs. Then compute each ledger record ID from snapshot ID, kind, its typed identity tuple and canonical payload. Exact replay is idempotent; changed facts create a new snapshot rather than mutating an earlier one. A snapshot records `lineage_cluster_ids` and post-commit trace event IDs; the latter are audit references, not authority.

**Ledger choice:** Four new tables: `phase6_assessment_snapshots` (assessment, cutoff, method/limit metadata, completion and canonical referenced record IDs), `phase6_target_ledger` (one typed `MCUComparisonProfile` per snapshot/target), `phase6_candidate_ledger` (one typed target/source/version decision, immutable source/version descriptors, bound/exclusion/failure/commit/context facts), and `phase6_derived_ledger` (typed multi-source or patent result with exact committed input IDs, lineage root IDs, cutoff and method). Rows have snapshot/assessment/target/source/version/index columns for joins and unique immutable record IDs; their `document_json` stores only the matching versioned Pydantic contract, not arbitrary events. An assessment with zero comparisons still gets a complete snapshot. The snapshot is appended once at the end; no historical candidate facts are fabricated for pre-v7 databases. A pre-v7 assessment without an explicit replayed ledger returns `HISTORICAL_LEDGER_UNAVAILABLE` from the trusted loader. A failed/incomplete snapshot remains unavailable to the trusted loader; retained audit records remain readable by separately labeled audit tooling.

**Graph-status choice:** `CommittedComparisonView` wraps the stored `ClassifiedComparison` and commit ID with `projection_status: Literal["GRAPH_AUTHORIZED", "SEMANTIC_ONLY", "NONRELATIONAL_STATUS"]` plus exact proposition/edge IDs. `AuthorizedGraphRelation` carries repository-validated `GraphEdge`, `GraphNode`, commit, verified-edge and classification IDs. For classes that produce relation edges under `verified_edge_graph_fragment`, a missing required node/edge/membership raises `Phase6AssessmentAuthorityError`. For a deliberately semantic-only commit or a class without a graph relation, the status is visible but its relation list is empty. A corrupt *present* projection always errors. The view also exposes full `ClassifiedComparison` chains, cited `PassageRecord`s and typed ledger records; it does not flatten chronology to a Boolean.

## Tasks

### Task 1: Define the canonical rich read-model contract

**Files:** Create `src/novelty_harness/evidence/graph/assessment_view.py` and `assessment_ledger.py`; test `tests/unit/evidence/graph/test_assessment_view.py`, `test_assessment_ledger.py`.

**Interfaces:** Define frozen `CitedPassageView(passage: PassageRecord, commitment_ids: tuple[str, ...])`; `CommittedComparisonView(comparison: ClassifiedComparison, commit_id: str, projection_status: Literal["GRAPH_AUTHORIZED", "SEMANTIC_ONLY", "NONRELATIONAL_STATUS"], proposition_node_id: str | None, graph_edge_ids: tuple[str, ...], cited_passages: tuple[CitedPassageView, ...])`; `AuthorizedGraphRelation(edge: GraphEdge, proposition_node: GraphNode, commit_id: str, verified_edge_id: EvidenceEdgeId, classification_id: ClassificationId)`; `Phase6AssessmentView(assessment_id: AssessmentId, snapshot_id: str, as_of: date, view_version: Literal[1], commit_ids: tuple[str, ...], committed_comparisons: tuple[CommittedComparisonView, ...], authorized_graph_relations: tuple[AuthorizedGraphRelation, ...], targets: tuple[MCUComparisonProfile, ...], candidate_outcomes: tuple[Phase6CandidateLedgerRecord, ...], coverage: Phase6CoverageLedger, multi_source_context: tuple[Phase6DerivedLedgerRecord, ...], patent_screenings: tuple[Phase6DerivedLedgerRecord, ...], lineage: tuple[EvidenceLineageCluster, ...], audit_refs: tuple[str, ...])`. Define the `Phase6*Ledger` contract types specified in Task 2 in `assessment_ledger.py` in this task, with `projection_intent: Literal["GRAPH_BACKED", "SEMANTIC_ONLY"]` on assessed candidates and `lineage_cluster_ids` on snapshots; Task 2 persists them. `Phase6AssessmentAuthorityError(ValueError)` is the loader's fail-closed signal. No public constructor implies repository authority.

- [ ] **Step 1: Write failing tests** for model immutability/version, distinct semantic/graph collections, exact `PassageRecord` attestation and scoped `ClassifiedComparison` retention, and rejection of a graph relation whose IDs do not match its comparison.
- [ ] **Step 2: Run** `uv run pytest tests/unit/evidence/graph/test_assessment_view.py -q`; confirm the new-contract tests fail for missing types/validation.
- [ ] **Step 3: Implement** the types above in `assessment_view.py` and the referenced ledger contracts in `assessment_ledger.py`; use Pydantic validators for local shape/identity only. Do not put repository or classification logic in these models.
- [ ] **Step 4: Run** the focused file and `uv run pyright`; require both pass.
- [ ] **Step 5: Commit** the contract and tests (`feat(phase6): define repository assessment view contract`).

### Task 2: Persist the typed append-only assessment ledger

**Files:** Modify `sqlalchemy_models.py`, `migrations.py`, `repository.py`, `sqlalchemy_repository.py`; test `tests/unit/evidence/graph/test_assessment_ledger.py` and existing `test_sqlalchemy_repository.py`.

**Interfaces:** Task 1 defines `Phase6AssessmentSnapshotRecord(snapshot_id, assessment_id, as_of, method_version, max_sources_per_mcu, max_versions_per_source, max_expansions, window_chars, target_record_ids, candidate_record_ids, derived_record_ids, lineage_cluster_ids, commit_ids, coverage: Phase6CoverageLedger, audit_refs, completed_at)`; `Phase6TargetLedgerRecord(snapshot_id, assessment_id, profile)`; `Phase6CandidateLedgerRecord(snapshot_id, assessment_id, target_id, source_id, source_version_id, source_content_hash, version_content_hash, evidence_families, decision, reason, failure_stage, projection_intent, commit_id, verified_edge_id, classification_id, expansions: tuple[ContextExpansion, ...], limitations)`; `Phase6DerivedLedgerRecord(snapshot_id, assessment_id, target_id, kind: Literal["MULTI_SOURCE", "PATENT"], input_commit_ids, input_edge_ids, input_classification_ids, lineage_root_ids, as_of, method_version, result: MultiSourceAssessment | PatentScreeningResult)`. `Phase6CoverageLedger` retains bounded selected/excluded source/version IDs and reasons plus limitations. This task adds `record_phase6_assessment(snapshot: Phase6AssessmentSnapshotRecord, *, targets: Sequence[Phase6TargetLedgerRecord], candidates: Sequence[Phase6CandidateLedgerRecord], derived: Sequence[Phase6DerivedLedgerRecord]) -> str` to the repository port; it atomically inserts or verifies the exact same immutable snapshot and returns its ID.

- [ ] **Step 1: Write failing tests** for duplicate same-ID conflicting ledger content, invalid assessment/target/source/version/commit joins, zero-comparison snapshot, exact replay versus changed-fact new snapshot, and v4/v5/v6 to v7 migration that creates no fake historical ledger; the trusted loader must report historical coverage unavailable until validated replay.
- [ ] **Step 2: Run** `uv run pytest tests/unit/evidence/graph/test_assessment_ledger.py -q`; confirm expected missing-schema/contract failures.
- [ ] **Step 3: Implement** the four tables and `record_phase6_assessment` in one SQL transaction. Store typed canonical documents plus relational identity columns and foreign keys to snapshot, and to commit where present. Validate input IDs against existing manifest/chain for assessed candidates; rejected/failed candidates may have no commit. `ensure_schema` adds empty v7 tables and advances metadata without backfill; retain v1–v3 unsafe-graph checks.
- [ ] **Step 4: Run** the focused ledger and SQL repository tests plus `uv run pyright`; require pass.
- [ ] **Step 5: Commit** contracts/schema/port/tests (`feat(phase6): persist typed assessment ledger`).

### Task 3: Record the target and bounded candidate universe

**Files:** Modify `src/novelty_harness/evidence/phase6_pipeline.py`; tests `tests/integration/test_phase6_evidence_pipeline.py`, `tests/unit/evidence/graph/test_assessment_ledger.py`.

**Interfaces:** Populate Task 2 target/candidate records from `MCUComparisonProfile`, `select_candidate_sources` and `select_versions`. Preserve the original eligibility universe: source/version ID, immutable digest/access, evidence family and routing priority; record selected, omitted-by-source-bound, omitted-by-version-bound, unversioned and missing-version-record cases with explicit reasons. Do not infer “not searched” from absence in this local ledger.

- [ ] **Step 1: Write failing tests** `test_ledger_records_combination_profile_and_topology`, `test_ledger_keeps_fourth_source_and_mixed_unversioned_passages`, and `test_ledger_records_no_selected_source_as_bounded_local_coverage`; assert exact target/source/version IDs and reason codes.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_phase6_evidence_pipeline.py -q -k ledger`; confirm failure because no repository ledger exists for these run facts.
- [ ] **Step 3: Implement** collection of typed records during target/selection loops, then final snapshot write after semantic commits. Preserve existing `Phase6EvidenceResult` and JSON artifacts as audit outputs. Add `snapshot_id` to the result only after successful ledger write.
- [ ] **Step 4: Run** focused pipeline and ledger suites, plus `tests/adversarial/test_phase6_r11_authoritative_publication.py`; require pass.
- [ ] **Step 5: Commit** target/coverage recording and tests (`feat(phase6): record bounded target and candidate coverage`).

### Task 4: Record failure, context and limitation outcomes without laundering them

**Files:** Modify `phase6_pipeline.py` and `assessment_ledger.py`; tests `tests/integration/test_phase6_evidence_pipeline.py`, `tests/adversarial/test_phase6_r11_authoritative_publication.py`.

**Interfaces:** Use existing `CandidateAssessmentResult.status`, `failure`, `classification`, `ContextExpansion`, and `coverage_limitations`. Candidate decision enum must distinguish `ASSESSED`, `EXCLUDED_SOURCE_BOUND`, `EXCLUDED_VERSION_BOUND`, `FAILED_MAPPING`, `FAILED_PASSAGE_SELECTION`, `UNASSESSABLE`, `AUTHORITY_REJECTED`; use `FAILED_VERIFICATION` only if the current pipeline actually catches and represents that failure, otherwise record `UNASSESSABLE` with `failure_stage="VERIFICATION"` when such handling is deliberately added. Capture returned post-commit `TraceEvent.event_id` values in snapshot `audit_refs`; immediate operational diagnostics are separately labeled. Do not fabricate a verifier judgment or commit ID for operational failure.

- [ ] **Step 1: Write failing tests** for all-failed mapping, one failed plus one committed, context expansion available/blocked, and stored-digest rejection. Assert failure and coverage survive in ledger/view inputs, rejected candidate has no commit, and no precommit success/negative-verifier trace assertion leaks.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_phase6_evidence_pipeline.py tests/adversarial/test_phase6_r11_authoritative_publication.py -q -k 'failure or rejected or ledger'`; confirm new assertions fail.
- [ ] **Step 3: Implement** candidate outcome and expansion recording at the existing `_assess_candidate`/`_commit_candidate` transitions; write only factual failure diagnostics until authority exists. A failed ledger-finalization aborts the run before `Phase6EvidenceResult` is returned as complete.
- [ ] **Step 4: Run** focused pipeline, R10, R11/R12 suites; require pass.
- [ ] **Step 5: Commit** failure/context recording and tests (`feat(phase6): retain failed candidates and context attempts`).

### Task 5: Bind multi-source and patent context to committed inputs

**Files:** Modify `phase6_pipeline.py`, `assessment_ledger.py`; tests `tests/integration/test_phase6_evidence_pipeline.py`, `tests/unit/evidence/precedent/test_patent.py` and existing precedent tests.

**Interfaces:** Store validated derived snapshots in Task 2 `Phase6DerivedLedgerRecord`, not a second decision engine. For each `MultiSourceAssessment` and `PatentScreeningResult`, record exact commit/edge/classification IDs, cutoff, method version and lineage-root IDs from the same Phase 5 cluster snapshot; retain patent locators/dates inside `PatentScreeningResult`. A reader validates dependencies against committed comparisons and lineage before exposing the derived snapshot. Move summary/patent success publication after ledger finalization or identify it as a committed-comparison result linked to the completed snapshot; never publish a snapshot finding whose ledger write failed.

- [ ] **Step 1: Write failing tests** for two distinct eligible partial patent roots, duplicate-family roots, one future plus one eligible patent, a direct single reference, and a rejected candidate excluded from both derived inputs. Assert exact dependency IDs/roots and no one-reference anticipation from two partials.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_phase6_evidence_pipeline.py tests/unit/evidence/precedent/test_patent.py -q -k 'ledger or lineage or patent'`; confirm missing dependency records.
- [ ] **Step 3: Implement** derived-record construction from `committed_comparisons` and `receipt_by_edge`; keep `summarize_multi_source` and `screen_patent_references` as the sole existing calculators. Do not recalculate from uncommitted `classifications` or trace files.
- [ ] **Step 4: Run** focused precedent/pipeline and R11/R12 publication suites; require pass.
- [ ] **Step 5: Commit** dependency records and tests (`feat(phase6): bind derived context to committed inputs`).

### Task 6: Load one consistent semantic assessment snapshot

**Files:** Modify `repository.py`, `sqlalchemy_repository.py`; test `tests/unit/evidence/graph/test_assessment_view.py`, `tests/integration/test_phase6_assessment_view.py`.

**Interfaces:** `EvidenceGraphRepository.load_phase6_assessment(assessment_id: AssessmentId, *, snapshot_id: str) -> Phase6AssessmentView`. Load the exact completed snapshot, targets, candidates, derived inputs, lineage and all referenced manifests/chains/classifications. Reuse `_resolve_phase6_commit_in_session` and existing content-authority checks. Assemble inside one explicit SQLite read transaction on one connection/session; no nested public `get_edge()`, `edges()`, `lineage_clusters()` or `resolve_phase6_commit()` calls that open another session. Expose committed statuses and exact citations even where a comparison has no graph relation; do not yet claim graph authorization.

- [ ] **Step 1: Write failing tests** for a zero-comparison complete snapshot, all five verifier states, scoped subset/remainder, exact passage text/locator/attestation/limitation and source version, cutoff/date basis, combination profile, foreign assessment/snapshot, and a test hook that changes membership between semantic and graph reads on another connection. The last test accepts one coherent old snapshot or an explicit authority failure, never a mixed assembled view.
- [ ] **Step 2: Run** `uv run pytest tests/unit/evidence/graph/test_assessment_view.py tests/integration/test_phase6_assessment_view.py -q`; confirm loader tests fail.
- [ ] **Step 3: Implement** the loader's semantic/ledger half with a single `Session` bound to a single explicit SQLite transaction. Validate referenced ledger IDs and exact derived input IDs. Keep its graph-dependent result unavailable/fail closed until Task 7 is complete; do not publish this intermediate loader as trusted production input.
- [ ] **Step 4: Run** focused loader tests and R10/R13 repository suites; require pass.
- [ ] **Step 5: Commit** semantic snapshot loading and tests (`feat(phase6): load one repository assessment snapshot`).

### Task 7: Enforce R15 graph authority in the assessment loader

**Files:** Modify `sqlalchemy_repository.py`; create `tests/adversarial/test_phase6_r15_assessment_authority.py`; update `tests/integration/test_phase6_assessment_view.py`.

**Interfaces:** In the same Task 6 transaction, derive expected proposition/graph relation IDs using `verified_edge_graph_fragment` and validate actual rows via existing `_authoritative_graph_node`/`_authoritative_graph_edge` with exact manifest membership and derived fields. Graph-backed relation classes are those for which that helper produces relation edges; do not invent edges for `SUPERFICIAL_SIMILARITY`, `UNRESOLVED`, or an unchained `UNASSESSABLE`. Semantic-only commits remain visible as `SEMANTIC_ONLY`, with no authorized relation, only when the candidate ledger explicitly records `projection_intent="SEMANTIC_ONLY"` and the repository verifies no claimed graph projection. The normal pipeline records `GRAPH_BACKED`; a snapshot claiming graph-backed completion with missing projection raises `Phase6AssessmentAuthorityError`.

- [ ] **Step 1: Write failing R15 tests**: valid direct relation/proposition appears; separately delete edge membership, node membership, graph edge row, proposition row; corrupt graph citation or associate a foreign manifest; migrate v5 manifest without v6 membership. In every invalid case, `resolve_phase6_commit(receipt)` may still return semantics but `load_phase6_assessment` raises and exposes no direct relation. Test positive exact replay, semantic-only status, and all existing graph relation kinds without class inflation.
- [ ] **Step 2: Run** `uv run pytest tests/adversarial/test_phase6_r15_assessment_authority.py -q`; confirm the baseline R15 case fails before implementation.
- [ ] **Step 3: Implement** current graph authority validation and typed status assignment inside the loader. Missing or corrupt required graph state is an integrity error, never an empty relation/no-direct result. Retain existing graph reader behavior for Phase 5 edges.
- [ ] **Step 4: Run** R15 plus R10–R14/provenance suites and graph repository tests; require pass.
- [ ] **Step 5: Commit** R15 loader gate and tests (`fix(phase6): require current graph membership in trusted assessment reads`).

### Task 8: Prove capability parity and the full semantic matrix

**Files:** Create `tests/integration/test_phase6_assessment_parity.py`; extend `tests/integration/test_phase6_assessment_view.py`.

**Interfaces:** The old adapter may be called only in this diagnostic test while it still exists. Compare each populated legacy field with the repository view for direct, strong partial, component, analogy, contradiction, no-direct, unresolved, combination and multi-passage cases. Treat the adapter's fixed provenance, empty limitations and tri-state date as lossy; assert the view has actual artifact provenance, access/context limits and full `ChronologyAssessment`. Test `SUPERFICIAL_SIMILARITY`, `UNASSESSABLE` and all five verifier states as typed statuses, and that an authorized graph relation exists only for graph-backed classes.

- [ ] **Step 1: Write failing parameterized parity/matrix tests** for the cases above; assert exact source/MCU/verified-edge/relation/citation/mapping/quality equivalence and richer version, attestation, claim, scoped coverage, context completeness, classification basis, commit and graph IDs. Add bounded coverage, failure and patent/lineage dependency assertions absent from legacy.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_phase6_assessment_parity.py -q`; confirm failures for any missing view capability.
- [ ] **Step 3: Make the smallest coherent corrections** to the view/ledger loaders and their contracts; no adapter deletion or Phase 7 logic.
- [ ] **Step 4: Run** parity, assessment view, Phase 6 adversarial and benchmark suites; require pass.
- [ ] **Step 5: Commit** parity suite and corrections (`test(phase6): prove rich-view capability parity`).

### Task 9: Introduce a view-aware fixture and report path

**Files:** Create `src/novelty_harness/application/phase6_fixture.py`; modify `src/novelty_harness/reporting/minimal.py`; tests `tests/integration/test_phase5_slice_with_phase6_evidence.py`, `tests/unit/test_minimal_report_compiler.py`.

**Interfaces:** `Phase6FixtureAdjudicator.adjudicate_phase6(*, assessment_id: AssessmentId, as_of: date, idea: CanonicalIdeaRepresentation, sufficiency: SufficiencyAssessment, mcus: Sequence[MCU], view: Phase6AssessmentView) -> FrozenAdjudication` is an injection port for the existing test fixture, not a production Phase 7 implementation. `compile_minimal_phase6_report(*, idea, sufficiency, mcus, view: Phase6AssessmentView, repository: EvidenceGraphRepository, adjudication: FrozenAdjudication) -> CompiledReport` re-loads the snapshot from the repository, checks it matches the supplied view and frozen decisive IDs against its `authorized_graph_relations`, then renders cited text/version/limits from the repository copy. Thus a deserialized or caller-built view alone cannot grant reporting authority. Existing `compile_minimal_report(..., edges: Sequence[EvidenceEdge])` remains for earlier fixtures.

- [ ] **Step 1: Write failing tests** for a fixture finding citing authorized direct evidence, a missing/foreign decisive ID, a fabricated/deserialized view without repository agreement, scoped partial and limitation display, and unchanged Phase 1 minimal report output. The test fixture must declare `provenance.kind="fixture"` and return `UNASSESSABLE` without implementing a novelty decision.
- [ ] **Step 2: Run** focused report/full-slice tests; confirm missing view-aware path.
- [ ] **Step 3: Implement** the protocol and view-aware deterministic compiler, sharing only rendering helpers with the legacy compiler. Never convert the view to `EvidenceEdge` for this path.
- [ ] **Step 4: Run** report and Phase 1 fixture tests plus `uv run pyright`; require pass.
- [ ] **Step 5: Commit** fixture/report interface and tests (`feat(phase6): render fixture reports from authorized view`).

### Task 10: Migrate the real Phase 6 vertical slice

**Files:** Modify `application/vertical_slice.py`, `application/evidence_phase6.py`, `tests/integration/test_phase5_slice_with_phase6_evidence.py`; optionally `application/models.py` only if the fixture injection belongs with `VerticalSliceComponents`.

**Interfaces:** Add `phase6_fixture_adjudicator: Phase6FixtureAdjudicator | None = None` to `run_vertical_slice`; require it for `phase6 is not None`. After `Phase6EvidenceComponents.execute`, reopen the same repository and call `load_phase6_assessment(record.assessment_id, snapshot_id=phase6_result.snapshot_id)`. Pass that view to the fixture adjudicator and new report compiler; validate frozen decisive references against authorized relation IDs. Write `phase6/assessment_view.json` only as a derived, labeled export containing snapshot/commit IDs; keep `evidence_edges.jsonl` for earlier fixture branches and historical runs, but stop writing it as trusted real Phase 6 output. Keep lifecycle `REPORTED`/`COMPLETED` and `PHASE7_FIXTURE_BOUNDARY`.

- [ ] **Step 1: Write failing full-slice tests** for a combination target and verifier-cited expanded passage, scoped partial and failed candidate in the view, `REPORTED`/`COMPLETED`, fixture provenance, missing membership preventing report completion, and Phase 1/4 fixture output unchanged.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_phase5_slice_with_phase6_evidence.py tests/integration/test_phase1_vertical_slice.py -q`; confirm the new real-Phase-6 assertions fail.
- [ ] **Step 3: Implement** the branch migration and strict fixture-input gate. Remove the production import/call of `project_verified_edges` from `vertical_slice.py`. Keep `Phase6EvidenceResult` only as an execution/audit result and snapshot locator, not as trusted downstream facts.
- [ ] **Step 4: Run** full-slice, Phase 1/4 fixture, R15 and architecture-guard suites; require pass.
- [ ] **Step 5: Commit** real-slice migration and tests (`feat(phase6): consume repository assessment view downstream`).

### Task 11: Retire the trusted legacy adapter surface

**Files:** Modify `application/evidence_phase6.py`, `tests/unit/test_phase6_architecture_guards.py`, R11/R13 positive bridge tests, README/API references; retain historical negative reproductions as diagnostic tests where practical.

**Interfaces:** Choose removal of `project_verified_edges` from the production module after Task 8 parity and Task 10 migration. If diagnostic comparison remains needed, place it in test-only code with an explicit nonauthority name. Do not delete `domain.evidence.EvidenceEdge` or `application.ports.AdjudicationEngine`; earlier fixtures still use them.

- [ ] **Step 1: Write failing architecture guard** that searches production `src/novelty_harness/` for a trusted real-Phase-6/future-stage import or call of `project_verified_edges`, and regressions for caller-created views/receipts and orphan graph state being rejected by the new loader. Move R11/R13 positive assertions to `load_phase6_assessment`; retain their forged/stale-receipt and negative-state cases.
- [ ] **Step 2: Run** the guard, R11/R13 and R15 suites; confirm the old production adapter path still fails the guard.
- [ ] **Step 3: Remove/isolate** the adapter only after no production caller remains; preserve Phase 1/4 `EvidenceEdge` APIs. Any diagnostic export must be derived from a loaded authorized view and labeled nonauthoritative.
- [ ] **Step 4: Run** architecture guard and R10–R15 suites; require pass.
- [ ] **Step 5: Commit** adapter retirement and tests (`refactor(phase6): retire legacy trusted projection`).

### Task 12: Document the authority boundary and verify the exact implementation commit

**Files:** Amend `docs/architecture/decisions/ADR-036-immutable-content-and-passage-attestation.md` or add a superseding ADR; update `docs/traceability/phase-6.yaml`, `docs/phase-6-completion.md`, `README.md`, run-artifact/API documentation and append an implementation-only record to `docs/reviews/phase-6-final-review.md`. Do not edit historical FAIL sections.

**Interfaces:** State verbatim: “The repository-derived `Phase6AssessmentView` is a read model, not a new source of truth.” State: “Real Phase 6 downstream consumers use repository-authoritative state; the legacy adapter is not an authority boundary.” Explain semantic-only audit status, v6 membership, v7 ledger unknown historical coverage, snapshot transaction, fixture limitation, export labels and future Phase 7 input contract. Keep R15 OPEN.

- [ ] **Step 1: Write a failing documentation/traceability check** in `tests/unit/test_phase6_architecture_guards.py` for the new view/ledger requirement mapping and absence of a trusted legacy call. Inspect every design section against the implemented tasks; record any explicit deferred fact as a limitation.
- [ ] **Step 2: Run** the architecture guard; confirm the new documentation assertion fails.
- [ ] **Step 3: Update** ADR/traceability/completion/README and append implementation evidence only; retain all prior review decisions. Document graph authority separately from semantic commit authority and no Phase 7 implementation.
- [ ] **Step 4: Run** the focused R10–R15, provenance, parity and full-slice suites, then `uv sync --dev`, `uv run python scripts/verify.py`, and `git diff --check` after the final change; require Ruff, Ruff format, Pyright and pytest all pass.
- [ ] **Step 5: Commit** documentation and worktree verification evidence (`docs(phase6): record downstream authority consolidation`); record the exact hash in the handoff. Create a clean detached checkout of that hash and repeat `uv sync --dev`, `uv run python scripts/verify.py`, `git diff --check` there. Report these detached-checkout results in the handoff without a subsequent repository edit. Give the exact commit to a reviewer independent of implementation for a fresh Stage-1 provenance/publication/commit/graph/downstream-authority attack; only that review may close R15. A separate full Gate-30 review follows any Stage-1 PASS. Phase 7 remains unstarted.

## Execution and review gate

Task order is strict because each downstream step depends on the repository contract and typed ledger. Every task follows **failing test → observed failure → smallest coherent implementation → focused pass → commit** and must leave the branch runnable. At meaningful milestones after Tasks 2 and 5, run the existing R10–R14/provenance suites; after Tasks 7, 10 and 11 include the newly added R15 suite. The full and fresh-checkout commands in Task 12 are mandatory evidence, not semantic acceptance. Stop implementation if an authority regression appears; investigate it before proceeding.

Implementation completion produces evidence for review; it does **not** self-close R15 or Gate 30. The independent Stage-1 reviewer must attack the exact committed downstream view and all R10–R15 boundaries. If Stage 1 passes, a separate full Gate-30 semantic review decides Phase 6 acceptance. No Phase 7 work begins under this plan.
