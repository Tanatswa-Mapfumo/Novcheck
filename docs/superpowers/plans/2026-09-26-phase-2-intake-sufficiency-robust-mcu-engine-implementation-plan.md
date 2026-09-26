# Phase 2 — Intake, Sufficiency, and Robust MCU Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Track progress with checkboxes.

**Goal:** Replace the Phase 1 fixture-backed idea-understanding layer with a real, provider-independent semantic pipeline that preserves user intent, assesses what can and cannot be evaluated, creates two independent MCU decompositions, reconciles them into a stable relationship-preserving MCU graph, runs structural decomposition criticism, and supports immutable user overrides/version history.

**Architecture:** Phase 2 implements semantic logic behind the Phase 1 application ports while retaining provider independence. LLM-assisted components consume the existing abstract `LLMProvider` and return strict structured contracts; deterministic code enforces structural ceilings, invariants, versioning, graph consistency, and lifecycle rules. Two decomposition strategies run independently, followed by alignment, reconciliation, and a structural critic. No search, prior-art retrieval, novelty verdict, prosecutor/defender, or evidence adjudication is implemented in this phase.

**Tech Stack:** Existing Python 3.12+ / `uv` / Pydantic v2 / pytest / Pyright / Ruff stack. Reuse the Phase 0 `LLMProvider` abstraction and deterministic mock provider. No concrete LLM SDK or live provider is required for tests. Do not add a vector database, search SDK, HTTP search provider, graph database, or persistence database in Phase 2.

**Spec:** `docs/specs/master-design-spec.md`, especially Sections 5, 9–12, 44, 46–49, 60 Phase 2, 61–62, Appendix E, and the accepted Phase 1 contracts.

## Global Constraints

- Start from the accepted Phase 1 final commit.
- Implement **Phase 2 only**.
- The master spec remains authoritative.
- Missing information MUST create uncertainty or an assessment ceiling; it MUST NOT increase novelty.
- Input length MUST NOT directly determine sufficiency.
- The normalizer MUST preserve the original input and MUST NOT invent an undisclosed mechanism.
- LLM outputs are untrusted until parsed into strict schemas and validated.
- No LLM self-reported confidence is treated as calibrated probability.
- Decomposition must use **Meaningful Contribution Units**, not sentence fragments or bags of keywords.
- Important functional/causal/architectural/procedural relationships must survive decomposition.
- Two decomposition passes MUST be genuinely independent in prompt/context construction; B must not receive A's output.
- Reconciliation MUST preserve disagreement instead of silently forcing consensus.
- Material unresolved decomposition instability MUST lower the maximum permitted assessment resolution for affected contributions.
- User overrides MUST be immutable/versioned and auditable.
- Do not implement search, evidence retrieval, RRF, citation chasing, prior-art equivalence, prosecutor/defender, novelty verdicts, or final novelty scoring.
- No live network calls in default tests.
- Production code MUST NOT import test fixtures.
- External input and model-produced text remain untrusted data.
- No persisted Phase 1 schema may change silently. Incompatible changes require explicit schema-version/migration handling.
- Every semantic component must expose its prompt/rubric version in trace metadata or persisted result metadata.
- Phase 2 is complete only when adversarial MCU/intake fixtures pass structural assertions and the Phase 1 end-to-end slice runs with real Phase 2 understanding components under deterministic mock LLM responses.

## Review Focus

1. **Invented mechanism:** normalization or decomposition fills in technical behavior the user never supplied.
2. **Over-bundling:** a giant MCU looks unique only because independent contributions were combined.
3. **Over-fragmentation:** the contribution-bearing relationship is destroyed into ordinary components.
4. **False sufficiency:** a vague idea receives `ASSESSABLE`/`HIGH_RESOLUTION` merely because the input is long or fluent.
5. **Reconciliation collapse:** two materially different decompositions are merged into false consensus instead of recording instability.

---

## Prerequisite Gate — Accepted Phase 1 Baseline

Before coding:

- base the new branch/worktree on Phase 1 final commit `6be737a` or an accepted descendant;
- run `uv sync --dev` and `uv run python scripts/verify.py`;
- confirm Phase 1 completion documentation remains accurate;
- create a new isolated Phase 2 worktree/branch;
- preserve the accepted Phase 1 worktree until Phase 2 has a clean baseline.

---

## Phase 2 File Map

Prefer focused modules like:

```text
src/novelty_harness/
  intake/
    models.py
    prompts.py
    normalization.py
    sufficiency.py
    pipeline.py
  mcu/
    models.py
    prompts.py
    decomposition.py
    alignment.py
    reconciliation.py
    critic.py
    overrides.py
  runtime/semantic/
    structured.py

tests/
  unit/intake/
  unit/mcu/
  unit/runtime/
  integration/
  adversarial/
  fixtures/phase2.py

docs/
  traceability/phase-2.yaml
  architecture/decisions/
```

If Phase 1 already introduced an equivalent focused module, extend it rather than duplicating responsibility.

---

### Task 1: Add strict semantic-call validation and prompt-version infrastructure

**Files:**
- `src/novelty_harness/runtime/semantic/structured.py`
- `tests/unit/runtime/test_structured_semantic_calls.py`
- `docs/architecture/decisions/ADR-008-phase2-semantic-prompt-versioning.md`

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class SemanticTaskSpec(Generic[T]):
    task_name: str
    prompt_version: str
    output_model: type[T]

async def run_structured_semantic_task(
    *,
    provider: LLMProvider,
    spec: SemanticTaskSpec[T],
    system_instruction: str,
    context: Sequence[ContextBlock],
    config: LLMCallConfig,
) -> T: ...
```

Requirements:
- derive a strict JSON schema from the target Pydantic model;
- validate returned data with the target model;
- reject unknown/missing/invalid nested fields;
- raise a typed `SemanticOutputValidationError` rather than coercing invalid output;
- retain task name, prompt version, provider metadata, request hash, and validation state in traceable metadata;
- treat user/retrieved text as data, never trusted instruction.

Tests: valid output, missing field, unknown field, bad enum, malformed nested structure, prompt-injection-like text in context.

Use TDD, run focused tests/type checks, commit.

---

### Task 2: Implement faithful idea normalization and CIR construction

**Files:**
- `src/novelty_harness/intake/models.py`
- `src/novelty_harness/intake/prompts.py`
- `src/novelty_harness/intake/normalization.py`
- `tests/unit/intake/test_normalization.py`

Add support structures such as:

```python
class InputSpanAttribution(ContractModel):
    field_path: str
    supporting_excerpt: str

class NormalizationResult(ContractModel):
    cir: CanonicalIdeaRepresentation
    extracted_claims: list[str]
    explicit_unknowns: list[str]
    ambiguities: list[str]
    source_attributions: list[InputSpanAttribution]
    prompt_version: str
```

`FaithfulIdeaNormalizer` implements the existing Phase 1 `IdeaNormalizer` port.

Policy:
- preserve original input exactly;
- extract only supported problem/context/claims/constraints;
- never invent mechanism, target user, performance, evidence, or causal relation;
- preserve contradictions and ambiguities;
- distinguish normalized wording from unsupported inference;
- treat “nobody has done this” as a user claim, not evidence;
- require attribution for material normalized fields where practicable.

Required cases: vague one-liner, long mechanism-free idea, explicit mechanism, contradictory description, buzzword-heavy wording, withheld mechanism, unsupported advantage claim, arbitrary specificity, instruction-like text.

Add deterministic post-validation that rejects unsupported material fields when required attribution is absent.

---

### Task 3: Implement structural sufficiency analysis with deterministic ceilings

**Files:**
- `src/novelty_harness/intake/sufficiency.py`
- `tests/unit/intake/test_sufficiency.py`

Contracts:

```python
class SufficiencySignals(ContractModel):
    problem_defined: bool
    contribution_identifiable: bool
    mechanism_described: bool
    relationship_structure_described: bool
    comparison_scope_identifiable: bool
    critical_unknowns: list[str] = Field(default_factory=list)

class SufficiencyReasoning(ContractModel):
    proposed_state: SufficiencyState
    assessable_dimensions: list[str]
    unassessable_dimensions: list[str]
    missing_information: list[str]
    consequences: list[str]
    signals: SufficiencySignals
    prompt_version: str

def apply_sufficiency_ceiling(
    reasoning: SufficiencyReasoning,
    cir: CanonicalIdeaRepresentation,
) -> SufficiencyAssessment: ...
```

Safety rules:
- no identifiable contribution -> `INSUFFICIENT`;
- problem landscape clear but contribution/mechanism not comparable -> maximum `EXPLORATORY`;
- withheld core mechanism -> mechanism dimension unassessable, never `HIGH_RESOLUTION` for that dimension;
- `HIGH_RESOLUTION` requires relationship-level detail for essential contributions and no critical unresolved blocker;
- word count, prose quality, buzzwords, or arbitrary specificity cannot independently raise sufficiency.

Metamorphic tests:
- paraphrase stability;
- irrelevant detail does not increase state;
- removing mechanism lowers/limits state;
- performance claim alone does not improve mechanism sufficiency;
- withheld mechanism creates explicit unassessable dimension.

---

### Task 4: Implement two independent MCU decomposition strategies

**Files:**
- `src/novelty_harness/mcu/models.py`
- `src/novelty_harness/mcu/prompts.py`
- `src/novelty_harness/mcu/decomposition.py`
- `tests/unit/mcu/test_decomposition.py`

Contracts:

```python
class MCUCandidate(ContractModel):
    mcu: MCU
    source_support: list[str]
    rationale: str
    unresolved_questions: list[str] = Field(default_factory=list)

class MCUDecomposition(ContractModel):
    strategy: Literal["INDEPENDENCE_FOCUSED", "RELATIONSHIP_FOCUSED"]
    prompt_version: str
    candidates: list[MCUCandidate]
    global_unknowns: list[str] = Field(default_factory=list)
```

Implement:
- `IndependenceFocusedDecomposer`
- `RelationshipFocusedDecomposer`

Independence rules:
- B must never receive A's output;
- prompts are separately versioned;
- both may share CIR/original input, but not candidate results;
- one run cannot mutate the other.

MCU rules:
- split until independently meaningful, not linguistically atomic;
- preserve contribution-bearing relationships;
- do not create novelty-bearing MCUs from ordinary ingredients when value lies only in their relationship;
- represent meaningful combinations separately;
- arbitrary context specificity does not justify a standalone MCU;
- candidates must trace to user-supported input/CIR content.

Required fixtures: giant bundle, over-fragmented mechanism, known components/new arrangement, multiple independent contributions, renamed concept, application-only difference, withheld mechanism.

---

### Task 5: Implement MCU alignment and explicit disagreement representation

**Files:**
- `src/novelty_harness/mcu/alignment.py`
- `tests/unit/mcu/test_alignment.py`

Contracts:

```python
class MCUAlignmentPair(ContractModel):
    left_mcu_id: MCUId
    right_mcu_id: MCUId
    relation: Literal[
        "EQUIVALENT", "OVERLAPPING", "LEFT_SUBSUMES_RIGHT",
        "RIGHT_SUBSUMES_LEFT", "DISTINCT", "UNRESOLVED"
    ]
    structural_reasons: list[str]
    relationship_differences: list[str]

class DecompositionAlignment(ContractModel):
    pairs: list[MCUAlignmentPair]
    unmatched_left: list[MCUId]
    unmatched_right: list[MCUId]
```

Use deterministic structural checks first: normalized text, feature sets, relationship signatures, source-support overlap. If unresolved, an injected semantic aligner may propose a mapping, but it must pass structural consistency checks.

Never equate text/embedding similarity with MCU equivalence.

Tests: paraphrase equivalence, merge-vs-split disagreement, same nouns/different relation graph, different nouns/same relation graph, ambiguous unresolved mapping.

---

### Task 6: Implement reconciliation and the structural MCU critic

**Files:**
- `src/novelty_harness/mcu/reconciliation.py`
- `src/novelty_harness/mcu/critic.py`
- `tests/unit/mcu/test_reconciliation.py`
- `tests/unit/mcu/test_critic.py`

Contracts:

```python
class StructuralTestResult(ContractModel):
    test_name: Literal[
        "REMOVAL", "INDEPENDENCE", "RELATIONSHIP_PRESERVATION",
        "MERGE", "PARAPHRASE_STABILITY", "SPECIFICITY"
    ]
    mcu_ids: list[MCUId]
    passed: bool | None
    severity: Literal["INFO", "WARNING", "MATERIAL"]
    explanation: str

class ReconciliationResult(ContractModel):
    mcus: list[MCU]
    combinations: list[MCUCombination]
    alignment: DecompositionAlignment
    structural_tests: list[StructuralTestResult]
    unresolved_disagreements: list[str]
    decomposition_stability: Literal[
        "STABLE", "MINOR_DISAGREEMENT", "MATERIAL_DISAGREEMENT"
    ]
    assessment_ceiling: SufficiencyState
```

Critic requirements:
- **Removal:** removing an MCU should remove a meaningful contribution; otherwise flag likely noise/over-fragmentation.
- **Independence:** unit must be independently assessable/comparable.
- **Relationship preservation:** splitting must not destroy the mechanism creating differentiation.
- **Merge:** merging independent units must not manufacture uniqueness.
- **Paraphrase stability:** meaning-preserving paraphrase should yield materially equivalent structure.
- **Specificity:** arbitrary contextual details must not create novelty units.

Deterministic rules handle graph integrity and obvious anti-patterns; semantic critic may handle meaning-level checks via the abstract LLM provider.

Material disagreement must remain visible and must cap high-resolution assessment for affected contributions.

---

### Task 7: Add immutable MCU graph versions and auditable user overrides

**Files:**
- `src/novelty_harness/mcu/overrides.py`
- `tests/unit/mcu/test_overrides.py`
- `docs/architecture/decisions/ADR-009-mcu-version-and-override-model.md`

Contracts:

```python
class MCUOverrideOperation(ContractModel):
    operation_id: str
    kind: Literal[
        "ADD_MCU", "EDIT_MCU", "REMOVE_MCU", "MERGE_MCUS",
        "SPLIT_MCU", "ADD_RELATIONSHIP", "REMOVE_RELATIONSHIP",
        "EDIT_COMBINATION"
    ]
    payload: dict[str, JsonValue]
    reason: str
    actor: str
    occurred_at: datetime

class MCUVersion(ContractModel):
    version_id: str
    parent_version_id: str | None
    created_at: datetime
    created_by: str
    mcus: list[MCU]
    combinations: list[MCUCombination]
    overrides: list[MCUOverrideOperation]
    source_reconciliation_hash: str
```

Behavior:
- every override returns a new version;
- parent remains unchanged;
- actor/reason required;
- reject duplicate IDs, dangling endpoints, invalid combinations/references;
- merge/split preserve provenance in payload;
- no in-place edit API.

Tests: add/edit/remove, merge/split, relationship edits, rollback by choosing parent, invalid references, hash changes when graph semantics change.

---

### Task 8: Build the full Phase 2 understanding pipeline

**Files:**
- `src/novelty_harness/intake/pipeline.py`
- `tests/integration/test_phase2_understanding_pipeline.py`
- `tests/integration/test_phase1_slice_with_phase2_components.py`
- `tests/fixtures/phase2.py`

Interface:

```python
@dataclass(frozen=True, slots=True)
class UnderstandingResult:
    cir: CanonicalIdeaRepresentation
    sufficiency: SufficiencyAssessment
    decomposition_a: MCUDecomposition
    decomposition_b: MCUDecomposition
    reconciliation: ReconciliationResult
    active_mcu_version: MCUVersion

async def understand_idea(... ) -> UnderstandingResult: ...
```

Required flow:
- preserve original input;
- create faithful CIR;
- assess sufficiency before final reconciliation;
- run A/B independently;
- align/reconcile only after both exist;
- run structural critic;
- propagate assessment ceiling from instability;
- create initial immutable MCU version;
- allow the Phase 1 vertical slice to substitute real Phase 2 normalization/sufficiency/MCU components while search/evidence/adjudication remain fixture-backed.

Expose/persist:
- `canonical_idea.json`
- `sufficiency.json`
- `mcu_candidates_A.json`
- `mcu_candidates_B.json`
- `mcu_alignment.json`
- `mcu_reconciliation.json`
- `mcu_graph.json`
- `mcu_version.json`

The existing end-to-end slice must still reach `REPORTED/COMPLETED` with later stages explicitly fixture-backed.

---

### Task 9: Add Phase 2 adversarial/metamorphic regression suite

**Files:**
- `tests/adversarial/test_phase2_mcu_attacks.py`
- extend `tests/fixtures/phase2.py`

Mandatory cases:
1. vague idea -> exploratory/unassessable mechanism;
2. buzzword inflation -> no sufficiency increase;
3. renamed concept -> normalize function without inventing novelty;
4. giant bundle -> split independent contributions;
5. fragmented causal contribution -> relationship restored;
6. arbitrary specificity -> no extra MCU;
7. known components + meaningful configuration -> components and combination represented separately;
8. performance claim/no mechanism -> value claim retained, mechanism sufficiency not increased;
9. withheld mechanism -> explicit unassessable dimension;
10. contradictory specification -> ambiguity retained;
11. paraphrase -> materially stable MCU graph;
12. removal of true differentiator -> structural result changes predictably;
13. different wording/same relationships -> alignable;
14. same words/different relationships -> not forced equivalent.

Metamorphic tests should compare structural properties, not brittle prose.

---

### Task 10: Traceability, architecture guards, and Phase 2 acceptance

**Files:**
- `docs/traceability/phase-2.yaml`
- `docs/phase-2-completion.md`
- update `README.md`
- extend `tests/unit/test_import_boundaries.py`
- create `tests/unit/test_phase2_architecture_guards.py`

Traceability must cover FR-IN and FR-MCU requirements implemented in Phase 2 and explicitly mark Phase 3+ search/evidence semantics deferred.

Architecture guards:
- no concrete LLM/search SDK imported into `domain`, `intake`, or `mcu`;
- no search/patent/web API calls in Phase 2;
- no novelty verdict logic in intake/MCU modules;
- no production imports from tests;
- decomposition B cannot receive A through constructor/function signature;
- overrides are immutable/versioned;
- prompt versions are explicit;
- no word/token-count threshold determines sufficiency.

Final verification:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

Perform fresh-checkout verification if practical and write `docs/phase-2-completion.md`.

---

## Phase 2 Acceptance Gate

Phase 2 is accepted only when all are true:

1. Phase 1 baseline passes before Phase 2 changes.
2. Full verification passes after final Phase 2 change.
3. Normalization preserves original input and does not silently invent unsupported mechanism/context/value claims.
4. Sufficiency is structural rather than length-based.
5. Missing/withheld mechanisms create explicit uncertainty/unassessability.
6. Two independent decomposition strategies exist and B never consumes A's result.
7. MCU output preserves meaningful functional/causal/architectural relationships.
8. Meaningful combinations are represented separately from component novelty.
9. Alignment distinguishes textual similarity from structural equivalence.
10. Reconciliation preserves material disagreement rather than forcing consensus.
11. Removal, independence, relationship-preservation, merge, paraphrase-stability, and specificity tests are represented and executed.
12. Material decomposition instability lowers the assessment ceiling.
13. User overrides create immutable auditable MCU versions.
14. Invalid/dangling graph edits are rejected.
15. Phase 2 adversarial/metamorphic fixtures pass.
16. The Phase 1 end-to-end slice runs with real Phase 2 understanding components and later stages still fixture-backed.
17. No real search/evidence/prior-art/adjudication logic was introduced.
18. No live network service is required by the default suite.
19. README/traceability accurately distinguish implemented Phase 2 semantics from later-phase deferrals.
20. Phase 3 has not started.

If any gate fails, do not begin Phase 3.

## Self-Review Against Master Spec

Phase 2 coverage:
- normalization -> Tasks 1–2;
- sufficiency -> Task 3;
- independent decomposers -> Task 4;
- relationship graph/alignment/reconciliation -> Tasks 4–6;
- structural decomposition tests -> Tasks 6 and 9;
- user override/versioning -> Task 7;
- end-to-end replacement of fixture understanding -> Task 8;
- adversarial cases -> Task 9.

Explicitly deferred:
- evidence-family applicability/query planning/search critic -> Phase 3;
- real provider integrations -> Phase 3;
- multi-strategy retrieval/RRF/adaptive research -> Phase 4;
- provenance/evidence graph -> Phase 5;
- evidence mapping/support verification -> Phase 6;
- prosecutor/defender/adjudication/verdict gates -> Phase 7;
- full report compiler -> Phase 8.

## Execution Handoff

Recommended execution: **isolated worktree + task-gated implementation**. Phase 2 defines the semantic representation that every later research stage depends on, so interface and reasoning errors here have high downstream cost.

Do not start Phase 3 until this phase has been reviewed and explicitly accepted.
