# Phase 8 Full Report Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile a complete, traceable nine-question report from repository-authoritative Phase 6 evidence and accepted frozen Phase 7 findings, with bounded generative explanation and immutable report acceptance.

**Architecture:** Implement Bounded Generative Reporting: hierarchical planner, section writer, independent atomic extraction, deterministic firewalls, independent semantic verification, one local repair and deterministic fallback. A single verified ReportIR drives citations and all formats; additive report persistence on the existing SQLite engine validates exact upstream and execution dependencies transactionally.

**Tech Stack:** Python 3.12+, uv, frozen Pydantic v2 contracts, SQLAlchemy 2/SQLite, existing SemanticRunner/LLMProvider/ContextBlock, canonical hashing, TraceSink, pytest, Ruff and strict Pyright. Add PyYAML only when the YAML renderer is implemented.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-8-full-report-compiler-design.md`, explicitly approved at `64fcc933aa778cf4965aae79c0e7ba859e2dd718`. Accepted Phase 7 baseline: `d36f3b12b12ff8f0f13afd64ec09382d9e8ca066`; frozen Phase 6 baseline: `e4dd4e09699f755dd0fe7b7bc3dd8be4e11f7ee1`.

## Global Constraints

- **Deterministic where authority matters; generative where explanation benefits.** Phase 6 is sole verified prior-art authority; Phase 7 is sole verdict/Gate/permission authority. Phase 8 has substantial analytical freedom and no adjudicative authority.
- Read AGENTS.md, master specification, approved Phase 8 design, this plan and accepted Phase 7 handoff/review before execution. Historical FAIL/OPEN records remain preserved; Phase 7 is accepted and complete.
- Implementation requires separate user approval of this plan and execution method. This planning task creates only this document; no production, tests, dependencies, ADR or schema changes occur now.
- No search, retrieval, browser, research escalation, citation expansion, evidence reclassification, Gate mutation, qualification issuer, uncertainty resolution or assessed-value invention. No Phase 9/10 work, legal patent opinion, scalar novelty/confidence score, calibration, polished UX or external publication.
- Repository locators seed authority. Caller bundles, FrozenAdjudication shapes, ReportIR, JSON/Markdown exports, proposals and traces confer none. Input, acceptance and load each use one explicit SQLite transaction and the exact dependency closure.
- Preserve assessment/adjudication/context/snapshot/compilation and target identities. Never transplant content into a successor context or silently substitute the latest adjudication for an explicit locator.
- Reuse VerdictState, ValueMaturity, LanguagePermissionClass, TargetRef and exact CANONICAL_QUESTIONS. Q1–Q9 outer order is fixed. Inner hierarchy, emphasis, compatible synthesis and prospective recommendations are generative.
- All semantic proposals are strict, versioned, frozen Pydantic models with extra="forbid". Revalidate serialized content before authority use; canonical semantic IDs exclude observations; observations use timezone-aware UTC.
- Compare complete residuals: missing elements/relationships, control flow, unsupported remainder, contradiction, chronology/context and combination topology. Strong partial remains strong partial; multiple sources never establish one direct combination precedent.
- Every material public assertion, including headings/table cells/presuppositions, gets independent extraction and support/completeness verification. Mechanical IDs and lexical checks cannot prove arbitrary textual entailment. SUPPORTED/REJECTED/UNRESOLVED are the only verifier dispositions; UNRESOLVED is not acceptance.
- Mandatory obligations and material limitations cannot disappear under token/display limits. Express a conclusion's attached limitations beside it and in Q9. Limits select complete fallback rather than omission or weaker checking.
- Register approved methods/configurations before invocation. Actual request/response/proposal/instruction hashes, including recovery, are trusted runtime records; never select the last shared-runner audit or trust model provenance.
- Default dispatch: one plan, up to nine section writes, per-section extraction/verification and one composition check. Normal calls allow one schema-recovery invocation maximum; repair allows none. One local repair per stable origin cluster; no segmentation reset, best-of-N, voting, agent debate or global rewrite.
- Valid authority permits complete deterministic Q1–Q9 fallback with no configured semantic ports. Authority failure is a hard ReportAuthorityError with no accepted/exported downgrade. Provider failure cannot change epistemic findings.
- M1 remains deferred: do not populate Phase 7 value/significance arrays. CIR advantages, including labels claiming higher maturity, are attributed input; Gate D does not establish measured advantage. Assessed value requires a resolvable accepted value-validation basis, absent on the current path.
- Schema v9 adds exactly four report tables on the existing engine, with foreign keys enabled and no historical report backfill. No modification of Phase 6/7 semantic rows, frozen records or execution provenance. Reports never enter terminal Phase 7 artifact containers.
- Deterministic citations and Markdown/JSON/safe YAML/compact summary derive from one accepted IR. Only admitted stored URLs/identifiers may link externally; no fetching or guessed bibliography.
- Deterministic tests disable Internet sockets and use recorded/scripted ports. Exact RED → minimal implementation → exact GREEN → nearby variants → component regression → commit → task done; stop progression on any red gate. Unexpected pre-existing passes are recorded, not manufactured into failures.
- No full 2,000+ test run after every task. Full worktree and clean detached verification occur at closeout; implementer green does not establish independent Phase 8 acceptance.

## Review Focus

1. A fully cited paragraph omits its decisive limitation: independent completeness/support checking rejects it (`test_supported_claim_cannot_drop_material_limitation`, Task 10).
2. Compatible multi-source description becomes an established combination: accept the descriptive case, reject the stitched implication (`test_synthesis_does_not_establish_combination`, Task 10).
3. A schema-valid execution has the wrong actual recovery instruction or another shared-runner audit: reject it before acceptance (`test_execution_uses_matching_audit_and_instruction`, Task 12).
4. Every semantic port is absent/failing: complete safe Q1–Q9 with retained obligations/citations is still accepted (`test_all_semantic_ports_unavailable_produces_full_report`, Task 21).
5. A valid report is transplanted across target/context/source-version dependencies with consistently recomputed hashes: authoritative read fails (`test_canonical_dependency_transplant_fails_load`, Task 20).

---

## Repository inspection and file responsibilities (before task decomposition)

Inspected clean design HEAD `64fcc93` on `phase-8-full-report-design` in `/private/tmp/novcheck-phase7.WORKTREE`. The accepted 2,037 passed / 5 network exclusions is historical baseline evidence, not a Phase 8 result. Governing inputs include the master §§34–39.1, 44–47, 54–57, Phase 8 exit criteria and Appendix C; approved Phase 7 design/plan; completion; and `docs/reviews/phase-7-remediation-review.md`.

| Actual existing file | Responsibility and compatibility constraint |
| --- | --- |
| `src/novelty_harness/domain/reporting.py` | Exact nine questions; fixture ReportAnswers/CompiledReport and real derived Phase7FrozenSummary. Reuse constants, preserve types. |
| `src/novelty_harness/reporting/minimal.py` | Legacy fixture compilers and locator-loaded Phase 7 summary. Retain without conversion to real report authority. |
| `src/novelty_harness/adjudication/{context,frozen,repository,execution}.py` | Sealed input, real frozen findings, repository read contract and accepted provenance. Reuse typed records; no new verdict policy or qualification producer. |
| `src/novelty_harness/evidence/graph/{assessment_view,sqlalchemy_repository,phase7_store}.py` | Phase 6 read authority and existing Phase 7 frozen validation. `_load_phase6_assessment_in_session` already exists; expose unchanged frozen-load validation for a shared transaction. |
| `src/novelty_harness/evidence/graph/{sqlalchemy_models,phase7_models,migrations}.py` | Shared Base, v8 rows and current schema=8. Existing migrations use create_all and version metadata; preserve legacy unsafe-migration guards. |
| `src/novelty_harness/evidence/normalization/models.py` | Actual SourceRecord/SourceVersionRecord. Resolve through `comparison.comparison.chain.source`/`.version`, not assumed graph-node metadata. |
| `src/novelty_harness/runtime/semantic/structured.py`, `src/novelty_harness/ports/{llm,models}.py` | Stateless strict output calls and actual SemanticCallAudit. Use actual call audit selection and separate trusted/untrusted ContextBlock data. |
| `src/novelty_harness/runtime/{artifacts/writer,tracing/hashing,tracing/models,tracing/sinks}.py` | Atomic replace exports, canonical IDs, trace delivery. Exports overwrite and cannot implement immutable acceptance. |
| `src/novelty_harness/application/{models,vertical_slice,phase7,phase7_model_adapter,phase7_execution}.py` | Existing real/fixture branch, accepted adjudication and trusted invocation pattern. Separate report attempt after frozen result; preserve summary-only operation. |
| `tests/unit/test_{import_boundaries,phase1_architecture_guards,phase5_architecture_guards,phase6_architecture_guards,phase7_architecture_guards}.py` | Existing import/SQL allowlists. Add narrowly scoped reporting/read/hash/YAML/store allowances with new guards; do not weaken existing provider/semantic bans. |
| `docs/traceability/phase-7.yaml`, `docs/phase-7-completion.md` | Existing requirement mapping and acceptance history. Add Phase 8 records, preserve Phase 7 history. |
| `docs/architecture/decisions/ADR-039-phase7-semantic-execution-provenance.md` | Highest current ADR. Reserve ADR-040 for report citations/acceptance; preserve ADR-010 (Phase 2 grounding). |

All following paths are exact; brace groups expand to individually named files. Existing reporting package initialization stays in place. New production files have these owners:

| New file under `src/novelty_harness/` | Single responsibility |
| --- | --- |
| `reporting/models.py` | Scope, native authority refs/dependencies, options, lens/detail/limits and shared report enums. |
| `reporting/bundle.py` | ReportInputBundle and source/authority/language projections. |
| `reporting/obligations.py` | CoverageObligation derivation and satisfaction joins. |
| `reporting/plan.py` | PlannerContext, QuestionPlan, proposals, validated plan and Plan Firewall. |
| `reporting/drafts.py` | SectionContext/SectionDraft/DraftBlock and complete bounded display closure. |
| `reporting/claims.py` | ReportClaim, ClaimBasisLink, extraction and span/block accounting. |
| `reporting/firewall.py` | Deterministic claim validation and typed rejection records. |
| `reporting/verification.py` | ClaimVerification/batch/completeness/composition contracts and result validation. |
| `reporting/repair.py` | Stable RepairCluster lineage and one-attempt eligibility. |
| `reporting/fallback.py` | Versioned deterministic sections and exact recomputation. |
| `reporting/value.py` | ValueProjection and assessed-value availability. |
| `reporting/recommendations.py` | Prospective ValidationRequirement validation and minimum requirements. |
| `reporting/wording.py` | ClaimWording tied to target language envelopes. |
| `reporting/uncertainty.py` | Actual UncertaintyItem/coverage projections and adjacency/Q9 requirements. |
| `reporting/citations.py` | ReportCitation/CitationRegistry, exact ancestry and inert link resolution. |
| `reporting/ir.py` | Accepted blocks, canonical ReportIR, CompiledAssessmentReport, deterministic summary. |
| `reporting/rendering.py` | Canonical JSON, safe YAML, Markdown and rendition parity. |
| `reporting/prompts.py`, `reporting/execution.py` | Versioned trusted instructions; immutable approved method/config/execution contracts and registry joins, respectively. |
| `reporting/artifacts.py` | ReportCompilationRecord, append-only statuses, discriminated ReportArtifact and identity functions. |
| `reporting/repository.py` | Six-method ReportRepository Protocol and ReportAuthorityError; no SQL. |
| `ports/reporting.py` | Four stateless semantic protocols and optional ReportPorts bundle. |
| `application/phase8_model_adapter.py`, `application/phase8_execution.py` | SemanticRunner adapters; actual invocation/configuration envelope attachment, respectively. |
| `application/phase8_sections.py` | Section write/extract/check/verify/repair/fallback orchestration. |
| `application/phase8.py` | Compilation orchestration over repository locators. |
| `application/phase8_exports.py`, `application/phase8_tracing.py` | Loaded report exports; post-commit trace projection/retry, respectively. |
| `evidence/graph/report_models.py` | Four v9 ORM tables on existing Base. |
| `evidence/graph/report_input.py` | In-session upstream bundle loading and semantic dependency resolution. |
| `evidence/graph/report_store.py` | Attempt/artifact transactions and report acceptance/load delegation. |
| `evidence/graph/report_validation.py` | Shared acceptance/read closure validation; no live semantic calls. |

Tests are created during execution only: `tests/fixtures/phase8.py`; `tests/unit/reporting/test_{contracts,bundle,obligations,attempts,plan,execution,drafts,claims,firewall,verification,recommendations,wording,value,uncertainty,fallback,repair,composition,citations,ir,rendering}.py`; `tests/unit/evidence/graph/test_report_store.py`; `tests/contract/test_report_ports.py`; `tests/integration/test_phase8_{compiler,slice}.py`; `tests/adversarial/test_phase8_authority_semantics.py`; `tests/unit/test_phase8_architecture_guards.py`; `tests/golden/test_phase8_reports.py` and `tests/golden/phase8/` deterministic JSON/Markdown/YAML fixtures. No production imports test helpers.

Documentation during execution: `docs/architecture/decisions/ADR-040-phase8-citations-and-report-acceptance.md`, `docs/traceability/phase-8.yaml`, `docs/phase-8-completion.md`, `README.md`. No unrelated refactor or design rewrite.

## Locked contracts, signatures and persistence decisions

Contract field locks inherit design §§6–18, 21–23; every scoped contract has `scope: ReportScope`, and every attempt artifact has `compilation_id: str`. Model proposals cannot include trusted execution certification. Native evidence/target IDs retain upstream types. NonBlankText is reused where appropriate. Every new contract kind is `phase8-<hyphenated-contract-name>-v1`; typed authority discriminators use their native names, not a second verdict enum.

- `ReportScope`: assessment_id: AssessmentId, adjudication_id: str, assessment_context_id: str, phase6_snapshot_id: str. `AuthorityRef`: kind, native_id, digest, scope, target: TargetRef|None, path: tuple[str|int,...]. Kinds: FROZEN, CONTEXT, INPUT_MANIFEST, CIR, GRAPH, TARGET, TARGET_FINDING, OVERALL_FINDING, GATE, QUALIFICATION, COUNTERFACTUAL, ROLE, REBUTTAL, JUDGE_RUN, JUDGE_COMPARISON, JUDGE_RESOLUTION, INPUT_NEED, RESEARCH_GAP, SUPERSESSION, RESEARCH_STATE, COVERAGE, CANDIDATE, COMPARISON, COMMIT, GRAPH_RELATION, PASSAGE, SOURCE, SOURCE_VERSION, LINEAGE, VALUE_BASIS. ID-less fields use parent native ID plus exact path. Paths cannot select arbitrary uncited document text.
- `ReportDependency`: dependency_kind: UPSTREAM|REPORT_ARTIFACT, dependency_id, expected_digest, authority_ref: AuthorityRef|None, report_artifact_id: str|None. Upstream dependency ID hashes kind/native_id/path/scope so multiple fields of one record do not collide; local dependency ID equals artifact ID and resolves its FK. Exactly one reference arm is populated.
- `QuestionId` is Literal[1,2,3,4,5,6,7,8,9]; `ReportSemanticRole` is PLANNER|WRITER|EXTRACTOR|VERIFIER|COMPOSITION|REPAIR. `ReportMethodRegistration` binds scope/compilation/role/version/instruction hash and approved registry identity.
- `ReportOptions`: lens: ReportLens=RESEARCH, detail: SHORT|STANDARD|DETAILED=STANDARD, compact_summary: bool=False, limits: ReportGenerationLimits, render_policy_version="p8-render-v1". Lens values: RESEARCH, PRODUCT, ENGINEERING, SOFTWARE, PROCESS, PATENT_SCREENING. No override/search parameters.
- Operational defaults: max_calls=96, max_tokens=100000, max_cost_usd=None, max_context_chars=80000, max_question_chars=24000, max_blocks_per_question=32, max_subsections_per_question=8, max_hierarchy_depth=2, max_repairs_total=9. Per-origin repair maximum is always 1. These bound generation, not fallback/export completeness or evidence permission; configured tighter limits select fallback. Provider/model selection and optional monetary cap are configuration, not a live-price assumption.
- `ReportInputBundle` fields are exactly design §7 (including full frozen/context/view projections and source metadata), with typed tuples/maps rather than arbitrary evidence JSON. `LanguageEnvelope` binds target kind/id/claim scope, exact verdict/permitted classes, required limitations and their authority refs. `CoverageObligation` binds obligation ID, question IDs, target scope, refs, requirement kind and materiality origin. Source metadata keeps source/version objects with comparison refs, missing fields and conflicting observations. SOURCE/SOURCE_VERSION AuthorityRef paths include their committed comparison identity when metadata observations differ; retain the native source/version ID, distinguish the observation paths, and rejoin content authority separately. Two admitted metadata observations cannot collide as one dependency or replace each other.
- `ReportPlanProposal`: scope, compilation_id, bundle_digest, questions: tuple[QuestionPlan,...]. QuestionPlan and subsection fields follow design §8. `ReportPlan` adds validation links through trusted code; no model-supplied validated flag. Question IDs are Literal[1,2,3,4,5,6,7,8,9]. All nine exact labels resolve from CANONICAL_QUESTIONS.
- `DraftBlock`: block_id, kind: HEADING|PARAGRAPH|LIST_ITEM|TABLE_CELL|CAPTION, text, typed inline style/citation tokens, basis_candidate_refs, obligation_ids; plain text only. SectionDraft adds question_id and ordered blocks. SectionContext binds validated plan/question, full selected basis closure, all target/overall constraints, limits, lens and an explicit omission manifest. Structural limits do not authorize dropping omitted decisive material.
- `ReportClaim`: claim_id, block_id, block_text_digest, spans: tuple[TextSpan,...] (half-open Unicode code-point offsets), normalized_assertion, category, use, target refs/claim scopes, basis_candidates, citation_candidates, required_qualification_refs. ClaimBasisLink links claim to exact AuthorityRef and proposition/use. Extraction adds block accounting; it cannot attach an authoritative complete=true flag.
- Categories: INPUT_DESCRIPTION, SOURCE_FACT, EQUIVALENCE_DESCRIPTION, NOVELTY_INTERPRETATION, NEGATIVE_CLAIM, POTENTIAL_NOVELTY_CLAIM, VALUE_CLAIM, COVERAGE_CLAIM, UNCERTAINTY_CLAIM, VALIDATION_RECOMMENDATION. ClaimUse: ASSERTION, ATTRIBUTED_INPUT_CLAIM, RECOMMENDATION, DISALLOWED_WORDING_EXAMPLE.
- `ClaimVerification`: claim_id, text_digest, basis_digest, permission_digest, disposition: SUPPORTED|REJECTED|UNRESOLVED, unmet_qualification_refs, reason_codes, reason, basis_refs. Trusted wrapper attaches execution reference separately. ClaimVerificationBatch also has one completeness/limitation disposition per public block. Every claim/block disposition is required exactly once. CompositionCheck binds full narrative/claim/envelope digests and implicated blocks/questions or indeterminate scope.
- `RepairCluster`: cluster_id, origin_id, question_id, original_block_ids, original_spans, claim_ids, obligation_ids, reason_codes. Origin derives from original draft identity and original interval; overlapping failures merge before dispatch. Replacement segmentation stays linked to that origin. SectionDraftFragment can replace only cluster-owned blocks.
- `ValueProjection`: AUTHORITATIVE_VALUE_FINDING (requires existing value-validation basis), ATTRIBUTED_INPUT_CLAIM or NO_VALUE_ASSESSMENT; maturity optional only for genuinely assessed findings. `ValidationRequirement` and `ClaimWording` use design §§16–17 exact fields and uses; UncertaintyItem uses design §17 fields and all original IDs. UNKNOWN availability is not ValueMaturity.
- `ReportIR` uses design §18 exact fields. AcceptedBlock contains draft block, accepted claims/basis/verification/obligation links, origin GENERATIVE_ACCEPTED|GENERATIVE_REPAIRED|DETERMINISTIC_FALLBACK and source artifact refs. `CompiledAssessmentReport` binds report_id, compilation_id, scope, ReportIR, exact dependencies, approved versions/config/execution refs and accepted_at UTC.
- `ReportCompilationRecord`: immutable scope, compilation_id, compilation_key, attempt_token, options, configuration, bundle_digest, started_at UTC. State is derived from append-only ReportStatusEvent artifacts, not an updated header. Status events have event_id, predecessor_id, expected_state, next_state, reason and observation. STARTED→PLANNED→DRAFTED→VERIFIED→ACCEPTED, or FAILED from a nonterminal state. Fallback completes those same stages. ACCEPTED is created only by acceptance.
- `ReportArtifact`: artifact_id, scope, compilation_id, kind, question_id|None, cluster_origin_id|None, method_version, execution_ref|None, typed document. Discriminated kinds: METHOD, CONFIGURATION, EXECUTION, PLAN_PROPOSAL, PLAN, DRAFT, EXTRACTION, FIREWALL, VERIFICATION, REPAIR, FALLBACK, COMPOSITION, STATUS. Each task extends the closed typed document union when its contract is introduced; no arbitrary JsonValue artifact acceptance. Invalid/rejected provider payloads belong to a typed execution-failure record with redacted audit data, never an evidence basis.

Public repository methods in `reporting/repository.py`, implemented by existing SqlAlchemyEvidenceGraphRepository delegating to report helpers:

```python
class ReportRepository(Protocol):
    def load_report_input_bundle(self, assessment_id: AssessmentId, *, adjudication_id: str) -> ReportInputBundle: ...
    def begin_report_compilation(self, assessment_id: AssessmentId, *, adjudication_id: str,
                                 options: ReportOptions, configuration: ReportCompilationConfiguration,
                                 attempt_token: str | None = None) -> ReportCompilationRecord: ...
    def record_report_artifact(self, compilation_id: str, artifact: ReportArtifact) -> str: ...
    def load_report_artifacts(self, compilation_id: str) -> tuple[ReportArtifact, ...]: ...
    def accept_compiled_report(self, compilation_id: str, proposed: CompiledAssessmentReport) -> str: ...
    def load_compiled_report(self, assessment_id: AssessmentId, *, report_id: str) -> CompiledAssessmentReport: ...
```

ReportPorts is a frozen dataclass with optional planner/writer/extractor/verifier and optional trace_sink; no repository/search capability. Each semantic port exposes a read-only `configuration: ReportPortConfiguration` identifying actual implementation/model/mode. The application validates it against its selected invocation; scripted ports are PORT_PROTOCOL, absent slots NOT_CONFIGURED. The configured main path is generative; no ports selects full fallback.

```python
class ReportPlannerPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def plan(self, context: PlannerContext, options: ReportOptions) -> ReportPlanProposal: ...

class SectionWriterPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def write(self, context: SectionContext) -> SectionDraft: ...
    async def repair(self, context: LocalRepairContext) -> SectionDraftFragment: ...

class ReportClaimExtractorPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def extract(self, context: ClaimExtractionContext) -> ClaimExtractionProposal: ...

class ReportClaimVerifierPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def verify(self, context: ClaimVerificationContext) -> ClaimVerificationBatch: ...
    async def check_composition(self, context: CompositionContext) -> CompositionCheck: ...

async def compile_assessment_report(assessment_id: AssessmentId, *, adjudication_id: str,
                                    repository: ReportRepository, ports: ReportPorts | None = None,
                                    options: ReportOptions,
                                    attempt_token: str | None = None) -> CompiledAssessmentReport: ...
```

Version registry: semantic `p8-plan-v1`, `p8-write-v1`, `p8-extract-v1`, `p8-verify-v1`, `p8-compose-check-v1`, `p8-repair-v1`; deterministic `p8-plan-firewall-v1`, `p8-semantic-firewall-v1`, `p8-fallback-v1`, `p8-citations-v1`, `p8-render-v1`, `p8-summary-v1`, `p8-lens-v1`, `p8-bundle-v1`, `p8-obligations-v1`. Immutable approved instruction hashes include separately registered schema-recovery variants and the actual trusted instruction delivered in ContextBlock, including the SemanticRunner isolation suffix; recovery is not relabeling. Tests compare the selected provider-visible trusted block, not a proposal label or unrelated audit. Supported versions are explicitly registered; changing default does not invalidate a supported older report; withdrawn/unknown/mismatched versions fail closed.

ReportPortConfiguration binds actual mode, provider/port implementation, model and sampling/structured settings. ReportRoleConfiguration adds the invocation role, approved method/version/instruction hash and scoped configuration ID; repair/composition get separate method bindings to their writer/verifier port configuration. ReportCompilationConfiguration binds selected role configurations and deterministic policy versions. ReportExecutionRecord binds invocation_id, role/task/version, actual instruction hash, configuration ID, request/raw-response/validated-proposal hashes, outcome, recovery/predecessor refs and separate token/cost/latency UTC observations. No trusted=true proposal field. Store actual completed divergent/rejected calls relevant to provenance.

Identity functions in `reporting/artifacts.py`: `compilation_key(scope: ReportScope, bundle_digest: str, options: ReportOptions, configuration: ReportCompilationConfiguration) -> str`; `compilation_id(key: str, attempt_token: str) -> str`; `report_artifact_id(artifact: ReportArtifact) -> str`. In `reporting/ir.py`: `report_id(report: CompiledAssessmentReport) -> str`. Prefixes p8key_, p8run_, p8report_, p8artifact_ and specialized p8plan_/p8draft_/p8claim_/p8verify_; include realized text/execution content, exclude IDs themselves and observations (not source publication dates). Exact replay compares canonical semantic content and preserves original observations; caller changes to semantic content fail.

### Exact four-table schema v9

Use String(512) identity columns, Text canonical `document_json`, String(64) kind/state columns, as in current graph/phase7_models.py. No additional status/execution table.

| Table | Columns and joins |
| --- | --- |
| report_compilations | compilation_id PK; compilation_key, attempt_token, assessment_id, adjudication_id FK phase7_frozen_manifests, context_id, snapshot_id, bundle_digest, options_digest, configuration_digest, document_json; UNIQUE(compilation_key,attempt_token) and UNIQUE(compilation_id,assessment_id,adjudication_id,context_id,snapshot_id). Semantic checks join all scope columns to the frozen manifest. |
| report_artifacts | artifact_id PK; compilation_id FK; assessment_id, adjudication_id, context_id, snapshot_id with composite FK to report_compilations scope; kind, nullable question_id, cluster_origin_id, nullable execution_artifact_id self-FK, document_json. Executions/config/method refs join within the same compilation and registered role; STATUS predecessor is typed and joined in document validation. |
| compiled_reports | report_id PK; compilation_id unique FK; assessment_id, adjudication_id FK, context_id, snapshot_id, bundle_digest, ir_digest, document_json, accepted_at. Composite scope FK to report_compilations. Revalidate exact adjudication identity semantically. |
| report_dependencies | report_id FK plus dependency_kind plus dependency_id composite PK; expected_digest; nullable upstream_kind/native_id/path_json/scope_json; nullable report_artifact_id FK report_artifacts; document_json. Enforce one valid typed arm, local ID equality and same-compilation join. Upstream paths resolve exact typed records; FKs alone confer no semantics. |

## Stages and test-fixture discipline

24 ordered task gates: I contracts/authority (1–5); II planning/writing (6–7); III claim assurance and runtime ports (8–12); IV failure-safe reporting (13–15); V canonical report/authority (16–20); VI integration/closeout (21–24). Complete each task's commit before advancing. Artifact document unions grow only through a task's strict contracts; acceptance/load are intentionally unavailable until Tasks 19–20.

Test assertion excerpts below are requirements to create during execution, not tests created by this planning task. Each task prepares the named fixtures/inputs it uses. Task 1 creates `tests/fixtures/phase8.py` strict shape factories; Task 3 adds `ReportCase(repository, frozen, bundle)` scenarios built via real Phase 6 commits/context/Phase 7 ports/freeze/load. Use existing `tests/unit/adjudication/test_context.py` snapshot/manifest patterns and `tests/integration/test_phase7_slice.py` recorded role/judge patterns; keep older tests unchanged except current-schema compatibility metadata explicitly owned by Task 2. Helpers may be reused inside tests, never in production. Scenario names DIRECT, PARTIAL_NEGATIVE, POTENTIAL, MIXED, UNASSESSABLE, LIMITED, BUDGET_STOPPED, PROVIDER_BLOCKED and NO_NEW_YIELD identify actual committed facts; no fabricated FrozenAdjudication establishes fixture repository authority.

Every task below specifies its primary named test and additional named cases. Create all cases first, execute the primary exact RED, then implement. Code excerpts give key assertions; import/setup/fixture construction belongs in the specified test file. Expected GREEN means all assertions pass with zero Internet calls. For every commit, stage only that task's listed files (expand brace groups) and run `git diff --cached --check` before the specified commit message; update this plan's checkboxes/task outcome ledger as planning-associated documentation during execution.

### Task 1: Strict report scope, options, identities and attempt vocabulary

**Files:** Create `src/novelty_harness/reporting/{models,artifacts,execution,prompts}.py`, `tests/fixtures/phase8.py`, `tests/unit/reporting/test_contracts.py`. Modify `tests/unit/test_phase1_architecture_guards.py` for exact new report contract dependencies; preserve the existing minimal.py exceptions.

**Interfaces:** Produce ReportScope, AuthorityRef, ReportDependency, ReportMethodRegistration, ReportOptions/ReportGenerationLimits, ReportLens, QuestionId, ReportSemanticRole, ReportPortConfiguration/ReportRoleConfiguration/ReportCompilationConfiguration, ReportExecutionRecord, ReportCompilationRecord, ReportStatusEvent, ReportArtifactKind and the initial typed ReportArtifact (METHOD/CONFIGURATION/EXECUTION/STATUS). Implement the three identity functions locked above. Consumes ContractModel, AssessmentId, TargetRef, canonical_hash/canonical_json; permit only their exact read/hash imports in report contracts.

- [x] **RED — write `test_report_contracts_are_strict_scoped_and_distinct` and the named cases below.** Assert forbidden extra/certification/score/search fields, all required scope IDs, immutable defaults, valid UTC observations, duplicate native refs and foreign target scope rejected. Add `test_observation_does_not_change_compilation_identity`, `test_options_have_operational_not_epistemic_limits`; canonical options/config changes must change key while observations do not. Fixtures generate shapes only, clearly distinct from authority.

```python
with pytest.raises(ValidationError):
    ReportOptions.model_validate({"novelty_override": "STRONG_EVIDENCE_OF_NOVELTY"})
assert ReportScope.model_config["frozen"] is True
assert set(ReportLens) == expected_six_lenses
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_contracts.py::test_report_contracts_are_strict_scoped_and_distinct -q`. Expect failure because strict scope/options contracts and identity functions are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Strict scope/options contracts and identity functions are absent; add local shape checks and hash projections without repository semantics. Add a narrow read-contract/hash allowlist for new reporting files, with reporting→application/provider/network imports still rejected. Define the immutable approved version/instruction registry in execution/prompts now so attempt primitives can reject unknown methods; actual invocation/audit validation belongs to Task 12.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_contracts.py::test_report_contracts_are_strict_scoped_and_distinct -q`; expect PASS.
- [x] **Nearby variants:** Add `test_dependency_paths_do_not_collide` for two CIR fields under the same native ID, and `test_semantic_options_change_compilation_key` for lens/model/render version versus UTC/cost observations. Run the contracts file.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_contracts.py tests/unit/test_phase1_domain_contracts.py tests/unit/test_phase1_architecture_guards.py tests/unit/test_import_boundaries.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): define scoped report contracts and identities"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 2: Additive schema v9 migration

**Files:** Create `src/novelty_harness/evidence/graph/report_models.py`, `tests/unit/evidence/graph/test_report_store.py`. Modify `src/novelty_harness/evidence/graph/migrations.py`, `tests/unit/test_phase5_architecture_guards.py`; update current-version expectations only in `tests/unit/evidence/graph/{test_sqlalchemy_repository,test_phase7_store}.py` and `tests/adversarial/{test_phase6_r15_assessment_authority,test_phase6_r13_commit_receipt_authority,test_phase6_sol_review_regressions,test_phase6_contract_consolidation}.py` where they assert current v8.

**Interfaces:** Produce the four locked ORM rows using existing Base, `SCHEMA_VERSION=9`; retain `ensure_schema(engine: Engine) -> int` and `schema_version(engine: Engine) -> int|None`. Register report_models before create_all; no change to graph/phase7 table definitions.

- [x] **RED — write `test_v8_migrates_to_empty_v9_preserving_authority` and the named cases below.** Build a genuine v8 database (report tables absent, version=8), retaining validated Phase 6/7 rows. Assert empty four-table migration, identical upstream canonical rows, loadable frozen record, enabled FK pragma. Add `test_v9_initialization_reopen_and_migration_rollback`, `test_v9_refuses_newer_and_unsafe_legacy_schema`; inject a failure before version commit and require recoverable unchanged version/no invented report authority.

```python
assert ensure_schema(repository.engine) == 9
assert report_table_names == {"report_compilations", "report_artifacts", "compiled_reports", "report_dependencies"}
assert phase6_phase7_rows_after == phase6_phase7_rows_before
assert all(count == 0 for count in report_row_counts)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/evidence/graph/test_report_store.py::test_v8_migrates_to_empty_v9_preserving_authority -q`. Expect failure because four report tables and schema v9 are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Four report tables and schema v9 are absent; register additive rows and extend supported migration metadata. Preserve all unsafe legacy checks. Make report-table creation and version advancement atomic for the v8 migration using explicit SQLite transaction handling; no historical backfill. Narrow SQL import allowlist to graph/report_models.py, report_input.py, report_store.py and report_validation.py only. Updating a current-schema assertion never removes a graph-authority assertion.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/evidence/graph/test_report_store.py::test_v8_migrates_to_empty_v9_preserving_authority -q`; expect PASS.
- [x] **Nearby variants:** Add `test_v9_fk_rejects_foreign_report_scope`, `test_migration_never_backfills_fixture_report`. Rollback/reopen both empty and populated v8 stores; retain v7→empty Phase 7 migration semantics even though current version becomes 9. Also run the existing exact controls: `uv run pytest tests/adversarial/test_phase6_r13_commit_receipt_authority.py::test_v4_semantic_rows_need_replay_to_gain_a_v7_commit_manifest tests/adversarial/test_phase6_sol_review_regressions.py::test_f07_schema_v1_migrates_to_v3 tests/adversarial/test_phase6_contract_consolidation.py::test_schema_v3_metadata_graph_migrates_and_unsafe_phase6_is_blocked -q`; expect PASS with only the current-version expectation updated to 9.
- [x] **Focused regression:** `uv run pytest tests/unit/evidence/graph/test_report_store.py tests/unit/evidence/graph/test_sqlalchemy_repository.py tests/unit/evidence/graph/test_phase7_store.py tests/unit/test_phase5_architecture_guards.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): add isolated schema v9 report tables"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 3: One-transaction authoritative ReportInputBundle

**Files:** Create `src/novelty_harness/reporting/{bundle,repository,obligations,value,uncertainty}.py` (projection shapes only for the last three), `src/novelty_harness/evidence/graph/report_input.py`, `tests/unit/reporting/test_bundle.py`. Modify `src/novelty_harness/evidence/graph/{phase7_store,sqlalchemy_repository}.py`, `tests/fixtures/phase8.py`, `tests/unit/evidence/graph/test_report_store.py`.

**Interfaces:** Produce ReportInputBundle, LanguageEnvelope, source metadata projections, CoverageObligation/ValueProjection/UncertaintyItem shapes; ReportAuthorityError; initial ReportRepository.load_report_input_bundle signature. Add `load_frozen_adjudication_in_session(session: Session, load_view_in_session: Callable[..., Phase6AssessmentView], assessment_id: AssessmentId, *, adjudication_id: str) -> FrozenAdjudication` retaining every existing frozen-load check. Public Phase 7 loader delegates under its same BEGIN/commit. Add `load_report_input_bundle_in_session(session: Session, load_view_in_session: Callable[..., Phase6AssessmentView], assessment_id: AssessmentId, *, adjudication_id: str) -> ReportInputBundle` in report_input; public repository loader opens explicit BEGIN, calls it and commits. No sequence of independent public loads.

- [x] **RED — write `test_bundle_revalidates_one_exact_authority_closure` and the named cases below.** Use real frozen fixtures, not deserialized exports. Assert exact cutoff/CIR/graph/target/scope/digest/dependencies; source/version records equal committed chain records, all cited attestation ancestry retained, semantic-only/nonrelational distinctions preserved. Add `test_bundle_refuses_export_or_caller_frozen_shape`, `test_bundle_source_metadata_preserves_conflicting_observations`, `test_bundle_keeps_complete_residual_and_decisive_closure`.

```python
assert bundle.scope.adjudication_id == frozen.adjudication_id
assert bundle.frozen_adjudication == frozen
assert observed_explicit_read_transactions == 1
assert tuple(p.target_id for p in bundle.target_profiles) == tuple(p.target_id for p in repository_phase6_targets)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_bundle.py::test_bundle_revalidates_one_exact_authority_closure -q`. Expect failure because report bundle loader and shared frozen read entry are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Report bundle loader and shared frozen read entry are absent; extract only existing load transaction-independent checks, preserving Phase 6 loader/Phase 7 validator semantics. Join sealed context and exact Phase 6 view in the same session, resolve all needed typed records, derive bundle projection and typed catalog. This gate proves the complete upstream authority projection; Task 4 supplies obligation/value/uncertainty derivation before report attempts or generative use are enabled in Task 5. Do not present the intermediate bundle as a completed Phase 8 product. Wrap failed upstream authority as ReportAuthorityError, never fallback.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_bundle.py::test_bundle_revalidates_one_exact_authority_closure -q`; expect PASS.
- [x] **Nearby variants:** Add `test_bundle_foreign_target_or_snapshot_fails`, `test_bundle_missing_gate_judge_or_passage_fails` and `test_bundle_semantic_only_never_creates_relation`. Inject a dependency change between reads and assert the loader holds one consistent transaction; compare extracted upstream validation behavior with existing load regression.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_bundle.py tests/unit/evidence/graph/test_report_store.py tests/unit/evidence/graph/test_phase7_store.py tests/integration/test_phase6_assessment_parity.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): load report inputs from transactional authority"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 4: Mandatory coverage, target envelopes, M1 and actual uncertainty

**Files:** Modify `src/novelty_harness/reporting/{bundle,obligations,value,uncertainty}.py`, `src/novelty_harness/evidence/graph/report_input.py`. Create `tests/unit/reporting/{test_obligations,test_value,test_uncertainty}.py`.

**Interfaces:** Produce `derive_coverage_obligations(bundle: ReportInputBundle) -> tuple[CoverageObligation,...]`, `project_value(bundle: ReportInputBundle) -> tuple[ValueProjection,...]`, `project_uncertainty(bundle: ReportInputBundle) -> tuple[UncertaintyItem,...]`, `derive_language_envelopes(bundle: ReportInputBundle) -> tuple[LanguageEnvelope,...]`. Bundle construction finalizes these projections before computing bundle_digest; pure functions confer no authority. All computed projection fields are excluded from their own derivation input/digest recursion.

- [x] **RED — write `test_obligations_preserve_every_target_and_material_limit` and the named cases below.** Assert decisive precedent, scoped negative, survivor/residual, accepted challenge, language ceiling, mixed/UNASSESSABLE target, coverage/stop/access and all Gate/judge/overall limitations have mechanical obligations. Add `test_cir_high_maturity_is_attributed_not_assessed_value`, `test_empty_value_and_significance_use_retained_gate_d_only`, `test_uncertainty_preserves_budget_no_yield_provider_and_ancestor_scope`.

```python
assert expected_target_ids == obligated_target_ids
assert all(limit_has_local_and_q9_obligations(limit) for limit in frozen_limits)
assert "MISSING_ASSESSED_VALUE" in obligation_kinds
assert potential_envelope.permitted_classes != negative_envelope.permitted_classes
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_obligations.py::test_obligations_preserve_every_target_and_material_limit -q`. Expect failure because complete mandatory coverage/value/uncertainty derivation is absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Complete mandatory coverage/value/uncertainty derivation is absent; derive IDs from scoped AuthorityRef records, retain native IDs when grouping, mark ancestor records history only. Treat CIR-only value entry as attributed even if frozen/CIR label says DEMONSTRATED; require resolvable VALUE_BASIS for assessed maturity, with no new issuer. Gate D contributes only its accepted resolved semantics; unresolved dependencies remain unresolved. Complete current coverage matrix remains machine-readable.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_obligations.py::test_obligations_preserve_every_target_and_material_limit -q`; expect PASS.
- [x] **Nearby variants:** Add `test_display_limit_cannot_drop_obligation`, `test_overall_permission_union_does_not_authorize_each_target`, `test_high_value_direct_stays_negative_in_projection` and `test_missing_value_target_binding_stays_assessment_scoped`.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_bundle.py tests/unit/reporting/test_obligations.py tests/unit/reporting/test_value.py tests/unit/reporting/test_uncertainty.py tests/unit/adjudication/test_policy.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): derive mandatory reporting obligations and envelopes"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 5: Durable report attempt, artifacts and exact retry

**Files:** Create `src/novelty_harness/evidence/graph/report_store.py`, `tests/unit/reporting/test_attempts.py`. Modify `src/novelty_harness/reporting/{artifacts,repository}.py`, `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`, `tests/unit/evidence/graph/test_report_store.py`.

**Interfaces:** Extend ReportRepository with the locked begin/record/load_artifacts methods. Produce `make_report_artifact(compilation: ReportCompilationRecord, kind: ReportArtifactKind, document: ReportArtifactDocument, *, method_version: str, execution_ref: str|None=None) -> ReportArtifact` in artifacts.py. ReportArtifactDocument is the closed discriminated union extended by later contract tasks. Beginning reloads bundle and validates approved configuration, allocates token if absent, commits header plus STARTED status. Load derives state from status chain.

- [x] **RED — write `test_exact_attempt_replays_without_duplicate_or_foreign_artifact` and the named cases below.** Assert same adjudication/config/options/token exact replay; new token regeneration; semantic options change distinct key; immutable original observations; same-ID/different-content failure; foreign context/target/execution/unknown artifact kind rejected. Add `test_status_chain_rejects_skip_fork_and_terminal_append` and `test_begin_rollback_leaves_no_partial_attempt`.

```python
assert retry.compilation_id == first.compilation_id
assert retry.attempt_token == first.attempt_token
assert repository.record_report_artifact(first.compilation_id, artifact) == artifact.artifact_id
with pytest.raises(ReportAuthorityError):
    repository.record_report_artifact(other.compilation_id, artifact)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_attempts.py::test_exact_attempt_replays_without_duplicate_or_foreign_artifact -q`. Expect failure because report attempt and artifact primitives are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Report attempt and artifact primitives are absent; use BEGIN IMMEDIATE writes, serialized strict revalidation, exact canonical scope/document joins and predecessor checks. No report-authority creation by artifact writes. Exact replay may read an existing terminal artifact, but no new semantic/status artifact can append to ACCEPTED/FAILED. STATUS advances require completed committed stage records; later Tasks 6–17 add their exact required record sets.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_attempts.py::test_exact_attempt_replays_without_duplicate_or_foreign_artifact -q`; expect PASS.
- [x] **Nearby variants:** Add `test_attempt_reopen_keeps_committed_output`, `test_wrong_bundle_digest_cannot_seed_begin`, `test_unknown_registration_hash_rejected` (valid known methods from approved constants), `test_artifact_provenance_not_supplied_by_trace`.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_attempts.py tests/unit/reporting/test_contracts.py tests/unit/evidence/graph/test_report_store.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): persist append only report attempts and artifacts"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 6: Hierarchical plan contracts and deterministic Plan Firewall

**Files:** Create `src/novelty_harness/reporting/plan.py`, `tests/unit/reporting/test_plan.py`. Modify `src/novelty_harness/reporting/{models,artifacts}.py` for ReportProposalError, PLAN_PROPOSAL/PLAN typed documents and stage requirements.

**Interfaces:** Produce PlannerContext, QuestionPlan/SubsectionPlan, ReportPlanProposal/ReportPlan and `validate_report_plan(proposal: ReportPlanProposal, bundle: ReportInputBundle, options: ReportOptions) -> ReportPlan`; `build_planner_context(bundle: ReportInputBundle, compilation: ReportCompilationRecord) -> PlannerContext`; `build_coverage_plan(bundle: ReportInputBundle, compilation: ReportCompilationRecord) -> ReportPlan` for fallback. Validated plans are created only by code; no trusted proposal flag.

- [x] **RED — write `test_planner_cannot_omit_decisive_precedent_or_limitation` and the named cases below.** Add `test_plan_keeps_q1_to_q9_and_generative_inner_hierarchy`, `test_plan_rejects_hidden_only_obligation_or_foreign_basis`, `test_plan_rejects_gate_research_value_or_scope_override`. Define ReportProposalError(ValueError) in models.py for untrusted proposal rejection distinct from repository authority failure. Duplicate subsection IDs, depth/size and disallowed typed question intent fail.

```python
with pytest.raises(ReportProposalError):
    validate_report_plan(incomplete_proposal, bundle, options)
fallback_plan = build_coverage_plan(bundle, compilation)
assert obligation_ids(fallback_plan) == obligation_ids(bundle)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_plan.py::test_planner_cannot_omit_decisive_precedent_or_limitation -q`. Expect failure because plan firewall and deterministic coverage plan are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Plan Firewall and deterministic coverage plan are absent; bind scope/bundle/question order, eligible IDs and complete comparison limitations, ensure visible obligation homes and exact envelope intents. Reject structural authority escapes; natural-language thesis remains untrusted and receives extraction/verification when displayed. Invalid plan is durably retained as rejected proposal, then one coverage plan is used without planner debate.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_plan.py::test_planner_cannot_omit_decisive_precedent_or_limitation -q`; expect PASS.
- [x] **Nearby variants:** Add `test_plan_heading_semantics_are_not_self_certified`, `test_q3_cannot_promote_partial_to_direct`, `test_q4_unassessable_has_no_positive_intent`; permute outer questions versus inner grouping to prove the boundary.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_plan.py tests/unit/reporting/test_obligations.py tests/unit/reporting/test_attempts.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): validate generative plans against mandatory coverage"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 7: Complete writer contexts, drafts, neutral data and lenses

**Files:** Create `src/novelty_harness/reporting/{drafts,repair}.py` (repair shapes), `tests/unit/reporting/test_drafts.py`. Modify `src/novelty_harness/reporting/artifacts.py` for DRAFT/REPAIR shapes.

**Interfaces:** Produce SectionContext, DraftBlock, SectionDraft, SectionDraftFragment, RepairCluster/LocalRepairContext shapes; `build_section_context(bundle: ReportInputBundle, plan: ReportPlan, *, question_id: QuestionId, compilation: ReportCompilationRecord) -> SectionContext`; `validate_section_draft(draft: SectionDraft, context: SectionContext) -> SectionDraft`; `lens_instruction(lens: ReportLens) -> str` in drafts.py, pinned p8-lens-v1. If closure exceeds configured display limit, return context marked requires_fallback with complete obligation/omission IDs; never dispatch a truncated decisive closure.

- [x] **RED — write `test_writer_context_retains_complete_residual_and_global_scope` and the named cases below.** Assert full comparison closure, topology/direction, contradictions, chronology/context/unsupported remainder; same global scope in every question. Add `test_context_limit_requires_fallback_instead_of_decisive_omission`, `test_lenses_change_presentation_only`, `test_heading_table_and_citation_tokens_are_structured`. All six lenses have useful presentation/Q7 emphasis without added source facts or legal authority.

```python
assert residual_authority_refs <= displayed_or_fallback_refs(context)
assert context.language_envelopes == bundle.language_envelopes
assert not hasattr(context, "repository")
with pytest.raises(ValidationError):
    SectionDraft.model_validate(draft_with_url_or_gate_override)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_drafts.py::test_writer_context_retains_complete_residual_and_global_scope -q`. Expect failure because complete section context and strict draft contracts are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Complete section context and strict draft contracts are absent; project validated plan plus complete selected authority, plain text/styles/typed citation tokens, bounded structures and explicit omissions. Material content cannot become decisive from omissions. Repair shape fixes local ownership and read-only neighboring window without implementing dispatch yet.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_drafts.py::test_writer_context_retains_complete_residual_and_global_scope -q`; expect PASS.
- [x] **Nearby variants:** Add `test_uncertain_chronology_display_not_earlier_precedent`, `test_terminology_difference_does_not_change_frozen_equivalence`, `test_patent_lens_cannot_stitch_sources`. Compare source-specific metadata variations and all lens scope fields.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_drafts.py tests/unit/reporting/test_plan.py tests/unit/reporting/test_contracts.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): project complete bounded section contexts"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 8: Independent claim extraction contracts and text accounting

**Files:** Create `src/novelty_harness/reporting/claims.py`, `tests/unit/reporting/test_claims.py`. Modify `src/novelty_harness/reporting/artifacts.py` for EXTRACTION typed records.

**Interfaces:** Produce TextSpan, ReportClaim, ClaimBasisLink, ClaimExtractionContext/ClaimExtractionProposal; `build_claim_extraction_context(draft: SectionDraft, context: SectionContext) -> ClaimExtractionContext`; `validate_claim_extraction(draft: SectionDraft, proposal: ClaimExtractionProposal) -> ClaimExtractionProposal`. Consume exact DraftBlock text; no writer-private reasoning or privileged support result.

- [x] **RED — write `test_extraction_accounts_actual_text_including_heading_and_table` and the named cases below.** Prepare a heading, two table cells, composite causal sentence, list, caption and absence presupposition. Assert exact half-open Unicode spans/text digests, native basis candidates, categories/use, unique claims and complete public block accounting. Add `test_empty_extraction_does_not_self_certify_safe_draft`, `test_extractor_hints_do_not_certify_material_completeness`; semantic completeness belongs to Task 10, code does not pretend to infer all assertions.

```python
assert accounted_block_ids == public_block_ids(draft)
assert all(draft_text[c.span.start:c.span.end] == c.exact_text for c in extracted_span_views)
with pytest.raises(ReportProposalError):
    validate_claim_extraction(draft, extraction_for_other_text)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_claims.py::test_extraction_accounts_actual_text_including_heading_and_table -q`. Expect failure because atomic extraction shapes and mechanical text accounting are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Atomic extraction shapes and mechanical text accounting are absent; validate actual text boundaries/digests and explicit per-block accounts. Composite material clauses have separate proposed claims, candidates remain hints. Empty claim lists with nonmaterial block accounts still require independent semantic completeness, never automatic acceptance.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_claims.py::test_extraction_accounts_actual_text_including_heading_and_table -q`; expect PASS.
- [x] **Nearby variants:** Add `test_unicode_spans_and_duplicate_claims_fail_closed`, `test_stale_block_digest_after_repair_rejected`, `test_disallowed_example_tag_not_an_authority_grant`. Test swapped cells and hidden heading assertion with seemingly complete writer annotations.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_claims.py tests/unit/reporting/test_drafts.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): account independently extracted claims against public text"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 9: Deterministic Semantic Firewall

**Files:** Create `src/novelty_harness/reporting/firewall.py`, `tests/unit/reporting/test_firewall.py`. Modify `src/novelty_harness/reporting/artifacts.py` for FIREWALL records.

**Interfaces:** Produce typed FirewallResult/FirewallViolation with accepted flag, claim/block/scope/ref digests and reason codes; `check_report_claims(draft: SectionDraft, extraction: ClaimExtractionProposal, bundle: ReportInputBundle, plan: ReportPlan) -> FirewallResult`. Consume validated extraction/envelopes/authority index; no LLM, confidence or final-verdict input.

- [x] **RED — write `test_real_citation_wrong_proposition_or_target_fails_firewall` and the named cases below.** Assert exact scope/span/digest/native basis/commitment/citation ancestry, target-permission/question-use and qualifier obligations. Add `test_firewall_rejects_structured_verdict_gate_and_value_override`, `test_firewall_rejects_source_stitch_and_universal_absence_intents`, `test_firewall_rejects_free_url_and_metadata_only_passage_basis`. A genuine same-target passage with unsupported natural-language assertion continues to semantic verification; membership alone never accepts.

```python
result = check_report_claims(draft, rebound_extraction, bundle, plan)
assert result.accepted is False
assert "BASIS_SCOPE_MISMATCH" in result.reason_codes
assert bundle.target_findings == original_target_findings
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_firewall.py::test_real_citation_wrong_proposition_or_target_fails_firewall -q`. Expect failure because deterministic claim firewall is absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Deterministic claim firewall is absent; return typed rejection records for failed joins, structural overclaims, known unsafe constructs and missing obligation links. Do not assign semantic entailment from source title, matching words or IDs. Verification cannot override mechanical rejection.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_firewall.py::test_real_citation_wrong_proposition_or_target_fails_firewall -q`; expect PASS.
- [x] **Nearby variants:** Add `test_overall_classes_do_not_authorize_foreign_target`, `test_right_title_wrong_version_fails`, `test_supported_score_cannot_override_rejection`; scope changes, unversioned records and unsafe javascript:/data: tokens fail without lookup.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_firewall.py tests/unit/reporting/test_claims.py tests/unit/reporting/test_obligations.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): enforce deterministic claim and citation permissions"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 10: Independent semantic verification and completeness contracts

**Files:** Create `src/novelty_harness/reporting/verification.py`, `tests/unit/reporting/test_verification.py`, `tests/unit/reporting/test_composition.py` (composition shape tests). Modify `src/novelty_harness/reporting/artifacts.py` for VERIFICATION/COMPOSITION records.

**Interfaces:** Produce ClaimVerificationContext/ClaimVerification/ClaimVerificationBatch, BlockCompleteness, CompositionContext/CompositionCheck; `build_claim_verification_context(draft: SectionDraft, extraction: ClaimExtractionProposal, bundle: ReportInputBundle, plan: ReportPlan) -> ClaimVerificationContext`; `validate_verification_batch(context: ClaimVerificationContext, batch: ClaimVerificationBatch, firewall: FirewallResult) -> ClaimVerificationBatch`. Checks result completeness/digests, not model entailment quality. Actual semantic calls arrive in Task 12.

- [x] **RED — write `test_supported_claim_cannot_drop_material_limitation` and the named cases below.** Use scripted semantic cases representing faithful/rejected meaning, including a real basis with omitted decisive qualifier. Require SUPPORTED only with qualifier already in public text and independent block completeness. Add `test_synthesis_does_not_establish_combination` (accept X/Y individually established plus accepted R survivor; reject X+Y established), `test_hidden_heading_table_presupposition_rejects_incomplete_extraction`, `test_verifier_cannot_supply_gate_verdict_or_qualification`, `test_unresolved_is_not_acceptance`, `test_verifier_supported_cannot_override_firewall`.

```python
assert scripted_semantic_batch.dispositions[0].disposition == "REJECTED"
assert "MISSING_MATERIAL_LIMITATION" in scripted_semantic_batch.dispositions[0].reason_codes
with pytest.raises(ReportProposalError):
    validate_verification_batch(context, incomplete_batch, firewall)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_verification.py::test_supported_claim_cannot_drop_material_limitation -q`. Expect failure because verification contracts and strict result validator are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Verification contracts and strict result validator are absent; include original text/surroundings and full compatible/contradictory/residual basis/envelope/obligations. Require every claim and public block exactly once and exact checked digests. No self-certification from extraction/annotations, confidence, majority or disposition on unrelated text. Scripted cases prove routing and envelope validation, not live semantic accuracy.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_verification.py::test_supported_claim_cannot_drop_material_limitation -q`; expect PASS.
- [x] **Nearby variants:** Add `test_semantic_paraphrases_do_not_escape_scope` parameterized for strong partial→direct, not-found→does-not-exist, scoped negative→whole-project, potential→definite, significance→demonstrated value. Add `test_example_or_recommendation_tag_cannot_hide_assertion` and `test_shared_model_has_no_writer_certification_context`.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_verification.py tests/unit/reporting/test_firewall.py tests/unit/reporting/test_claims.py tests/unit/reporting/test_composition.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): validate independent semantic support and completeness"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 11: Q7 prospective requirements and Q8 defensible wording

**Files:** Create `src/novelty_harness/reporting/{recommendations,wording}.py`, `tests/unit/reporting/{test_recommendations,test_wording}.py`. Modify `src/novelty_harness/reporting/{firewall,verification}.py` for typed recommendation/wording checks.

**Interfaces:** Produce ValidationRequirement and ClaimWording; `validate_validation_requirement(proposal: ValidationRequirement, bundle: ReportInputBundle) -> ValidationRequirement`; `minimum_validation_requirements(bundle: ReportInputBundle) -> tuple[ValidationRequirement,...]`; `validate_claim_wording(wording: ClaimWording, bundle: ReportInputBundle) -> ClaimWording`; `safe_claim_wording(bundle: ReportInputBundle) -> tuple[ClaimWording,...]`. Consume target-specific LanguageEnvelope, attributed advantages, exact counterfactual/gap/input refs.

- [x] **RED — write `test_useful_prospective_ablation_is_not_an_experiment_result` and the named cases below.** Accept a basis-linked ablation with admitted comparator, proposed latency/reliability measurements and a numeric proposed criterion explicitly labeled a choice to justify. Reject fabricated existing measurements, benchmark facts, comparator capabilities, performed research or resolved user meaning (embedded text through semantic check). Add `test_q8_respects_per_target_ceiling_and_unsupported_examples`, `test_valid_whole_configuration_wording_requires_frozen_whole_target`, `test_unassessable_wording_never_becomes_novelty`.

```python
assert validated.status == "RECOMMENDATION"
assert validated.basis_refs == accepted_target_basis
with pytest.raises(ValidationError):
    ValidationRequirement.model_validate(proposal_with_observed_result)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_recommendations.py::test_useful_prospective_ablation_is_not_an_experiment_result -q`. Expect failure because prospective requirement and wording validators are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Prospective requirement and wording validators are absent; bind exact refs/status/target/no observed result fields. Recommendations may use generic experimental concepts without fake bibliography; named external comparators must be admitted records. Generate minimum fallback needs and exact scoped wording, not new value/novelty decisions. Example/recommendation discourse still receives full semantic meaning checking when generative.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_recommendations.py::test_useful_prospective_ablation_is_not_an_experiment_result -q`; expect PASS.
- [x] **Nearby variants:** Add `test_q7_cannot_invent_comparator_capability`, `test_q8_union_class_cannot_be_rebound`, `test_q8_universal_absence_example_requires_visible_label`. Test missing user topology remains clarification, Q7 control-flow tests remain prospective and the patent lens remains nonlegal.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_recommendations.py tests/unit/reporting/test_wording.py tests/unit/reporting/test_verification.py tests/unit/reporting/test_value.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): bind recommendations and wording to accepted scope"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 12: Provider-neutral ports, registered prompts and actual execution provenance

**Files:** Create `src/novelty_harness/ports/reporting.py`, `src/novelty_harness/application/{phase8_model_adapter,phase8_execution}.py`, `tests/unit/reporting/test_execution.py`, `tests/contract/test_report_ports.py`. Modify `src/novelty_harness/reporting/{execution,artifacts,prompts}.py`, `src/novelty_harness/evidence/graph/report_store.py`.

**Interfaces:** Implement all six locked async operations over four protocols/ReportPorts. Produce ReportModelAdapter using existing SemanticRunner; read-only configuration and `execution_for(proposal: ContractModel) -> ReportExecutionRecord`. Produce `invocation_configuration(port: object, role: ReportSemanticRole, compilation: ReportCompilationRecord) -> ReportRoleConfiguration`; `completed_invocation(port: object, proposal: ContractModel, configuration: ReportRoleConfiguration, request: JsonValue) -> ReportExecutionRecord` in phase8_execution.py. Approved registry/instructions live in reporting execution/prompts; application registers before invoking. Store joins METHOD/CONFIGURATION/EXECUTION and proposal hashes on writes, not traces.

- [x] **RED — write `test_execution_uses_matching_audit_and_instruction` and the named cases below.** Use a shared runner interleaving two actual requests and one recovery. Assert own audit selected by task/request identity, raw-response hash distinct from parsed-proposal hash, actual method/config/instruction/provider/implementation retained. Add `test_model_provenance_fields_are_forbidden`, `test_stale_prompt_hash_rejected_on_record`, `test_roles_are_fresh_invocations_with_untrusted_draft_and_evidence`, `test_normal_schema_recovery_once_repair_never_recovers`, `test_protocol_ports_never_claim_llm_execution`. Shared provider contract tests validate context/metadata without live network.

```python
assert execution.request_hash == selected_call.request_hash
assert execution.actual_instruction_hash == canonical_hash(actual_recovery_instruction)
assert execution.validated_proposal_hash == canonical_hash(parsed_proposal)
assert execution.request_hash != unrelated_last_audit.request_hash
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_execution.py::test_execution_uses_matching_audit_and_instruction -q`. Expect failure because ports, prompts and report adapter execution joins are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Ports, prompts and report adapter execution joins are absent; implement bounded strict calls with separated trusted instructions/untrusted data and separately registered recovery hashes. Capture each actual invocation audit, including INVALID/PROVIDER_FAILURE outcomes before fallback; no shared conversation, writer-private reasoning or arbitrary trusted flag. Repair permits one semantic invocation only. If concurrency cannot select audits unambiguously, isolate runners per invocation rather than accept ambiguous provenance.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_execution.py::test_execution_uses_matching_audit_and_instruction -q`; expect PASS.
- [x] **Nearby variants:** Add `test_completed_divergent_retry_output_cannot_be_hidden`, `test_missing_port_records_not_configured_without_fake_execution`, `test_foreign_configuration_and_withdrawn_method_fail`. Provider failure retries have finite explicit transport limits and never best-of-N acceptance. Run all role operations through shared contract assertions.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_execution.py tests/contract/test_report_ports.py tests/contract/test_mock_provider_contracts.py tests/unit/runtime/test_structured_semantic_calls.py tests/unit/adjudication/test_execution_provenance.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): register bounded semantic calls and actual provenance"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 13: Complete offline deterministic fallback

**Files:** Create `src/novelty_harness/reporting/fallback.py`, `tests/unit/reporting/test_fallback.py`, `tests/golden/test_phase8_reports.py`, `tests/golden/phase8/` fixtures. Modify `src/novelty_harness/reporting/{verification,artifacts}.py` to add VerifiedSection/FallbackRecord shapes and FALLBACK artifacts.

**Interfaces:** Produce VerifiedSection (draft, claims, basis_links, verification_refs, obligation_satisfaction, per-block origins, source_artifact_refs), FallbackRecord; `render_fallback_section(bundle: ReportInputBundle, compilation: ReportCompilationRecord, *, question_id: QuestionId, obligation_ids: tuple[str,...]|None=None) -> VerifiedSection`; `validate_fallback_section(section: VerifiedSection, bundle: ReportInputBundle, compilation: ReportCompilationRecord) -> None`. Renderer pinned p8-fallback-v1. Local fallback retains original obligations; optional obligation_ids can select only a complete local unit, otherwise render full question.

- [x] **RED — write `test_fallback_alone_answers_all_nine_questions_without_inventing_value` and the named cases below.** Offline fixture goldens for DIRECT, PARTIAL_NEGATIVE, POTENTIAL, MIXED, UNASSESSABLE and M1. Assert exact local negative/candidate/unassessable wording, complete residuals, accepted challenges, real chronology/coverage/uncertainty, Q7 prospective needs, Q8 permissions and Q9 actual state. Add `test_fallback_label_does_not_authorize_arbitrary_text`, `test_raw_upstream_prose_is_escaped_and_attributed`, `test_fallback_unresolved_counterfactual_remains_unresolved`.

```python
assert tuple(s.draft.question_id for s in fallback_sections) == tuple(range(1, 10))
assert satisfied_obligation_ids(fallback_sections) == obligation_ids(bundle)
assert assessed_value_availability(fallback_sections[5]) == "NO_VALUE_ASSESSMENT"
assert rendered_target_findings == bundle.target_findings
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_fallback.py::test_fallback_alone_answers_all_nine_questions_without_inventing_value -q`. Expect failure because complete fallback renderer and exact recomputation are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Complete fallback renderer and exact recomputation are absent; use known enum/scope transformations and attributed escaped upstream prose, never inferred facts/assessed value. Deterministic claims/basis/obligation links record transformations; no successful semantic model is required. Acceptance/load later recompute text/structure/bases/origins exactly from bundle+renderer. Storage/export capacity is separate from model draft/context budget.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_fallback.py::test_fallback_alone_answers_all_nine_questions_without_inventing_value -q`; expect PASS.
- [x] **Nearby variants:** Add `test_fallback_handles_zero_generation_budget`, `test_fallback_citation_like_source_text_is_inert`, `test_fallback_partial_negative_lists_independent_relationship_residual`. Assert unsafe HTML, fake headings/verifier instructions, javascript/data URLs cannot escape attributed text. Do not update goldens merely to silence a failed semantic obligation.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_fallback.py tests/unit/reporting/test_value.py tests/unit/reporting/test_uncertainty.py tests/unit/reporting/test_recommendations.py tests/unit/reporting/test_wording.py tests/golden/test_phase8_reports.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): render complete permission safe deterministic fallback"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 13 outcome:** Primary RED: absent `reporting.fallback` (1 failed, 20.15s). Complete deterministic Q1–Q9 renderer, exact fallback artifact store/load recomputation, retained native residuals/challenges/concessions, M1 high-label attribution, prospective Q7 and scoped Q8, actual Q9 states and six recorded scenario goldens implemented. Final focused regression (the six planned suites plus Phase 1 architecture guards): **71 passed, 247.77s**; scoped Ruff check/format PASS and targeted strict Pyright zero errors. Known deterministic transformations require no semantic provider. Repository acceptance and compilation remain later gates. Owning obligation satisfaction shape was introduced now for strict VerifiedSection typing; owning store/fixture/guard extensions and bounded golden hash/UTC normalization are recorded in the execution ledger. Native publication/cutoff dates and realized report retrieval dates remain retained.

### Task 14: One local repair with immutable origin and section assurance

**Files:** Create `src/novelty_harness/application/phase8_sections.py`, `tests/unit/reporting/test_repair.py`. Modify `src/novelty_harness/reporting/{repair,verification,artifacts}.py` and `tests/unit/reporting/test_execution.py`.

**Interfaces:** Produce `select_repair_clusters(draft: SectionDraft, violations: tuple[ReportViolation,...]) -> tuple[RepairCluster,...]`, `validate_repair_fragment(fragment: SectionDraftFragment, cluster: RepairCluster, context: LocalRepairContext) -> SectionDraftFragment`, `repair_available(cluster: RepairCluster, artifacts: tuple[ReportArtifact,...]) -> bool`. ReportViolation is the normalized claim/block/span/obligation reason view of firewall and verification failures, defined in repair.py. Async `assure_report_section(compilation: ReportCompilationRecord, context: SectionContext, *, bundle: ReportInputBundle, plan: ReportPlan, ports: ReportPorts, repository: ReportRepository) -> VerifiedSection` in phase8_sections.py drives write→extract→firewall→verify→local repair/fallback.

- [x] **RED — write `test_resegmentation_cannot_reset_one_repair_origin` and the named cases below.** Write rejected local text, split its replacement into different blocks, reject again: no second repair or schema recovery and retained obligations via fallback. Add `test_overlapping_rejections_merge_before_repair`, `test_repair_cannot_edit_neighbors_or_drop_limits`, `test_repair_reextracts_and_reverifies_actual_replacement`, `test_missing_extractor_or_verifier_never_accepts_generative_text`.

```python
assert repair_calls_for_origin == 1
assert rewritten_segmentation_origin == original_cluster.origin_id
assert unsafe_after_repair.origin == "DETERMINISTIC_FALLBACK"
assert neighboring_blocks_after == neighboring_blocks_before
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_repair.py::test_resegmentation_cannot_reset_one_repair_origin -q`. Expect failure because origin-bound one-repair accounting and section assurance are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Origin-bound one-repair accounting and section assurance are absent; merge original intervals before dispatch and persist ownership/attempt events before calling repair. Never expand its authority context, reset by new block IDs or retry semantic repair. Fresh extraction/firewall/verification binds replacement text. Invalid/unavailable providers choose local/question fallback and preserve rejected drafts/executions. Aggregate max_repairs_total is an operational bound, not another per-cluster allowance.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_repair.py::test_resegmentation_cannot_reset_one_repair_origin -q`; expect PASS.
- [x] **Nearby variants:** Add `test_transport_retry_cannot_double_semantic_repair`, `test_malformed_repair_goes_directly_to_fallback`, `test_repair_attempt_committed_before_crash_resumes_to_fallback`, `test_independent_verifier_rejects_writer_self_certification`. If a process dies after consuming a repair but before durable response, resume to fallback; do not claim another semantic attempt.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_repair.py tests/unit/reporting/test_execution.py tests/unit/reporting/test_verification.py tests/unit/reporting/test_fallback.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): bound local repair and assure independent sections"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 14 outcome:** Original RED: missing `repair_available` (1 failed /18.45s). Primary GREEN: 1 passed /155.90s. Persisted replacement-origin reset was reproduced (1 failed /163.46s) and fixed (1 passed /147.43s) by joining consumed origins to the original writer draft and committed failure receipts. Fresh focused gate: `uv run pytest tests/unit/reporting/test_repair.py tests/unit/reporting/test_execution.py tests/unit/reporting/test_verification.py tests/unit/reporting/test_fallback.py -q` — 90 passed /1112.73s. The earlier gate (89 passed, 1 failed /1047.64s) exposed a test attempt-token reuse; distinct attempts restored all three failure-response cases (3 passed /274.22s), without a production change for that setup failure. Actual failed model repair remains one invocation with retained execution and no recovery (1 passed /83.89s). Architecture/import controls: 31 passed /1.41s. Targeted Ruff/format PASS and production Pyright zero errors. Owning store and exact hash guard extensions are included for repair consumption/fragment/derived-draft joins; no upstream semantic write, new table, or report acceptance. Commit and post-commit gate are recorded in the execution ledger.

### Task 15: Composition implications and final mandatory coverage

**Files:** Modify `src/novelty_harness/reporting/{verification,obligations,fallback}.py`, `src/novelty_harness/application/phase8_sections.py`, `tests/unit/reporting/test_composition.py`.

**Interfaces:** Produce ObligationSatisfaction(scope, compilation_id, obligation_id, question_id, block_ids, claim_ids, basis_refs, verification_refs, fallback_transformation_ref: str|None) and `build_composition_context(sections: tuple[VerifiedSection,...], bundle: ReportInputBundle, compilation: ReportCompilationRecord) -> CompositionContext`; `validate_composition_check(context: CompositionContext, check: CompositionCheck) -> CompositionCheck`; `check_report_coverage(sections: tuple[VerifiedSection,...], bundle: ReportInputBundle) -> tuple[ObligationSatisfaction,...]` in obligations.py. Async `assure_report_composition(compilation: ReportCompilationRecord, sections: tuple[VerifiedSection,...], *, bundle: ReportInputBundle, ports: ReportPorts, repository: ReportRepository) -> tuple[VerifiedSection,...]` uses at most one normal composition check plus its one schema recovery.

- [x] **RED — write `test_cross_section_stronger_whole_implication_uses_fallback_not_rewrite` and the named cases below.** Compose individually supported target facts into an implied whole-project negative/positive via heading or pronoun scope. Script composition rejection; affected question(s) fallback, not new repair or global rewrite. Add `test_composition_unknown_scope_replaces_full_report`, `test_missing_local_limitation_even_when_q9_has_it_rejected`, `test_unavailable_composition_verifier_forces_complete_safe_fallback`. Unseen obligation IDs do not count as expressed content.

```python
assert composition_calls == 1
assert generative_global_rewrites == 0
assert implicated_question_origin == "DETERMINISTIC_FALLBACK"
assert satisfied_obligation_ids(final_sections) == obligation_ids(bundle)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_composition.py::test_cross_section_stronger_whole_implication_uses_fallback_not_rewrite -q`. Expect failure because composition validation and final coverage joins are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Composition validation and final coverage joins are absent; validate exact assembled public text/claim/envelope digests and implicated scope. Require all questions/targets/material limits locally plus Q9. If global checking is unavailable or localization uncertain, fallback all affected content, up to full report. Mechanically validate final recomputed fallback; no second global semantic loop.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_composition.py::test_cross_section_stronger_whole_implication_uses_fallback_not_rewrite -q`; expect PASS.
- [x] **Nearby variants:** Add `test_unassessable_target_not_lost_in_composition`, `test_summary_like_heading_has_no_extra_permission`, `test_cross_question_value_implies_novelty_rejected`. Verify localized safe sections survive repair-free composition replacement.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_composition.py tests/unit/reporting/test_repair.py tests/unit/reporting/test_obligations.py tests/unit/reporting/test_fallback.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): validate composition without global generative rewrites"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 15 outcome:** Primary RED: missing `check_report_coverage` (1 failed /18.05s). Strengthened actual stronger-whole-heading GREEN: 1 passed /32.39s. Expanded composition and stored input/execution cases: 11 passed /179.71s. Exact focused gate: `uv run pytest tests/unit/reporting/test_composition.py tests/unit/reporting/test_repair.py tests/unit/reporting/test_obligations.py tests/unit/reporting/test_fallback.py -q` — 48 passed /1040.65s. Existing architecture/import controls: 31 passed /1.25s. Targeted Ruff/format PASS and production Pyright zero errors. Closed COMPOSITION documents now retain the checked context and bind exact committed drafts, extraction, independent support/completeness or recomputed fallback plus the actual execution. One check localizes deterministic replacement; unknown/unavailable checking selects full fallback, with local and Q9 obligation homes retained. Routing-only generative unit shapes confer no accepted authority; real generative acceptance remains gated by Tasks 19/21/24. Commit and post-commit gate are recorded in the execution ledger.

### Task 16: Deterministic citation identity and source-version ancestry

**Files:** Create `src/novelty_harness/reporting/citations.py`, `tests/unit/reporting/test_citations.py`, `docs/architecture/decisions/ADR-040-phase8-citations-and-report-acceptance.md`. Modify `tests/unit/test_phase1_architecture_guards.py` only for exact admitted normalization/passages read contracts if required.

**Interfaces:** Produce ReportCitation/CitationRegistry; `build_citation_registry(sections: tuple[VerifiedSection,...], bundle: ReportInputBundle) -> CitationRegistry`; `resolve_citation_link(citation: ReportCitation) -> str|None`; `validate_citation_registry(registry: CitationRegistry, sections: tuple[VerifiedSection,...], bundle: ReportInputBundle) -> None`. p8cite_ hashes exact source/version/passage/locator/comparison/commitment identity; display numbering stable native identity sort.

- [x] **RED — write `test_citations_bind_exact_claim_source_version_passage_and_commitment` and the named cases below.** Assert claim→basis→comparison/commitment→source/version/passage closure, no metadata-only support, known stored canonical link/identifier only. Add `test_wrong_title_version_or_locator_cannot_rescue_claim`, `test_citation_numbers_do_not_depend_on_prose_order`, `test_unknown_identifier_and_unsafe_scheme_render_plain_text`, `test_related_versions_do_not_become_independent_evidence`.

```python
assert citation.source_version_id == committed_version_id
assert citation.passage_id == supported_passage_id
with pytest.raises(ReportProposalError):
    validate_citation_registry(rebound_registry, sections, bundle)
assert no_url_citation.external_link is None
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_citations.py::test_citations_bind_exact_claim_source_version_passage_and_commitment -q`. Expect failure because deterministic citation registry and link policy are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Deterministic citation registry and link policy are absent; resolve only validated cited passages and committed source/version metadata. Versionless page explicitly labeled, missing dates/title unknown or source ID, publication/retrieval/cutoff distinct. Versioned resolver v1 supports stored DOI through https://doi.org/ with safe encoded identifier only; other stored identifiers remain plain without a registered rule. Never guess identifiers/fetch links. ADR-040 records this policy and transactional acceptance, preserving ADR-010; recheck number availability at execution and record any documentation-only renumbering.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_citations.py::test_citations_bind_exact_claim_source_version_passage_and_commitment -q`; expect PASS.
- [x] **Nearby variants:** Add `test_source_url_not_in_draft_cannot_be_fabricated`, `test_same_source_wrong_proposition_is_not_supported`, `test_internal_input_gate_gap_recommendation_refs_need_no_fake_external_cite`. Preserve conflicting metadata observations rather than latest-looking replacement.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_citations.py tests/unit/reporting/test_firewall.py tests/unit/reporting/test_bundle.py tests/unit/test_phase1_architecture_guards.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): resolve exact deterministic citations and record ADR"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 16 outcome:** Primary RED: citation module absent (1 failed /21.03s), after native upstream fixtures loaded. Exact primary GREEN: 1 passed /22.75s. Citation variants: 13 passed /33.80s. Required focused gate: `uv run pytest tests/unit/reporting/test_citations.py tests/unit/reporting/test_firewall.py tests/unit/reporting/test_bundle.py tests/unit/test_phase1_architecture_guards.py -q` — 50 passed /301.79s. Targeted Ruff/format PASS and production Pyright zero errors. Citations preserve actual claim bases, scoped passage/comparison/commitment/source/version ancestry and separate committed metadata observations. Stable numbers do not depend on prose order; stored URLs/DOI links are inert and versionless canonical pages remain labeled. Publication/retrieval/cutoff stay distinct; metadata membership does not certify arbitrary textual support. ADR-040 was available and records this policy and the later transactional acceptance/read contract, preserving ADR-010. Related-version identity checks use explicitly non-authoritative caller shapes. Commit and post-commit gate are recorded in the execution ledger.

### Task 17: Canonical ReportIR, realized report identity and safe summary

**Files:** Create `src/novelty_harness/reporting/ir.py`, `tests/unit/reporting/test_ir.py`. Modify `src/novelty_harness/reporting/{artifacts,verification}.py` for final accepted block/dependency contracts.

**Interfaces:** Produce AcceptedBlock, ReportIR, CompiledAssessmentReport, CompactSummary; `build_report_ir(bundle: ReportInputBundle, compilation: ReportCompilationRecord, sections: tuple[VerifiedSection,...], citations: CitationRegistry, artifacts: tuple[ReportArtifact,...]) -> ReportIR`; `validate_report_ir(ir: ReportIR, bundle: ReportInputBundle, compilation: ReportCompilationRecord, artifacts: tuple[ReportArtifact,...]) -> None`; `derive_compact_summary(ir: ReportIR) -> CompactSummary` (summary-free IR content projection avoids recursion); locked report_id function. Exact realized text and execution hashes contribute to identity.

- [x] **RED — write `test_ir_preserves_mixed_targets_and_summary_limitations` and the named cases below.** Assert Q1–Q9, target universe, exact verdict/language projections, complete citations/obligations/uncertainty/recommendations/value availability and per-block provenance. Add `test_compact_summary_cannot_strengthen_or_drop_decisive_limit`, `test_different_actual_prose_changes_report_id`, `test_report_identity_ignores_only_observations`, `test_generative_acceptance_needs_exact_verification_refs`.

```python
assert ir.target_findings == bundle.target_findings
assert ir.overall_finding == bundle.overall_finding
assert summary_target_ids == frozen_target_ids
assert all(material_limits_are_present(target, summary) for target in bundle.target_findings)
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_ir.py::test_ir_preserves_mixed_targets_and_summary_limitations -q`. Expect failure because canonical ir and deterministic compact summary are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Canonical IR and deterministic compact summary are absent; construct one structured accepted content graph, preserve origin/audit refs and complete exact dependency manifest including rejected calls relevant to repair/fallback. No extra summary-generation LLM. Recompute summary during validation; actual text/proposal/request/response/method hashes stay semantic, source dates stay facts, tokens/cost/latency/UTC observations stay outside semantic identity.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_ir.py::test_ir_preserves_mixed_targets_and_summary_limitations -q`; expect PASS.
- [x] **Nearby variants:** Add `test_caller_ir_cannot_upgrade_value_or_target_class`, `test_whole_negative_requires_actual_frozen_whole_scope`, `test_unassessable_and_mixed_summary_never_flattens`, `test_same_config_distinct_realizations_do_not_collide`.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_ir.py tests/unit/reporting/test_citations.py tests/unit/reporting/test_composition.py tests/unit/reporting/test_contracts.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): compose canonical verified report and deterministic summary"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 17 outcome:** Original RED: IR module absent (1 failed /59.79s), with committed plan and full fallback records loaded. Initial GREEN exposed obligation-home reconstruction ordering (1 failed /64.84s); canonical ordering and conflicting-copy rejection restored exact GREEN (1 passed /72.38s). Nonmaterial block-accounting regression: RED 1 failed /63.00s → GREEN 1 passed /62.60s; its neutral projection hint confers no semantic completeness. Retrieval-observation identity regression: RED 1 failed /68.87s → all 15 IR variants GREEN /230.62s, retaining publication facts and actual realization/execution hashes. Actual failed protocol invocation remains in the exact artifact dependency/provenance closure. Required focused gate: `uv run pytest tests/unit/reporting/test_ir.py tests/unit/reporting/test_citations.py tests/unit/reporting/test_composition.py tests/unit/reporting/test_contracts.py -q` — 46 passed /447.13s, without warnings after schema-valid enum attack setup. Targeted Ruff/format PASS, production Pyright zero errors, architecture/import controls 31 passed /1.60s. IR and summary preserve frozen target/verdict/permission/value/uncertainty and all mandatory homes; generative origins require matching local records and actual executions. Existing artifact dependency contracts and semantic digest helper are reused. Transactional acceptance/read remain gated by Tasks 19–20; final state-proof integration uses their owning validator and Task 21 coordinator. Commit and post-commit gate are recorded in the execution ledger.

### Task 18: Single-IR Markdown, canonical JSON and safe YAML

**Files:** Create `src/novelty_harness/reporting/rendering.py`, `tests/unit/reporting/test_rendering.py`. Modify `pyproject.toml`, `uv.lock`, `tests/golden/test_phase8_reports.py`, `tests/golden/phase8/`, `tests/unit/test_phase1_architecture_guards.py` for exact yaml serializer allowance.

**Interfaces:** Produce ReportRenditions(json: str, yaml: str, markdown: str, rendition digests); `render_compiled_report(report: CompiledAssessmentReport, *, renderer_version: str="p8-render-v1") -> ReportRenditions`; `validate_rendition_parity(report: CompiledAssessmentReport, renditions: ReportRenditions) -> None`. Add PyYAML>=6,<7 and types-PyYAML dev only here; safe_dump of canonical JSON-compatible structure, no custom constructors/tags. Allow yaml import only in rendering.py, keeping provider/network/application bans.

- [x] **RED — write `test_all_formats_preserve_questions_scope_permissions_and_limitations` and the named cases below.** Assert exact findings/targets/permissions/cites/coverage/uncertainty/material limitations/nine questions represented visibly, not only hidden JSON IDs. Add `test_markdown_missing_material_limit_fails_parity`, `test_html_links_yaml_tags_and_source_citation_syntax_are_inert`, `test_no_separate_semantic_call_per_format`. Format deterministic goldens only after verified semantic expectations.

```python
assert json.loads(renditions.json) == yaml.safe_load(renditions.yaml)
assert public_markdown_question_ids == tuple(range(1, 10))
assert markdown_projection == required_public_projection(report.ir)
assert rendition_digests_match_emitted_bytes
```

- [x] **Run exact RED:** `uv run pytest tests/unit/reporting/test_rendering.py::test_all_formats_preserve_questions_scope_permissions_and_limitations -q`. Expect failure because deterministic renderers and parity checks are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Deterministic renderers and parity checks are absent; render structured blocks with versioned escaping, stable references/local anchors and permitted stored external links. YAML derives the identical model, canonical JSON existing serializer, Markdown no live HTML/free model URLs. Rendition metadata/digest remains outside IR semantic content. Rendering failure cannot change accepted report findings.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/reporting/test_rendering.py::test_all_formats_preserve_questions_scope_permissions_and_limitations -q`; expect PASS.
- [x] **Nearby variants:** Add `test_markdown_table_cell_and_heading_escaping`, `test_rendered_unsupported_example_cannot_look_permitted`, `test_unknown_metadata_and_unversioned_url_are_labeled`. Reorder safe prose without changing stable citation numbers; perturb one format omission and require rejection.
- [x] **Focused regression:** `uv run pytest tests/unit/reporting/test_rendering.py tests/unit/reporting/test_ir.py tests/unit/reporting/test_citations.py tests/golden/test_phase8_reports.py tests/unit/test_phase1_architecture_guards.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): render one report IR as Markdown JSON and safe YAML"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 18 outcome:** Primary RED: renderer module absent after native committed fixtures loaded (1 failed /65.49s). Exact primary GREEN: 1 passed /175.09s. Variants: 9 passed, 1 failed /620.43s; sole failure was a test literal omitting the deliberately escaped slash in a closing HTML tag. Corrected literal exact GREEN: 1 passed /88.97s; no production fix or relaxed escaping. Required focused gate: `uv run pytest tests/unit/reporting/test_rendering.py tests/unit/reporting/test_ir.py tests/unit/reporting/test_citations.py tests/golden/test_phase8_reports.py tests/unit/test_phase1_architecture_guards.py -q` — 57 passed /1163.95s. Targeted Ruff/format PASS, production reporting Pyright zero errors, prior architecture/import controls 31 passed /1.49s and new YAML confinement guard passed /0.78s. Canonical JSON and safe YAML preserve the identical wrapper; Markdown visibly retains questions, targets, permissions, recommendations, value, coverage, uncertainty, limitations and exact reference ancestry. All markup and free URLs remain inert, typed citations use local anchors, and rendered-byte digests cannot rescue omissions. Format goldens preserve the public projection alongside six complete fallback prose goldens, normalizing only hashed identities/retrieval observations. Dependency setup DNS/cache failures were recorded separately; reviewed network resolution installed runtime PyYAML6.0.3 and development type stubs without changing existing dependency versions. Transactional acceptance remains Task19; caller shapes used by pure rendering tests confer no authority. Commit/post-commit gate are recorded in the execution ledger.

### Task 19: Atomic report acceptance and complete dependency validation

**Files:** Create `src/novelty_harness/evidence/graph/report_validation.py`. Modify `src/novelty_harness/evidence/graph/{report_store,sqlalchemy_repository}.py`, `src/novelty_harness/reporting/repository.py`, `tests/unit/evidence/graph/test_report_store.py`. Create `tests/adversarial/test_phase8_authority_semantics.py`.

**Interfaces:** Implement locked accept_compiled_report API; `validate_compiled_report_in_session(session: Session, load_view_in_session: Callable[..., Phase6AssessmentView], compilation_id: str, proposed: CompiledAssessmentReport) -> tuple[ReportInputBundle,tuple[ReportArtifact,...]]` in report_validation.py shared by acceptance/load. Extend repository Protocol only now that compiled contract exists. Consumes bundle, IR/citation/render/parity/fallback/repair/execution validators; no provider handle or semantic calls inside transaction.

- [x] **RED — write `test_acceptance_revalidates_exact_text_execution_and_dependency_set` and the named cases below.** Build committed valid generative and full-fallback candidates through approved artifacts, not a ready-authoritative caller object. Assert complete upstream and report closure, exact text/basis/permission/execution/method/config joins, all mandatory visible limitations, recomputed fallback/summary/citations/parity and legal repair lineage. Add `test_caller_compiled_shape_or_ir_export_cannot_skip_acceptance`, `test_accepted_label_cannot_bypass_fallback_recompute`, `test_acceptance_failure_rolls_back_dependencies_and_status`, `test_acceptance_rejects_foreign_context_snapshot_or_compilation`.

```python
with pytest.raises(ReportAuthorityError):
    repository.accept_compiled_report(compilation.compilation_id, proposal_with_omitted_rejected_call)
assert compiled_rows == 0
assert accepted_status_events == 0
```

- [x] **Run exact RED:** `uv run pytest tests/unit/evidence/graph/test_report_store.py::test_acceptance_revalidates_exact_text_execution_and_dependency_set -q`. Expect failure because atomic report acceptance and exact dependency validator are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Atomic report acceptance and exact dependency validator are absent; use BEGIN IMMEDIATE, reload upstream closure/bundle/catalog, validate all committed artifacts including rejected calls, compare exact required dependency set. Write manifest/dependency rows/ACCEPTED status atomically only from VERIFIED. Exact retry revalidates existing report and semantic identity; conflict fails. No Phase 6/7 write or downgraded authoritative result. Pinned supported versions checked against approved registry.
- [x] **Run exact GREEN:** `uv run pytest tests/unit/evidence/graph/test_report_store.py::test_acceptance_revalidates_exact_text_execution_and_dependency_set -q`; expect PASS.
- [x] **Nearby variants:** Add `test_missing_verification_cannot_be_replaced_by_supported_trace`, `test_wrong_source_version_or_missing_gate_judge_fails_accept`, `test_second_repair_or_fake_execution_cannot_accept`, `test_model_vote_cannot_authorize_rejected_claim`. Inject failure on dependency insert and ensure no ACCEPTED/report row remains.
- [x] **Focused regression:** `uv run pytest tests/unit/evidence/graph/test_report_store.py tests/adversarial/test_phase8_authority_semantics.py tests/unit/reporting/test_execution.py tests/unit/reporting/test_ir.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): accept reports only through transactional validation"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 19 outcome:** Exact primary RED: atomic acceptance API absent (1 failed /21.86s), then GREEN (1 passed /299.44s). A provider-failure helper expectation was corrected to the application-specific ReportProposalError before that GREEN; no failure outcome was hidden. Terminal receipt replay regression RED: existing committed ACCEPTED receipt rejected (1 failed /207.22s); scoped replay fix GREEN: 1 passed /224.11s. Missing-terminal retry regression RED: deleted ACCEPTED receipt still replayed (1 failed /321.07s); terminal-chain requirement GREEN: 1 passed /302.07s. Final required component command `uv run pytest tests/unit/evidence/graph/test_report_store.py tests/adversarial/test_phase8_authority_semantics.py tests/unit/reporting/test_execution.py tests/unit/reporting/test_ir.py -q` — 63 passed /2800.50s, exit0. Scoped Ruff/format PASS, production Pyright zero errors, architecture/import controls 42 passed /2.72s. Acceptance revalidates native upstream and committed report closure, exact text/basis/verification/method/config/execution/dependencies, deterministic fallback/summary/citations/rendering and repair lineage in BEGIN IMMEDIATE; compiled rows/dependencies/ACCEPTED commit atomically and upstream canonical rows stay unchanged. Canonically rehashed second repair and wrong approved-role instruction attacks reach semantic lineage/method joins. Exact replay preserves original acceptance observations and requires the terminal receipt. The sole ACCEPTED receipt is validated separately from preacceptance dependencies to avoid a report-ID cycle. Tests clone genuine native preacceptance snapshots only into empty independent report stores; two reuse controls passed /121.96s. An interrupted component log was not counted; the superseded resumed gate passed62 /3283.83s but final63 is the current-source evidence. Post-commit verification uses durable command/HEAD/PID/exit receipts to survive usage-limit interruptions. Authoritative report read remains Task20; no whole-phase or live semantic-quality acceptance is claimed. Commit/post-commit evidence is recorded in the execution ledger.

### Task 20: Authoritative report read, replay and dependency corruption

**Files:** Modify `src/novelty_harness/evidence/graph/{report_validation,report_store,sqlalchemy_repository}.py`, `src/novelty_harness/reporting/repository.py`, `tests/unit/evidence/graph/test_report_store.py`, `tests/adversarial/test_phase8_authority_semantics.py`.

**Interfaces:** Implement locked load_compiled_report API using one explicit BEGIN read transaction; shared Task 19 validator plus accepted terminal/manifest-column/ID/digest/exact dependency-row equality checks. Add `load_compiled_report_in_session(session: Session, load_view_in_session: Callable[..., Phase6AssessmentView], assessment_id: AssessmentId, *, report_id: str) -> CompiledAssessmentReport` in report_store.py. Public loader never returns a caller receipt/export as authority.

- [x] **RED — write `test_canonical_dependency_transplant_fails_load` and the named cases below.** Start from accepted happy path, replace one target/context/source-version dependency using otherwise valid records, recompute all affected hashes/IDs/FKs consistently, then require semantic join rejection. Add `test_load_missing_gate_judge_verification_or_passage_fails`, `test_load_revoked_phase6_relation_fails`, `test_load_replaced_context_or_stale_actual_prompt_fails`, `test_supported_older_version_loads_without_default_relabel`, `test_reopen_exact_replay_and_terminal_artifact_rules`.

```python
with pytest.raises(ReportAuthorityError):
    repository.load_compiled_report(assessment_id, report_id=rehashed_transplanted_report_id)
assert newly_accepted_report_rows == 0
```

- [x] **Run exact RED:** `uv run pytest tests/adversarial/test_phase8_authority_semantics.py::test_canonical_dependency_transplant_fails_load -q`. Expect failure because authoritative report read and complete corruption checks are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Authoritative report read and complete corruption checks are absent; reload manifest and exact report/upstream closure in one transaction, recheck methods/actual executions, fallback/summary equality, claims/cites/render obligations and ACCEPTED state. Missing/corrupt authority raises ReportAuthorityError without plausible downgraded report. Explicit older adjudication still supported when its own closure remains valid; do not adopt successor context.
- [x] **Run exact GREEN:** `uv run pytest tests/adversarial/test_phase8_authority_semantics.py::test_canonical_dependency_transplant_fails_load -q`; expect PASS.
- [x] **Nearby variants:** Add `test_changed_source_content_rejected_even_with_same_title`, `test_missing_rejected_call_dependency_fails_read`, `test_deleted_comparison_does_not_become_unassessable_report`, `test_withdrawn_policy_fails_but_new_default_alone_does_not`. Observe BEGIN count and atomic snapshot under concurrent dependency changes.
- [x] **Focused regression:** `uv run pytest tests/unit/evidence/graph/test_report_store.py tests/adversarial/test_phase8_authority_semantics.py tests/adversarial/test_phase6_r14_graph_authority.py tests/adversarial/test_phase6_r15_assessment_authority.py tests/unit/evidence/graph/test_phase7_store.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): revalidate compiled report authority on read"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 20 outcome:** Exact corrected transplant GREEN: 2 passed / 486.21s. Final expanded regression (the required five suites plus contracts/execution, `-q -x --tb=short`): 171 passed / 4941.32s, exit 0. The earlier ENOSPC-interrupted gate is not verification evidence; bounded native fixture teardown and an isolated actual-prompt recovery (1 passed / 205.21s) preceded this complete rerun. Native authoritative read uses one explicit transaction and the shared acceptance validator; exact scope, dependency rows, terminal receipt, source/version ancestry and actual instructions are revalidated. Supported pinned methods remain separate from invocation defaults. Final scoped Ruff/format and production Pyright are recorded with the task ledger. Phase acceptance remains OPEN pending remaining gates and independent review.

**Post-commit recovery:** After additional disk capacity became available, the complete required five-suite post-commit gate passed: 144 tests / 4644.31s, exit 0 (`-q -x --tb=short`). Task 20 is complete at `a3c518a`; the earlier storage-failure record is retained as history. Task 21 may proceed.

### Task 21: Real compilation coordinator, bounded cost and crash replay

**Files:** Create `src/novelty_harness/application/phase8.py`, `tests/integration/test_phase8_compiler.py`. Modify `src/novelty_harness/application/phase8_sections.py`, `src/novelty_harness/reporting/artifacts.py`, `tests/fixtures/phase8.py`.

**Interfaces:** Implement the locked async compile_assessment_report signature; use ReportRepository and ReportPorts only, registered configuration before dispatch. Pipeline: load/begin/resume/register → plan/coverage fallback → nine sections/assurance → one composition check/fallback → citations/IR/dependencies → acceptance → authoritative reload. Consume committed status/artifacts to skip completed invocations and accepted content on exact attempt retry. Coordinator returns loaded CompiledAssessmentReport; export is a separate Task 22 operation.

- [x] **RED — write `test_all_semantic_ports_unavailable_produces_full_report` and the named cases below.** Add `test_generative_planner_writer_synthesis_survives_full_pipeline`, `test_direct_partial_potential_mixed_and_unassessable_compile`, `test_all_configured_providers_fail_to_complete_fallback`, `test_retry_replays_committed_sections_without_calls`, `test_new_model_lens_or_attempt_changes_report_not_adjudication`, `test_operational_limits_fallback_without_omission`. Normal safe configured path must retain generative hierarchy/text, not always template fallback.

```python
report = await compile_assessment_report(assessment_id, adjudication_id=frozen.adjudication_id, repository=repository, ports=None, options=options)
assert question_ids(report.ir) == tuple(range(1, 10))
assert report.ir.target_findings == frozen.target_findings
assert repository.load_compiled_report(assessment_id, report_id=report.report_id) == report
```

- [x] **Run exact RED:** `uv run pytest tests/integration/test_phase8_compiler.py::test_all_semantic_ports_unavailable_produces_full_report -q`. Expect failure because real coordinator and resource-aware replay are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Real coordinator and resource-aware replay are absent; persist each stage/output/execution before advancing status, bind actual calls/cumulative tokens/cost to report attempt, apply limits before dispatch. At most one planner, nine normal writes, section extraction/verification, one composition check plus approved recoveries/local repairs. NOT_CONFIGURED has no fake execution. Crash after completed stage resumes by committed record; unfinished repair cannot get another call. Runtime config change requires new key/attempt.
- [x] **Run exact GREEN:** `uv run pytest tests/integration/test_phase8_compiler.py::test_all_semantic_ports_unavailable_produces_full_report -q`; expect PASS.
- [x] **Nearby variants:** Add `test_partial_outage_affects_only_unverified_content`, `test_limited_input_missing_meaning_cannot_gain_positive_report`, `test_budget_provider_no_yield_remain_distinct`, `test_replay_after_acceptance_does_not_regenerate`, `test_zero_yield_successor_requires_its_own_report_scope`. Compare upstream canonical rows before/after compilation.
- [x] **Focused regression:** `uv run pytest tests/integration/test_phase8_compiler.py tests/unit/reporting tests/unit/evidence/graph/test_report_store.py tests/adversarial/test_phase8_authority_semantics.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [x] **Commit:** `git commit -m "feat(phase8): coordinate bounded real report compilation and replay"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

**Task 21 checkpoint (in progress):** Corrected exact RED failed at the missing coordinator after native authority fixture setup; exact fallback GREEN passed (1 / 429.14s). Budget, committed-stage replay and explanatory category defects received recorded RED/GREEN fixes. The all-nine generative variant passed (1 / 2655.96s), with 31 actual role calls and authoritative acceptance/readback. All 36 compiler integration cases have passed in the current combined gate, including all six lenses, limits, outages, actual uncertainty states and crash/replay checkpoints. The combined gate stopped at an existing IR failed-invocation fixture (201 passed / 1 failed / 22931.02s): its default operational limits prevented the call it intends to test. The owning fixture correction and complete rerun are pending; no Task 21 completion or commit is claimed. Scripted tests do not establish live semantic quality.

**Task 21 recovery checkpoint (8 October):** The IR failed-call fixture received an explicit operational allowance without changing its provenance assertions or product defaults: exact RED 1 failed / 31.13s → GREEN 1 passed / 80.15s; the owning IR suite plus tight-budget cases passed 19 / 322.95s. The subsequent full gate stopped at missing recorded fixture data (20 passed / 1 setup failure / 15972.75s), after tracked files and temporary Git/environment files disappeared; this is environment failure, not a semantic test result. Remaining work and Git metadata were preserved before recovery. Missing current-HEAD files were restored from exact Git blobs, all twelve changed Task 21 Python files matched the preserved archive, and a clean locked environment synchronized successfully offline using the recovery cache. The affected LIMITED case then passed 1 / 577.03s. Scoped Ruff/format, production Pyright and whitespace checks passed. A new complete four-suite gate is running over the unchanged implementation; Task 21 remains uncommitted and incomplete until its required gates pass. Current HEAD and accepted baseline trees are recovered; three early historical Phase 7 root-tree objects remain unavailable, with an optional backup-path request pending.

**Task 21 implementation gate outcome:** The restored-environment four-suite command, with `-q -x --tb=short` and `UV_CACHE_DIR=/private/tmp/uv-phase8-recovery-cache`, passed **377 tests / 27497.48s (7:38:17)**, exit 0. All 36 compiler integration cases and the corrected IR provenance case passed in that complete run. Final scoped Ruff check passed, all twelve Python files passed the format check, production Pyright reported zero errors/warnings, and whitespace checks passed. The coordinator loads native authority, registers actual role configurations, resumes committed outputs, enforces operational allowances, preserves rejected/failed execution provenance, and returns an authoritatively reloaded report. All-provider fallback and the configured generative path retain Q1–Q9, exact findings, citations and obligations. RPT-01/02/16–19/21–23/25/27 and design §§21–23/25 are exercised here; the final phase gate and independent acceptance remain outstanding. Owning plan/firewall and budget-sensitive fixture extensions are recorded with their exact RED/GREEN evidence in the execution ledger. Commit and required post-commit task completion gate follow; scripted results do not establish live semantic quality.

### Task 22: Explicit real vertical-slice branch and loaded exports

**Files:** Create `src/novelty_harness/application/phase8_exports.py`, `tests/integration/test_phase8_slice.py`. Modify `src/novelty_harness/application/{models,vertical_slice}.py`; extend `tests/integration/test_phase7_slice.py` and `tests/unit/test_minimal_report_compiler.py` only for compatibility assertions.

**Interfaces:** Produce `ReportCompilationRequest(options: ReportOptions, ports: ReportPorts|None=None, attempt_token: str|None=None)` frozen application dataclass; add `phase8: ReportCompilationRequest|None=None` keyword to run_vertical_slice, return union also containing `Phase8VerticalSliceResult(record: AssessmentRecord, run_dir: Path, adjudication: real FrozenAdjudication, report: CompiledAssessmentReport, summary: Phase7FrozenSummary)`. Existing function result dataclasses live in vertical_slice.py; place new result there, request in application/models.py. Produce `export_compiled_report(assessment_id: AssessmentId, *, report_id: str, repository: ReportRepository, artifact_writer: RunArtifactWriter) -> tuple[Path,Path,Path]` in phase8_exports.py.

- [x] **RED — write `test_real_slice_compiles_loaded_report_and_preserves_summary_only_branch` and the named cases below.** Assert explicit real report branch requires real Phase 7, rejects fixture FrozenAdjudication/export seed, preserves old fixture and summary-only routes. Compile only after freeze/reload, with separate attempt. Add `test_report_generation_or_export_failure_does_not_rewrite_adjudication`, `test_export_retry_uses_accepted_report_without_semantic_calls`, `test_full_report_operation_can_run_after_completed_phase7_lifecycle`.

```python
assert full.report.scope.adjudication_id == full.adjudication.adjudication_id
assert summary_only.summary.overall_verdict == summary_only.adjudication.overall_finding.verdict
assert exported_report_id == repository_loaded_report.report_id
assert phase7_row_bytes_after_report == phase7_row_bytes_before_report
```

- [x] **Run exact RED:** `uv run pytest tests/integration/test_phase8_slice.py::test_real_slice_compiles_loaded_report_and_preserves_summary_only_branch -q`. Expect failure because real report integration and locator-loaded exports are absent; record the actual failure, not a setup/network error.
- [x] **IMPLEMENT:** Real report integration and locator-loaded exports are absent; invoke compiler after accepted freeze, before emitting the chosen REPORTED presentation in new slice execution. A standalone compile over a completed Phase 7 assessment never reopens its lifecycle. Per-report paths `reports/<report_id>/report.json`, `.yaml`, `.md` are derived exports via existing safe writer; include locators/digests. No mutable report files used as acceptance store. Report operational failure retains frozen adjudication and its summary; error is report-specific.
- [ ] **Run exact GREEN:** `uv run pytest tests/integration/test_phase8_slice.py::test_real_slice_compiles_loaded_report_and_preserves_summary_only_branch -q`; expect PASS.
- [ ] **Nearby variants:** Add `test_fixture_report_cannot_masquerade_as_real_report`, `test_corrupt_authority_prevents_any_report_export`, `test_two_reports_keep_separate_export_paths`; inject I/O failure after report commit then reload/export without writer/verifier calls.
- [ ] **Focused regression:** `uv run pytest tests/integration/test_phase8_slice.py tests/integration/test_phase8_compiler.py tests/integration/test_phase7_slice.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/unit/test_minimal_report_compiler.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [ ] **Commit:** `git commit -m "feat(phase8): integrate explicit full reports and authoritative exports"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 23: Post-commit observability and capability guards

**Files:** Create `src/novelty_harness/application/phase8_tracing.py`, `tests/unit/test_phase8_architecture_guards.py`. Modify `src/novelty_harness/application/{phase8,phase8_sections,phase8_exports}.py`, `tests/adversarial/test_phase8_authority_semantics.py`; modify `src/novelty_harness/runtime/tracing/models.py` only if existing typed event vocabulary needs report-stage additions.

**Interfaces:** Produce `publish_report_events(compilation_id: str, *, repository: ReportRepository, sink: TraceSink) -> tuple[str,...]` in phase8_tracing.py; returns failed delivery event IDs, events deterministically projected from committed records with retryable stable event identities. Add semantic/capability architecture guards over new reporting/application/store paths, preserving approved imports and legacy fixture exceptions.

- [ ] **RED — write `test_report_success_trace_follows_commit_and_cannot_authorize_text` and the named cases below.** Events for load/begin/resume/registration/planner/plan firewall/writer/extraction/firewall/verification/repair/fallback/composition/citation/accept/reload/export carry scope/artifact/execution IDs/hashes/reason/status/observations. Add `test_trace_retry_never_duplicates_semantic_execution`, `test_prompt_injection_and_fake_verifier_instruction_are_untrusted`, `test_phase8_has_no_search_research_or_upstream_write_capability`, `test_real_report_cannot_import_fixture_authority`. Architecture tests inspect imports, call names, port annotations and malicious import fixtures, not a single source substring.

```python
assert semantic_success_observed_after_commit
assert trace_execution_hashes == committed_execution_hashes
assert authoritative_report_after_sink_failure == accepted_report
with pytest.raises(ReportAuthorityError):
    load_report_from_trace_only_fixture()
```

- [ ] **Run exact RED:** `uv run pytest tests/adversarial/test_phase8_authority_semantics.py::test_report_success_trace_follows_commit_and_cannot_authorize_text -q`. Expect failure because post-commit report trace projection and capability guards are absent; record the actual failure, not a setup/network error.
- [ ] **IMPLEMENT:** Post-commit report trace projection and capability guards are absent; derive successful semantic trace only after artifact commit, accept event only after acceptance, preserve report on sink failure and retry delivery without semantic calls. No hidden chain-of-thought/secrets stored. Pure report contracts prohibit provider SDK/application imports; allow exact shared read contracts/hash utilities and yaml in renderer. Store alone has SQL authority over report tables; forbid compiler calls to Phase 6 writes/Phase 7 mutation. Integration may invoke preexisting run_phase7 upstream, never through semantic ports.
- [ ] **Run exact GREEN:** `uv run pytest tests/adversarial/test_phase8_authority_semantics.py::test_report_success_trace_follows_commit_and_cannot_authorize_text -q`; expect PASS.
- [ ] **Nearby variants:** Add `test_guard_detects_relative_dynamic_and_reexported_capability_leak`, `test_rendered_source_instructions_cannot_execute_or_expand_citations`, `test_numeric_novelty_fields_or_tests_imports_are_banned`. Keep Internet disabled by existing pytest-socket config, and prove generated ports have no repository/browser/retrieval attributes.
- [ ] **Focused regression:** `uv run pytest tests/unit/test_phase8_architecture_guards.py tests/unit/test_import_boundaries.py tests/unit/test_phase1_architecture_guards.py tests/unit/test_phase5_architecture_guards.py tests/unit/test_phase6_architecture_guards.py tests/unit/test_phase7_architecture_guards.py tests/adversarial/test_phase8_authority_semantics.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [ ] **Commit:** `git commit -m "feat(phase8): trace committed reporting and guard authority boundaries"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

### Task 24: Adversarial closure, traceability and exact verification handoff

**Files:** Modify `tests/adversarial/test_phase8_authority_semantics.py`, `tests/golden/test_phase8_reports.py`, `tests/golden/phase8/` and only reproduced-defect owning Phase 8 files/tests. Create `docs/traceability/phase-8.yaml`, `docs/phase-8-completion.md`; modify `README.md`. Preserve Phase 6/7 history and the approved design.

**Interfaces:** No new runtime interface. Produce exact implementation commit evidence, requirements→task/module/test mapping, prompt/policy/config registry versions, known limits and one final independent review handoff. Closeout tests cross actual upstream freeze→bundle→plan/write→verification/repair→IR/cites→accept/load/export.

- [ ] **RED — write `test_full_generative_report_repair_acceptance_replay_and_revocation` and the named cases below.** Perturb an accepted generative happy path by revoking its decisive graph relation only after acceptance/replay; preserve accepted upstream semantic labels and require read/export refusal. Add `test_complete_fallback_cannot_hide_missing_value_or_uncertainty`, `test_ordered_model_votes_cannot_accept_rejected_material_claim`, `test_consistent_hashes_do_not_rescue_wrong_version_or_context`, `test_hidden_heading_assertion_crosses_extraction_and_composition_boundary`. Existing invariants that already pass are recorded honestly; only reproduced defects receive red fixes.

```python
assert initial_realization_has_generative_accepted_blocks
assert repair_calls_per_origin <= 1
assert exact_retry.report_id == accepted.report_id
with pytest.raises(ReportAuthorityError):
    repository.load_compiled_report(assessment_id, report_id=accepted.report_id)
```

- [ ] **Run exact RED:** `uv run pytest tests/adversarial/test_phase8_authority_semantics.py::test_full_generative_report_repair_acceptance_replay_and_revocation -q`. Expect failure because integrated adversarial closure and completion evidence are not recorded; record the actual failure, not a setup/network error.
- [ ] **IMPLEMENT:** Integrated adversarial closure and completion evidence are not recorded; test all cases in the coverage matrix below, fix only reproduced Phase 8 defects with individual RED/GREEN owning tests. Map RPT-01–27, master INV-01–15, §§34–39.1/44–47/54–57, FR-AUD-001/002/003, FR-CTX-001/002/003, FR-SEC-001/002/003, FR-OBS-001/002 and exit criteria to exact tests/modules. README says implementation verified, acceptance OPEN pending independent review; no self-acceptance.
- [ ] **Run exact GREEN:** `uv run pytest tests/adversarial/test_phase8_authority_semantics.py::test_full_generative_report_repair_acceptance_replay_and_revocation -q`; expect PASS.
- [ ] **Nearby variants:** Attempt fresh combinations of target/context/source-version/provenance/repair ordering and state, including right passage wrong proposition, false example tags, cumulative no-yield limitations, incomplete residual negative, M1 maturity inflation, skipped composition and full outage. Record bounded attacks and counterexamples without claiming live semantic quality or Phase 9 robustness qualification.
- [ ] **Focused regression:** `uv run pytest tests/unit/reporting tests/unit/evidence/graph/test_report_store.py tests/contract/test_report_ports.py tests/integration/test_phase8_compiler.py tests/integration/test_phase8_slice.py tests/adversarial/test_phase8_authority_semantics.py tests/golden/test_phase8_reports.py tests/unit/test_phase8_architecture_guards.py -q`; expect all PASS. Run targeted Ruff/Pyright if interfaces/imports changed; stop on red.
- [ ] **Commit:** `git commit -m "docs(phase8): record exact compiler verification and review handoff"` after explicit staging of the listed files and cached whitespace check; record task done with actual results.

## Required scenario and attack ownership

Each row names tests added during execution; the primary and variants above also remain mandatory. Assertions concern basis/scope/permissions/dispositions/coverage, not exact stochastic wording. Only deterministic fallback/rendering copy uses text goldens.

| Scenario or attack | Owning task and named test |
| --- | --- |
| Direct negative, one source, no global saturation | 21 `test_direct_negative_retains_single_source_and_scoped_wording`; 13 DIRECT golden. |
| Scoped strong-partial negative with complete localized NON_SUBSTANTIVE residual | 3 `test_bundle_keeps_complete_residual_and_decisive_closure`; 13 `test_partial_negative_retains_relationships_remainder_and_original_class`. Perturb an independently causal residual: rejected interpretation cannot become a report negative. |
| Potential, meaningful survivor, weak/unproven value | 21 `test_potential_candidate_remains_scoped_without_value_upgrade`; 13 POTENTIAL golden. |
| Mixed MCU/combination and UNASSESSABLE | 17 `test_unassessable_and_mixed_summary_never_flattens`; 21 scenario test; 13 MIXED/UNASSESSABLE goldens. |
| Complete LIMITED vs decisive missing input | 21 `test_limited_input_missing_meaning_cannot_gain_positive_report`; 11 wording tests. Preserve accepted negative/potential permission where available; missing meaning stays unresolved. |
| Budget stop, provider/access blocked, no new yield, cumulative usage | 4 `test_uncertainty_preserves_budget_no_yield_provider_and_ancestor_scope`; 21 `test_budget_provider_no_yield_remain_distinct`. No saturation/no-art inference, direct negative not erased. |
| M1 absent value/significance; CIR claims higher maturity | 4 `test_cir_high_maturity_is_attributed_not_assessed_value`; 13 full fallback M1; 24 `test_complete_fallback_cannot_hide_missing_value_or_uncertainty`. |
| Planner hides decisive source or limitation; unsupported thesis | 6 primary and `test_plan_heading_semantics_are_not_self_certified`; 10 public-text verification. |
| Source/URL invention, right source wrong claim, passage/version/title rebound | 9 primary/variants; 16 ancestry tests; 24 `test_consistent_hashes_do_not_rescue_wrong_version_or_context`. |
| Implicit absence/definite novelty, partial→direct, component stitching, whole-project scope | 10 `test_semantic_paraphrases_do_not_escape_scope` and `test_synthesis_does_not_establish_combination`; 15 composition tests. |
| Gate D→value, value→novelty, model changes verdict/Gate/qualification | 4 value cases; 9 overrides; 10 strict verifier schema; 15 cross-question value implication. |
| Useful Q7 recommendation vs fabricated experiment/benchmark/comparator/research | 11 primary and `test_q7_cannot_invent_comparator_capability`; semantic verifier inspects premises, not only status. |
| Extractor misses heading/table/presupposition; empty extraction | 8 accounting; 10 `test_hidden_heading_table_presupposition_rejects_incomplete_extraction`; 24 cross-subsystem heading attack. |
| Incomplete/duplicate dispositions; semantic support despite mechanical failure | 10 primary/variants; 19 `test_model_vote_cannot_authorize_rejected_claim`. |
| Shared model/conversation, wrong audit and actual recovery hash | 12 primary and separate-role context tests; 20 stale load checks. |
| Second repair, segmentation reset, recursive schema recovery, transport retries | 14 primary/variants; 19 illegal lineage acceptance. |
| Composition implies stronger whole claim or uncertainty moved only to Q9 | 15 primary and adjacency variant. No global rewrite/another semantic repair. |
| Summary strength/omission; all six lenses with same adjudication | 17 summary recompute; 21 `test_new_model_lens_or_attempt_changes_report_not_adjudication`, parameterize six lenses and compare target/Gate/permission/dependency parity. |
| JSON/YAML/Markdown drift, HTML, YAML tags, fake cite syntax | 18 primary/variants; 23 injection guard tests. |
| All providers unavailable, no ports, tight token/cost budget | 13 standalone fallback; 21 primary/failures/budget variants. Complete citations and obligations must survive. |
| Accepted happy path perturbed by missing/revoked dependency | 20 primary canonical transplant; 24 integrated revocation test. |
| Caller wrapper/IR/valid export, foreign compilation/context/snapshot | 19 primary/forgery; 20 read join tests. |
| Deleted Gate/judge/comparison/passage/verification; changed version/graph relation | 19–20 parameterized mutation cases require ReportAuthorityError; no plausible downgrade. |
| Stale method, mismatched instruction/config/proposal, missing rejected-call audit | 12 runtime joins; 19 exact dependency set; 20 load mutation. |
| Same ID different content, exact replay, reopen/rollback, v8 migration isolation | 2, 5, 19–20. No existing semantic row changes or backfill. |
| Legacy fixtures/minimal summary and explicit real report result | 22 branch/fixture tests, existing slice/report regressions. |

The authoritative mutation matrix for Tasks 19–20 parameterizes UPSTREAM and REPORT_ARTIFACT arms separately: deleted Gate, judge resolution/comparison/run, Phase 6 comparison, revoked graph membership, changed source/version content, deleted passage/attestation, replaced context/snapshot, foreign target, stale method/hash, missing verification, omitted rejected-call execution, missing/extra dependency row and same-ID content conflict. Recompute hashes/FKs consistently in at least one cross-context and one source-version attack; tests must reach semantic equality/scope checks, not stop merely at an invalid canonical ID. Exact locally supported older method versions remain valid; unknown/withdrawn/mismatched versions do not.

## Design coverage and requirement traceability map

This table is the planning self-review coverage map and the seed for Task 24's phase-8.yaml; it does not claim implementation.

| Approved design sections | Tasks | Requirements |
| --- | --- | --- |
| 1–5 objective, architecture, invariants, accepted boundaries | 1–5, 19–24 | RPT-01–03, 17, 21, 23; INV-01–15; §§34–38. |
| 6 strict vocabulary | 1, 3–12, 13, 16–17 | RPT-12, 21, 27; FR-AUD-002. |
| 7 input closure, metadata, obligations | 3–4 | RPT-01, 04, 10–11, 14, 21, 23; INV-14/15; §§37,45. |
| 8 hierarchical planner/firewall | 6, 12, 21 | RPT-05, 11–12, 22; §38. |
| 9 writer and compatible synthesis | 7, 10, 12, 14 | RPT-02–09, 11–12; INV-02/03/04/12/15. |
| 10 independent extraction | 8, 10, 12 | RPT-04, 12, 24; INV-14. |
| 11 deterministic Semantic Firewall | 9, 11, 19–20 | RPT-02–10, 14, 21; INV-05/12/13/14/15. |
| 12 semantic support/completeness | 10, 12, 14 | RPT-04, 11–13, 24; INV-14/15. |
| 13 repair/fallback/composition | 13–15, 19–21 | RPT-11, 18–19, 24–25; FR-OBS-001. |
| 14 canonical Q1–Q9 | 3–4, 6–11, 13, 15, 17–18, 21–22 | RPT-04–11, 26; §§38,57; Phase 8 exit criteria. |
| 15 Q6/M1 | 4, 10, 13 | RPT-09–10; INV-09; §§6,38 Q6. |
| 16 Q7 useful prospective validation | 11, 13 | RPT-26; §38 Q7. |
| 17 Q8 language/Q9 actual uncertainty | 4, 9–11, 13, 15 | RPT-05–08, 11, 13; INV-01/05/06/12/13; §38 Q8/Q9,45. |
| 18 IR/formats/compact summary | 17–18 | RPT-15, 20; §57. |
| 19 deterministic citations | 3, 9, 16, 18–20 | RPT-04, 14; INV-07/14; FR-AUD-002. |
| 20 lenses | 1, 7, 21 | RPT-16; FR-CTX-001/002/003; §39.1. |
| 21 ports/application | 12, 14–15, 21–22 | RPT-12–13, 17–19; §§42,56. |
| 22 four-table persistence/API/transactional accept/read | 2–5, 19–20 | RPT-01, 21–23, 27; FR-AUD-001/002/003; §44. |
| 23 identity/provenance/recovery | 1, 5, 12, 14, 17, 19–21 | RPT-12, 22, 25, 27; FR-AUD-002/003. |
| 24 failure/security | 9–15, 18–23 | RPT-17–19, 23–25; FR-SEC-001/002/003; §§46–47. |
| 25 cost/observability/integration | 12, 14–15, 21–23 | RPT-18–19, 22, 25, 27; FR-OBS-001/002; §§54–56. |
| 26 test strategy | all task gates, 24 | All RPT/INV requirements; §49 and Phase 8 exit criteria. |
| 27 acceptance/Phase 9 boundary | 23–24, single review below | RPT-01–27; Phase 8 exit criteria; Appendix C. |
| 28 resolved decisions/non-goals, 29 self-review | header, locked decisions, this self-review | No redesign, no later-phase authorization. |

## Progressive verification and Task 24 final gate

Use exact task test → owning suite → report contract/application/store suites → frozen Phase 6 authority → Phase 7 permission/provenance → real Phase 8 slice → adversarial/golden tests → full verification. Component commands appear in every task. In Task 24 run, in order, after final runtime/test changes:

```bash
uv sync --dev
uv run pytest tests/unit/reporting tests/unit/evidence/graph/test_report_store.py tests/contract/test_report_ports.py tests/unit/test_phase8_architecture_guards.py -q
uv run pytest tests/adversarial/test_phase6_r10_content_authority.py tests/adversarial/test_phase6_r11_authoritative_publication.py tests/adversarial/test_phase6_r13_commit_receipt_authority.py tests/adversarial/test_phase6_r14_graph_authority.py tests/adversarial/test_phase6_r15_assessment_authority.py tests/adversarial/test_phase6_r15_public_graph_consistency.py tests/adversarial/test_phase6_sol_review_regressions.py tests/adversarial/test_phase6_contract_consolidation.py -q
uv run pytest tests/unit/adjudication tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py tests/integration/test_phase7_slice.py -q
uv run pytest tests/integration/test_phase8_compiler.py tests/integration/test_phase8_slice.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/unit/test_minimal_report_compiler.py -q
uv run pytest tests/adversarial/test_phase8_authority_semantics.py tests/golden/test_phase8_reports.py -q
uv run python scripts/verify.py
git diff --check
```

Use `UV_CACHE_DIR=/private/tmp/uv-cache` where the existing environment requires it. If dependency synchronization needs network unavailable in the environment, record the failed setup and use `uv sync --dev --offline` only when the lockfile packages exist in cache; never count failed setup as a test result. Default pytest excludes network tests and disables Internet sockets. No numeric Phase 8 pass count is predicted; record actual new count, changed tests and the five current opt-in exclusions rather than carrying 2,037 forward as a result.

Task 24 then commits the final verified implementation changes, records that exact SHA, and runs full verification again in a **new clean detached checkout at that SHA**:

```bash
git worktree add --detach /private/tmp/novcheck-phase8-verify-<short-sha> <full-implementation-sha>
```

In that checkout run `git rev-parse HEAD`, `git status --short`, `uv sync --dev`, `uv run python scripts/verify.py`, `git diff --check`, `git status --short`. Expected: exact SHA, initially/finally clean, synchronization success or documented offline cache recovery, Ruff/format PASS, Pyright zero errors, all deterministic tests PASS, network exclusions reported. `scripts/verify.py` includes `ruff check .`, `ruff format --check .`, `pyright`, `pytest`. Never claim live semantic quality from scripted tests.

Only after those gates, complete `docs/phase-8-completion.md` with exact SHA, commands/counts/logs/limits/registry versions, update traceability and README, and make the Task 24 documentation handoff commit. If that commit changes documentation only, distinguish the verified implementation tree SHA from handoff SHA; check `git diff <implementation-sha>..<handoff-sha> -- src tests scripts pyproject.toml uv.lock` is empty. Verify documentation whitespace/links at handoff. Any runtime/test/configuration change after the recorded full gate invalidates that evidence and requires rerunning the affected gate plus final full verification. No reviewer edits to implementation are part of closeout.


## Execution-plan ruling — 8 October 2026

User-authorized verification optimization supersedes redundant post-commit and unchanged multi-hour component reruns for Tasks 21–23. Before this ruling, the clean implementation commit `1f50323fe10987f08bbda45040158736390c5c49`, source tree, recovery Git metadata and complete execution records were separately preserved at `/private/tmp/novcheck-phase8-checkpoint-20261008T093526Z`; no worktree or historical Git data was deleted.

The 377-test GREEN (`27497.48s`, receipt `task-21-focused-environment-restored-receipt.json`) is verified against the commit: all 428 tracked non-documentation files have identical bytes and executable modes in the preserved passing snapshot, committed tree and current checkout. Of these, 306 missing files match the exact restored Task 20 blobs and restoration ledger; remaining files come from the preserved pre-run archive. Canonical comparison manifest SHA256: `e53ab9b824cc3139fc43ecc09ac6714390f23c8d26da49b03ad273aaacadd360`. Only plan documentation was updated after the passing run; source equivalence evidence is `source-equivalence.json` and `passing-tree-manifest.json` in the checkpoint.

The duplicate post-commit run received SIGINT after preservation/equality checks. It is **INTERRUPTED**, with 11 tests completed in `7817.00s`; this is not a suite pass. Original receipt and pre/post interruption logs are retained in the checkpoint and execution workspace. A focused post-commit smoke gate covers report contracts, actual execution audit/instruction binding, invocation budget guards, and Phase 6/7 architecture guards. Task completion may use this smoke command after the already complete, byte-equivalent 377-test GREEN.

Tasks 22/23 retain exact RED→GREEN, all named task cases, focused owning components, relevant Phase 6/7 authority/capability guards, static checks and task commits. Unchanged multi-hour compiler/store/adversarial suites are deferred to Task 24. Any reproduced failure must be fixed and verified before progression; assertions and adversarial cases remain intact. Task 24 still requires the complete Phase 8 regression, all specified upstream authority regressions, full repository verification, and a new clean detached checkout at the exact implementation SHA, followed by the single independent whole-phase review. No interrupted run or scripted port establishes live semantic quality.

Immutable SQLite fixture reuse is an investigation, not an authority exemption: snapshots must originate from real upstream construction, be closed/checkpointed, copied to a private database per test, and undergo unchanged native authority loading. Shared mutable databases and bypassed validation are forbidden; savings require measured evidence before adoption.

Task 22 fixture/runtime investigation: native SQLite backup copies took 0.004–0.015 seconds and unchanged frozen/bundle loading took 3.33–3.56 seconds, with equal authority IDs/digests and source bytes unchanged. The existing acceptance fixture already uses this pattern. New export tests compile one native baseline and clone it privately; corruption in one clone must leave the baseline loadable. No production authority cache was added. A cProfile construction run recorded 111 million calls; canonical serialization and repeated native validation are substantial costs. Expanded native history caused 60–387 MB fallback sections because long limitation statements are repeated across basis links. Diagnostic runs are retained as INTERRUPTED, not GREEN; payload amplification remains a performance risk. The new focused slice fixture uses one recorded registered provider, one actual deep round, one source per target, and no expansion, before native sealing. It retains three targets and their combination, records other families as unsearched, and leaves all question/scope/authority/export assertions intact. Its measured research result is 141,214 bytes versus 527,326 bytes for the earlier fixture. Full final regression and detached verification remain required; no end-to-end snapshot speedup is claimed from profiled build timing.

Repository integrity remains a final acceptance blocker: `git fsck --full --no-reflogs` exits 2 for missing historical trees `217fe71733284877a69d7e8a2188b9b1ed4c7dcd`, `fd80d34d5d5ea05c4c728740f0702e1646c38129`, and `b4d9c8f0ef9ed46cab9a56f5fb44c2d29f15592a`. Current implementation and accepted baseline trees are available; implementation can proceed, but final acceptance cannot be declared until exact objects are recovered and integrity verification passes. No history rewrite or fabricated object is permitted.

## Single independent acceptance review

After all 24 task gates and clean detached verification pass, dispatch exactly **one fresh whole-phase independent reviewer** over the exact handoff/implementation tree, with read-only production/tests authority. Review: unchanged Phase 6/7 authority; transactional bundle; obligation coverage; useful generative synthesis; independent extraction/completeness; non-adjudicative verifier; Q6 M1/Q7 recommendations/Q8 ceilings/Q9 uncertainty; source/version/passage citations; one-repair lineage; all-provider fallback; schema v9; exact accept/load closure; canonical context/provenance substitution; format/summary/lens parity; and no report-stage search. Reviewer records concrete reproduction, severity and required remediation scope in `docs/reviews/phase-8-final-review.md`; historical Phase 7 records remain unchanged.

Critical/Important findings keep Phase 8 acceptance OPEN and receive **one bounded implementer remediation pass** limited to reproduced approved-contract defects, each exact RED/GREEN/variant/regression and new clean final verification. Any targeted closure confirmation follows that original review's findings; do not schedule another broad acceptance review or per-task reviewer treadmill. Minor observations may be deferred only without violating the acceptance contract. Do not enter Phase 9 from implementer test results; independent acceptance must satisfy design §27 and master Phase 8 exit criteria.

## Planning self-review and execution handoff

| Required self-review | Completed result |
| --- | --- |
| Spec coverage | All design §§1–29 and RPT-01–27 have owners in the coverage map; all nine questions, M1 and real acceptance closure included. No uncovered design requirement found. |
| Step scan | Each task has exact files/signatures, named failing tests and key assertion excerpts, exact RED/GREEN/component commands, scoped minimal implementation, nearby attacks and coherent commit. No implementation body transcript or unspecified semantic policy. |
| Type consistency | Shared scope/native refs/options/QuestionId/ReportSemanticRole and API names consistent. Proposal contracts are introduced before their port/adapters; compiled contract before acceptance/load; stage artifacts are closed typed unions. Read helper reuses accepted upstream validator. |
| Review Focus | Five named tests are owned by Tasks 10, 10, 12, 21 and 20, respectively, including permitted synthesis positive control and canonical transplant attack. |
| Proportion | Focused responsibilities and 24 independently testable gates; code excerpts are signatures/assertions only. No source-code bodies, Phase 7 redesign, report templates as the main architecture or Phase 9 scope. |
| Actual baseline | Exact design HEAD clean; current schema v8, actual SourceRecord ancestry, existing report fixture/summary boundaries, runtime audits, SQL/import guard constraints and next ADR-040 verified. No literal architectural contradiction found. |
| Planning verification | Check relative documentation links, balanced fences, 24 numbered task gates, five Review Focus owners, all RPT IDs, referenced existing files/commands and no unfinished-decision placeholders; run `git diff --check`. No production/test/schema change or implementation test result is claimed by this plan. |

Recommend **Native / task-gated implementation with one final independent whole-phase review**. The 24 gates share scope, dependency, execution, repair-origin and acceptance identities; keeping one implementing context reduces handoff errors while focused attacks and commits retain checkable progression. This recommendation is not execution approval. Prior Phase 7 execution-method authorization does not silently authorize Phase 8.

No planning-critical question remains. Concrete provider/model choice and operational caps can be configured within the locked boundaries; the plan fixes operational defaults without implying live-model quality or cost calibration. Please review this plan and approve the execution method before implementation. Only this implementation plan is committed by the planning task.
