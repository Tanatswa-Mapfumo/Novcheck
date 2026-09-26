# Phase 1 — Deterministic Thin Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the Novelty Assessment Harness end-to-end architecture with deterministic fixture-backed semantic components, final-shape contracts, a full lifecycle run, machine-readable artifacts, and a minimal nine-question Markdown report—without real novelty reasoning or live providers.

**Architecture:** Phase 1 introduces the application/orchestration layer that connects the Phase 0 domain contracts, provider ports, tracing, and lifecycle to a complete assessment run. Semantic operations are represented behind explicit application protocols and are supplied by deterministic fixture implementations in tests; later phases replace those fixtures with real intake, MCU, research, evidence, adjudication, and reporting logic without changing the orchestration shape. The slice writes versioned run artifacts to a directory and compiles the report strictly from frozen structured findings.

**Tech Stack:** Existing Phase 0 stack (Python 3.12+, `uv`, Pydantic v2, pytest, pytest-asyncio, pytest-socket, Ruff, Pyright). Do not add a database, HTTP client, concrete search/LLM SDK, Typer, or live provider in Phase 1 unless a reviewed ADR demonstrates that the vertical slice cannot be implemented without it.

**Spec:** `docs/specs/master-design-spec.md`, especially Sections 8–12, 27, 34–38, 44, 56–57, 60 Phase 1, 61–62, and Appendix D.

## Global Constraints

- The master design spec remains authoritative.
- Phase 1 MUST remain a **thin vertical slice**, not an early implementation of Phase 2–8 semantics.
- Use final-shape/versioned contracts for CIR, sufficiency, MCU, search-plan, evidence-edge, adjudication, and output artifacts even when some fields are empty or fixture-supplied.
- Do not implement real LLM-based idea normalization, sufficiency reasoning, MCU decomposition, query generation, evidence equivalence, prosecutor/defender reasoning, or novelty verdict logic in this phase.
- Do not add real network providers. Existing deterministic mocks remain the only provider implementations used by Phase 1 tests.
- Unit/contract/integration tests MUST remain network-blocked by default.
- The application layer MAY depend on domain, ports, and runtime abstractions. The domain layer MUST NOT depend on application/runtime/provider implementations.
- The report compiler MUST consume frozen findings and MUST NOT mutate or re-decide adjudication.
- All external/retrieved fixture content remains untrusted data.
- Do not invent research budgets, saturation thresholds, confidence scores, or calibrated novelty probabilities.
- Preserve original input separately from normalized structured artifacts.
- Every artifact written by the vertical slice MUST be versioned/serializable and reproducible from deterministic fixtures.
- Every lifecycle stage transition MUST remain explicit and traced.
- Stages whose true semantics belong to later phases MAY be executed through deterministic fixture stage components, but the trace/artifacts MUST make the fixture origin explicit.
- Phase 1 is complete only when the deterministic end-to-end fixture produces both machine-readable artifacts and a Markdown report and the complete repository verification suite passes.

## Prerequisite Gate — Close Remaining Phase 0 Review Findings

Before the first Phase 1 task:

- Read `docs/phase-0-completion.md` and the review material it references.
- Resolve the documented **reranker mapping/rank validation** finding exactly as reviewed.
- Resolve the documented **exception traceback/cause logging** finding exactly as reviewed.
- Add regression tests for both.
- Run `uv run python scripts/verify.py`.
- Commit these fixes separately from Phase 1 work.
- Do not alter master-spec semantics while closing them.

Phase 1 MUST NOT start until this gate passes.

## Review Focus

1. **Fixture leakage:** production orchestration must not accidentally hard-code fixture conclusions or call test modules.
2. **Semantic overreach:** Phase 1 must prove plumbing without implementing fake novelty intelligence that later phases must undo.
3. **Lifecycle truthfulness:** every canonical stage must be represented, but mocked/deferred stage behavior must be explicitly traceable as fixture-backed.
4. **Report mutation:** report generation must not change the frozen adjudication or introduce unsupported factual claims.
5. **Artifact reproducibility:** the same deterministic fixture must produce semantically identical structured artifacts across repeated runs except for explicitly volatile IDs/timestamps supplied by the fixture clock.

---

## Phase 1 File Map

Create or extend the repository toward this shape:

```text
src/novelty_harness/
  application/
    __init__.py
    models.py
    ports.py
    vertical_slice.py
  domain/
    idea.py
    mcu.py
    research.py
    evidence.py
    adjudication.py
    reporting.py
  reporting/
    __init__.py
    minimal.py
  runtime/
    artifacts/
      __init__.py
      writer.py

tests/
  unit/
    test_phase1_domain_contracts.py
    test_application_ports.py
    test_artifact_writer.py
    test_phase1_fixtures.py
    test_minimal_report_compiler.py
    test_phase1_architecture_guards.py
  integration/
    test_phase1_vertical_slice.py
  fixtures/
    phase1.py

docs/
  traceability/
    phase-1.yaml
```

If Phase 0 already introduced an equivalent focused file, extend it rather than duplicating responsibility.

Dependency direction:

```text
domain              <- application models/ports
ports/runtime        <- application orchestration
domain              -X-> application/runtime/concrete providers
reporting            -> frozen domain findings only
tests/fixtures       -> application protocols + existing mock providers
```

---

### Task 1: Add final-shape Phase 1 domain contracts

**Files:**
- Create: `src/novelty_harness/domain/idea.py`
- Create: `src/novelty_harness/domain/mcu.py`
- Create: `src/novelty_harness/domain/research.py`
- Create: `src/novelty_harness/domain/evidence.py`
- Create: `src/novelty_harness/domain/adjudication.py`
- Create: `src/novelty_harness/domain/reporting.py`
- Create: `tests/unit/test_phase1_domain_contracts.py`

**Interfaces:**
- Consumes: `ContractModel`, typed IDs, enums, `JsonValue`.
- Produces the versioned data contracts used by the Phase 1 slice and later phases.

- [ ] **Step 1: Write failing CIR and sufficiency contract tests**

Define CIR/sufficiency contracts matching the master spec:
- `ProblemDescription`
- `IdeaContext`
- `ClaimedAdvantage`
- `CanonicalIdeaRepresentation`
- `SufficiencyAssessment`

Required fields include original input preservation, problem/context, MCU and combination slots, claimed advantages, user evidence, constraints, unknowns, assessable/unassessable dimensions, missing information, and consequences.

Tests must prove:
- unknown fields are rejected;
- original input is retained exactly;
- empty/whitespace-only problem statements are rejected;
- CIR and sufficiency artifacts round-trip via JSON.

- [ ] **Step 2: Write failing MCU contract tests**

Define:
- `MCUFeature`
- `MCURelationship`
- `MCU`
- `MCUCombination`

Structural validation only:
- IDs/labels/statements must be non-blank;
- combination member list must contain at least two distinct MCU IDs;
- do **not** implement decomposition-quality logic yet.

- [ ] **Step 3: Write failing research/evidence contract tests**

Define:
- `PlannedQuery`
- `SearchPlan`
- `EvidenceComparison`
- `EvidenceEdge`

Tests must reject:
- a search plan with zero queries;
- blank query text/rationale;
- an evidence edge with zero passage IDs.

- [ ] **Step 4: Write failing frozen-adjudication/output tests**

Define:
- `MCUFinding`
- `FrozenAdjudication`
- `ReportAnswers`
- `CompiledReport`

All nine canonical report answers must be represented explicitly.

- [ ] **Step 5: Run focused tests and verify failure**

```bash
uv run pytest tests/unit/test_phase1_domain_contracts.py -v
```

Expected: FAIL before implementation.

- [ ] **Step 6: Implement the contracts with structural validation only**

Do not encode novelty heuristics or assessment logic in Pydantic validators.

- [ ] **Step 7: Run tests and typing**

```bash
uv run pytest tests/unit/test_phase1_domain_contracts.py -v
uv run pyright src/novelty_harness/domain
```

- [ ] **Step 8: Commit**

```bash
git add src/novelty_harness/domain tests/unit/test_phase1_domain_contracts.py
git commit -m "feat: add phase one assessment artifact contracts"
```

---

### Task 2: Define application semantic-component ports

**Files:**
- Create: `src/novelty_harness/application/__init__.py`
- Create: `src/novelty_harness/application/models.py`
- Create: `src/novelty_harness/application/ports.py`
- Create: `tests/unit/test_application_ports.py`

**Interfaces:**
- Consumes: Phase 1 domain contracts and existing provider DTOs.
- Produces replaceable semantic-component protocols.

Required async protocols:
- `IdeaNormalizer`
- `SufficiencyAnalyzer`
- `MCUDecomposer`
- `MCUReconciler`
- `SearchPlanner`
- `SearchPlanReviewer`
- `EvidenceMapper`
- `EvidenceVerifier`
- `AdjudicationEngine`

Create a frozen standard-library dataclass `VerticalSliceComponents` containing instances of those protocols. Do not put protocol instances in a persisted Pydantic model.

- [ ] Write runtime-checkable protocol/conformance tests using small local fakes.
- [ ] Verify no application protocol imports test fixtures.
- [ ] Run tests/type checks.
- [ ] Commit:

```bash
git add src/novelty_harness/application tests/unit/test_application_ports.py
git commit -m "feat: define replaceable phase one application ports"
```

---

### Task 3: Add a run-artifact writer with atomic versioned output

**Files:**
- Create: `src/novelty_harness/runtime/artifacts/__init__.py`
- Create: `src/novelty_harness/runtime/artifacts/writer.py`
- Create: `tests/unit/test_artifact_writer.py`

**Interface:**

```python
class RunArtifactWriter:
    def __init__(self, root: Path) -> None: ...
    def assessment_dir(self, assessment_id: AssessmentId) -> Path: ...
    def write_json(self, assessment_id: AssessmentId, relative_name: str, value: BaseModel | JsonValue) -> Path: ...
    def write_jsonl(self, assessment_id: AssessmentId, relative_name: str, values: Sequence[BaseModel | JsonValue]) -> Path: ...
    def write_text(self, assessment_id: AssessmentId, relative_name: str, text: str) -> Path: ...
```

- [ ] Write failing tests asserting:
  - paths cannot escape the assessment directory;
  - JSON uses deterministic UTF-8 serialization;
  - JSONL writes one object per line;
  - final writes use temp-file + atomic replace semantics;
  - the assessment directory is created lazily.

- [ ] Implement.
- [ ] Run:

```bash
uv run pytest tests/unit/test_artifact_writer.py -v
```

- [ ] Commit.

---

### Task 4: Add deterministic fixture-backed semantic components

**Files:**
- Create: `tests/fixtures/phase1.py`
- Extend only if needed: `tests/fixtures/providers.py`
- Create: `tests/unit/test_phase1_fixtures.py`

The synthetic fixture MUST include:
- one `AssessmentRequest`;
- a CIR preserving original input;
- an `ASSESSABLE` sufficiency result;
- at least two MCUs;
- a reviewed `SearchPlan`;
- at least one mock search result and source;
- deterministic passages;
- at least one verified `EvidenceEdge`;
- a fixture `FrozenAdjudication`;
- fixed provider metadata/timestamps.

Important:
- fixture adjudication is **test data**, not the result of Phase 1 novelty reasoning;
- fixture classes use a `Fixture...` prefix;
- production code MUST NOT import `tests.fixtures`;
- fixture/deferred stage trace events must be explicitly marked.

- [ ] Test protocol conformance.
- [ ] Test deterministic repeated outputs.
- [ ] Test no network usage.
- [ ] Commit.

---

### Task 5: Implement the minimal report compiler from frozen findings only

**Files:**
- Create: `src/novelty_harness/reporting/__init__.py`
- Create: `src/novelty_harness/reporting/minimal.py`
- Create: `tests/unit/test_minimal_report_compiler.py`

**Interface:**

```python
def compile_minimal_report(
    *,
    idea: CanonicalIdeaRepresentation,
    sufficiency: SufficiencyAssessment,
    mcus: Sequence[MCU],
    edges: Sequence[EvidenceEdge],
    adjudication: FrozenAdjudication,
) -> CompiledReport:
    ...
```

Rules:
- no provider/LLM/search port is accepted;
- hash serialized frozen adjudication before rendering;
- inputs must not be mutated;
- all nine canonical questions must be answered;
- missing structured evidence becomes explicit unknown/unsupported wording rather than invented content;
- the compiler must not create a new verdict.

- [ ] Write tests for nine headings, frozen-hash preservation, unsupported evidence exclusion, and no verdict mutation.
- [ ] Implement.
- [ ] Run focused tests.
- [ ] Commit.

---

### Task 6: Implement the Phase 1 vertical-slice orchestrator

**Files:**
- Create: `src/novelty_harness/application/vertical_slice.py`
- Create: `tests/integration/test_phase1_vertical_slice.py`

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class VerticalSliceResult:
    ...

async def run_vertical_slice(
    *,
    request: AssessmentRequest,
    components: VerticalSliceComponents,
    search_provider: SearchProvider,
    content_resolver: ContentResolver,
    trace_sink: TraceSink,
    artifact_writer: RunArtifactWriter,
    clock: Callable[[], datetime] = utc_now,
) -> VerticalSliceResult:
    ...
```

The orchestrator must:
1. create the assessment at `RECEIVED/ACTIVE`;
2. persist `request.json`;
3. normalize and advance to `NORMALIZED`;
4. analyze sufficiency and advance to `SUFFICIENCY_ASSESSED`;
5. decompose and advance to `MCU_DECOMPOSED`;
6. reconcile and advance to `MCU_RECONCILED`;
7. build and review search plan;
8. execute deterministic mock screening;
9. record adaptive research as explicitly fixture-backed/deferred;
10. map/verify evidence;
11. record adversarial challenge/defence as fixture-backed/deferred;
12. obtain fixture adjudication;
13. record robustness as fixture-backed/deferred;
14. freeze/persist adjudication;
15. compile report from frozen findings only;
16. persist machine-readable output and Markdown;
17. reach `REPORTED`, then `COMPLETED`.

Required artifacts:

```text
request.json
canonical_idea.json
sufficiency.json
mcu_graph.json
search_plan.json
sources.jsonl
passages.jsonl
evidence_edges.jsonl
adjudication.json
assessment.json
report.json
report.md
trace.jsonl   # when JsonlTraceSink is used
```

The integration test must assert:
- canonical stage order;
- final `REPORTED/COMPLETED`;
- all artifacts deserialize;
- original input preserved;
- all nine report sections exist;
- report adjudication hash matches persisted adjudication;
- no live network;
- no production import from `tests`;
- deferred fixture stages are visible in trace data;
- repeat runs are semantically reproducible apart from intentionally volatile IDs/timestamps.

- [ ] Write failing integration test.
- [ ] Implement minimal orchestration.
- [ ] Run:

```bash
uv run pytest tests/integration/test_phase1_vertical_slice.py -v
```

- [ ] Commit.

---

### Task 7: Add machine-readable assessment summary and traceability

**Files:**
- Create: `docs/traceability/phase-1.yaml`
- Modify: `README.md`
- Extend: `tests/integration/test_phase1_vertical_slice.py`

The run must produce `assessment.json` with:
- id;
- as_of;
- input_sufficiency;
- overall_verdict;
- mcu_findings;
- closest_precedents;
- value_findings;
- evidence_limitations;
- coverage_matrix;
- trace_ref.

Fields whose real semantics are later-phase work may be empty, but must not be populated with fabricated conclusions.

Traceability must mark Phase 1 architecture as implemented and later semantic requirements as deferred.

- [ ] Update tests.
- [ ] Update README accurately.
- [ ] Commit.

---

### Task 8: Add Phase 1 architecture guards and final acceptance gate

**Files:**
- Modify: `tests/unit/test_import_boundaries.py`
- Create: `tests/unit/test_phase1_architecture_guards.py`
- Create: `docs/phase-1-completion.md`

Guards must assert:
- domain does not import application/runtime/test modules/concrete SDKs;
- reporting does not import providers;
- production source has no `tests` imports;
- no concrete network providers were added;
- no numeric novelty/confidence scoring was added;
- report compiler works from frozen findings rather than an adjudicator/provider;
- default test suite remains network-blocked.

- [ ] Run focused architecture tests.
- [ ] Run:

```bash
uv sync --dev
uv run python scripts/verify.py
```

- [ ] Perform a fresh-checkout verification if practical.
- [ ] Write `docs/phase-1-completion.md`.
- [ ] Commit.

---

## Phase 1 Acceptance Gate

Phase 1 is accepted only when all are true:

1. The two remaining Phase 0 review findings are closed with regression tests.
2. Clean dependency install succeeds.
3. `uv run python scripts/verify.py` exits 0 after the final change.
4. CIR, sufficiency, MCU, search-plan, evidence-edge, frozen-adjudication, and report contracts serialize/round-trip.
5. The application layer uses replaceable semantic component protocols; fixture implementations are not imported by production code.
6. One deterministic synthetic idea traverses the canonical lifecycle to `REPORTED/COMPLETED`.
7. Every deferred stage is explicitly marked fixture-backed/deferred in trace data.
8. Only deterministic mock providers are used; no network is required.
9. At least one search result, passage, verified evidence edge, and frozen adjudication flow through the slice.
10. The report answers all nine canonical questions.
11. Report generation cannot mutate or re-decide frozen adjudication.
12. Machine-readable assessment output and Markdown report are produced.
13. Required run artifacts deserialize from disk.
14. Original user input is retained independently of CIR.
15. Domain/provider/import boundaries remain intact.
16. README and Phase 1 traceability accurately distinguish architecture from deferred semantics.
17. No Phase 2 semantic MCU/intake logic, real provider integration, equivalence engine, prosecutor/defender, or calibrated scoring has been implemented.

If any gate fails, do not begin Phase 2.

---

## Self-Review Against the Master Spec

### Spec coverage
Phase 1 requirements are covered: idea intake, fixture-backed sufficiency, MCU creation, mocked search plan, evidence mapping, frozen adjudication, minimal nine-question report, machine-readable output, and deterministic end-to-end execution.

### Semantic safety
The plan intentionally defers the true logic assigned to Phases 2–8. Phase 1 proves replaceability and data flow only.

### Review-focus coverage
- Fixture leakage -> Tasks 2, 4, 8.
- Semantic overreach -> Global constraints, Tasks 4, 6, 8.
- Lifecycle truthfulness -> Task 6.
- Report mutation -> Task 5.
- Artifact reproducibility -> Tasks 3, 4, 6.

## Execution Handoff

Recommended execution approach: **task-gated/subagent-driven if available**. Do not start Phase 2 until this acceptance gate has been reviewed and explicitly accepted.
