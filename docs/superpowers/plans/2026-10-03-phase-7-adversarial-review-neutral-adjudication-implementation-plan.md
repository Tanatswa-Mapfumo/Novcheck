# Phase 7 Adversarial Review and Neutral Adjudication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Produce claim-specific, conservative Phase 7 verdicts from repository-authoritative Phase 6 evidence and one sealed assessment world-state, then freeze the result for Phase 8.

**Architecture:** Extend the existing SQLite evidence repository with schema v8 Phase 7 manifests and immutable artifacts. A repository-loaded Phase 6 view plus validated upstream manifest produces one sealed context and deterministic case packet; independent role proposals, bounded rebuttal, typed escalation, neutral counterbalanced judging and Gates A–D feed a deterministic verdict policy. Only a repository-frozen adjudication is authoritative.

**Tech Stack:** Python 3.12+, Pydantic v2, SQLAlchemy 2/SQLite, uv, pytest, Ruff, Pyright; existing `SemanticRunner`, `LLMProvider`, `canonical_hash`, `TraceSink` and Phase 3–6 services.

**Spec:** `docs/superpowers/specs/2026-10-02-phase-7-adversarial-review-neutral-adjudication-design.md` (approved 3 October amendments); accepted Phase 6 baseline `e4dd4e09699f755dd0fe7b7bc3dd8be4e11f7ee1`.

## Global Constraints

- Read `AGENTS.md`, the master spec, this plan and approved design before implementation. Phase 6 semantics and its Gate 30 record are frozen.
- No Phase 8 narrative compiler, Phase 9 live robustness work, Phase 10 calibration, novelty probability/score, legal patent opinion, polished UX or unrestricted agent browsing.
- Phase6AssessmentView is the sole verified prior-art authority. A caller model, trace, receipt, JSON export or role/judge proposal conveys no authority.
- One run binds one immutable `assessment_context_id`; changed evidence or verdict-relevant research/input state starts a new run. Only a repository-proven true no-op can resume.
- Gate A input needs never enter research dispatch. Gate B/C and evidence-dependent D gaps may use the reviewed Phases 3–6 path.
- HIGH_IMPACT disputes always receive reversed-order judging under an otherwise identical packet/rubric/model/configuration/evidence.
- Heterogeneous judges are independent semantic probes, not voters. For a HIGH_IMPACT dispute, an alternate judge also receives both reversed argument orders; no single third call or majority rule can establish semantics.
- Frozen Pydantic contracts, `extra="forbid"`, canonical hashes, timezone-aware UTC observations, append-only corrections and bounded provider recovery. No live network in deterministic tests.
- Current production cannot issue a strong-positive verdict without repository-validated robustness and domain qualification. Fixture-only qualifications may exercise the pure future policy path, but cannot authorize production freeze.
- Every semantic or authority task is test-first: exact red, minimal implementation, exact green, nearby variant, surrounding regression, then commit. Stop progression on a red gate.

## Review Focus

1. Same Phase 6 snapshot with changed Phase 4 budget/coverage must supersede the old packet (`test_research_only_change_restarts_roles`, Task 8).
2. A schema-valid fabricated source/passage ID in a persuasive role case must be rejected before judging (`test_role_case_rejects_packet_absent_passage`, Task 4).
3. Missing claimed topology or mechanism must create input clarification, never a search request or potential verdict (`test_gate_a_unknown_topology_never_dispatches`, Task 9).
4. A direct-precedent dispute must retain both validated semantic alternatives and counterbalance when either could change claim-specific negative permission (`test_dispute_contains_two_bounded_resolution_candidates`, Task 7; `test_direct_dispute_requires_reversed_order`, Task 15).
5. Valid-looking frozen JSON after dependency deletion or context replacement must fail authoritative load (`test_frozen_load_rejects_missing_dependency`, Task 19).

## Existing file map and compatibility boundary

| Existing file(s) | Actual responsibility at accepted commit; planned use |
| --- | --- |
| `src/novelty_harness/domain/base.py` | Phase 0 `ContractModel` and shared typed identities; reuse frozen/forbidden-extra conventions in distinct Phase 7 contracts. |
| `src/novelty_harness/domain/enums.py` | Existing canonical `VerdictState`, `ValueMaturity`, evidence and gate enums; reuse rather than define a duplicate Phase 7 verdict. |
| `src/novelty_harness/domain/adjudication.py`, `application/ports.py`, `application/phase6_fixture.py` | Sparse Phase 1 `FrozenAdjudication` and fixture `AdjudicationEngine`/`Phase6FixtureAdjudicator`; retain for Phase 1–6 compatibility, never coerce into real Phase 7 authority. |
| `domain/idea.py`, `domain/mcu.py`, `mcu/overrides.py` | CIR, sufficiency, MCU/combination graph and optional content-hashed `MCUVersion`; validated policy/input manifest inputs. |
| `research/models.py`, `research/coverage.py`, `research/adaptive/{models,pipeline,stopping}.py`, `runtime/budgets/controller.py` | `ResearchPlan`, `CoverageCell`, `AdaptiveCoverageCell`, `ResearchResult`, `BranchState`, `StopAssessment`, `BudgetUsage`; seal their exact current records/digests, not inferred search quality. |
| `evidence/graph/{assessment_view,assessment_ledger,repository,sqlalchemy_repository,sqlalchemy_models,migrations}.py` | Repository-loaded `Phase6AssessmentView`, v7 ledger and graph/content authority. Extend the same SQLite store; schema becomes v8. |
| `runtime/semantic/structured.py`, `ports/llm.py`, `runtime/tracing/{hashing,models,sinks}.py` | Strict structured model calls, provider-neutral port, canonical identity and post-commit trace delivery. Reuse; no vendor imports in domain policy. |
| `application/{models,research_phase4,evidence_phase6,vertical_slice}.py`, `reporting/minimal.py` | Typed existing slice results, reviewed Phase 3–6 execution and current real-Phase-6/fixture-Phase-7 bridge. Add an explicit real Phase 7 path while preserving earlier fixtures. |
| `tests/{unit,integration,adversarial}`, `tests/unit/test_phase6_architecture_guards.py`, `docs/traceability/phase-6.yaml` | Existing deterministic, full-slice and architecture conventions; add Phase 7 files and traceability without rewriting Phase 6 history. |

## Proposed file map

| File | One responsibility |
| --- | --- |
| `src/novelty_harness/adjudication/__init__.py` | Mark the real Phase 7 package as distinct from the Phase 1 fixture module. |
| `src/novelty_harness/adjudication/models.py` | Real Phase 7 identities, run states and target/argument base contracts. |
| `src/novelty_harness/adjudication/context.py` | `Phase7InputManifest`, `SealedAssessmentContext`, canonical context identity and true-no-op comparison. |
| `src/novelty_harness/adjudication/packet.py` | Deterministic complete `AdjudicationCasePacket` and display-omission references. |
| `src/novelty_harness/adjudication/roles.py` | Prosecutor, defender, explicit dispute-resolution candidates and bounded rebuttal contracts. |
| `src/novelty_harness/adjudication/needs.py` | Input clarification, external research gaps, escalation budget and outcome contracts. |
| `src/novelty_harness/adjudication/gates.py` | Four typed gate findings and deterministic gate checks. |
| `src/novelty_harness/adjudication/counterfactual.py` | Structured surviving-difference localization. |
| `src/novelty_harness/adjudication/judge.py` | Judge proposals, deterministic impact trigger, full counterbalance comparisons and non-voting reconciliation. |
| `src/novelty_harness/adjudication/policy.py` | Pure verdict permission rules and language ceiling. |
| `src/novelty_harness/adjudication/qualifications.py` | Robustness/domain qualification records and authority references. |
| `src/novelty_harness/adjudication/frozen.py` | Target/whole composition and real immutable `FrozenAdjudication`. |
| `src/novelty_harness/adjudication/repository.py` | Phase 7 repository protocol and authority errors; no SQL. |
| `src/novelty_harness/ports/adjudication.py` | Provider-neutral role, rebuttal, judge and research-escalation protocols. |
| `src/novelty_harness/application/phase7_model_adapter.py` | Bounded structured-output calls implementing role/judge ports over the existing semantic runner. |
| `src/novelty_harness/application/phase7_roles.py` | Independent role calls, bounded rebuttal and neutral judging orchestration. |
| `src/novelty_harness/application/phase7_research.py` | Approved research dispatch, changed-context restart and true-no-op continuation. |
| `src/novelty_harness/application/phase7.py` | Real Phase 7 run, gate and freeze coordinator. |
| `src/novelty_harness/adjudication/prompts.py` | Versioned prosecutor/defender/rebuttal/judge instructions and rubric IDs; untrusted evidence remains data. |
| `src/novelty_harness/evidence/graph/phase7_models.py` | v8 ORM rows using the existing SQLAlchemy Base. |
| `src/novelty_harness/evidence/graph/phase7_store.py` | Same-database Phase 7 transactions and authority checks. |
| `src/novelty_harness/evidence/graph/migrations.py` | Safe v7→v8 schema registration without historical backfill. |
| `src/novelty_harness/evidence/graph/sqlalchemy_repository.py` | Public delegation and shared in-session Phase 6 authority validation. |
| `src/novelty_harness/application/models.py` | Typed real Phase 7 result branch distinct from fixture adjudication summary. |
| `src/novelty_harness/application/vertical_slice.py` | Explicit real Phase 7 handoff while retaining fixture paths. |
| `src/novelty_harness/reporting/minimal.py` | Labeled frozen summary at the existing report fixture boundary. |
| `tests/unit/adjudication/test_contracts.py` | Frozen contract and fixture separation tests. |
| `tests/unit/adjudication/test_context.py` | Manifest, successor and true-no-op tests. |
| `tests/unit/adjudication/test_packet.py` | Exact packet preservation and display-omission tests. |
| `tests/unit/adjudication/test_roles.py` | Proposal validation, first-pass isolation and rebuttal tests. |
| `tests/unit/adjudication/test_needs.py` | Gate A input versus B/C/D external-research routing tests. |
| `tests/unit/adjudication/test_gates.py` | Four categorical gate and counterfactual tests. |
| `tests/unit/adjudication/test_judge.py` | Consequence trigger, counterbalance and instability tests. |
| `tests/unit/adjudication/test_policy.py` | Five verdict permissions and qualification ceiling tests. |
| `tests/unit/adjudication/test_frozen.py` | Whole-assessment aggregation and frozen shape tests. |
| `tests/unit/evidence/graph/test_phase7_store.py` | Migration, transaction, replay and authoritative read/write cases. |
| `tests/integration/test_phase7_slice.py` | Real repository-loaded Phase 7 lifecycle and fixture migration. |
| `tests/adversarial/test_phase7_authority_semantics.py` | Fresh semantic and authority boundary attacks. |
| `tests/unit/test_phase7_architecture_guards.py` | Import and authority pathway checks. |
| `tests/unit/evidence/graph/test_sqlalchemy_repository.py` | Existing graph repository migration and regression controls. |
| `tests/integration/test_phase5_slice_with_phase6_evidence.py` | Existing real Phase 6/fixture Phase 7 behavior retained beside the new branch. |
| `tests/unit/test_minimal_report_compiler.py` | Existing fixture report behavior retained. |
| `docs/traceability/phase-7.yaml` | Requirement-to-task/module/test mapping. |
| `docs/phase-7-completion.md` | Exact implementation verification and independent-review handoff. |
| `README.md` | Current phase status and real versus fixture entrypoint description. |

## Locked repository and interface decisions

**Schema v8:** Create `phase7_input_manifests` (PK `manifest_id`, `assessment_id`, canonical document), `phase7_assessment_contexts` (PK `context_id`, FK `(snapshot_id, assessment_id)` to v7 snapshot, FK `manifest_id`, nullable self-FK `parent_context_id`, unique `(context_id,assessment_id,snapshot_id)`), `phase7_runs` (PK `run_id`, FK `(context_id,assessment_id,snapshot_id)`, unique `(context_id,attempt_token)`), `phase7_run_transitions` (PK `transition_id`, FK `run_id`, nullable self-FK predecessor, state/document), `phase7_artifacts` (PK `artifact_id`, FK `run_id` and `(context_id,assessment_id,snapshot_id)`, kind/target/document; typed kinds include dispute, judge run, counterbalance comparison and judge resolution), `phase7_qualification_refs` (PK `qualification_id`, FK context/target, status/issuer/document), `phase7_frozen_manifests` (PK `adjudication_id`, unique FK `run_id`, FK context, document), and `phase7_frozen_dependencies` (composite PK `(adjudication_id,artifact_id)`, FKs to frozen manifest and artifact). Validate same-run/context identity and the **exact** required dependency set transactionally; relational FKs alone do not prove semantics. `document_json` is canonical, typed and immutable. A v7 database gains empty v8 tables and no invented Phase 7 record. Existing v7 Phase 6 rows and readers retain their contracts. SQLite foreign keys remain enabled.

**Canonical identity:** Prefix and hash normalized semantic payload plus assessment/context/snapshot, target, input-manifest digest, method/prompt/rubric/policy version. `p7ctx_`, `p7run_`, `p7case_`, `p7arg_`, `p7need_`, `p7gap_`, `p7judge_`, `p7gate_`, `p7frozen_` are separate namespaces. The repository allocates an attempt token for an intentional new run on one context; exact retry reuses it. Exclude UTC observation and trace-delivery times from semantic IDs and store observations/events separately. Same-ID/different-content writes fail; exact replay is idempotent.

**Public signatures fixed for tasks below:** `seal_phase7_context(assessment_id: AssessmentId, *, snapshot_id: str, manifest: Phase7InputManifest, parent_context_id: str | None = None) -> SealedAssessmentContext`; `load_phase7_context(assessment_id: AssessmentId, *, context_id: str) -> SealedAssessmentContext`; `build_adjudication_case(context: SealedAssessmentContext, view: Phase6AssessmentView) -> AdjudicationCasePacket`; `freeze_phase7_adjudication(run_id: str, proposed: FrozenAdjudication) -> str`; `load_frozen_adjudication(assessment_id: AssessmentId, *, adjudication_id: str) -> FrozenAdjudication`. The application passes only repository-loaded context/view to the builder; freeze reloads both in one transaction. A constructed Pydantic shape cannot confer authority.

**Upstream sealing:** The real application handoff supplies exact typed CIR, sufficiency, graph/version, reviewed research plan, `ResearchResult`, coverage policy, limits, attempts and provenance when those stages complete. The repository cross-checks assessment/cutoff, target universe, source digest, Phase 6 snapshot, IDs and canonical hashes before sealing. Historical artifacts that cannot be validated are explicitly UNKNOWN at Gates A/B; a run-artifact file is an audit source, not independent authority. A research-only change creates a new input manifest/context over the same Phase 6 snapshot; a changed Phase 6 ledger creates a new snapshot/context. Neither updates a prior manifest.

**Contract field locks:** `InputClarificationNeed` has `need_id,assessment_id,assessment_context_id,phase6_snapshot_id,target_id,reason,missing_input_fields,unresolved_structure,material_gate='A',resolution_requirement,provenance`. `ResearchGapRequest` has `request_id`, the same four scope IDs, `requesting_stage,gap_type,reason,research_hypothesis,evidence_families,query_family_hints,retrieval_strategy_hints,material_gate in {B,C,D},linked_argument_ids,linked_comparison_ids,priority,stop_condition,provenance`; D also carries a missing-prior-art reference. `AdjudicationCasePacket` has `case_id`, those scope IDs, `manifest_id,digest,as_of,target_profiles,comparisons,authorized_relations,cited_passages,candidate_outcomes,coverage,research_state,unresolved_questions,builder_version`. `DisputeResolutionCandidate` has `candidate_id,dispute_id,target_id,gate_c_candidate: GateCState|None,gate_d_candidate: GateDState|None,basis_argument_ids,basis_phase6_ids,bounded,reason`; `Dispute` has exactly two distinct bounded candidates derived from validated opposing positions, or `resolution_space_unbounded=true` with no asserted candidate pair. `ProsecutionCase`, `DefenseCase`, `RebuttalCase`, `JudgeFinding`, all four `Gate*Finding`, `CounterbalanceRun`, `CounterbalanceComparison`, `TargetFinding` and real `FrozenAdjudication` share scope IDs and typed basis IDs; their exact role-specific payloads are fixed in Tasks 1, 4, 9–17. No role/judge proposal has a final-verdict, language-permission, novelty-score or HIGH_IMPACT field. Candidate interpretations are not evidence.

**Role and decision payload locks:** `ProsecutionCase` contains challenge IDs, thesis, matched elements/relationships, missing elements, exact packet evidence refs, effect, counterfactual and limitations; `DefenseCase` contains defense IDs, concessions/objections/unresolved points, exact refs, differentiators and limitations. `RebuttalCase` names its role and only selected dispute/argument IDs. `JudgeFinding` contains accepted/rejected/uncertain challenge IDs, exact Phase 6 refs, proposed Gate C/D states and reasons, never a verdict. Each `CounterbalanceRun` binds dispute, packet, argument IDs/order, evidence digest, rubric, model/config and full finding. `CounterbalanceComparison` retains both run IDs and actual findings with those shared identities, their stability, materially disputed dimensions and a normalized semantic resolution only when internally stable. Each `Gate*Finding` contains categorical state, basis IDs, limiting factors and provenance. `TargetFinding` contains exact claim scope, verdict, gate IDs, basis IDs and language permission; `FrozenAdjudication` contains all target findings, overall state and dependency IDs. The complete packet remains repository-derived; shorter prompt displays cannot create new basis IDs.

**Repository protocol:** Task 2 defines `Phase7AdjudicationRepository` with the five Locked public methods. Task 6 adds `begin_phase7_run`, `record_phase7_artifact` and `transition_phase7_run`; Task 13 adds `load_phase7_qualifications`; Tasks 18–19 implement freeze/load. `SqlAlchemyEvidenceGraphRepository` implements this protocol through helpers on its existing engine. Task 20's `Phase7Ports` bundle is defined in Task 5. All caller inputs are revalidated from serialized content before authority use.

## Design and master-spec coverage

| Approved design sections | Owning tasks | Master-spec anchors |
| --- | --- | --- |
| 1–5 architecture, authority and invariants | 1–4, 13, 18–21 | INV-01/02/03/05/06/07/09/11/12/13/14/15; §§31–37 |
| 6–8 coordinator, lifecycle, packet | 2–3, 6, 8, 20 | FR-AUD-001/002; §§34–35 |
| 9–12 roles, rebuttal and typed needs | 4–8 | §§31–32; FR-SEC-001/002 |
| 13–14 budget, stopping and restart | 2, 8, 10 | FR-ARC-001/002; FR-OBS-001 |
| 15–18 judge, counterbalance and instability | 14–16 | §33; FR-AUD-002 |
| 19–22 Gate A/B/C/D | 9–12 | §35; FR-EQ-004; FR-EVID-004 |
| 23–30 verdicts, qualification, value, aggregation, abstention | 9–13, 16–17 | §36; INV-09/12/13 |
| 31–35 frozen authority, IDs, audit, Phase 8 handoff | 17–21 | §§34,37; FR-AUD-001/002 |
| 36–38 ports, cost and failures | 5–8, 14–16, 20–21 | §§31–35; FR-SEC-001/002 |
| 39–45 tests, fixture migration, acceptance, non-goals and hooks | 13, 16, 20–22 | Phase 7 exit criteria; FR-OBS-002 |

## Stages and task gates

Five ordered stages: (I) typed contracts/context/packet, Tasks 1–4; (II) independent roles and bounded escalation, Tasks 5–8; (III) gates, neutral judging and verdict policy, Tasks 9–16; (IV) frozen repository authority and real slice, Tasks 17–20; (V) traceability, adversarial closure and acceptance, Tasks 21–22. Each task's green gate plus nearby attacks precedes its commit and the next task. Run only focused/component suites during development; full verification is Task 22.

### Task 1: Real Phase 7 contract vocabulary

**Files:** Create `src/novelty_harness/adjudication/__init__.py`, `src/novelty_harness/adjudication/models.py`, `src/novelty_harness/adjudication/roles.py`, `src/novelty_harness/adjudication/needs.py`, `src/novelty_harness/adjudication/gates.py`, `src/novelty_harness/adjudication/counterfactual.py`, `src/novelty_harness/adjudication/judge.py`, `src/novelty_harness/adjudication/qualifications.py`, `src/novelty_harness/adjudication/frozen.py`; test `tests/unit/adjudication/test_contracts.py`.

**Interfaces:** Define frozen versioned `Phase7RunState` with CASE_BUILT, FIRST_PASSES_COMPLETE, ESCALATION_PENDING, SUPERSEDED_BY_NEW_ASSESSMENT_STATE, JUDGING, FROZEN, ABSTAINED and FAILED; `TargetRef(kind: MCU|COMBINATION,id)`, `RoleArgument`, `ProsecutionCase`, `DefenseCase`, `RebuttalCase`, `DisputeResolutionCandidate`, `Dispute`, `InputClarificationNeed(material_gate: Literal['A'])`, `ResearchGapRequest(material_gate: Literal['B','C','D'])`, `CounterfactualLocalization`, `GateAFinding`, `GateBFinding`, `GateCFinding`, `GateDFinding`, `JudgeFinding`, `CounterbalanceRun`, `NormalizedJudgeFinding`, `CounterbalanceComparison`, `JudgeStability`, `JudgeResolution`, `RobustnessQualification`, `DomainQualification`, `NoveltySignificance`, `LanguagePermissionClass`, `TargetFinding` and the real `FrozenAdjudication`. Reuse `domain.enums.VerdictState` and `ValueMaturity`; define Gate C/D categorical states once for their findings and pre-judge candidates. All new artifacts carry assessment/context/snapshot/target IDs where applicable and a versioned `contract_kind`; no Phase 1 fixture import or verdict field in role proposals.

- [x] **Failing test:** `test_phase7_contracts_are_frozen_distinct_and_typed` asserts extra fields, duplicate argument IDs, Gate A research type, role verdict/HIGH_IMPACT fields and a candidate-supplied final verdict or language ceiling fail validation; fixture `domain.adjudication.FrozenAdjudication` remains distinct. Packet membership checks belong to Task 4.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_contracts.py::test_phase7_contracts_are_frozen_distinct_and_typed -q`; expect missing types or failed validation.
- [x] **Minimal implementation:** Add only typed contracts and local shape validators; defer repository authority and semantic policy to later tasks.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_contracts.py::test_phase7_contracts_are_frozen_distinct_and_typed -q`; expect PASS.
- [x] **Nearby variants:** Run the exact test, then `uv run pytest tests/unit/test_phase1_domain_contracts.py tests/unit/adjudication/test_contracts.py -q`; add `test_phase7_contract_rejects_cross_snapshot_target` before leaving.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_contracts.py tests/unit/test_phase1_domain_contracts.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): define distinct adjudication contracts`.

### Task 2: Schema v8 and sealed assessment context

**Files:** Create `src/novelty_harness/adjudication/context.py`, `src/novelty_harness/adjudication/repository.py`, `src/novelty_harness/evidence/graph/phase7_models.py`, `src/novelty_harness/evidence/graph/phase7_store.py`; modify `src/novelty_harness/evidence/graph/migrations.py`, `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`; test `tests/unit/adjudication/test_context.py`, `tests/unit/evidence/graph/test_phase7_store.py`.

**Interfaces:** `Phase7InputManifest` binds `CanonicalIdeaRepresentation`, `SufficiencyAssessment`, `MCUGraph|MCUVersion`, reviewed `ResearchPlan|None`, `ResearchResult|None`, `CoveragePolicy|None`, `BudgetLimits|None`, exact upstream IDs/digests and method versions; unknown historical inputs are explicit. `SealedAssessmentContext(context_id,assessment_id,snapshot_id,manifest_id,manifest_digest,parent_context_id)` is repository-loaded. `is_true_noop(before: SealedAssessmentContext, after: SealedAssessmentContext) -> bool` compares snapshot and manifest digests and every bound research/input field; it is only a pure comparison, while Task 8 requires repository-loaded, authority-checked inputs before using its result to resume. Add the two public repository context methods in Locked decisions.

- [x] **Failing tests:** `test_v7_migrates_to_empty_v8_without_phase7_backfill`, `test_v8_initialization_is_idempotent_and_rollback_is_atomic`, `test_context_seals_matching_phase6_snapshot`, `test_context_changes_for_same_snapshot_new_budget_or_coverage`, `test_context_true_noop_requires_all_bound_state_equal` assert migration, reopen, rollback, exact ID binding, successor creation for CIR/coverage/budget/stop/provider/access/query changes, and unchanged replay.
- [x] **Red:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py tests/unit/adjudication/test_context.py -q`; expect absent v8 rows/API.
- [x] **Minimal implementation:** Register `phase7_models.py` with `Base.metadata` before `create_all`, add the eight tables above, advance v7 to v8 without backfill and retain older unsafe migration checks. Implement same-database context write/load with validated Phase 6 view, canonical digest, FK and transactional rollback. Reject same-ID/content conflict and foreign target/assessment/cutoff.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_context.py::test_context_seals_matching_phase6_snapshot -q`; expect PASS.
- [x] **Nearby variants:** Run both files and `tests/unit/evidence/graph/test_sqlalchemy_repository.py`; add same-snapshot/different-provider, missing validated research history, reopened DB and fake caller-context variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_context.py tests/unit/evidence/graph/test_phase7_store.py tests/unit/evidence/graph/test_sqlalchemy_repository.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): seal assessment context in schema v8`.

### Task 3: Deterministic case packet

**Files:** Create `src/novelty_harness/adjudication/packet.py`; test `tests/unit/adjudication/test_packet.py` and `tests/integration/test_phase7_slice.py`.

**Interfaces:** `build_adjudication_case(context: SealedAssessmentContext, view: Phase6AssessmentView) -> AdjudicationCasePacket` uses the Locked signature. Packet fields include full target topology, classified chains, `AuthorizedGraphRelation` IDs, exact cited passages, scoped subset/remainder, contradictions, chronology, lineage, patent/multi-source context, all candidate outcomes, exclusions, coverage, budget/stop/access and unresolved questions. `select_role_display(packet, *, target_id: str, max_chars: int) -> RoleDisplay` records every omitted ID; a judge cannot cite omitted content as decisive.

- [x] **Failing test:** `test_packet_preserves_full_phase6_and_research_state` asserts exact IDs and scoped/negative/failed facts from a repository-loaded view; `test_display_omission_is_not_decisive_basis` rejects an omitted decisive citation.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_packet.py -q`; expect absent builder/selection.
- [x] **Minimal implementation:** Canonical packet ID over context and normalized content; validate matching assessment/snapshot/target universe and reconstruct no Phase 6 classification.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_packet.py::test_packet_preserves_full_phase6_and_research_state -q`; expect PASS.
- [x] **Nearby variants:** Run packet and `tests/integration/test_phase6_assessment_parity.py`; add semantic-only status and missing-combination-member variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_packet.py tests/integration/test_phase6_assessment_parity.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): build complete context-bound case packet`.

### Task 4: Strict argument and need validation

**Files:** Modify `src/novelty_harness/adjudication/roles.py`, `src/novelty_harness/adjudication/needs.py`; test `tests/unit/adjudication/test_roles.py`, `tests/unit/adjudication/test_needs.py`, `tests/adversarial/test_phase7_authority_semantics.py`.

**Interfaces:** `validate_prosecution_case(case: ProsecutionCase, packet: AdjudicationCasePacket) -> ProsecutionCase`, `validate_defense_case(case: DefenseCase, packet: AdjudicationCasePacket) -> DefenseCase`, `validate_rebuttal_case(case: RebuttalCase, packet: AdjudicationCasePacket) -> RebuttalCase`, `route_need(need: InputClarificationNeed | ResearchGapRequest) -> Literal['INPUT','RESEARCH']`. Validate every source/version/passage/comparison/graph/argument ID against packet membership; role effects remain arguments, not Phase 6 reclassifications. A D research request requires a linked missing prior-art fact.

- [x] **Failing tests:** `test_role_case_rejects_packet_absent_passage`, `test_role_case_rejects_foreign_context_and_target`, `test_gate_a_need_never_routes_research`, `test_gate_d_gap_requires_external_prior_art`, `test_model_cannot_supply_high_impact_flag`, `test_model_cannot_supply_hypothetical_final_verdict`; assert fabricated IDs and semantic-authority keys fail closed.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_roles.py tests/unit/adjudication/test_needs.py -q`; expect validator/routing failures.
- [x] **Minimal implementation:** Strict JSON revalidation followed by exact packet ID joins and typed Gate A/B/C/D routing; no source memory or caller object substitutes.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_roles.py::test_role_case_rejects_packet_absent_passage -q`; expect PASS.
- [x] **Nearby variants:** Run these files plus adversarial `-k role`; add copied argument, wrong version, invented relation, and material input disguised as D gap.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_roles.py tests/unit/adjudication/test_needs.py tests/adversarial/test_phase7_authority_semantics.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): validate role arguments and separate input needs`.

### Task 5: Provider-neutral ports, prompts and bounded recovery

**Files:** Create `src/novelty_harness/ports/adjudication.py`, `src/novelty_harness/adjudication/prompts.py`, `src/novelty_harness/application/phase7_model_adapter.py`; test `tests/unit/adjudication/test_roles.py`, `tests/unit/test_phase7_architecture_guards.py`.

**Interfaces:** Async protocols `ProsecutionPort.propose(packet: AdjudicationCasePacket) -> ProsecutionCase`, `DefensePort.propose(packet: AdjudicationCasePacket) -> DefenseCase`, `RebuttalPort.propose(packet: AdjudicationCasePacket, disputed_ids: tuple[str,...], other_case: ProsecutionCase|DefenseCase) -> RebuttalCase`, `EvidenceJudgePort.judge(packet: AdjudicationCasePacket, arguments: tuple[RoleArgument,...], *, order: tuple[str,str], rubric_version: str) -> JudgeFinding`. Define `Phase7Ports` as the typed bundle of these ports plus optional research escalation. Version IDs `p7-prosecutor-v1`, `p7-defender-v1`, `p7-rebuttal-v1`, `p7-judge-rubric-v1`. The application adapter implements the four protocols over existing `SemanticRunner.run` and `ContextBlock`, which carry trusted instruction separately from untrusted evidence.

- [x] **Failing tests:** `test_phase7_prompts_keep_evidence_as_untrusted_data` inspects actual call blocks; `test_malformed_role_output_is_bounded_failure` asserts at most one schema-recovery retry and operational failure, never a fabricated case.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_roles.py -q -k 'prompts or malformed'`; expect missing ports/prompts.
- [x] **Minimal implementation:** Add versioned instructions, strict proposal schemas and a bounded wrapper over `SemanticRunner`; record prompt/rubric/model/request/response hashes and token/cost/latency metadata. No direct search or verdict assignment in prompts.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_roles.py::test_phase7_prompts_keep_evidence_as_untrusted_data -q`; expect PASS.
- [x] **Nearby variants:** Run role and architecture files; add prompt-injection passage and extra JSON verdict key variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_roles.py tests/unit/test_phase7_architecture_guards.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): add provider neutral role prompts and ports`.

### Task 6: Independent first passes and durable run identity

**Files:** Create `src/novelty_harness/application/phase7_roles.py`; modify `src/novelty_harness/adjudication/models.py`, `src/novelty_harness/evidence/graph/phase7_store.py`; test `tests/unit/adjudication/test_roles.py`, `tests/unit/evidence/graph/test_phase7_store.py`.

**Interfaces:** Define `Phase7RunRecord`, `Phase7RunTransition` and `Phase7Artifact` in `adjudication/models.py`. `begin_phase7_run(context_id: str, *, attempt_token: str|None=None) -> Phase7RunRecord`, `record_phase7_artifact(run_id: str, artifact: Phase7Artifact) -> str`, `transition_phase7_run(run_id: str, *, expected_state: Phase7RunState, next_state: Phase7RunState) -> Phase7RunTransition`; async `run_independent_first_passes(run_id: str, packet: AdjudicationCasePacket, prosecutor: ProsecutionPort, defender: DefensePort, repository: Phase7AdjudicationRepository) -> tuple[ProsecutionCase,DefenseCase]`. Store immutable run header and append-only transitions; `FIRST_PASSES_COMPLETE` requires both committed and validated cases.

- [x] **Failing tests:** `test_first_passes_cannot_observe_each_other` captures call inputs and asserts only the identical packet was passed; `test_run_rejects_foreign_case_before_first_pass_complete` checks transaction/state boundary.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_roles.py -q -k first_passes`; expect missing coordinator.
- [x] **Minimal implementation:** Obtain same repository-loaded packet for each independent context, validate outputs, persist each, then append the transition. A provider failure records FAILED, not UNASSESSABLE.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_roles.py::test_first_passes_cannot_observe_each_other -q`; expect PASS.
- [x] **Nearby variants:** Run role/store files; add retry duplicate and one-side-malformed cases.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_roles.py tests/unit/evidence/graph/test_phase7_store.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): commit independent first pass cases`.

### Task 7: Material dispute selection and bounded rebuttal

**Files:** Modify `src/novelty_harness/application/phase7_roles.py`, `src/novelty_harness/adjudication/roles.py`, `src/novelty_harness/evidence/graph/phase7_store.py`; test `tests/unit/adjudication/test_roles.py`.

**Interfaces:** Define `DisputeResolutionCandidate` and `Dispute` in `adjudication/roles.py`. Each candidate binds candidate/dispute/target IDs, `gate_c_candidate: GateCState|None`, `gate_d_candidate: GateDState|None`, exact basis argument and Phase 6 IDs, `bounded=True` and reason. A `None` gate state means that dimension is agreed and held at its validated baseline; if no such baseline can be established, the resolution space is unbounded. `Dispute` binds target, exact argument IDs and disputed effect, plus **exactly two distinct, bounded** prosecution/defense semantic candidates, or `resolution_space_unbounded=True` with no asserted pair. `material_disputes(prosecution: ProsecutionCase, defense: DefenseCase, packet: AdjudicationCasePacket, *, rebuttals: tuple[RebuttalCase,...]=()) -> tuple[Dispute,...]` deterministically derives and canonically identifies the complete alternative set from validated positions and packet state, without an LLM call. Recompute with the validated rebuttals before judging; if they make the alternatives incomplete, mark the space unbounded rather than drop a plausible outcome. Async `run_rebuttals(run_id: str, packet: AdjudicationCasePacket, disputes: tuple[Dispute,...], prosecutor_port: RebuttalPort, defender_port: RebuttalPort, repository: Phase7AdjudicationRepository) -> tuple[RebuttalCase,...]` persists at most one rebuttal per role/run; only selected dispute IDs and packet evidence may appear.

- [x] **Failing tests:** `test_dispute_contains_two_bounded_resolution_candidates`, `test_unbounded_dispute_has_no_asserted_pair`, `test_no_material_dispute_skips_rebuttal`, `test_second_rebuttal_for_role_is_rejected`, `test_rebuttal_rejects_cross_context_and_new_source`; an evidence gap produces a typed request rather than a third debate round.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_roles.py::test_dispute_contains_two_bounded_resolution_candidates -q`; expect absent candidate contract/extraction.
- [x] **Minimal implementation:** Compare structured first-pass effects/concessions/IDs, derive the two complete semantic candidates or mark the space unbounded, dispatch one bounded call per side if needed, validate and persist; forbid reply-to-reply links. After rebuttal, recompute and persist the current immutable dispute artifact; Task 15 uses that exact version. Candidate states are interpretations of existing packet evidence, not evidence or verdicts.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_roles.py::test_dispute_contains_two_bounded_resolution_candidates -q`; expect PASS.
- [x] **Nearby variants:** Run role tests plus `tests/adversarial/test_phase7_authority_semantics.py -q -k rebuttal`; add copied challenge from another target, missing candidate, duplicated candidate, foreign Phase 6 basis and rebuttal that expands the resolution space.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_roles.py tests/adversarial/test_phase7_authority_semantics.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): bound material rebuttal to one turn per role`.

### Task 8: Typed research escalation, zero-yield restart and true no-op

**Files:** Create `src/novelty_harness/application/phase7_research.py`; modify `src/novelty_harness/adjudication/needs.py`, `src/novelty_harness/ports/adjudication.py`, `src/novelty_harness/evidence/graph/phase7_store.py`; test `tests/unit/adjudication/test_needs.py`, `tests/integration/test_phase7_slice.py`.

**Interfaces:** Async `ResearchEscalationPort.execute(request: ResearchGapRequest, context: SealedAssessmentContext) -> ResearchEscalationOutcome` adapts approved requests to existing Phase 3 planning, Phase 4 retrieval, Phase 5 provenance and Phase 6 verification; no browser/search method is given to roles. Define `ResearchEscalationBudget`, `ResearchEscalationOutcome`, `GapDecision` and `ResearchContinuation(context: SealedAssessmentContext, run_id: str, restarted: bool)` in `adjudication/needs.py`. `GapEscalationPolicy.decide(request: ResearchGapRequest, context: SealedAssessmentContext, budget: ResearchEscalationBudget) -> GapDecision` enforces materiality, deduplication and `BudgetLimits`; `complete_research_escalation(run_id: str, outcome: ResearchEscalationOutcome, repository: Phase7AdjudicationRepository) -> ResearchContinuation` atomically seals changed state, appends `SUPERSEDED_BY_NEW_ASSESSMENT_STATE` and starts a new run, or verifies strict true no-op and resumes. The coordinator then builds the successor packet and reruns both independent first passes. The outcome includes exact updated manifest and snapshot locator, attempt/stop/access facts and cost.

- [x] **Failing tests:** `test_research_only_change_restarts_roles` executes a zero-source result with changed `BudgetUsage`, `CoverageCell`, query history and `NO_NEW_YIELD`; assert new context ID, superseded old run and fresh calls. `test_proven_true_noop_resumes_same_run` asserts all bound facts identical and no new case; `test_gate_a_request_never_reaches_research_port` asserts zero calls.
- [x] **Red:** `uv run pytest tests/integration/test_phase7_slice.py -q -k 'research_only_change or true_noop'`; expect absent restart.
- [x] **Minimal implementation:** Use existing Phase 3–6 application components through the adapter; reload repository Phase 6 view, seal updated manifest and compare full context. Do not interpret zero results as saturation or reuse old arguments after any material change.
- [x] **Green:** `uv run pytest tests/integration/test_phase7_slice.py::test_research_only_change_restarts_roles -q`; expect PASS.
- [x] **Nearby variants:** Run integration and need tests; add provider-blocked, same-snapshot changed-stop, changed CIR and duplicate-gap variants.
- [x] **Focused regression:** `uv run pytest tests/integration/test_phase7_slice.py tests/unit/adjudication/test_needs.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): restart adjudication after changed research state`.

### Task 9: Gate A input sufficiency

**Files:** Modify `src/novelty_harness/adjudication/gates.py`, `src/novelty_harness/adjudication/needs.py`; test `tests/unit/adjudication/test_gates.py`.

**Interfaces:** `evaluate_gate_a(packet: AdjudicationCasePacket, target: TargetRef) -> tuple[GateAFinding,tuple[InputClarificationNeed,...]]` derives ASSESSABLE/LIMITED/INSUFFICIENT from sealed `SufficiencyAssessment`, CIR unknowns, MCUVersion or graph stability and topology. Explicit Phase 2 INSUFFICIENT cannot be upgraded. Gate A has no `ResearchGapRequest` return path.

- [x] **Failing tests:** `test_gate_a_unknown_topology_never_dispatches`, `test_gate_a_missing_mechanism_is_unassessable`, `test_gate_a_exploratory_is_limited`, `test_gate_a_phase2_insufficient_cannot_upgrade`; assert `material_gate='A'`, no ResearchEscalationPort call and no positive permission.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_gates.py -q -k gate_a`; expect absent evaluator.
- [x] **Minimal implementation:** Deterministic per-target sufficiency and typed input-resolution requirements; do not search to fill claim meaning.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_gates.py::test_gate_a_unknown_topology_never_dispatches -q`; expect PASS.
- [x] **Nearby variants:** Run gate/need tests; add reversed relationship and unstable combination decomposition variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_gates.py tests/unit/adjudication/test_needs.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): enforce input clarification at Gate A`.

### Task 10: Gate B research sufficiency

**Files:** Modify `src/novelty_harness/adjudication/gates.py`; test `tests/unit/adjudication/test_gates.py`.

**Interfaces:** `evaluate_gate_b(packet: AdjudicationCasePacket, target: TargetRef) -> GateBFinding` returns a categorical permission set: `CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE`, `MEANINGFUL_BOUNDED_POSITIVE_COMPARISON`, `STRONG_POSITIVE_COVERAGE`, plus limitations. Consume sealed `ResearchPlan`, `AdaptiveCoverageCell`, `BranchState`, `StopAssessment`, `BudgetUsage`, Phase 6 failures/exclusions and accepted gap outcomes. Reuse approved `CoveragePolicy`, not a new arbitrary numeric threshold.

- [x] **Failing tests:** `test_gate_b_direct_negative_needs_no_global_saturation`, `test_gate_b_budget_stop_is_not_saturation`, `test_gate_b_no_new_yield_is_not_saturation`, `test_gate_b_unassessed_source_limits_positive_permission`; assert provider blocked never means no prior art.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_gates.py -q -k gate_b`; expect absent categorical permission.
- [x] **Minimal implementation:** Derive permissions solely from current sealed context and exact Phase 6 view facts; preserve provider/access and historical-unknown limitations.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_gates.py::test_gate_b_budget_stop_is_not_saturation -q`; expect PASS.
- [x] **Nearby variants:** Run gate and context tests; add same-snapshot/new-budget versus stale-packet comparison.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_gates.py tests/unit/adjudication/test_context.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): derive categorical research permission at Gate B`.

### Task 11: Gate C equivalence without Phase 6 reclassification

**Files:** Modify `src/novelty_harness/adjudication/gates.py`; test `tests/unit/adjudication/test_gates.py`.

**Interfaces:** `evaluate_gate_c(packet: AdjudicationCasePacket, target: TargetRef, judge: JudgeFinding|None) -> GateCFinding` returns DIRECT_ESTABLISHED, SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA, NO_DIRECT_IN_REVIEWED_SCOPE, DISPUTED or UNASSESSABLE with exact comparison/authorized-graph/citation IDs. Only an eligible supported one-source same-target direct chain establishes DIRECT; strong partial remains Phase 6 strong partial even if a later claim-level negative is possible.

- [x] **Failing tests:** `test_gate_c_direct_requires_authorized_single_source`, `test_gate_c_partials_across_sources_never_stitch`, `test_gate_c_uncertain_chronology_not_direct`, `test_gate_c_local_no_direct_stays_local`; assert no mutation of `ClassifiedComparison`.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_gates.py -q -k gate_c`; expect missing gate.
- [x] **Minimal implementation:** Rejoin IDs to packet's repository-derived comparisons and authorized relations, preserve support/context/chronology; judge may resolve claim scope but cannot replace verified facts.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_gates.py::test_gate_c_direct_requires_authorized_single_source -q`; expect PASS.
- [x] **Nearby variants:** Run gate tests plus `tests/adversarial/test_phase6_equivalence_attacks.py`; add caller-forged graph ID and reversed-relationship variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_gates.py tests/adversarial/test_phase6_equivalence_attacks.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): resolve Gate C from exact Phase 6 chains`.

### Task 12: Gate D and counterfactual contribution localization

**Files:** Modify `src/novelty_harness/adjudication/counterfactual.py`, `src/novelty_harness/adjudication/gates.py`; test `tests/unit/adjudication/test_gates.py`.

**Interfaces:** `validate_counterfactual(packet: AdjudicationCasePacket, target: TargetRef, proposal: CounterfactualLocalization) -> CounterfactualLocalization`; `evaluate_gate_d(packet: AdjudicationCasePacket, target: TargetRef, judge: JudgeFinding|None, localization: CounterfactualLocalization|None) -> GateDFinding`. States SUBSTANTIVE, NON_SUBSTANTIVE, UNRESOLVED, NOT_APPLICABLE_TO_DIRECT. The semantic role/judge proposes the removal effect; deterministic validation joins it to the nearest packet comparison and cannot invent equivalence. A missing user mechanism redirects to Gate A; inaccessible closest historical implementation may create a D external-evidence request.

- [x] **Failing tests:** `test_gate_d_terminology_only_is_non_substantive`, `test_gate_d_causal_or_topology_change_can_be_substantive`, `test_gate_d_missing_user_meaning_is_input_need`, `test_gate_d_missing_closest_source_can_request_research`; asserted value maturity never changes result.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_gates.py -q -k gate_d`; expect missing evaluator/localization.
- [x] **Minimal implementation:** Validate structured judge rationale and removal effect against packet IDs; record unresolved effects rather than inventing a nearest source. Include parameter, cosmetic order, model/provider substitution, control flow and enabling-constraint fixtures.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_gates.py::test_gate_d_causal_or_topology_change_can_be_substantive -q`; expect PASS.
- [x] **Nearby variants:** Run gate tests; add wrong-context counterfactual and high-value/non-substantive variant.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_gates.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): localize Gate D differentiators without value inflation`.

### Task 13: Qualification ceiling and deterministic verdict permission

**Files:** Modify `src/novelty_harness/adjudication/qualifications.py`, `src/novelty_harness/adjudication/repository.py`, `src/novelty_harness/evidence/graph/phase7_store.py`; create `src/novelty_harness/adjudication/policy.py`; test `tests/unit/adjudication/test_policy.py`.

**Interfaces:** `VerdictPermissionPolicy.evaluate(*, packet: AdjudicationCasePacket, gate_a: GateAFinding, gate_b: GateBFinding, gate_c: GateCFinding, gate_d: GateDFinding, stability: JudgeStability, robustness: RobustnessQualification, domain: DomainQualification) -> TargetFinding`. `load_phase7_qualifications(context_id: str, target: TargetRef) -> tuple[RobustnessQualification,DomainQualification]` returns repository-owned NOT_YET_QUALIFIED/NOT_QUALIFIED defaults. Future QUALIFIED issuers are absent in Phase 7; a clearly marked validated fixture may exercise the pure strong-positive branch, but production freeze rejects fixture and caller-created QUALIFIED authority.

- [x] **Failing tests:** `test_direct_scope_permits_claim_specific_negative`, `test_single_strong_partial_non_substantive_delta_can_be_negative`, `test_bounded_substantive_survivor_is_potential`, `test_missing_input_or_weak_research_is_unassessable`, `test_unqualified_strong_positive_is_denied`, `test_validated_fixture_qualifications_exercise_strong_policy_only`, `test_value_maturity_cannot_change_verdict`; assert Phase 6 strong-partial label remains unchanged.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_policy.py -q`; expect missing policy.
- [x] **Minimal implementation:** Pure intersection of categorical conditions and language ceilings; no scalar score, no global absence inference, no model-proposed verdict. Keep production strong-positive disabled absent trusted future qualification issuer.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_policy.py::test_direct_scope_permits_claim_specific_negative -q`; expect PASS.
- [x] **Nearby variants:** Run policy/gate/judge files; add local-no-direct with worse coverage, high-value direct and copied qualification from foreign target/context variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_policy.py tests/unit/adjudication/test_gates.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): gate verdicts with deterministic permission policy`.

### Task 14: Deterministic HIGH_IMPACT consequence classifier

**Files:** Modify `src/novelty_harness/adjudication/judge.py`; test `tests/unit/adjudication/test_judge.py`.

**Interfaces:** Define `GateFacts(gate_a: GateAFinding, gate_b: GateBFinding, undisputed_c: GateCFinding|None, undisputed_d: GateDFinding|None, robustness: RobustnessQualification, domain: DomainQualification)` and `DisputeImpact(level: HIGH_IMPACT|LOW_IMPACT, changed_dimensions: tuple[str,...])` in `adjudication/judge.py`. `classify_dispute_impact(dispute: Dispute, packet: AdjudicationCasePacket, gate_facts: GateFacts, *, prosecution: ProsecutionCase, defense: DefenseCase, rebuttals: tuple[RebuttalCase,...]=()) -> DisputeImpact` deterministically rederives the complete candidate set from the committed role and rebuttal positions and packet, rejects a mismatched supplied `Dispute`, substitutes each candidate's Gate C/D state into a hypothetical finding using exact basis IDs, and holds Gate A/B, qualifications and other policy facts constant. `None` uses only a validated undisputed gate baseline. For both hypothetical policy calls, use the same neutral pre-judge stability assumption; actual `JudgeStability` is unknown until Task 16 and cannot be an impact-classifier input. Compare Gate C, Gate D, deterministic per-target verdict permission, assessability, maximum language class, claim-specific negative permission and POTENTIALLY_NOVEL permission. Any difference is HIGH_IMPACT. An unbounded space, missing baseline or unsafe hypothetical is HIGH_IMPACT; an incomplete or caller-trimmed bounded pair is rejected. The classifier calls no LLM and accepts no source count, token count, price, confidence or model-supplied HIGH_IMPACT flag.

- [x] **Failing tests:** `test_impact_uses_explicit_resolution_candidates` proves no semantic alternative is inferred inside the classifier; `test_high_impact_for_each_semantic_consequence` parametrizes Gate C, Gate D, target verdict, assessability, maximum language class, negative permission and POTENTIALLY_NOVEL permission; `test_unbounded_resolution_space_defaults_high_impact` covers unbounded or missing baseline; `test_caller_cannot_remove_unfavorable_candidate_resolution` rejects a copied dispute with one candidate; `test_model_cannot_supply_high_impact_flag` rejects a model-proposed shortcut.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_judge.py::test_impact_uses_explicit_resolution_candidates -q`; expect absent explicit-candidate evaluation.
- [x] **Minimal implementation:** Revalidate the pair's provenance, construct each hypothetical Gate C/D finding from its explicit semantic candidate and existing packet basis, invoke deterministic policy twice, and record changed dimensions. Never invent an alternative in this function or let the orchestrator narrow the set.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_judge.py::test_impact_uses_explicit_resolution_candidates -q`; expect PASS.
- [x] **Nearby variants:** Run judge and policy files; add duplicate candidate IDs, foreign argument/Phase 6 basis, `None` with no agreed baseline, unchanged wording/nonmaterial emphasis and fake low-cost override variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_judge.py tests/unit/adjudication/test_policy.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): classify counterbalance impact deterministically`.

### Task 15: Neutral, blinded and mandatory counterbalanced judge

**Files:** Modify `src/novelty_harness/application/phase7_roles.py`, `src/novelty_harness/adjudication/judge.py`, `src/novelty_harness/adjudication/prompts.py`; test `tests/unit/adjudication/test_judge.py`, `tests/integration/test_phase7_slice.py`.

**Interfaces:** Async `run_neutral_judging(run_id: str, packet: AdjudicationCasePacket, disputes: tuple[Dispute,...], gate_facts_by_target: Mapping[str,GateFacts], judge_port: EvidenceJudgePort, repository: Phase7AdjudicationRepository) -> tuple[CounterbalanceRun,...]`. Load the committed prosecution/defense cases and any rebuttals, then rederive each dispute's complete candidate pair before `classify_dispute_impact`; a caller copy with a removed or replaced candidate cannot suppress a judge call. Validate `JudgeFinding` target/argument/Phase 6 IDs. HIGH_IMPACT makes calls with orders `(A,B)` and `(B,A)` under identical packet, rubric, model/config and evidence, including when this function is invoked with an alternate configured judge. Sealed role mapping remains audit-only; judge sees Argument A/B. LOW_IMPACT may use one call. Task 16 turns the retained pair into `CounterbalanceComparison` before resolution or freeze.

- [x] **Failing tests:** `test_direct_dispute_requires_reversed_order`, `test_counterbalance_inputs_differ_only_in_order`, `test_judge_rejects_trimmed_resolution_candidates`, `test_judge_cannot_reclassify_phase6_or_add_passage`; assert both judge outputs persist with distinct order IDs.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_judge.py -q -k counterbalance`; expect missing orchestration.
- [x] **Minimal implementation:** Material-dispute classifier determines number of calls before judging; submit neutral role labels and fixed rubric; persist both results before any stable conclusion.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_judge.py::test_direct_dispute_requires_reversed_order -q`; expect PASS.
- [x] **Nearby variants:** Run judge and integration files; add wrong-packet second call, reduced negative path, alternate configured judge with only one order, and provider failure between pair variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_judge.py tests/integration/test_phase7_slice.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): enforce neutral reversed order judging`.

### Task 16: Judge instability and optional heterogeneous escalation

**Files:** Modify `src/novelty_harness/adjudication/judge.py`, `src/novelty_harness/application/phase7_roles.py`; test `tests/unit/adjudication/test_judge.py`.

**Interfaces:** Define `NormalizedJudgeFinding` (target, accepted challenge IDs, decisive Phase 6 IDs and Gate C/D effects), `CounterbalanceComparison(comparison_id,dispute_id,assessment_id,context_id,snapshot_id,packet_id,argument_ids,evidence_digest,rubric_version,model_config_id,first_run_id,second_run_id,first_finding,second_finding,stability,materially_disputed_dimensions,resolution_if_stable: NormalizedJudgeFinding|None)` and `JudgeResolution(primary_comparison_id,alternate_comparison_id: str|None,resolved_semantics: NormalizedJudgeFinding|None,permitted_ceiling: VerdictState|None,unresolved_dimensions,limiting_factors)` in `adjudication/judge.py`. `compare_counterbalance(first: CounterbalanceRun, second: CounterbalanceRun) -> CounterbalanceComparison` verifies the same dispute, packet, evidence, rubric and model/config with opposite `(A,B)`/`(B,A)` order, retains both actual findings and normalizes harmless wording/list order. STABLE and MINOR_ORDER_VARIATION have one material `resolution_if_stable`; MATERIAL_ORDER_INSTABILITY has none. Persist each comparison as an immutable run artifact. `resolve_judge_comparisons(primary: CounterbalanceComparison, alternate: CounterbalanceComparison|None) -> JudgeResolution` validates the alternate pair's same dispute/context/packet/arguments/evidence/rubric and different configured model, then applies the rules below. For a HIGH_IMPACT dispute, alternate escalation invokes Task 15 twice under the same reversed-order protocol before building its comparison; a single third finding is never an input.

**Deterministic reconciliation:** (1) Materially stable primary alone uses its normalized resolution; no alternate is needed unless another approved trigger invokes one. (2) Materially unstable primary without an alternate remains unresolved: a negative-versus-positive or assessability flip is UNASSESSABLE, while a potential-versus-strong flip has a POTENTIALLY_NOVEL ceiling. (3) Both pairs materially unstable remain unresolved. (4) A materially stable alternate may resolve a materially unstable primary under the configured heterogeneous-escalation policy, retaining the primary instability as a recorded limitation. (5) Two materially stable pairs that disagree on a material dimension remain unresolved; agreeing pairs use the common resolution. (6) An alternate pair with invented/cross-context evidence fails validation and cannot resolve the primary; if an otherwise valid alternate is materially unstable, the invoked probes remain unresolved even when the primary was stable. Heterogeneous models are independent semantic probes, **not voters**: no two-of-three, majority, plurality, weighted-provider or preferred-provider rule grants authority.

- [x] **Failing tests:** `test_counterbalance_comparison_retains_both_findings_and_citations`, `test_judge_wording_variation_is_nonmaterial`, `test_different_decisive_citation_is_material`, `test_gate_or_assessability_flip_abstains`, `test_primary_stable_needs_no_heterogeneous_tiebreak`, `test_primary_unstable_without_alternate_remains_unresolved`, `test_alternate_high_impact_judge_is_also_counterbalanced`, `test_both_pairs_unstable_remain_unresolved`, `test_stable_alternate_can_resolve_order_unstable_primary`, `test_two_stable_models_that_materially_disagree_remain_unresolved`, `test_heterogeneous_majority_vote_is_not_supported`, `test_alternate_fabricated_citation_cannot_resolve_instability`.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_judge.py::test_two_stable_models_that_materially_disagree_remain_unresolved -q`; expect missing comparison/reconciliation contract.
- [x] **Minimal implementation:** Retain both findings in each comparison, validate exact pair identities and citations, normalize material outcomes, and reconcile comparison records under the six rules. The optional alternate `EvidenceJudgePort` can be scripted; it is never a paid-provider requirement or a tie-breaking vote.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_judge.py::test_two_stable_models_that_materially_disagree_remain_unresolved -q`; expect PASS.
- [x] **Nearby variants:** Run judge suite; add list reordering, Gate D flip, primary stable/alternate unstable, two stable agreeing pairs, alternate one-order-only and cross-context citation variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_judge.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): preserve material judge instability`.

### Task 17: Whole-assessment aggregation and frozen contract

**Files:** Modify `src/novelty_harness/adjudication/frozen.py`; test `tests/unit/adjudication/test_frozen.py`.

**Interfaces:** `compose_assessment(targets: tuple[TargetFinding,...], expected_targets: tuple[TargetRef,...]) -> OverallFinding`; `FrozenAdjudication` binds run/context/snapshot/case IDs, four gate IDs per target, role/rebuttal/gap/input-need/judge-run, counterbalance-comparison and judge-resolution IDs, stability and any heterogeneous reconciliation limitation, research/supersession history, exact Phase 6 basis refs, `NoveltySignificance`, separate `ValueMaturity` findings, permitted language classes and forbidden UNIVERSAL_ABSENCE/CERTAIN_NOVELTY. MIXED_CONTRIBUTION_SPECIFIC is overall-only.

- [x] **Failing tests:** `test_negative_mcu_plus_potential_combination_is_mixed`, `test_unassessable_target_is_not_dropped`, `test_incomplete_target_universe_has_no_unqualified_whole_verdict`, `test_whole_negative_requires_whole_configuration_target`.
- [x] **Red:** `uv run pytest tests/unit/adjudication/test_frozen.py -q`; expect missing composer/contract.
- [x] **Minimal implementation:** Compose by target meaning and coverage, never vote/source count/average; immutable frozen shape stores only references and structured findings, not a duplicate Phase 6 evidence store.
- [x] **Green:** `uv run pytest tests/unit/adjudication/test_frozen.py::test_negative_mcu_plus_potential_combination_is_mixed -q`; expect PASS.
- [x] **Nearby variants:** Run frozen/policy files; add all-same scoped verdict and value-versus-novelty variants.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication/test_frozen.py tests/unit/adjudication/test_policy.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): compose target findings without flattening`.

### Task 18: Atomic freeze transaction

**Files:** Modify `src/novelty_harness/adjudication/repository.py`, `src/novelty_harness/evidence/graph/phase7_store.py`, `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`; test `tests/unit/evidence/graph/test_phase7_store.py`, `tests/adversarial/test_phase7_authority_semantics.py`.

**Interfaces:** `freeze_phase7_adjudication(run_id: str, proposed: FrozenAdjudication) -> str` from Locked decisions. In one SQLite transaction reload context and Phase 6 view, validate packet/role/rebuttal/need/gap/judge runs, complete primary and optional alternate `CounterbalanceComparison`, `JudgeResolution`, gate/qualification dependencies and policy/rubric versions, recompute target verdicts and overall composition, then write frozen manifest plus exact dependency rows and terminal FROZEN or ABSTAINED transition. Reject a missing reversed-order pair, omitted candidate, single alternate finding or voted outcome. FAILED has no semantic freeze.

- [x] **Failing tests:** `test_freeze_rolls_back_on_missing_passage_or_relation`, `test_freeze_rejects_stale_context_or_policy`, `test_freeze_rejects_missing_high_impact_pair`, `test_freeze_rejects_alternate_single_call_or_voted_result`, `test_freeze_recomputes_verdict_permission`, `test_freeze_accepts_unassessable_without_operational_failure`.
- [x] **Red:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py -q -k freeze`; expect absent freezer.
- [x] **Minimal implementation:** Extract the existing Phase 6 assessment loader validation into an in-session helper without changing public semantics; use it and Phase 7 dependency/policy checks in the same SQLite transaction. Persist only after all joins pass; exact replay idempotent, same ID/different content rejected. Commit precedes semantic trace publication.
- [x] **Green:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py::test_freeze_recomputes_verdict_permission -q`; expect PASS.
- [x] **Nearby variants:** Run store and adversarial `-k freeze`; mutate/delete comparison membership, context, gate, second judge and qualification between proposal and freeze.
- [x] **Focused regression:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): freeze only repository validated adjudications`.

### Task 19: Authoritative frozen load and migration/reopen proof

**Files:** Modify `src/novelty_harness/evidence/graph/phase7_store.py`, `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`; test `tests/unit/evidence/graph/test_phase7_store.py`, `tests/adversarial/test_phase7_authority_semantics.py`.

**Interfaces:** `load_frozen_adjudication(assessment_id: AssessmentId, *, adjudication_id: str) -> FrozenAdjudication` from Locked decisions revalidates manifest and exact dependencies, current Phase 6 content/graph authority and policy output in one read transaction. No deserialized receipt/object or JSON export is accepted as authority.

- [x] **Failing tests:** `test_frozen_load_rejects_missing_dependency`, `test_frozen_load_rejects_revoked_phase6_graph_authority`, `test_v7_migration_does_not_authorize_fixture_adjudication`, `test_v8_reopen_and_exact_replay`; assert partial writes and foreign context fail closed.
- [x] **Red:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py -q -k 'load or migration'`; expect missing loader/authority check.
- [x] **Minimal implementation:** Load under one explicit SQLite read transaction using the in-session Phase 6 authority helper from Task 18; resolve every dependency and equality/hash check; expose an authority error, not a plausible downgraded verdict.
- [x] **Green:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py::test_frozen_load_rejects_missing_dependency -q`; expect PASS.
- [x] **Nearby variants:** Run store plus existing R10–R15 authority tests; add caller-copied frozen object and corrupted manifest-member row.
- [x] **Focused regression:** `uv run pytest tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): revalidate frozen adjudication on read`.

### Task 20: Real application slice and fixture boundary

**Files:** Create `src/novelty_harness/application/phase7.py`; modify `src/novelty_harness/application/models.py`, `src/novelty_harness/application/vertical_slice.py`, `src/novelty_harness/reporting/minimal.py`; test `tests/integration/test_phase7_slice.py`, `tests/integration/test_phase5_slice_with_phase6_evidence.py`.

**Interfaces:** Async `run_phase7(assessment_id: AssessmentId, *, context_id: str, repository: Phase7AdjudicationRepository, ports: Phase7Ports) -> FrozenAdjudication` loads the case, coordinates roles/escalation/judge/gates, builds the primary `CounterbalanceComparison` and an optional alternate reversed-order comparison, calls `resolve_judge_comparisons`, freezes, then reloads authority. A HIGH_IMPACT alternate never enters as a single third finding. Add an explicit real Phase 7 branch in the vertical slice and a typed result boundary; retain `Phase6FixtureAdjudicator` and `domain.adjudication.FrozenAdjudication` for earlier fixtures. `reporting/minimal.py` may show a labeled Phase 7 frozen summary/citation only; Phase 8 narrative remains deferred.

- [x] **Failing tests:** `test_real_phase7_slice_freezes_repository_result`, `test_real_phase7_slice_supports_direct_partial_and_combination`, `test_clear_direct_reduced_path_skips_unneeded_steps`, `test_positive_candidate_runs_material_gap_path`, `test_real_slice_reconciles_heterogeneous_pairs_without_vote`, `test_fixture_adjudication_cannot_masquerade_as_real_phase7`, `test_phase8_boundary_rejects_caller_created_frozen_shape`; preserve earlier slice assertions.
- [x] **Red:** `uv run pytest tests/integration/test_phase7_slice.py -q`; expect no real branch.
- [x] **Minimal implementation:** Capture typed upstream outputs at handoff, seal manifest/context, run Phase 7 on repository-loaded view, load frozen record for derived artifact/report; do not import fixture edges as authority.
- [x] **Green:** `uv run pytest tests/integration/test_phase7_slice.py::test_real_phase7_slice_freezes_repository_result -q`; expect PASS.
- [x] **Nearby variants:** Run both integration files and `tests/unit/test_minimal_report_compiler.py`; add missing historical upstream artifact, scoped partial and contradictory candidate variants.
- [x] **Focused regression:** `uv run pytest tests/integration/test_phase7_slice.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/unit/test_minimal_report_compiler.py -q`; expect PASS.
- [x] **Commit:** `feat(phase7): integrate real frozen adjudication into slice`.

### Task 21: Audit, architecture guard and requirement traceability

**Files:** Create `tests/unit/test_phase7_architecture_guards.py`, `docs/traceability/phase-7.yaml`; modify `src/novelty_harness/application/phase7.py`, `README.md`; test `tests/adversarial/test_phase7_authority_semantics.py`.

**Interfaces:** Phase 7 semantic trace events carry committed run/context/snapshot/artifact IDs, input/output hashes, prompt/rubric/provider versions, tokens/cost/latency and typed failure codes. Trace delivery follows commit and is retryable. Architecture guard bans provider SDKs in `adjudication/`, Phase 7 imports in Phase 6 evidence semantics, a real path through fixture `FrozenAdjudication`, and direct JSON/report authority.

- [x] **Failing tests:** `test_phase7_semantic_event_follows_commit`, `test_rejected_context_has_no_successful_verdict_trace`, `test_phase7_domain_has_no_provider_sdk_or_phase8_import`, `test_real_path_never_uses_fixture_authority`.
- [x] **Red:** `uv run pytest tests/unit/test_phase7_architecture_guards.py tests/adversarial/test_phase7_authority_semantics.py -q`; expect missing guards/events.
- [x] **Minimal implementation:** Add post-commit events and guard, then map design §§1–45 and master INV-01/02/03/05/06/07/09/11/12/13/14/15, FR-EQ-004, FR-ARC-001/002, FR-AUD-001/002, FR-SEC-001/002 and master §§31–37 to owning modules/tests in traceability; update README phase status without claiming acceptance.
- [x] **Green:** `uv run pytest tests/unit/test_phase7_architecture_guards.py::test_phase7_domain_has_no_provider_sdk_or_phase8_import -q`; expect PASS.
- [x] **Nearby variants:** Run architecture/adversarial tests; add trace-sink failure after freeze, retry replay and prompt-injection data variant.
- [x] **Focused regression:** `uv run pytest tests/unit/test_phase7_architecture_guards.py tests/adversarial/test_phase7_authority_semantics.py -q`; expect PASS.
- [x] **Commit:** `docs(phase7): trace authority and guard architecture`.

### Task 22: Bounded self-adversarial closeout and verification

**Files:** Test `tests/adversarial/test_phase7_authority_semantics.py`; modify only reproduced-defect owning files/tests; create `docs/phase-7-completion.md`; update `docs/traceability/phase-7.yaml` and `README.md` after exact verification. No external reviewer implementation edits.

**Interfaces:** No new runtime interface. Completion record names final commit, requirements, test files, exact commands/results, known limits, prompt/method versions and one independent review handoff.

- [x] **Failing test:** Add `test_full_slice_zero_yield_counterbalance_freeze_replay` in the adversarial file: an accepted zero-yield search changes budget/coverage, supersedes the old run, independently rebuilds both cases, requires A/B and B/A judging for a verdict-changing dispute, freezes and reloads only the successor result. Add `test_heterogeneous_majority_vote_cannot_upgrade_result`: a primary order-unstable pair and one alternate finding cannot be counted as two votes for a stronger result; a valid alternate must be a full pair and two materially disagreeing stable pairs remain unresolved. Attempt fresh variants for input clarification, research escalation, context forgery, role isolation, citations, rebuttal cap, instability, gates, value, mixed aggregation and frozen authority; every reproduced existing-invariant bug gets its own red regression.
- [x] **Red:** `uv run pytest tests/adversarial/test_phase7_authority_semantics.py::test_full_slice_zero_yield_counterbalance_freeze_replay tests/adversarial/test_phase7_authority_semantics.py::test_heterogeneous_majority_vote_cannot_upgrade_result -q`; confirm a missing cross-boundary behavior fails. If both already pass, record that observation rather than manufacture a failure; all earlier task gates still required a real red cycle.
- [x] **Minimal implementation:** Fix only reproduced Phase 7 defects and complete the integrated handoff, running each owning suite after a fix. Do not alter Phase 6 semantics to mask a Phase 7 defect.
- [x] **Green:** `uv run pytest tests/adversarial/test_phase7_authority_semantics.py::test_full_slice_zero_yield_counterbalance_freeze_replay tests/adversarial/test_phase7_authority_semantics.py::test_heterogeneous_majority_vote_cannot_upgrade_result -q`; expect PASS.
- [x] **Nearby variants:** Record the bounded cross-boundary attack results for all twelve listed areas, including candidate omission and an attempted heterogeneous majority vote; add red tests only for reproduced existing-invariant failures.
- [x] **Focused regression:** `uv run pytest tests/unit/adjudication tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py tests/integration/test_phase7_slice.py -q`; expect PASS. Then run `uv sync --dev`, the Phase 6 authority regressions, full slice, `uv run python scripts/verify.py`, and `git diff --check`; repeat full verification from a clean detached checkout at the exact final implementation commit. Record test counts and opt-in network exclusions.
- [x] **Commit:** `docs(phase7): record implementation and verification handoff` after all required checks. Keep the Phase 7 acceptance gate OPEN pending the single independent review; do not claim Phase 7 complete from implementer tests.

## Progressive verification and independent acceptance

Use exact test in each task → task component suite → `tests/unit/adjudication` and `tests/unit/evidence/graph/test_phase7_store.py` → Phase 6 authority and Phase 7 adversarial suites → real integration slice → full `scripts/verify.py`. No full 1,745+ test rerun after every edit. One bounded independent whole-phase semantic/authority acceptance review runs only after Task 22 is green; it checks evidence authority, input/research separation, one world-state and zero-yield restart, role independence, bounded rebuttal, explicit HIGH_IMPACT alternatives and counterbalance, primary/alternate comparison reconciliation without voting, Gates A–D, verdicts, qualifications, mixed targets, value separation and frozen read authority. Do not schedule repeated external reviews after individual tasks.

## Scope and execution handoff

Defer the Phase 8 nine-question compiler, Phase 9 live/full robustness, Phase 10 empirical calibration, novelty probabilities, scalar scores, legal patent opinions, polished UX and unrestricted model browsing. Current Phase 7 stores typed future hooks only. Recommend **Native/task-gated implementation** with aggressive local adversarial tests and one independent whole-phase review: the 22 tasks share context, artifact and repository identities, so handoffs between an implementer and a fresh subagent after every task add coupling cost without replacing the final independent acceptance review. Execution still requires user review and execution-method approval.

No design-critical ambiguity remains. The planning interpretation of the approved one-world-state rule is explicit: a changed Phase 3/4 manifest makes a successor Phase 7 context even if the Phase 6 snapshot ID is unchanged; unvalidated historical upstream state stays UNKNOWN at Gates A/B. This plan does not authorize implementation.

## Phase 7 acceptance gate

Phase 7 is accepted only when the accepted Phase 6 baseline and full repository verification still pass; Phase 6 remains sole prior-art authority; sealed context and exact packet identity hold; Gate A never dispatches research; Gate B/C and evidence-dependent D use typed Phases 3–6 escalation; changed zero-yield state supersedes and restarts while only a proven true no-op resumes; old artifacts cannot cross contexts; independent roles and one-rebuttal cap hold; fabricated citations fail closed; every material dispute carries exactly two validated bounded semantic alternatives or an unbounded marker, and a caller cannot omit an unfavorable one; the deterministic pre-judge consequence check treats any changed Gate C/D, verdict, assessability or language permission as HIGH_IMPACT and defaults unbounded space to HIGH_IMPACT; every HIGH_IMPACT dispute receives reversed-order judging; optional heterogeneous escalation for it also uses a full reversed-order pair, retains both comparison records and never uses a single third finding or majority vote; two internally stable but materially disagreeing models remain unresolved; material instability lowers permission or abstains; all four gates and deterministic claim-specific negative/potential permissions hold; missing information never creates novelty; weak research blocks strong positive; UNASSESSABLE differs from FAILED; MCU and combination findings remain distinct; value cannot alter novelty; production strong positive requires genuine validated robustness/domain records; caller-created frozen shapes cannot establish authority; the real slice uses the repository-frozen record; Phase 8 remains deferred; and **one bounded independent Phase 7 acceptance review passes**. Any failed criterion keeps Phase 8 blocked.
