# Phase 0 — Repository, Governance, and Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` when available. Otherwise follow this plan task-by-task with the same TDD, review, and verification gates. Track steps with the checkboxes below.

**Goal:** Create the project skeleton, governance rules, typed domain contracts, lifecycle state machine, configuration, provider ports, trace/logging contracts, deterministic mocks, and verification tooling required by every later phase of the Novelty Assessment Harness.

**Architecture:** Phase 0 establishes a provider-independent Python domain using Pydantic contracts and explicit ports. It deliberately does **not** implement novelty research, MCU generation, search, evidence adjudication, or reporting. The phase creates stable interfaces and test/trace infrastructure so later phases can add semantics without rewriting foundational types.

**Tech Stack:** Python 3.12+, `uv`, Pydantic v2, `pydantic-settings`, pytest, pytest-asyncio, pytest-socket, Ruff, Pyright, standard-library structured logging/JSONL tracing. Typer, SQLAlchemy, HTTPX, concrete search providers, and concrete LLM SDKs are deferred until the first phase that actually uses them.

**Spec:** `docs/specs/master-design-spec.md`, especially Sections 0, 5, 7–8, 42–44, 46–47, 54, 58–62, and Phase 0 in Section 60.

## Global Constraints

- The master design spec is authoritative for system behavior.
- Implement **Phase 0 only**. No real search, LLM, embeddings, evidence mapping, MCU generation, adjudication, or report generation.
- Python MUST be 3.12+.
- Use a `src/` package layout with import package `novelty_harness`.
- Use Pydantic v2 for persisted/serialized contracts.
- Domain code MUST NOT import concrete external provider SDKs.
- Provider interfaces are asynchronous from the start so later network adapters do not require breaking API changes.
- Unit and provider-contract tests MUST make no live network calls.
- External/retrieved content is untrusted data; Phase 0 types must not introduce any mechanism that treats content as executable instructions.
- API keys/secrets MUST NOT appear in configuration dumps, traces, fixtures, or committed files.
- Use timezone-aware UTC timestamps in persisted events.
- Schema/model classes MUST reject unknown fields unless the plan explicitly says otherwise.
- Do not assign numerical meanings to novelty, search coverage, saturation, or verdict confidence in Phase 0.
- Do not hardcode default research budgets or saturation thresholds; the master spec deliberately defers them.
- A phase is complete only when clean install, lint, format check, type check, unit/contract tests, and the Phase 0 smoke flow pass.

## Review Focus

The following failure modes are most likely to create expensive downstream semantic drift. Each is pinned to a task/test below.

1. **Lifecycle ambiguity:** abstention/partial results must remain reportable and resumable without corrupting the canonical processing stage. Task 4 separates pipeline stage from run status and tests the allowed transitions.
2. **Silent schema drift:** unknown fields or incompatible enum strings must not be accepted silently. Tasks 2–3 test `extra="forbid"`, enum serialization, and round trips.
3. **Secret leakage:** configuration/tracing must not serialize credential values. Tasks 5 and 7 include explicit redaction/non-storage tests.
4. **Concrete-provider coupling:** the domain layer must not depend on vendor SDKs or concrete adapters. Task 6 defines ports and tests mock conformance; Task 9 includes an import-boundary check.
5. **Hidden network usage:** unit/contract suites must fail if code opens a socket. Task 8 configures and tests global network blocking.

---

## Phase 0 File Map

The implementation should finish Phase 0 with this shape (files created by later phases are intentionally omitted):

```text
novelty-harness/
  AGENTS.md
  README.md
  pyproject.toml
  uv.lock
  scripts/
    verify.py
  docs/
    specs/
      master-design-spec.md
    architecture/
      decisions/
        ADR-001-tooling-stack.md
        ADR-002-lifecycle-stage-and-status.md
    superpowers/
      plans/
        2026-09-26-phase-0-repository-governance-contracts.md
    traceability/
      phase-0.yaml
  src/
    novelty_harness/
      __init__.py
      domain/
        __init__.py
        base.py
        enums.py
        ids.py
        assessment.py
        state_machine.py
      ports/
        __init__.py
        models.py
        search.py
        content.py
        citations.py
        llm.py
        embeddings.py
        reranking.py
      runtime/
        __init__.py
        config/
          __init__.py
          models.py
          loader.py
        tracing/
          __init__.py
          models.py
          sinks.py
          hashing.py
        logging.py
  tests/
    conftest.py
    unit/
      test_base_contracts.py
      test_enums_and_ids.py
      test_assessment_models.py
      test_state_machine.py
      test_config.py
      test_port_models.py
      test_tracing.py
    contract/
      provider_contracts.py
      test_mock_provider_contracts.py
    integration/
      test_phase0_smoke.py
    fixtures/
      __init__.py
      providers.py
```

### Dependency direction fixed by this plan

```text
runtime/config  ---> domain value types only
runtime/tracing ---> domain IDs/enums only
ports           ---> domain/base value types only
domain          -X-> runtime
 domain         -X-> concrete provider SDKs
```

Later application services may depend on both `domain` and `ports`; Phase 0 does not create those services yet.

---

### Task 1: Bootstrap repository governance and deterministic quality tooling

**Files:**
- Create: `pyproject.toml`
- Create: `src/novelty_harness/__init__.py`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `scripts/verify.py`
- Create: `docs/specs/master-design-spec.md` (copy the approved master spec verbatim)
- Create: `docs/architecture/decisions/ADR-001-tooling-stack.md`
- Create: `tests/unit/test_base_contracts.py` with the initial package-import test only; later tasks extend it

**Interfaces:**
- Consumes: approved master spec.
- Produces: importable `novelty_harness` package; one deterministic repository verification command: `uv run python scripts/verify.py`.

- [ ] **Step 1: Create the minimal `pyproject.toml` and package stub**

Use:

```toml
[project]
name = "novelty-assessment-harness"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2,<3",
  "pydantic-settings>=2,<3",
]

[dependency-groups]
dev = [
  "pyright",
  "pytest",
  "pytest-asyncio",
  "pytest-socket",
  "ruff",
]
```

Configure Ruff for Python 3.12 and a 100-character line length. Configure Pyright in strict mode for `src/novelty_harness`. Configure pytest with strict markers/config; network blocking is added in Task 8.

Do not add Typer, SQLAlchemy, HTTPX, LLM SDKs, or search SDKs in Phase 0 because they are not used yet.

- [ ] **Step 2: Write the package import/version test**

In `tests/unit/test_base_contracts.py`:

```python
def test_package_exposes_version() -> None:
    import novelty_harness

    assert novelty_harness.__version__ == "0.1.0"
```

- [ ] **Step 3: Run the focused test and verify it fails before `__version__` is implemented**

Run:

```bash
uv sync --dev
uv run pytest tests/unit/test_base_contracts.py::test_package_exposes_version -v
```

Expected: FAIL because `__version__` is absent or incorrect.

- [ ] **Step 4: Implement `__version__` and repository documentation**

`src/novelty_harness/__init__.py` must expose only:

```python
__version__: str = "0.1.0"
```

Copy the approved master spec verbatim to `docs/specs/master-design-spec.md`. Copy the reviewed root `AGENTS.md` into the repository. `README.md` must state that the project is phase-gated and point to the master spec and current phase plans; do not describe unimplemented behavior as working.

Create `ADR-001-tooling-stack.md` documenting the Phase 0 choices above and why unused runtime dependencies are deferred until first use.

- [ ] **Step 5: Implement `scripts/verify.py`**

The script is invoked as `uv run python scripts/verify.py`. Inside that activated environment it must execute these commands in order and exit immediately on a non-zero return code:

```text
ruff check .
ruff format --check .
pyright
pytest
```

Use `subprocess.run(..., check=True)`; do not duplicate tool logic in Python and do not recursively invoke `uv run` from inside the verification script.

- [ ] **Step 6: Run package/quality smoke checks**

Run:

```bash
uv run pytest tests/unit/test_base_contracts.py -v
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock README.md AGENTS.md scripts/verify.py docs/specs docs/architecture src/novelty_harness/__init__.py tests/unit/test_base_contracts.py
git commit -m "chore: bootstrap novelty harness repository"
```

---

### Task 2: Define canonical enums and typed identifiers

**Files:**
- Create: `src/novelty_harness/domain/__init__.py`
- Create: `src/novelty_harness/domain/enums.py`
- Create: `src/novelty_harness/domain/ids.py`
- Create: `tests/unit/test_enums_and_ids.py`

**Interfaces:**
- Consumes: Python/Pydantic baseline from Task 1.
- Produces: stable string enums and validated ID aliases used by every later contract.

- [ ] **Step 1: Write failing enum serialization tests**

Tests must assert exact string values for:

```text
AssessmentStage:
RECEIVED, NORMALIZED, SUFFICIENCY_ASSESSED, MCU_DECOMPOSED,
MCU_RECONCILED, SEARCH_PLANNED, SEARCH_PLAN_REVIEWED, SCREENING,
ADAPTIVE_RESEARCH, EVIDENCE_NORMALIZED, EVIDENCE_MAPPED,
EVIDENCE_VERIFIED, ADVERSARIAL_CHALLENGE, DEFENCE_REVIEW,
PRELIMINARY_ADJUDICATION, ROBUSTNESS_REVIEW, FINDINGS_FROZEN, REPORTED

AssessmentStatus:
ACTIVE, PARTIAL, ABSTAINED, BLOCKED, FAILED, COMPLETED

SufficiencyState:
INSUFFICIENT, EXPLORATORY, ASSESSABLE, HIGH_RESOLUTION

ResearchDepth:
INACTIVE, SCREENING, STANDARD, DEEP, ESCALATED, SATURATED,
BUDGET_STOPPED, ACCESS_BLOCKED

ResearchMode:
QUICK, STANDARD, DEEP, MAXIMUM

EvidenceFamily:
SCHOLARLY, PATENT, SOFTWARE, PRODUCT, GENERAL_WEB, STANDARDS,
REGULATORY_GOVERNMENT, GREY_LITERATURE, HISTORICAL_ARCHIVAL

EvidenceTier:
A, B, C, D

ValueMaturity:
CLAIMED, PLAUSIBLE, SUPPORTED, DEMONSTRATED

PrecedentState:
DIRECT_PRECEDENT, STRONG_PARTIAL_PRECEDENT, COMPONENT_PRECEDENT_ONLY,
ANALOGOUS_PRECEDENT, SUPERFICIAL_SIMILARITY,
NO_DIRECT_PRECEDENT_IDENTIFIED, CONTRADICTORY_EVIDENCE, UNRESOLVED,
UNASSESSABLE

SupportVerificationState:
SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, INSUFFICIENT_CONTEXT,
CONTRADICTED

VerdictState:
STRONG_EVIDENCE_OF_NOVELTY, POTENTIALLY_NOVEL,
MIXED_CONTRIBUTION_SPECIFIC, NOT_NOVEL_AT_CLAIMED_LEVEL, UNASSESSABLE

TraceStatus:
SUCCESS, FAILURE, SKIPPED, DEGRADED
```

`FailureClass` must contain every failure class listed in master-spec Section 46 verbatim.

- [ ] **Step 2: Run tests and verify missing definitions fail**

Run:

```bash
uv run pytest tests/unit/test_enums_and_ids.py -v
```

Expected: FAIL from missing enum/ID modules.

- [ ] **Step 3: Implement enums as `str, Enum`**

All persisted enum values must equal their member names exactly so JSON/YAML artifacts are stable and human-readable.

- [ ] **Step 4: Write failing typed-ID validation/factory tests**

Define aliases/factories for:

```text
AssessmentId -> prefix "asm_"
IdeaId       -> prefix "idea_"
MCUId        -> prefix "mcu_"
SourceId     -> prefix "src_"
PassageId    -> prefix "pass_"
EvidenceEdgeId -> prefix "edge_"
QueryId      -> prefix "qry_"
SearchRunId  -> prefix "run_"
TraceEventId -> prefix "trace_"
LifecycleEventId -> prefix "life_"
```

Tests must assert:

- factory output uses the correct prefix;
- two calls produce different opaque IDs;
- validated aliases reject the wrong prefix and empty suffix;
- all IDs serialize as strings.

Factories use UUID4-derived opaque suffixes in Phase 0. Stable content-derived source/passage IDs are introduced only when source normalization exists; do not pretend Phase 0 random IDs satisfy that later requirement.

- [ ] **Step 5: Implement ID aliases and factories**

Use Pydantic-compatible `Annotated[str, StringConstraints(...)]` aliases. Keep factory names explicit, e.g. `new_assessment_id() -> AssessmentId`.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/test_enums_and_ids.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/novelty_harness/domain tests/unit/test_enums_and_ids.py
git commit -m "feat: add canonical domain enums and identifiers"
```

---

### Task 3: Establish versioned Pydantic base contracts and assessment records

**Files:**
- Create: `src/novelty_harness/domain/base.py`
- Create: `src/novelty_harness/domain/assessment.py`
- Modify: `tests/unit/test_base_contracts.py`
- Create: `tests/unit/test_assessment_models.py`

**Interfaces:**
- Consumes: enums/ID aliases from Task 2.
- Produces:
  - `ContractModel`
  - `utc_now() -> datetime`
  - `AssessmentRequest`
  - `AssessmentRecord`
  - `LifecycleEvent`

- [ ] **Step 1: Add failing base-contract tests**

Required assertions:

```python
class ExampleContract(ContractModel):
    value: str

assert ExampleContract(value="x").schema_version == "0.1"
```

Also assert:

- unknown fields raise Pydantic validation error;
- `model_dump(mode="json")` is JSON-serializable;
- `utc_now()` returns timezone-aware UTC.

- [ ] **Step 2: Implement `ContractModel` and `utc_now()`**

`ContractModel` must use Pydantic `ConfigDict(extra="forbid")` and include:

```python
schema_version: Literal["0.1"] = "0.1"
```

Do not globally freeze all future contracts; immutability decisions belong to individual models.

- [ ] **Step 3: Add failing assessment-model tests**

`AssessmentRequest` fields:

```python
class AssessmentRequest(ContractModel):
    idea_id: IdeaId
    input_text: str
    as_of: date
    mode: ResearchMode = ResearchMode.STANDARD
    title: str | None = None
    user_evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
```

Use `Field(default_factory=...)` for mutable fields and require `input_text` after trimming to contain at least one non-whitespace character.

`AssessmentRecord` fields:

```python
class AssessmentRecord(ContractModel):
    assessment_id: AssessmentId
    request: AssessmentRequest
    stage: AssessmentStage = AssessmentStage.RECEIVED
    status: AssessmentStatus = AssessmentStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
```

`LifecycleEvent` fields:

```python
class LifecycleEvent(ContractModel):
    event_id: LifecycleEventId
    assessment_id: AssessmentId
    event_type: Literal["STAGE_TRANSITION", "STATUS_TRANSITION"]
    from_value: str
    to_value: str
    actor: str
    reason: str
    occurred_at: datetime
```

Tests must cover round-trip JSON serialization and empty-input rejection.

- [ ] **Step 4: Run failing tests**

```bash
uv run pytest tests/unit/test_base_contracts.py tests/unit/test_assessment_models.py -v
```

Expected: FAIL from missing assessment models.

- [ ] **Step 5: Implement assessment contracts**

Use validators only for structural constraints. Do not infer or normalize idea content in Phase 0.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/test_base_contracts.py tests/unit/test_assessment_models.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/novelty_harness/domain/base.py src/novelty_harness/domain/assessment.py tests/unit/test_base_contracts.py tests/unit/test_assessment_models.py
git commit -m "feat: add versioned assessment contracts"
```

---

### Task 4: Implement lifecycle stage/status state machine without conflating abstention with processing stage

**Files:**
- Create: `src/novelty_harness/domain/state_machine.py`
- Create: `tests/unit/test_state_machine.py`
- Create: `docs/architecture/decisions/ADR-002-lifecycle-stage-and-status.md`

**Interfaces:**
- Consumes: `AssessmentRecord`, `LifecycleEvent`, stage/status enums.
- Produces:

```python
def can_advance_stage(current: AssessmentStage, target: AssessmentStage) -> bool: ...

def advance_stage(
    record: AssessmentRecord,
    target: AssessmentStage,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> tuple[AssessmentRecord, LifecycleEvent]: ...

def can_change_status(current: AssessmentStatus, target: AssessmentStatus) -> bool: ...

def change_status(
    record: AssessmentRecord,
    target: AssessmentStatus,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> tuple[AssessmentRecord, LifecycleEvent]: ...

def complete_assessment(
    record: AssessmentRecord,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> tuple[AssessmentRecord, LifecycleEvent]: ...
```

- [ ] **Step 1: Write failing canonical-stage transition tests**

Tests must assert:

- every adjacent transition in Section 8 succeeds;
- skipping a stage fails;
- moving backward fails;
- advancing from `REPORTED` fails;
- `BLOCKED`, `FAILED`, or `COMPLETED` records cannot advance stage;
- `PARTIAL` and `ABSTAINED` records may continue advancing so they can still produce frozen findings/reports.

- [ ] **Step 2: Write failing status-transition tests**

Use this Phase 0 status policy:

```text
ACTIVE -> PARTIAL | ABSTAINED | BLOCKED | FAILED
PARTIAL -> ACTIVE | ABSTAINED | BLOCKED | FAILED
ABSTAINED -> ACTIVE | PARTIAL | BLOCKED | FAILED
BLOCKED -> ACTIVE | FAILED
FAILED -> (none)
COMPLETED -> (none)
```

`COMPLETED` may be entered only through `complete_assessment()` and only when stage is `REPORTED`.

This separation is an implementation representation of the master spec's lifecycle plus additional partial/abstained/blocked/failed states; it preserves the ability to report an abstained or partial assessment instead of making those labels destroy pipeline progress.

- [ ] **Step 3: Run tests and verify failure**

```bash
uv run pytest tests/unit/test_state_machine.py -v
```

Expected: FAIL from missing state machine.

- [ ] **Step 4: Implement pure transition logic**

Requirements:

- functions return copied `AssessmentRecord` values; do not mutate the input instance in place;
- update `updated_at` to the transition timestamp;
- every successful change returns a `LifecycleEvent` containing old/new value, actor, reason, and UTC timestamp;
- invalid transitions raise a dedicated `InvalidLifecycleTransition(ValueError)` containing current/target values;
- actor and reason must be non-empty after trimming.

- [ ] **Step 5: Document the representation decision**

`ADR-002-lifecycle-stage-and-status.md` must explain why Phase 0 models pipeline `stage` separately from run `status`, show how this maps to master-spec Section 8, and state that this is representational rather than a change to verdict semantics.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/test_state_machine.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/novelty_harness/domain/state_machine.py tests/unit/test_state_machine.py docs/architecture/decisions/ADR-002-lifecycle-stage-and-status.md
git commit -m "feat: add auditable assessment lifecycle state machine"
```

---

### Task 5: Add safe configuration and budget contracts without inventing research thresholds

**Files:**
- Create: `src/novelty_harness/runtime/__init__.py`
- Create: `src/novelty_harness/runtime/config/__init__.py`
- Create: `src/novelty_harness/runtime/config/models.py`
- Create: `src/novelty_harness/runtime/config/loader.py`
- Create: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `ResearchMode`.
- Produces:

```python
class BudgetLimits(ContractModel): ...
class HarnessSettings(BaseSettings): ...
def load_settings() -> HarnessSettings: ...
```

- [ ] **Step 1: Write failing budget/config tests**

`BudgetLimits` contains optional non-negative limits, all defaulting to `None`:

```text
max_provider_calls
max_llm_input_tokens
max_llm_output_tokens
max_elapsed_seconds
max_retrieved_documents
max_full_text_fetches
max_deep_search_rounds
```

Tests must prove Phase 0 does **not** silently invent a research budget.

`HarnessSettings` fields:

```text
data_dir: Path = Path(".novelty-harness")
research_mode: ResearchMode = STANDARD
log_level: str = "INFO"
budget: BudgetLimits = empty/unbounded
```

Environment prefix: `NOVELTY_`.

- [ ] **Step 2: Write secret-safety tests**

The settings model must contain no fields named/typed as provider API keys or tokens in Phase 0. Test that representative environment variables such as `OPENAI_API_KEY` or `GITHUB_TOKEN` do not appear anywhere in `HarnessSettings.model_dump()`.

Future provider adapters may read credential references from environment-specific code; those secret values must not become part of general serialized run settings.

- [ ] **Step 3: Run failing tests**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: FAIL from missing config modules.

- [ ] **Step 4: Implement settings models/loader**

Use `pydantic-settings`. Reject negative budget values. Normalize `log_level` to an allowed set: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

Do not map `ResearchMode` to hardcoded budget numbers in Phase 0; that is explicitly deferred by the master spec.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/novelty_harness/runtime/config tests/unit/test_config.py
git commit -m "feat: add safe harness configuration contracts"
```

---

### Task 6: Define provider-neutral ports and transport contracts

**Files:**
- Create: `src/novelty_harness/ports/__init__.py`
- Create: `src/novelty_harness/ports/models.py`
- Create: `src/novelty_harness/ports/search.py`
- Create: `src/novelty_harness/ports/content.py`
- Create: `src/novelty_harness/ports/citations.py`
- Create: `src/novelty_harness/ports/llm.py`
- Create: `src/novelty_harness/ports/embeddings.py`
- Create: `src/novelty_harness/ports/reranking.py`
- Create: `tests/contract/provider_contracts.py`
- Create: `tests/unit/test_port_models.py`

**Interfaces:**
- Consumes: base contracts, IDs, `EvidenceFamily`.
- Produces: async `Protocol` interfaces matching master-spec Section 42 and reusable provider DTOs.

- [ ] **Step 1: Write failing provider DTO tests in `tests/unit/test_port_models.py`**

Define these Pydantic models in `ports/models.py`:

```python
class ProviderCallMetadata(ContractModel):
    provider_name: str
    provider_version: str | None = None
    started_at: datetime
    finished_at: datetime
    request_hash: str
    status: TraceStatus
    failure_code: str | None = None

class ProviderCapabilities(ContractModel):
    evidence_families: set[EvidenceFamily] = set()
    supports_pagination: bool = False
    supports_full_text: bool = False
    supports_backward_citations: bool = False
    supports_forward_citations: bool = False

class ProviderHealth(ContractModel):
    healthy: bool
    detail: str | None = None

class SearchQuery(ContractModel):
    query_id: QueryId
    text: str
    evidence_family: EvidenceFamily
    purpose: str
    filters: dict[str, JsonValue] = {}

class SourceRef(ContractModel):
    provider_name: str
    provider_source_id: str
    canonical_url: str | None = None
    title: str | None = None

class SearchResult(ContractModel):
    source: SourceRef
    rank: int
    snippet: str | None = None
    metadata: dict[str, JsonValue] = {}

class SearchPage(ContractModel):
    results: list[SearchResult]
    next_cursor: str | None = None
    call: ProviderCallMetadata

class SourceContent(ContractModel):
    source: SourceRef
    text: str | None
    content_type: str | None = None
    call: ProviderCallMetadata

class Passage(ContractModel):
    passage_id: PassageId
    source: SourceRef
    text: str
    locator: str | None = None

class CitationLink(ContractModel):
    source: SourceRef
    related: SourceRef
    relation: Literal["BACKWARD_CITATION", "FORWARD_CITATION", "RELATED"]

class CitationResult(ContractModel):
    links: list[CitationLink]
    call: ProviderCallMetadata

class EmbeddingResult(ContractModel):
    vectors: list[list[float]]
    call: ProviderCallMetadata

class ContextBlock(ContractModel):
    label: str
    text: str
    trusted_instruction: bool = False

class LLMCallConfig(ContractModel):
    model: str | None = None
    temperature: float | None = None
    metadata: dict[str, JsonValue] = {}

class StructuredResult(ContractModel):
    data: dict[str, JsonValue]
    raw_text: str | None = None
    call: ProviderCallMetadata

class RankedCandidate(ContractModel):
    candidate_id: str
    score: float
    rank: int

class RerankResult(ContractModel):
    candidates: list[RankedCandidate]
    call: ProviderCallMetadata
```

`ContextBlock.trusted_instruction` MUST default to `False`; later evidence adapters must not mark retrieved content as trusted instructions.

- [ ] **Step 2: Run focused tests and verify missing models fail**

```bash
uv run pytest tests/unit/test_port_models.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement DTOs and async protocols**

Required protocol signatures:

```python
@runtime_checkable
class SearchProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def search(self, query: SearchQuery, cursor: str | None = None) -> SearchPage: ...
    async def capabilities(self) -> ProviderCapabilities: ...
    async def health(self) -> ProviderHealth: ...

@runtime_checkable
class ContentResolver(Protocol):
    @property
    def name(self) -> str: ...
    async def resolve(self, source_ref: SourceRef) -> SourceContent: ...
    async def resolve_passage(self, source_ref: SourceRef, locator: str) -> Passage: ...

@runtime_checkable
class CitationProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def backward_citations(self, source_ref: SourceRef) -> CitationResult: ...
    async def forward_citations(self, source_ref: SourceRef) -> CitationResult: ...
    async def related(self, source_ref: SourceRef) -> CitationResult: ...

@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def generate_structured(
        self,
        *,
        task: str,
        schema: dict[str, JsonValue],
        context: Sequence[ContextBlock],
        config: LLMCallConfig,
    ) -> StructuredResult: ...

@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...

@runtime_checkable
class Reranker(Protocol):
    @property
    def name(self) -> str: ...
    async def rank(
        self,
        query_representation: str,
        candidates: Sequence[str],
    ) -> RerankResult: ...
```

- [ ] **Step 4: Add reusable contract assertion helpers**

`tests/contract/provider_contracts.py` must expose async helper functions such as:

```python
async def assert_search_provider_contract(provider: SearchProvider) -> None: ...
async def assert_content_resolver_contract(provider: ContentResolver) -> None: ...
async def assert_citation_provider_contract(provider: CitationProvider) -> None: ...
async def assert_llm_provider_contract(provider: LLMProvider) -> None: ...
async def assert_embedding_provider_contract(provider: EmbeddingProvider) -> None: ...
async def assert_reranker_contract(provider: Reranker) -> None: ...
```

These helpers become the shared suite later concrete adapters must pass.

- [ ] **Step 5: Run type and contract tests**

```bash
uv run pyright src/novelty_harness/ports tests/contract/provider_contracts.py tests/unit/test_port_models.py
uv run pytest tests/unit/test_port_models.py -v
```

Expected: provider DTO tests PASS and the reusable contract-helper module type-checks. Collected end-to-end provider contract tests are added with mocks in Task 8.

- [ ] **Step 6: Commit**

```bash
git add src/novelty_harness/ports tests/contract/provider_contracts.py tests/unit/test_port_models.py
git commit -m "feat: define provider-neutral application ports"
```

---

### Task 7: Implement append-only tracing, canonical hashing, secret redaction, and JSON logging

**Files:**
- Create: `src/novelty_harness/runtime/tracing/__init__.py`
- Create: `src/novelty_harness/runtime/tracing/models.py`
- Create: `src/novelty_harness/runtime/tracing/hashing.py`
- Create: `src/novelty_harness/runtime/tracing/sinks.py`
- Create: `src/novelty_harness/runtime/logging.py`
- Create: `tests/unit/test_tracing.py`

**Interfaces:**
- Consumes: IDs, `TraceStatus`, Pydantic base contracts.
- Produces:

```python
class TraceEvent(ContractModel): ...
class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...
class JsonlTraceSink: ...
class InMemoryTraceSink: ...
def canonical_hash(value: JsonValue | BaseModel) -> str: ...
def redact_mapping(value: Mapping[str, object]) -> dict[str, object]: ...
def configure_logging(level: str) -> None: ...
```

- [ ] **Step 1: Write failing canonical-hash tests**

Assert:

- dictionary key order does not change the SHA-256 hash;
- changing a value changes the hash;
- the same Pydantic model produces the same hash across repeated calls.

- [ ] **Step 2: Write failing trace-model/sink tests**

`TraceEvent` fields:

```text
event_id: TraceEventId
assessment_id: AssessmentId
occurred_at: datetime
stage: AssessmentStage
component: str
status: TraceStatus
mcu_id: MCUId | None
provider_name: str | None
provider_version: str | None
request_hash: str | None
response_hash: str | None
latency_ms: float | None
estimated_cost: float | None
input_tokens: int | None
output_tokens: int | None
reason_code: str | None
data: dict[str, JsonValue]
```

Tests must assert:

- JSONL sink writes one valid JSON object per event;
- a second emit appends rather than replaces the first line;
- `InMemoryTraceSink.events` preserves order;
- negative latency/token/cost values are rejected.

- [ ] **Step 3: Write failing redaction tests**

`redact_mapping()` must recursively replace values whose case-insensitive key contains any of:

```text
api_key, apikey, access_token, refresh_token, auth_token, password, secret, authorization, bearer
```

with the literal string `[REDACTED]`. Match normalized sensitive names/suffixes rather than the generic substring `token`, so harmless fields such as `input_tokens` and `output_tokens` remain visible.

This is defense-in-depth, not permission to put secrets into traces.

- [ ] **Step 4: Run tests and verify failure**

```bash
uv run pytest tests/unit/test_tracing.py -v
```

Expected: FAIL.

- [ ] **Step 5: Implement tracing/hashing/redaction**

Use canonical JSON with sorted keys and stable separators for hashing. Use a process-local lock around append writes in `JsonlTraceSink` so two threads do not interleave one JSON line.

- [ ] **Step 6: Implement structured standard-library logging**

`configure_logging(level)` must install a JSON formatter containing at least `timestamp`, `level`, `logger`, and `message`. Do not attach assessment semantics to normal logs; durable assessment decisions belong in `TraceEvent`.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/unit/test_tracing.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/novelty_harness/runtime/tracing src/novelty_harness/runtime/logging.py tests/unit/test_tracing.py
git commit -m "feat: add auditable tracing and structured logging"
```

---

### Task 8: Add deterministic mock providers, shared contract tests, and hard network blocking

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/providers.py`
- Create: `tests/contract/test_mock_provider_contracts.py`
- Create: `tests/conftest.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: provider ports/DTOs from Task 6, trace metadata model.
- Produces: deterministic mocks reusable by Phase 1+ integration tests.

- [ ] **Step 1: Configure pytest network blocking**

In pytest configuration, add `--disable-socket` (from `pytest-socket`) to the default test options. Do not globally allow hosts.

Add markers now for future suites:

```text
unit
contract
integration
network
```

The `network` marker is descriptive only; live-network tests must later be executed in a separate explicitly opt-in command that removes/overrides socket blocking.

- [ ] **Step 2: Write a test proving ordinary socket access is blocked**

In `tests/conftest.py` or a small collected test, attempt a TCP socket connection and assert `pytest_socket.SocketBlockedError`.

The test must not depend on DNS or an external host actually being reachable; the plugin should reject before network I/O.

- [ ] **Step 3: Implement deterministic mock providers**

`tests/fixtures/providers.py` must implement:

```text
MockSearchProvider
MockContentResolver
MockCitationProvider
MockLLMProvider
MockEmbeddingProvider
MockReranker
```

All responses are constructor-supplied fixtures; mocks must never open sockets.

Every mock provider call must return deterministic `ProviderCallMetadata` supplied by the fixture or built using a fixed test clock/hash helper.

- [ ] **Step 4: Add collected shared contract tests**

`tests/contract/test_mock_provider_contracts.py` instantiates each mock and invokes the corresponding assertion helper from `provider_contracts.py`.

Tests must also assert `isinstance(mock, ProtocolType)` for runtime-checkable protocols.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/contract/test_mock_provider_contracts.py -v
uv run pytest tests/unit tests/contract -v
```

Expected: PASS without network access.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/fixtures tests/contract
git commit -m "test: add deterministic provider contracts and network isolation"
```

---

### Task 9: Add Phase 0 smoke flow, traceability, import-boundary checks, and final quality gate

**Files:**
- Create: `tests/integration/test_phase0_smoke.py`
- Create: `tests/unit/test_import_boundaries.py`
- Create: `docs/traceability/phase-0.yaml`
- Modify: `README.md`
- Modify: `docs/architecture/decisions/ADR-001-tooling-stack.md` if implementation revealed necessary clarifications only

**Interfaces:**
- Consumes: all Phase 0 interfaces.
- Produces: one deterministic proof that the foundational contracts cooperate without any external provider.

- [ ] **Step 1: Write the failing Phase 0 smoke test**

The integration test must:

1. create an `AssessmentRequest` and `AssessmentRecord` at `RECEIVED/ACTIVE`;
2. create an `InMemoryTraceSink`;
3. advance through every canonical `AssessmentStage` in order using `advance_stage()`;
4. emit a `TraceEvent` for each lifecycle event;
5. set status to `PARTIAL` at an intermediate stage and prove stage progression still works;
6. return status to `ACTIVE`;
7. set status to `ABSTAINED` before `FINDINGS_FROZEN` and prove the assessment can still reach `REPORTED`;
8. call `complete_assessment()` at `REPORTED` and obtain `COMPLETED`;
9. round-trip serialize the final record and all trace events;
10. assert no provider or network call occurred.

This is a lifecycle/contract smoke test only. It MUST NOT fabricate search/evidence/adjudication semantics.

- [ ] **Step 2: Add import-boundary test**

`tests/unit/test_import_boundaries.py` must inspect Python files under `src/novelty_harness/domain/` and fail if they import from:

```text
novelty_harness.runtime
novelty_harness.ports
httpx
openai
anthropic
google
requests
sqlalchemy
```

The list may grow later. This test protects the domain from provider/infrastructure coupling.

- [ ] **Step 3: Run focused tests and verify any missing glue fails**

```bash
uv run pytest tests/integration/test_phase0_smoke.py tests/unit/test_import_boundaries.py -v
```

Expected before final glue fixes: FAIL only for genuine missing Phase 0 contract integration, not because the test invents later-phase behavior.

- [ ] **Step 4: Fix the smallest Phase 0 integration issues**

Do not introduce application services or later-phase abstractions solely to satisfy the smoke test. Fix only contract/state/tracing inconsistencies exposed by the test.

- [ ] **Step 5: Create Phase 0 requirement traceability**

`docs/traceability/phase-0.yaml` must include at least:

```yaml
phase: 0
requirements:
  - requirement: "Section 0.2 / 0.4"
    implementation: ["AGENTS.md", "docs/specs/master-design-spec.md"]
    tests: []
    status: implemented
  - requirement: "Section 8"
    implementation: ["src/novelty_harness/domain/state_machine.py"]
    tests: ["tests/unit/test_state_machine.py"]
    status: implemented
  - requirement: "Section 42"
    implementation: ["src/novelty_harness/ports/"]
    tests: ["tests/contract/test_mock_provider_contracts.py"]
    status: implemented
  - requirement: "FR-PROV-003"
    implementation: ["src/novelty_harness/ports/models.py", "src/novelty_harness/runtime/tracing/models.py"]
    tests: ["tests/unit/test_tracing.py", "tests/contract/test_mock_provider_contracts.py"]
    status: implemented
  - requirement: "FR-SEC-003"
    implementation: ["src/novelty_harness/runtime/config/", "src/novelty_harness/runtime/tracing/"]
    tests: ["tests/unit/test_config.py", "tests/unit/test_tracing.py"]
    status: implemented
  - requirement: "Section 54"
    implementation: ["src/novelty_harness/runtime/tracing/", "src/novelty_harness/runtime/logging.py"]
    tests: ["tests/unit/test_tracing.py"]
    status: implemented
  - requirement: "Phase 0 / Section 60"
    implementation: ["phase-0"]
    tests: ["tests/integration/test_phase0_smoke.py"]
    status: implemented
```

Do not mark later semantic requirements implemented merely because an enum exists for them.

- [ ] **Step 6: Update README with verified commands only**

Document:

```bash
uv sync --dev
uv run python scripts/verify.py
```

List Phase 0 capabilities exactly; explicitly state that real research, MCU extraction, evidence analysis, adjudication, and reporting are not implemented yet.

- [ ] **Step 7: Run full Phase 0 verification**

Run:

```bash
uv sync --dev
uv run python scripts/verify.py
```

Expected:

- Ruff lint PASS;
- Ruff format check PASS;
- Pyright PASS;
- pytest PASS;
- no test makes a live network call.

- [ ] **Step 8: Confirm Phase 0 exit criteria manually**

Check each item:

- [ ] clean install succeeds;
- [ ] lint/type/unit/contract/integration suite succeeds;
- [ ] canonical lifecycle smoke flow reaches `REPORTED`/`COMPLETED`;
- [ ] partial/abstained states remain reportable;
- [ ] no external provider is required;
- [ ] unit/contract tests block network access;
- [ ] root `AGENTS.md`, master spec, ADRs, and traceability file exist;
- [ ] no real novelty semantics were invented in Phase 0.

- [ ] **Step 9: Commit**

```bash
git add README.md docs/traceability tests/integration tests/unit/test_import_boundaries.py
git commit -m "test: verify phase zero foundation"
```

---

## Phase 0 Acceptance Gate

Phase 0 is accepted only when all of the following are true:

1. `uv sync --dev` succeeds from a clean checkout.
2. `uv run python scripts/verify.py` exits `0`.
3. Domain enums/IDs and assessment contracts round-trip cleanly through JSON.
4. Invalid lifecycle transitions are rejected and logged as explicit errors rather than silently coerced.
5. Pipeline stage and run status are distinct, so `PARTIAL`/`ABSTAINED` do not prevent report-stage progression.
6. Provider interfaces are vendor-neutral and pass deterministic mock contract tests.
7. Unit/contract tests cannot access the network.
8. Trace output is append-only JSONL, canonically hashable, and redacts obvious secret-bearing keys.
9. General settings contain no provider secret values and no invented research/saturation thresholds.
10. The domain package has no dependency on runtime, ports, database, or provider SDK modules.
11. The smoke assessment traverses the full canonical lifecycle without real network/provider dependencies.
12. Requirement traceability accurately marks only Phase 0 behavior as implemented.

If any item fails, do not begin Phase 1.

---

## Explicitly Deferred to Later Phases

The Phase 0 implementer MUST NOT add these unless required to fix a Phase 0 contract bug:

- CLI commands beyond package/tooling smoke behavior (Phase 1+);
- SQLAlchemy/database persistence (introduced when persisted run/application services are implemented);
- CIR/sufficiency semantic analysis (Phase 1/2);
- MCU schemas beyond IDs/enums needed by base contracts (Phase 1/2);
- query generation/search critic/coverage floors (Phase 3);
- real search/content/citation providers (Phase 3);
- HTTPX (Phase 3 when a network adapter needs it);
- semantic/vector retrieval, RRF, adaptive research, saturation (Phase 4);
- source normalization/provenance/evidence graph (Phase 5);
- evidence edge mapping/support verification (Phase 6);
- prosecutor/defender/adjudication/verdict gates (Phase 7);
- nine-question report compiler (Phase 8);
- adversarial red-team suite beyond Phase 0 infrastructure tests (Phase 9);
- calibrated scores/probabilities/thresholds (Phase 10+);
- web/TUI/public product UX (Phase 11).

Deferral is sequencing, **not removal from the architecture**.

---

## Self-Review Against the Master Spec

### Spec coverage

Phase 0 deliverables from Section 60 are covered:

- repository/governance: Task 1;
- `AGENTS.md`: Task 1;
- tooling: Tasks 1 and 9;
- configuration: Task 5;
- domain IDs/enums: Task 2;
- state machine: Task 4;
- base Pydantic contracts: Task 3;
- structured logging/tracing: Task 7;
- provider protocols: Task 6;
- deterministic mock providers: Task 8;
- CI-equivalent one-command verification: Tasks 1 and 9;
- state/schema/provider/no-network tests: Tasks 2–9;
- mocked lifecycle smoke flow: Task 9.

### Type consistency

The plan uses one set of canonical names throughout:

- `AssessmentStage` for canonical pipeline progression;
- `AssessmentStatus` for active/partial/abstained/blocked/failed/completed run condition;
- `AssessmentRecord` as the root Phase 0 assessment value;
- `LifecycleEvent` for stage/status transitions;
- `ProviderCallMetadata` for provider-call provenance;
- `TraceEvent`/`TraceSink` for durable trace output.

### Scope discipline

The plan does not implement research or novelty semantics. It establishes the contracts required for later phases and explicitly defers concrete providers, persistence, MCU semantics, evidence mapping, adjudication, and report generation.

### Review-focus coverage

- Lifecycle ambiguity -> Task 4 state/status tests.
- Silent schema drift -> Tasks 2–3 strict serialization tests.
- Secret leakage -> Tasks 5 and 7.
- Provider coupling -> Tasks 6 and 9 import-boundary test.
- Hidden network usage -> Task 8 socket-blocking test.

---

## Execution Handoff

Plan complete. Before implementation, review this plan together with `docs/specs/master-design-spec.md` and the root `AGENTS.md`.

Recommended execution approach for Phase 0: **subagent-driven/task-gated implementation if available**, because the tasks define foundational interfaces that every later phase will depend on and interface mistakes are expensive to unwind. A single native implementation is also reasonable if it strictly follows the task order and runs a fresh whole-phase review before acceptance.

Do not start Phase 1 until the Phase 0 acceptance gate above is explicitly accepted.
