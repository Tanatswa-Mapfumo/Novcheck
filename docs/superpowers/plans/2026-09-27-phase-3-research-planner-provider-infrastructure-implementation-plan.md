# Phase 3 — Research Planner and Provider Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Track every step with checkboxes. Do not begin Phase 4.

**Goal:** Replace the Phase 1/2 fixture-backed research-planning layer with a real, auditable planner that decides which evidence families are plausibly relevant to each MCU, generates diverse provider-neutral search intents, independently critiques and revises the plan, evaluates configurable coverage floors, compiles intents into provider-specific queries, and executes traceable screening through the first real provider adapters.

**Architecture:** Phase 3 separates four concerns that MUST NOT collapse into one LLM call: (1) evidence-family applicability, (2) provider-neutral search strategy, (3) independent search-plan criticism/revision, and (4) provider-specific query compilation/execution. Semantic planning uses the existing provider-independent LLM abstraction and Phase 2 structured semantic-call infrastructure. Deterministic policy code enforces family coverage, required rationales, query-family diversity, provider capabilities, rate-limit/failure handling, and trace completeness. Concrete HTTP providers live behind existing `SearchProvider`/content/citation ports. Phase 3 performs broad screening only; retrieval fusion, adaptive deepening, saturation, citation chasing, evidence normalization, equivalence, and novelty adjudication remain later phases.

**Initial concrete providers:**
- `OpenAlexSearchProvider` — `SCHOLARLY`, primary scholarly screening provider.
- `CrossrefSearchProvider` — `SCHOLARLY`, independent secondary scholarly metadata provider.
- `GitHubSearchProvider` — `SOFTWARE`, repository-level software screening provider.

**Deferred live providers but supported by the architecture:** Semantic Scholar, EPO OPS/patent, Brave/general-web, standards, regulatory/government, historical/archive and additional software/product providers.

**Tech Stack:** Existing Python 3.12+ / `uv` / Pydantic v2 / pytest / pytest-asyncio / pytest-socket / Ruff / Pyright stack. Add `httpx` because this is the first phase with concrete network adapters. Prefer `httpx.MockTransport` for deterministic adapter tests. Do not add vendor SDKs where a small HTTP adapter is sufficient.

**Spec:** `docs/specs/master-design-spec.md`, especially Sections 13–17, 42, 45–47, 54–56, 60 Phase 3, 61–62, Appendix E, and accepted Phase 2 contracts.

---

## Global Constraints

- Start from accepted Phase 2 final commit `558a22a` or an explicitly accepted descendant.
- Implement **Phase 3 only**.
- The master design spec remains authoritative.
- Evidence-family applicability MUST be assessed per MCU, not only once per idea.
- Every plausibly relevant evidence family MUST either receive its screening floor or carry an explicit recorded limitation/exclusion state.
- `UNRESOLVED` family applicability defaults toward screening/limitation, not silent exclusion.
- A provider being unavailable MUST NOT be transformed into `NOT_APPLICABLE`.
- No search results MUST NOT be interpreted as evidence of novelty.
- Search-plan generation MUST use multiple query families. A single canonical query is never sufficient for a strong research plan.
- Provider-neutral search intent MUST remain separate from provider-specific syntax.
- Search-plan criticism MUST be independent from the initial planner context; the critic sees the CIR/MCUs and proposed plan, not hidden strategist reasoning.
- The critic MUST return structured defects/corrections, not a prose “looks good”.
- Deep/adaptive research is not implemented in Phase 3. Screening may execute only a reviewed plan.
- Coverage floors are configurable operational policies, not calibrated novelty-confidence thresholds.
- Provider fallback MUST be explicit and traced. Never silently substitute a weaker provider or family.
- Concrete provider code MUST live outside the domain layer.
- Default unit/contract/integration tests MUST remain network-blocked.
- Live provider tests MUST be opt-in and marked `network`.
- API keys/tokens MUST remain outside persisted run artifacts. Configuration may store environment-variable names or credential references, never secret values.
- Every external response is untrusted data.
- Provider-specific ranking scores MUST NOT be compared across providers as if they share a scale.
- Phase 3 MUST NOT implement RRF, semantic/vector fusion, adaptive research, search saturation, citation chasing, provenance clustering, evidence equivalence, prosecutor/defender, verdict gates, or novelty scoring.
- Search results in Phase 3 are **screening candidates**, not evidence findings.
- Every provider request MUST retain provider/model/index/API version where available, request hash, timing, status, failure state, and rate-limit/quota metadata when exposed.

---

## Provider Research Basis for Phase 3

The implementation should encode capabilities rather than assume providers behave alike.

### OpenAlex
- Works search covers title, abstract, and full text through the `search` parameter.
- Cursor paging exists and should be represented as a provider capability.
- OpenAlex also exposes semantic search and citation-neighborhood data, but semantic retrieval/fusion and citation expansion belong to Phase 4.
- Search operations are usage-metered and responses expose rate/budget metadata; the adapter must record these headers/meta values when present.
- API keys are optional for limited use but improve the daily budget. Secrets remain external to persisted settings.

### Crossref
- REST access is available without signup; polite access is obtained by identifying the client/email.
- Query/list calls have stricter request rates than singleton lookups.
- `query.bibliographic` is appropriate for broad bibliographic matching but is **not a general Boolean search language**. The provider compiler must not pretend otherwise.
- Crossref is useful as an independent scholarly metadata/index channel and should not be treated as equivalent to OpenAlex full-text search.

### GitHub
- Repository/code search uses separate rate-limit resources from the general REST API.
- Phase 3 uses repository search for broad software screening. Code-level retrieval/search is a later retrieval-depth capability.
- Authentication is optional for public REST access but authenticated quotas are higher. Rate-limit response headers are authoritative and must be captured.

### Patent roadmap
- EPO Open Patent Services (OPS) provides bibliographic/legal/full-text patent data through REST/XML and OAuth credentials, with explicit fair-use/volume conditions.
- Phase 3 must make `PATENT` a first-class evidence family in applicability and coverage, but strong patent coverage MUST be reported as unavailable/blocked unless a patent provider is actually configured.
- Do not fake patent screening by silently substituting general web results.

Document these choices in an ADR/provider matrix. Provider details are operational assumptions that may evolve; the stable contract is capability-driven.

---

## Review Focus

1. **Silent family omission:** planner decides a difficult family is irrelevant merely because no provider is configured.
2. **Canonical-term trap:** query plan relies on the user’s terminology and misses functional/relational/historical wording.
3. **Provider-language leakage:** OpenAlex/Crossref/GitHub syntax contaminates provider-neutral planning.
4. **False coverage:** a branch is marked screened even though a provider failed, rate-limited, or never met the configured floor.
5. **Rate-limit corruption:** retries hide provider failure or duplicate screening events without traceability.

---

## Phase 3 File Map

Prefer the following decomposition unless accepted Phase 2 files already own the responsibility:

```text
src/novelty_harness/
  research/
    __init__.py
    models.py
    applicability.py
    query_taxonomy.py
    planning.py
    critique.py
    revision.py
    coverage.py
    screening.py
    prompts.py
    provider_queries.py
  providers/
    __init__.py
    registry.py
    http.py
    errors.py
    openalex.py
    crossref.py
    github.py
  runtime/
    config/
      search.py

tests/
  unit/
    research/
      test_applicability.py
      test_query_taxonomy.py
      test_search_planning.py
      test_search_critique.py
      test_coverage_floor.py
      test_provider_query_compilation.py
    providers/
      test_registry.py
      test_http_runtime.py
      test_openalex.py
      test_crossref.py
      test_github.py
  integration/
    test_phase3_research_plan_pipeline.py
    test_phase3_screening_pipeline.py
    test_phase2_slice_with_phase3_planner.py
  contract/
    test_phase3_provider_contracts.py
  adversarial/
    test_phase3_search_strategy_attacks.py
  fixtures/
    phase3.py
    provider_responses/
      openalex/
      crossref/
      github/
  network/
    test_phase3_live_provider_smoke.py

docs/
  providers/
    provider-matrix.md
  traceability/
    phase-3.yaml
  architecture/decisions/
    ADR-013-search-intent-vs-provider-query.md
    ADR-014-coverage-floor-policy.md
    ADR-015-phase3-provider-set.md
  phase-3-completion.md
```

Dependency direction:

```text
research semantic planning -> domain/application contracts + LLMProvider
research deterministic policy -> research/domain models only
provider adapters -> ports + HTTP runtime + provider-specific DTO translation
screening service -> research plan + provider registry + trace/artifact interfaces
research/domain -X-> concrete provider SDKs
provider adapters -X-> novelty/adjudication logic
```

---

# Task 1 — Establish Phase 3 research-plan contracts and query taxonomy

**Files:**
- Create/extend `src/novelty_harness/research/models.py`
- Create `src/novelty_harness/research/query_taxonomy.py`
- Create `tests/unit/research/test_query_taxonomy.py`
- Create `tests/unit/research/test_search_planning.py`

**Interfaces:** Extend existing Phase 1/2 `SearchPlan` artifacts backward-compatibly where possible; if the accepted repository already has a differently named equivalent, adapt instead of duplicating.

Add stable enums/contracts equivalent to:

```python
class FamilyApplicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    POSSIBLY_APPLICABLE = "POSSIBLY_APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"

class QueryFamily(str, Enum):
    DIRECT_CANONICAL = "DIRECT_CANONICAL"
    SYNONYM_ACRONYM = "SYNONYM_ACRONYM"
    FUNCTIONAL = "FUNCTIONAL"
    MECHANISM = "MECHANISM"
    RELATIONSHIP = "RELATIONSHIP"
    OUTCOME_OBJECTIVE = "OUTCOME_OBJECTIVE"
    HISTORICAL_TERMINOLOGY = "HISTORICAL_TERMINOLOGY"
    ADJACENT_DOMAIN = "ADJACENT_DOMAIN"
    COMPONENT = "COMPONENT"
    COMBINATION = "COMBINATION"
    ENTITY_DISCOVERY = "ENTITY_DISCOVERY"

class EvidenceFamilyAssessment(ContractModel):
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    applicability: FamilyApplicability
    rationale: str
    exclusion_reason: str | None = None
    limitations: list[str] = Field(default_factory=list)

class SearchIntent(ContractModel):
    query_id: QueryId
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    query_family: QueryFamily
    text: str
    rationale: str
    concepts: list[str]
    relationship_terms: list[str] = Field(default_factory=list)
    historical_terms: list[str] = Field(default_factory=list)
    filters: dict[str, JsonValue] = Field(default_factory=dict)

class SearchPlan(ContractModel):
    assessment_id: AssessmentId
    as_of: date
    family_assessments: list[EvidenceFamilyAssessment]
    intents: list[SearchIntent]
    reviewed: bool = False
    review_id: str | None = None
    limitations: list[str] = Field(default_factory=list)
```

**Required deterministic validation:**
- every intent targets a known MCU and evidence family;
- query/rationale/concept fields are non-blank;
- `NOT_APPLICABLE` requires `exclusion_reason`;
- `APPLICABLE`, `POSSIBLY_APPLICABLE`, and `UNRESOLVED` cannot use exclusion as a substitute for screening;
- duplicate query IDs rejected;
- identical normalized text/family/MCU/query-family duplicates rejected;
- plan may be incomplete before review, but a “reviewed” plan must reference an actual review artifact.

- [ ] Write failing tests.
- [ ] Implement contracts/taxonomy.
- [ ] Preserve schema/version migration discipline from Phase 2.
- [ ] Run tests/type checks.
- [ ] Commit.

---

# Task 2 — Implement per-MCU evidence-family applicability

**Files:**
- Create `src/novelty_harness/research/applicability.py`
- Extend `src/novelty_harness/research/prompts.py`
- Create `tests/unit/research/test_applicability.py`

**Interface:**

```python
class EvidenceFamilyApplicabilityAssessor:
    async def assess(
        self,
        *,
        idea: CanonicalIdeaRepresentation,
        mcus: Sequence[MCU],
    ) -> list[EvidenceFamilyAssessment]: ...
```

Use the Phase 2 structured semantic helper and `LLMProvider` to propose applicability, followed by deterministic policy validation.

**Policy rules:**
- all nine master-spec evidence families must appear for each MCU unless a documented domain-specific configuration intentionally adds more;
- absence of a configured provider does not influence semantic applicability;
- `UNRESOLVED` is retained if the model cannot justify exclusion;
- technical/software mechanisms should normally leave SCHOLARLY/SOFTWARE/PATENT at least unresolved/possibly applicable unless the MCU clearly cannot exist in those ecosystems;
- product/workflow claims may activate PRODUCT/GENERAL_WEB/GREY_LITERATURE even when scholarly relevance is low;
- standards/regulatory/government applicability must be based on the MCU/context, not on whether adapters exist;
- family applicability is versioned and traceable.

**Adversarial tests:**
- software idea with no patent adapter configured still marks PATENT independently of provider availability;
- academic framing does not silently suppress SOFTWARE/PRODUCT when the MCU describes an implementable system;
- product framing does not suppress SCHOLARLY/PATENT automatically;
- empty/vague MCU yields UNRESOLVED rather than broad NOT_APPLICABLE;
- user statement “there are no patents” does not become an exclusion rationale.

- [ ] Write failing tests.
- [ ] Implement assessor + deterministic policy checks.
- [ ] Commit.

---

# Task 3 — Implement provider-neutral multi-family search strategist

**Files:**
- Create `src/novelty_harness/research/planning.py`
- Extend `src/novelty_harness/research/prompts.py`
- Create `tests/unit/research/test_search_planning.py`

**Interface:**

```python
class SearchStrategist:
    async def build_plan(
        self,
        *,
        assessment_id: AssessmentId,
        as_of: date,
        idea: CanonicalIdeaRepresentation,
        mcus: Sequence[MCU],
        combinations: Sequence[MCUCombination],
        applicability: Sequence[EvidenceFamilyAssessment],
    ) -> SearchPlan: ...
```

The strategist MUST generate multiple query families for each applicable/plausible MCU-family branch. The planner produces **search intents**, not OpenAlex/GitHub/Crossref syntax.

Minimum semantic coverage for technical/research-like MCUs should attempt, where meaningful:
- direct/canonical;
- synonym/acronym;
- functional;
- mechanism;
- relationship;
- outcome/objective;
- historical terminology;
- adjacent-domain;
- component;
- combination;
- entity-discovery once entities exist.

Not every family must be forced when nonsensical; omitted families require structured rationale available to the critic.

**Hard rules:**
- relationship queries must contain the contribution-bearing relation, not just nouns;
- historical queries must change terminology/time framing, not simply prepend “old”;
- adjacent-domain queries must identify the transferable function/mechanism;
- combination queries may target an MCU combination but cannot relabel individual known components as novel;
- query generation must not add dates/language filters unless the CIR/cutoff/policy justifies them;
- `as_of` belongs in the plan and later provider compilation, not inside free-text queries by default.

**Metamorphic tests:**
- renaming the idea preserves functional/mechanistic query families;
- buzzwords do not replace core terms;
- changing only an application context affects context queries but not the core mechanism query family;
- a relation-bearing MCU produces at least one relationship-focused intent.

- [ ] Write failing tests using deterministic mock semantic outputs.
- [ ] Implement strategist.
- [ ] Commit.

---

# Task 4 — Implement independent PRESS-inspired search-plan critic and reviser

**Files:**
- Create `src/novelty_harness/research/critique.py`
- Create `src/novelty_harness/research/revision.py`
- Create `tests/unit/research/test_search_critique.py`

**Contracts:**

```python
class SearchPlanIssueCategory(str, Enum):
    QUESTION_TRANSLATION = "QUESTION_TRANSLATION"
    CONCEPT_COVERAGE = "CONCEPT_COVERAGE"
    QUERY_FAMILY_GAP = "QUERY_FAMILY_GAP"
    TERMINOLOGY_GAP = "TERMINOLOGY_GAP"
    RELATIONSHIP_GAP = "RELATIONSHIP_GAP"
    HISTORICAL_GAP = "HISTORICAL_GAP"
    ADJACENT_DOMAIN_GAP = "ADJACENT_DOMAIN_GAP"
    BOOLEAN_OR_PROXIMITY = "BOOLEAN_OR_PROXIMITY"
    SPELLING_OR_SYNTAX = "SPELLING_OR_SYNTAX"
    LIMIT_OR_FILTER = "LIMIT_OR_FILTER"
    FAMILY_OMISSION = "FAMILY_OMISSION"
    OVERRELIANCE_ON_USER_TERMS = "OVERRELIANCE_ON_USER_TERMS"
    OVERCONSTRAINT = "OVERCONSTRAINT"

class SearchPlanIssue(ContractModel):
    issue_id: str
    category: SearchPlanIssueCategory
    severity: Literal["INFO", "WARNING", "MATERIAL"]
    mcu_id: MCUId | None
    evidence_family: EvidenceFamily | None
    query_ids: list[QueryId]
    explanation: str
    required_correction: str | None = None

class SearchPlanReview(ContractModel):
    review_id: str
    status: Literal["PASS", "REVISE", "BLOCKED"]
    issues: list[SearchPlanIssue]
    critic_prompt_version: str
```

`SearchPlanCritic` receives CIR + MCUs + applicability + proposed plan only. It MUST NOT receive strategist chain-of-thought/rationale beyond persisted plan fields.

Critic checklist adapts PRESS-style principles:
- correct translation of the contribution into searchable concepts;
- missing synonyms/acronyms/spelling/historical terms;
- functional/mechanistic/relationship representation;
- overly broad/narrow concepts;
- Boolean/proximity logic where a provider-neutral intent explicitly uses it;
- accidental exclusions via NOT/date/language filters;
- missing adjacent disciplines/classifications;
- family omissions;
- overreliance on user terminology;
- renamed-established-concept robustness.

`SearchPlanReviser` applies structured corrections through a separate semantic call. Cap automatic revision attempts with a configurable engineering limit; exhausted revision attempts produce `BLOCKED`/limitation, never an implicit pass.

**Required deterministic checks independent of LLM critic:**
- every `NOT_APPLICABLE` has rationale;
- all non-excluded families appear in plan branches;
- required relationship query when MCU contains material relationships;
- no malformed/blank intents;
- date cutoff is not later than assessment `as_of`;
- plan cannot set `reviewed=True` unless final review is PASS.

- [ ] Write failing critic/revision tests.
- [ ] Test canonical-only plan -> REVISE.
- [ ] Test hidden family omission -> MATERIAL issue.
- [ ] Test over-restrictive date/language filter -> issue.
- [ ] Test unresolved revision -> BLOCKED.
- [ ] Implement and commit.

---

# Task 5 — Implement configurable coverage-floor policy and matrix states

**Files:**
- Create `src/novelty_harness/research/coverage.py`
- Create/extend `src/novelty_harness/runtime/config/search.py`
- Create `tests/unit/research/test_coverage_floor.py`
- Create `docs/architecture/decisions/ADR-014-coverage-floor-policy.md`

**Contracts:**

```python
class CoverageFloor(ContractModel):
    min_distinct_query_families: int
    min_configured_providers: int
    required_query_families: set[QueryFamily] = Field(default_factory=set)
    min_results_inspected_per_query: int | None = None

class CoveragePolicy(ContractModel):
    by_family: dict[EvidenceFamily, CoverageFloor]

class CoverageState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXCLUDED_WITH_RATIONALE = "EXCLUDED_WITH_RATIONALE"
    PLANNED = "PLANNED"
    READY_FOR_SCREENING = "READY_FOR_SCREENING"
    SCREENED = "SCREENED"
    DEGRADED = "DEGRADED"
    BLOCKED_NO_PROVIDER = "BLOCKED_NO_PROVIDER"
    BLOCKED_PLAN_DEFECT = "BLOCKED_PLAN_DEFECT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"

class CoverageCell(ContractModel):
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    state: CoverageState
    planned_query_families: set[QueryFamily]
    configured_providers: list[str]
    successful_providers: list[str] = Field(default_factory=list)
    inspected_results: int = 0
    limitations: list[str] = Field(default_factory=list)
```

**Policy principles:**
- values are configuration, not scientific confidence thresholds;
- a missing provider yields `BLOCKED_NO_PROVIDER`, never `NOT_APPLICABLE`;
- a provider failure yields degraded/failure state even if another provider succeeds;
- raw hit count does not itself satisfy query-diversity requirements;
- Phase 3 coverage tracks **screening completion**, not search saturation;
- `SATURATED` is forbidden in Phase 3 output because saturation belongs to Phase 4.

Provide one documented default profile for local development/standard screening, but make every value overrideable. The ADR must explain that these are operational floors subject to later calibration.

- [ ] Write failing tests.
- [ ] Implement policy loader/evaluator.
- [ ] Commit.

---

# Task 6 — Build HTTP runtime, provider registry, capability and failure model

**Files:**
- Add `httpx` to `pyproject.toml`
- Create `src/novelty_harness/providers/errors.py`
- Create `src/novelty_harness/providers/http.py`
- Create `src/novelty_harness/providers/registry.py`
- Create `tests/unit/providers/test_http_runtime.py`
- Create `tests/unit/providers/test_registry.py`
- Create `docs/architecture/decisions/ADR-013-search-intent-vs-provider-query.md`

**Provider failure taxonomy:**
- `AUTHENTICATION_FAILURE`
- `AUTHORIZATION_FAILURE`
- `RATE_LIMITED`
- `QUOTA_EXHAUSTED`
- `TIMEOUT`
- `TRANSPORT_FAILURE`
- `BAD_REQUEST`
- `SERVER_FAILURE`
- `PARSE_FAILURE`
- `CAPABILITY_MISMATCH`
- `PROVIDER_UNAVAILABLE`

**HTTP runtime requirements:**
- inject `httpx.AsyncClient`/transport, clock, and sleeper for deterministic tests;
- timeout explicitly configured;
- retry only idempotent requests and only retryable failure classes;
- honor `Retry-After` when present;
- provider adapters may parse rate-limit/reset headers into a common `RateLimitSnapshot`;
- exponential backoff policy is engineering configuration and fully traceable;
- never retry 400/401/authorization failures as generic transient errors;
- GitHub rate-limit 403/429 must be distinguishable from ordinary authorization failure using headers/response data;
- every attempt emits trace data without secret-bearing headers.

**Provider registry:**

```python
class ProviderDescriptor(ContractModel):
    name: str
    evidence_families: set[EvidenceFamily]
    search_capabilities: set[str]
    auth_mode: str
    supports_pagination: bool
    supports_citations: bool = False
    supports_full_text: bool = False

class ProviderRegistry:
    def register(self, provider: SearchProvider, descriptor: ProviderDescriptor) -> None: ...
    def providers_for(self, family: EvidenceFamily) -> tuple[RegisteredProvider, ...]: ...
```

Registry availability MUST NOT alter semantic family applicability.

- [ ] Write tests for duplicate provider names, family lookup, unavailable providers, safe credential references, rate-limit retry, non-retryable 4xx, timeout, JSON/XML parse failure and explicit fallback tracing.
- [ ] Implement.
- [ ] Commit.

---

# Task 7 — Implement provider-query compilation boundary

**Files:**
- Create `src/novelty_harness/research/provider_queries.py`
- Create `tests/unit/research/test_provider_query_compilation.py`

**Contracts:**

```python
class CompiledProviderQuery(ContractModel):
    query_id: QueryId
    provider_name: str
    evidence_family: EvidenceFamily
    endpoint: str
    method: Literal["GET", "POST"]
    params: dict[str, JsonValue] = Field(default_factory=dict)
    body: dict[str, JsonValue] | None = None
    headers_profile: str | None = None
    compilation_notes: list[str] = Field(default_factory=list)

class ProviderQueryCompiler(Protocol):
    def compile(self, intent: SearchIntent, *, as_of: date) -> CompiledProviderQuery: ...
```

Rules:
- compilers are provider-specific deterministic translators;
- unsupported intent features raise `CAPABILITY_MISMATCH` instead of silently dropping constraints;
- assessment cutoff must become a supported provider filter where possible; where impossible, the compiled query records that chronology must be filtered post-retrieval;
- provider syntax never mutates the original `SearchIntent`;
- provider query strings/params are persisted for reproducibility, after secret redaction.

- [ ] Write contract tests using stub compilers.
- [ ] Implement boundary.
- [ ] Commit.

---

# Task 8 — Implement OpenAlex scholarly screening adapter

**Files:**
- Create `src/novelty_harness/providers/openalex.py`
- Create `tests/unit/providers/test_openalex.py`
- Add recorded fixtures under `tests/fixtures/provider_responses/openalex/`

**Phase 3 capabilities:**
- evidence family: `SCHOLARLY`;
- standard Works text search only for screening;
- cursor metadata represented, but Phase 3 screening need not exhaust pages;
- capture title, OpenAlex ID, DOI, canonical URL, publication date/year, authors where configured, abstract/snippet availability and provider relevance rank/score as provider metadata;
- capture API usage/rate metadata when returned;
- optional API key read only from environment/credential resolver;
- no semantic-search execution in Phase 3 even though OpenAlex exposes it; flag capability for Phase 4;
- no citation expansion in Phase 3 even though OpenAlex exposes citation relations.

**Compiler:** map provider-neutral intent text to `/works?search=` and provider-supported filters/select fields. Use supported page size; do not rely on deprecated pagination behavior.

**Tests via `httpx.MockTransport`:**
- successful first page;
- cursor parsing;
- empty results;
- malformed response;
- 429 + rate metadata;
- 500 retry then success;
- invalid query 400 -> explicit failure;
- API key never appears in trace/artifacts;
- publication cutoff handling/limitation trace.

- [ ] Implement adapter + compiler.
- [ ] Pass shared `SearchProvider` contract tests.
- [ ] Commit.

---

# Task 9 — Implement Crossref independent scholarly screening adapter

**Files:**
- Create `src/novelty_harness/providers/crossref.py`
- Create `tests/unit/providers/test_crossref.py`
- Add recorded fixtures under `tests/fixtures/provider_responses/crossref/`

**Phase 3 capabilities:**
- evidence family: `SCHOLARLY`;
- `/works` bibliographic query screening;
- use `query.bibliographic`/supported filters, not invented Boolean semantics;
- support polite-pool identification via configured mailto/client identification without placing personal/email values in durable trace fields;
- parse DOI, title, type, publication dates, publisher/container, URL and Crossref relevance score as provider-local metadata;
- capture Crossref rate/concurrency headers where present;
- cursor support represented but screening may use bounded first-page retrieval.

**Critical behavior:** Crossref matching behavior is different from OpenAlex. Never claim that a Crossref query reproduces an OpenAlex Boolean/full-text query. Store compilation notes/limitations.

**Tests:**
- successful response;
- no DOI/title edge cases;
- polite identification not leaked into artifact;
- public/polite rate-limit headers;
- 429 backoff;
- 403/block -> explicit provider failure;
- malformed metadata;
- date cutoff filter or post-filter limitation;
- query intent remains immutable.

- [ ] Implement adapter + compiler.
- [ ] Pass shared provider contract tests.
- [ ] Commit.

---

# Task 10 — Implement GitHub repository screening adapter

**Files:**
- Create `src/novelty_harness/providers/github.py`
- Create `tests/unit/providers/test_github.py`
- Add recorded fixtures under `tests/fixtures/provider_responses/github/`

**Phase 3 capabilities:**
- evidence family: `SOFTWARE`;
- repository search only in Phase 3;
- code search/deep repository inspection deferred to Phase 4+;
- normalize repo full name, URL, description, topics where returned, timestamps, archived flag, default branch/license metadata where available;
- preserve provider rank/score as provider-local metadata;
- optional `GITHUB_TOKEN` credential resolved externally;
- set/record explicit GitHub REST API version header in non-secret provider metadata;
- capture `x-ratelimit-*` headers and search resource bucket.

**Compiler:** translate intent into GitHub repository search terms/qualifiers only when supported. If a concept requires code-level search, emit capability limitation instead of pretending repository search is equivalent.

**Tests:**
- repository search success;
- unauthenticated path;
- authenticated header redaction;
- search rate-limit exhausted;
- secondary-rate-limit-style 403/429 handling;
- pagination metadata;
- archived repo retained as precedent candidate rather than silently excluded;
- malformed repository data;
- cutoff/creation/update dates captured without equating creation date to invention date.

- [ ] Implement adapter + compiler.
- [ ] Pass shared provider contract tests.
- [ ] Commit.

---

# Task 11 — Implement reviewed-plan screening executor and coverage accounting

**Files:**
- Create `src/novelty_harness/research/screening.py`
- Create `tests/integration/test_phase3_screening_pipeline.py`
- Extend artifact writer usage as needed without introducing database persistence.

**Contracts:**

```python
class ScreeningHit(ContractModel):
    query_id: QueryId
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    provider_name: str
    source: SourceRef
    provider_rank: int
    provider_score: float | None = None
    snippet: str | None = None
    retrieved_at: datetime
    call_metadata: ProviderCallMetadata

class ScreeningRunResult(ContractModel):
    assessment_id: AssessmentId
    plan_review_id: str
    hits: list[ScreeningHit]
    coverage: list[CoverageCell]
    provider_failures: list[ProviderFailureRecord]
    limitations: list[str]
```

**Execution rules:**
- refuse unreviewed/non-PASS plans;
- compile each search intent separately for each configured provider assigned to its family;
- respect coverage-floor/provider requirements;
- execute bounded screening only;
- do not RRF/fuse/rerank across providers in Phase 3;
- retain provider-local rank/score separately;
- duplicate sources across providers MAY coexist in Phase 3; canonical source deduplication belongs to Phase 5;
- explicitly record partial provider failure and continue other branches where possible;
- `0 results` records a zero-hit screening event, not novelty evidence;
- update coverage states from actual successful/failed calls;
- do not mark any branch `SATURATED`.

Required artifacts:
```text
family_applicability.json
search_plan.json
search_plan_review.json
compiled_queries.jsonl
screening_events.jsonl
screening_hits.jsonl
coverage_matrix.json
provider_failures.jsonl
```

- [ ] Write integration tests with all three provider adapters using `MockTransport`.
- [ ] Test one provider failure while another scholarly provider succeeds -> `DEGRADED`, not silent success.
- [ ] Test PATENT applicable with no provider -> `BLOCKED_NO_PROVIDER` while other branches screen normally.
- [ ] Implement.
- [ ] Commit.

---

# Task 12 — Integrate Phase 3 planner/screening into the accepted vertical slice

**Files:**
- Create/extend `tests/integration/test_phase3_research_plan_pipeline.py`
- Modify application orchestration only at the Phase 3 planning/screening seam.
- Extend `tests/integration/test_phase2_slice_with_phase3_planner.py` or equivalent accepted integration test.

Required pipeline:
1. accepted Phase 2 CIR/sufficiency/MCU graph;
2. real Phase 3 family applicability;
3. real Phase 3 provider-neutral strategy;
4. real independent critic;
5. revision/re-review if needed;
6. coverage-floor preflight;
7. provider-specific compilation;
8. concrete-provider screening through deterministic HTTP transports in CI;
9. coverage matrix + hits persisted;
10. later evidence mapping/adjudication/report semantics remain fixture-backed.

The full end-to-end assessment must still reach `REPORTED/COMPLETED` using real Phase 2 understanding + real Phase 3 planning/screening + fixture-backed Phase 4+ semantics.

Trace must clearly identify the boundary where real Phase 3 ends and fixture/deferred later stages begin.

- [ ] Write failing integration test.
- [ ] Implement smallest orchestration changes.
- [ ] Run full integration suite.
- [ ] Commit.

---

# Task 13 — Add Phase 3 adversarial search-strategy regression suite

**Files:**
- Create `tests/adversarial/test_phase3_search_strategy_attacks.py`
- Extend `tests/fixtures/phase3.py`

Mandatory cases:
1. **Canonical-term trap:** known function described under renamed terminology -> functional/relationship queries still generated.
2. **User-term anchoring:** user repeats one branding phrase -> plan includes synonyms/mechanism, not phrase-only search.
3. **Overconstraint:** gratuitous English-only/date filters -> critic rejects/flags.
4. **Family suppression:** no patent provider configured -> PATENT remains applicable/blocked, not excluded.
5. **Academic-only bias:** implementable software MCU -> SOFTWARE branch remains.
6. **Product-only bias:** startup pitch -> scholarly/patent applicability still considered.
7. **Relationship erasure:** query contains all nouns but omits causal/control relation -> critic flags.
8. **Historical terminology:** modern phrase only -> historical query gap identified.
9. **Adjacent-domain omission:** generic mechanism plausibly transferred -> critic flags missing adjacent-domain search.
10. **Crossref Boolean illusion:** provider compiler refuses/rewrites unsupported Boolean assumptions with explicit notes.
11. **Provider failure:** OpenAlex 429 + Crossref success -> scholarly branch degraded, not “covered perfectly”.
12. **Zero hits:** zero across one branch -> no novelty conclusion or saturation state.
13. **Duplicate result inflation:** same DOI from OpenAlex/Crossref remains two screening hits but cannot count as independent evidence yet.
14. **Rate-limit replay:** retry attempts stay traceable and do not duplicate logical query identity.
15. **Prompt injection in provider snippet:** snippet cannot alter planner/critic behavior.

Assertions should focus on structural plan/coverage behavior rather than exact generated prose.

- [ ] Implement fixtures/tests.
- [ ] Run adversarial suite.
- [ ] Commit.

---

# Task 14 — Add provider documentation, opt-in live smoke tests, traceability and final acceptance

**Files:**
- Create `docs/providers/provider-matrix.md`
- Create `docs/traceability/phase-3.yaml`
- Create `docs/architecture/decisions/ADR-015-phase3-provider-set.md`
- Create `tests/network/test_phase3_live_provider_smoke.py`
- Extend architecture guards/import-boundary tests.
- Update `README.md`
- Create `docs/phase-3-completion.md`

## Provider matrix
Document at minimum:
- evidence family;
- provider;
- live status (`IMPLEMENTED`, `PLANNED`, `OPTIONAL`);
- auth requirements;
- query capabilities;
- pagination;
- rate/quota behavior;
- full-text/citation capabilities;
- current Phase 3 limitations;
- later-phase capability activation.

Include planned rows for:
- Semantic Scholar;
- EPO OPS;
- Brave/general web;
- standards;
- government/regulatory;
- historical/archive.

Do not represent planned providers as implemented.

## Live smoke tests
Marked `network`, excluded from default suite.
- OpenAlex: one minimal works query;
- Crossref: one minimal works query;
- GitHub: one minimal public repository query.

Tests must:
- skip with clear reason when network unavailable;
- avoid consuming excessive quota;
- never print secrets;
- validate response contract only, not result identity/ranking;
- be runnable via an explicit command documented in README.

## Architecture guards
Assert:
- domain has no concrete provider imports;
- research planning does not import concrete providers;
- provider adapters contain no novelty/verdict logic;
- no RRF/adaptive/saturation implementation added;
- `CoverageState` has no `SATURATED` state in Phase 3;
- provider availability cannot change stored family applicability;
- SearchPlan PASS is required before screening;
- no production import from tests;
- network remains blocked in default suite.

## Traceability
Cover:
- FR-EV-001/002/003;
- FR-SRCH-001/002/003/004;
- provider abstraction requirements in Section 42;
- provider metadata/failure isolation requirements;
- Search Coverage Matrix architecture;
- relevant failure classes from Section 46;
- Phase 3 Section 60 deliverables.

Explicitly defer Phase 4+ semantics.

## Final verification
Run after final change:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

If network is available, additionally run the documented opt-in provider smoke command. Live-smoke failure caused solely by unavailable credentials/network must be reported separately and MUST NOT be hidden by editing deterministic tests.

Perform fresh-checkout verification if practical.

- [ ] Write completion report.
- [ ] Commit.

---

# Phase 3 Acceptance Gate

Phase 3 is accepted only when all are true:

1. Phase 2 baseline passes before Phase 3 changes.
2. Final deterministic verification passes from the Phase 3 worktree.
3. Fresh-checkout verification passes if practical.
4. Evidence-family applicability is represented for every MCU across all nine master-spec families.
5. Provider availability does not determine semantic applicability.
6. Every non-excluded/plausible family is either ready/screened or explicitly blocked/degraded with reasons.
7. Query taxonomy includes direct, synonym, functional, mechanism, relationship, outcome, historical, adjacent-domain, component, combination and entity-discovery families.
8. Real search plans contain diverse query families appropriate to the MCU rather than canonical keywords only.
9. Provider-neutral intents are separated from provider-specific compiled queries.
10. Independent search-plan criticism is implemented and can block/revise a defective plan.
11. A reviewed PASS plan is required before screening execution.
12. Coverage-floor policy is configurable and clearly documented as operational rather than calibrated confidence.
13. Missing provider coverage produces explicit `BLOCKED_NO_PROVIDER`/limitation, not silent exclusion.
14. HTTP runtime handles timeouts, retryable failures, rate limits and non-retryable 4xx distinctly and traceably.
15. OpenAlex adapter passes shared contracts and recorded-response tests.
16. Crossref adapter passes shared contracts and recorded-response tests.
17. GitHub repository-search adapter passes shared contracts and recorded-response tests.
18. No provider secret appears in traces, settings dumps, fixtures or persisted artifacts.
19. Screening results preserve provider-local rank/score without cross-provider score comparison.
20. Provider failure can degrade one branch without crashing unrelated branches.
21. Zero results never produce novelty or saturation state.
22. PATENT can remain applicable and explicitly blocked when no patent provider is configured.
23. Search-plan, review, compiled-query, screening-event, hit, coverage and provider-failure artifacts are persisted and deserialize.
24. Phase 3 adversarial search-strategy tests pass.
25. The accepted vertical slice reaches `REPORTED/COMPLETED` using real Phase 2 understanding + real Phase 3 planning/screening while Phase 4+ remains fixture-backed.
26. Default tests make no live network calls.
27. Optional live provider smoke tests are isolated behind the `network` marker and documented.
28. Provider matrix truthfully distinguishes implemented vs planned providers.
29. README and traceability accurately describe Phase 3 capabilities/limitations.
30. No Phase 4 retrieval fusion/adaptive research/saturation logic has started.

If any deterministic gate fails, do not begin Phase 4.

---

# Self-Review Against the Master Spec

## Phase 3 coverage
- evidence-family applicability -> Task 2;
- query taxonomy and strategist -> Tasks 1–3;
- search critic/review gate -> Task 4;
- coverage floors -> Task 5;
- provider health/failure infrastructure -> Task 6;
- provider-specific translation -> Task 7;
- first concrete providers across scholarly/software families -> Tasks 8–10;
- query/retrieval trace storage and coverage matrix -> Task 11;
- real-planner vertical-slice integration -> Task 12;
- adversarial strategy regression -> Task 13;
- provider matrix/live smoke/traceability -> Task 14.

## Explicitly deferred
- semantic/vector multi-strategy retrieval and RRF -> Phase 4;
- citation/entity expansion -> Phase 4;
- adaptive depth allocation -> Phase 4;
- saturation vs budget-stop logic -> Phase 4;
- source canonicalization/provenance -> Phase 5;
- passage evidence/equivalence/support verification -> Phase 6;
- prosecutor/defender/verdict gates -> Phase 7;
- full report compiler -> Phase 8.

## Review-focus coverage
- silent family omission -> Tasks 2, 4, 5, 13;
- canonical-term trap -> Tasks 3, 4, 13;
- provider-language leakage -> Task 7 and provider tests;
- false coverage -> Tasks 5, 11, 13;
- rate-limit corruption -> Tasks 6, 8–11, 13.

---

# Execution Handoff

Recommended execution: **isolated Git worktree from accepted Phase 2 commit `558a22a`, task-gated implementation, and a fresh whole-phase review before acceptance**. Provider integration creates a new external-failure surface, so deterministic transport fixtures and strict tracing are mandatory even if live smoke tests succeed.

Do not begin Phase 4 until Phase 3 is reviewed and explicitly accepted.
