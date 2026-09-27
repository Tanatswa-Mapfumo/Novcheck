# Phase 4 — Multi-Strategy Retrieval and Adaptive Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Track progress with the checkboxes below.

**Goal:** Replace Phase 3 first-page screening with a diversified, adaptive retrieval engine that can retrieve across lexical, semantic, relational, citation, entity, and chronology-aware paths; merge heterogeneous candidate lists without score leakage; escalate research when apparent novelty remains high; and distinguish `SATURATED`, `BUDGET_STOPPED`, and `ACCESS_BLOCKED` honestly.

**Architecture:** Phase 4 extends the Phase 3 planner/provider layer rather than replacing it. Provider-neutral `SearchIntent` remains the conceptual plan. Provider-specific adapters execute multiple retrieval strategies and return normalized candidate records. Rank fusion operates on ranks rather than provider-local score scales. An adaptive controller allocates additional research depth based on unresolved decision impact, query/provider diversity, yield, and budget state. Citation/entity expansion is modeled separately from ordinary search. Search stopping is explicit, traceable, and branch-specific.

**Tech Stack:** Existing Python 3.12+ / `uv` / Pydantic v2 / pytest / Pyright / Ruff stack. Reuse Phase 3 HTTP/provider infrastructure. Add no graph database. Use provider-native semantic/citation features where available. A local embedding model is not required for Phase 4 conformance; provider semantic search and existing `EmbeddingProvider` ports may be used.

**Spec:** `docs/specs/master-design-spec.md`, especially Sections 18–22, 42, 44–46, 49–50, 54–55, 60 Phase 4, 61–62, Appendix E, and Phase 3 traceability/contracts.

## Global Constraints

- Base Phase 4 on accepted Phase 3 commit `da34f36` or an explicitly accepted descendant.
- Implement **Phase 4 only**.
- Preserve Phase 3 evidence-family applicability, search-plan critique, coverage-floor semantics, and provider-neutral search intents.
- No search result or zero-result branch may be interpreted as a novelty verdict.
- Provider-local scores MUST NOT be compared across providers as though they share one scale.
- Lexical, semantic, citation, relation, and entity retrieval are distinct strategies and MUST remain identifiable in trace data.
- `RRF` or equivalent fusion is a **candidate-ranking aid**, never a novelty score.
- Search depth MUST be allocated adaptively after screening, but adaptive depth MUST NOT silently deactivate plausible evidence families.
- Apparent novelty MUST increase research rigor before strong positive novelty can later be permitted.
- Citation expansion, author/entity lineage, chronology, and historical-term expansion MUST be traceable as separate research actions.
- Every assessment has an `as_of` date; evidence after it may be stored but MUST be marked temporally invalid for historical novelty.
- `SATURATED` and `BUDGET_STOPPED` are distinct states.
- Budget exhaustion MUST NOT be relabeled as saturation.
- Access/provider failure MUST be explicit and branch-specific.
- Capture-recapture, if implemented, is diagnostic only and MUST NOT be reported as exact prior-art coverage.
- No source may become decisive evidence in Phase 4; source normalization/provenance/evidence graph remain Phase 5.
- No equivalence mapping or support verification in Phase 4; those belong to Phase 6.
- No prosecutor/defender or novelty adjudication in Phase 4; those belong to Phase 7.
- No live network in default tests. Live provider tests remain opt-in.
- External responses remain untrusted data.
- Provider-specific feature support MUST be discovered through capability metadata rather than assumed globally.
- New provider-native strategy support MUST not leak vendor-specific semantics into the domain layer.
- Phase 4 is complete only when known-item retrieval fixtures recover designated disguised prior art at the project-defined baseline and the end-to-end slice uses real Phase 2 + Phase 3 + Phase 4 behavior while later evidence/adjudication remains fixture-backed.

## Research-informed provider facts to respect

These are implementation constraints derived from current provider behavior, not product semantics:

- OpenAlex semantic search is a distinct search mode, uses up to 2,000 query characters, returns up to 50 results, and cannot be mixed with ordinary `search` in the same request.
- OpenAlex works expose outgoing references, incoming citation queries, and related-work neighborhoods.
- Semantic Scholar exposes relevance search, embeddings, citations, references, and author-paper traversal.
- Crossref supports cursor pagination and large row counts, but remains bibliographic rather than a general semantic/citation engine.
- GitHub search uses separate search-rate accounting; response headers are authoritative for current quota state.

Provider capabilities must encode these differences explicitly.

## Review Focus

1. **Score leakage:** provider-local relevance/cosine/search scores get mixed as if comparable.
2. **False saturation:** diminishing yield from one strategy/provider is treated as global saturation.
3. **Search monoculture:** many paraphrases through the same retrieval mechanism are mistaken for diversified coverage.
4. **Chronology leakage:** post-cutoff sources silently negate historical novelty.
5. **Adaptive bias:** branches with initially few hits receive less effort instead of more falsification effort.

---

## Phase 4 File Map

Prefer the following focused structure unless accepted Phase 3 files already own the responsibility:

```text
src/novelty_harness/
  research/
    retrieval/
      __init__.py
      models.py
      executor.py
    fusion/
      __init__.py
      rrf.py
      clustering.py
    expansion/
      __init__.py
      citations.py
      entities.py
      chronology.py
    adaptive/
      __init__.py
      models.py
      controller.py
      escalation.py
      stopping.py
      pipeline.py
    providers/
      openalex_semantic.py
      semantic_scholar.py
      crossref_pagination.py
      github_expansion.py
  runtime/
    budgets/
      controller.py
  evaluation/
    known_item.py

tests/
  unit/
    research/
      retrieval/
      fusion/
      expansion/
      adaptive/
  integration/
    test_phase4_retrieval_pipeline.py
    test_phase3_slice_with_phase4_research.py
  adversarial/
    test_phase4_retrieval_attacks.py
  benchmarks/
    test_known_item_retrieval.py
  fixtures/
    phase4.py
    known_items/

docs/
  traceability/
    phase-4.yaml
  architecture/
    decisions/
      ADR-016-retrieval-strategy-taxonomy.md
      ADR-017-rank-fusion.md
      ADR-018-adaptive-stopping.md
      ADR-019-semantic-scholar-provider.md
```

---

## Prerequisite Gate — Accept Phase 3 Baseline

Before Phase 4 coding:

- create an isolated worktree based on accepted Phase 3 final commit `da34f36`;
- suggested branch: `phase-4-adaptive-retrieval`;
- run:
  ```bash
  uv sync --dev
  uv run python scripts/verify.py
  git diff --check
  ```
- confirm Phase 3 completion report remains accurate;
- do not begin Phase 4 if baseline verification fails.

---

### Task 1: Define retrieval-strategy and candidate contracts

**Files:**
- Create: `src/novelty_harness/research/retrieval/models.py`
- Create: `tests/unit/research/retrieval/test_models.py`
- Create: `docs/architecture/decisions/ADR-016-retrieval-strategy-taxonomy.md`

**Interfaces:**

```python
class RetrievalStrategy(str, Enum):
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"
    RELATIONAL = "RELATIONAL"
    CITATION_BACKWARD = "CITATION_BACKWARD"
    CITATION_FORWARD = "CITATION_FORWARD"
    RELATED_WORK = "RELATED_WORK"
    ENTITY_LINEAGE = "ENTITY_LINEAGE"
    HISTORICAL_TERM = "HISTORICAL_TERM"
    ADJACENT_DOMAIN = "ADJACENT_DOMAIN"

class RetrievalCandidate(ContractModel):
    candidate_key: str
    source: SourceRef
    mcu_id: MCUId | None
    evidence_family: EvidenceFamily
    provider_name: str
    strategy: RetrievalStrategy
    query_id: QueryId | None
    local_rank: int
    provider_score: float | None = None
    discovered_at: datetime
    raw_metadata: dict[str, JsonValue] = Field(default_factory=dict)

class RetrievalBatch(ContractModel):
    strategy: RetrievalStrategy
    provider_name: str
    candidates: list[RetrievalCandidate]
    next_cursor: str | None = None
    exhausted: bool = False
    call: ProviderCallMetadata
```

Validation:
- rank >= 1;
- candidate keys non-blank;
- provider score is retained as provider-local metadata only;
- strategy and provider identity mandatory;
- duplicate candidate IDs within one batch rejected or normalized deterministically.

Tests must prove two candidates with identical numerical scores from different providers are not treated as comparable by any shared model helper.

- [ ] Write failing tests.
- [ ] Implement models.
- [ ] Write ADR defining what counts as genuinely distinct retrieval strategy.
- [ ] Commit.

---

### Task 2: Implement lexical, relational, historical, and adjacent-domain retrieval execution

**Files:**
- Create: `src/novelty_harness/research/retrieval/executor.py`
- Create: `tests/unit/research/retrieval/test_executor.py`

**Interface:**

```python
class RetrievalExecutor:
    async def execute_intent(
        self,
        *,
        intent: SearchIntent,
        provider: SearchProvider,
        strategy: RetrievalStrategy,
        cursor: str | None = None,
    ) -> RetrievalBatch:
        ...
```

Policy:
- Phase 3 `SearchIntent` remains the conceptual input;
- provider compiler translates it;
- lexical/direct/function/mechanism/outcome query families execute as lexical/search-native retrieval unless provider capability says otherwise;
- `RELATIONSHIP` retains `RELATIONAL` strategy label even if executed through provider-native text search;
- historical terminology retains `HISTORICAL_TERM`;
- adjacent-domain retains `ADJACENT_DOMAIN`;
- candidate identity and local rank retained exactly;
- no fusion in this module.

Tests:
- pagination cursor propagation;
- zero-result batch is valid;
- provider failure remains explicit;
- strategy label does not collapse merely because the same endpoint is used;
- local score remains provider-local.

- [ ] Write tests.
- [ ] Implement.
- [ ] Commit.

---

### Task 3: Extend OpenAlex with semantic search and citation/related expansion

**Files:**
- Extend accepted OpenAlex adapter;
- Create: `src/novelty_harness/research/providers/openalex_semantic.py` if separation is cleaner;
- Create/extend provider contract tests;
- Add recorded fixtures.

Required capabilities:
- semantic work search;
- ordinary cursor pagination for non-semantic work search;
- referenced works;
- incoming citations;
- related works.

Constraints:
- semantic mode must not be silently combined with ordinary search;
- semantic input limit must be enforced/truncated only with explicit trace metadata;
- result cap/endpoint constraints must be represented in capability metadata;
- citation/related expansion returns `RetrievalCandidate`s with correct strategy labels;
- no OpenAlex relevance score is compared to Crossref/Semantic Scholar scores.

Tests:
- semantic search compilation;
- 2,000-character handling;
- citation direction correctness;
- related-work classification;
- cursor handling;
- chronology metadata extraction where provided.

- [ ] Implement + contract tests.
- [ ] Add opt-in live smoke coverage.
- [ ] Commit.

---

### Task 4: Add Semantic Scholar scholarly retrieval/expansion provider

**Files:**
- Create: `src/novelty_harness/research/providers/semantic_scholar.py`
- Create provider tests/fixtures.
- Create: `docs/architecture/decisions/ADR-019-semantic-scholar-provider.md`

Capabilities:
- paper relevance search;
- paper metadata lookup;
- backward references;
- forward citations;
- related author-paper/entity traversal where used;
- optional SPECTER embedding fields may be captured but MUST NOT be treated as calibrated novelty/equivalence.

Provider rules:
- API-key support optional/configurable;
- pagination/offset continuation explicit;
- rate-limit/provider failures explicit;
- citations/references mapped to correct expansion strategies;
- do not request nested expansion data in bulk-search endpoints that do not support it;
- provider score remains local.

- [ ] Write recorded contract tests first.
- [ ] Implement adapter.
- [ ] Add opt-in live smoke test.
- [ ] Document ADR.
- [ ] Commit.

---

### Task 5: Upgrade Crossref and GitHub for deeper retrieval

**Files:**
- Create/extend: `crossref_pagination.py`
- Create/extend: `github_expansion.py`
- Add tests/fixtures.

Crossref:
- support cursor pagination;
- preserve `next-cursor`;
- stop when returned rows are fewer than requested or cursor exhausts;
- remain lexical/bibliographic, not semantic;
- retain DOI/title/date metadata for later normalization.

GitHub:
- support paginated repository search;
- retain owner/org/repository entities;
- allow explicit entity-lineage follow-up for owner/org repositories where configured;
- respect authoritative rate-limit response headers;
- repository search only unless a later ADR expands scope.

Tests:
- cursor continuation;
- pagination exhaustion;
- GitHub search-bucket cooldown;
- entity lineage;
- no silent fallback from blocked GitHub to general web.

- [ ] Implement.
- [ ] Commit.

---

### Task 6: Implement Reciprocal Rank Fusion without score leakage

**Files:**
- Create: `src/novelty_harness/research/fusion/__init__.py`
- Create: `src/novelty_harness/research/fusion/rrf.py`
- Create: `tests/unit/research/fusion/test_rrf.py`
- Create: `docs/architecture/decisions/ADR-017-rank-fusion.md`

**Interface:**

```python
class FusedCandidate(ContractModel):
    candidate_key: str
    source_refs: list[SourceRef]
    contributing_lists: list[str]
    rrf_score: float
    best_local_rank: int
    strategies: set[RetrievalStrategy]
    providers: set[str]

def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[RetrievalCandidate]],
    *,
    k: int = 60,
) -> list[FusedCandidate]:
    ...
```

Rules:
- use ranks only;
- provider scores must not enter formula;
- `k` configurable and validated positive;
- same candidate appearing across multiple strategies/providers accumulates rank evidence;
- duplicates from one identical query/run must not be double-counted;
- stable deterministic tie-breaking.

Tests:
- exact RRF arithmetic;
- score leakage guard;
- duplicate-list guard;
- stable ties;
- one provider cannot dominate merely because its score scale is larger.

- [ ] Write tests.
- [ ] Implement.
- [ ] Commit.

---

### Task 7: Implement cross-strategy candidate clustering/deduplication

**Files:**
- Create: `src/novelty_harness/research/fusion/clustering.py`
- Create: `tests/unit/research/fusion/test_clustering.py`

Phase 4 dedup is candidate-level only, not Phase 5 provenance clustering.

Identity precedence:
1. stable provider/global identifier (DOI/OpenAlex/S2/GitHub repo identity);
2. canonical URL where appropriate;
3. conservative bibliographic identity;
4. otherwise keep separate.

Do not merge merely because titles are similar.

Output must preserve:
- all discovery paths;
- all provider identities;
- all strategy labels;
- earliest and latest observed dates;
- conflicting metadata for Phase 5 resolution.

Tests:
- same DOI across OpenAlex/Crossref/S2 clusters;
- title-similar distinct papers remain separate;
- GitHub fork/duplicate remains separate unless explicit identity relation known;
- conflicting dates retained rather than overwritten.

- [ ] Implement.
- [ ] Commit.

---

### Task 8: Implement citation, related-work, and entity expansion controller

**Files:**
- Create: `src/novelty_harness/research/expansion/citations.py`
- Create: `src/novelty_harness/research/expansion/entities.py`
- Create: `tests/unit/research/expansion/`

**Interfaces:**

```python
class ExpansionRequest(ContractModel):
    source: SourceRef
    mcu_id: MCUId | None
    kinds: set[RetrievalStrategy]
    depth: int = 1

class ExpansionResult(ContractModel):
    candidates: list[RetrievalCandidate]
    attempted_kinds: set[RetrievalStrategy]
    unavailable_kinds: set[RetrievalStrategy]
    failures: list[str]
```

Policy:
- strong candidate sources may trigger backward/forward citations and related work;
- author/project/company/entity expansion is explicit and budgeted;
- depth > 1 is not automatic;
- expansion must retain source-lineage seed;
- later source claiming to extend an earlier source should make predecessor investigation possible;
- unsupported provider capabilities become explicit unavailable kinds.

Tests:
- backward vs forward direction;
- expansion provider unavailable;
- no recursive explosion without controller approval;
- duplicate discoveries retain multiple paths.

- [ ] Implement.
- [ ] Commit.

---

### Task 9: Implement chronology capture and historical cutoff enforcement

**Files:**
- Create: `src/novelty_harness/research/expansion/chronology.py`
- Create: `tests/unit/research/expansion/test_chronology.py`

**Contracts:**

```python
class CandidateChronology(ContractModel):
    publication_date: date | None = None
    first_public_version: date | None = None
    repository_created_at: datetime | None = None
    first_release_date: date | None = None
    patent_priority_date: date | None = None
    patent_publication_date: date | None = None
    product_launch_date: date | None = None
    archive_capture_date: date | None = None

class TemporalAssessment(ContractModel):
    as_of: date
    predates_cutoff: bool | None
    decisive_date_field: str | None
    ambiguity: list[str] = Field(default_factory=list)
```

Rules:
- retain multiple date types;
- do not collapse dates to one generic `date`;
- post-cutoff evidence may still be stored for context, but must be marked invalid for negating historical novelty;
- uncertain date does not become a guessed date;
- metadata-derived chronology is provisional until Phase 5 source normalization.

Tests:
- pre/post-cutoff;
- repo creation vs release;
- patent priority vs publication;
- ambiguous/incomplete dates;
- later paper pointing to earlier predecessor.

- [ ] Implement.
- [ ] Commit.

---

### Task 10: Implement research budget controller

**Files:**
- Create/extend: `src/novelty_harness/runtime/budgets/controller.py`
- Create: `tests/unit/runtime/budgets/test_controller.py`

**Interface:**

```python
class BudgetUsage(ContractModel):
    provider_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    retrieved_documents: int = 0
    full_text_fetches: int = 0
    deep_search_rounds: int = 0
    elapsed_seconds: float = 0.0

class BudgetDecision(ContractModel):
    allowed: bool
    exhausted_dimensions: list[str]
    remaining: dict[str, float | int | None]

class BudgetController:
    def check(self, usage: BudgetUsage, limits: BudgetLimits) -> BudgetDecision: ...
```

Rules:
- `None` remains unlimited;
- hitting any configured hard limit makes additional action disallowed for that dimension;
- budget decisions are deterministic and independent of novelty judgment;
- budget exhaustion emits `BUDGET_STOPPED`, never `SATURATED`.

- [ ] Tests.
- [ ] Implement.
- [ ] Commit.

---

### Task 11: Implement adaptive research controller and escalation policy

**Files:**
- Create: `src/novelty_harness/research/adaptive/models.py`
- Create: `src/novelty_harness/research/adaptive/controller.py`
- Create: `src/novelty_harness/research/adaptive/escalation.py`
- Create: `tests/unit/research/adaptive/`

**Contracts:**

```python
class BranchState(ContractModel):
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    depth: ResearchDepth
    strategies_attempted: set[RetrievalStrategy]
    providers_attempted: set[str]
    rounds: int
    relevant_candidate_count: int
    new_candidate_yield: list[int]
    unresolved: bool
    access_failures: list[str]
    budget_stopped: bool = False

class ResearchAction(ContractModel):
    action_type: str
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    strategy: RetrievalStrategy | None
    provider_name: str | None
    rationale: str
```

Conceptual priority may use:
`relevance likelihood × uniqueness × decision impact / expected cost`,
but Phase 4 MUST NOT pretend these are calibrated probabilities.

Escalation policy:
- sparse/no matches on a plausible branch may trigger **more** strategy/provider diversity;
- high apparent novelty candidate state triggers additional providers, semantic retrieval, citation expansion, historical terminology, adjacent domains, and optionally multilingual hook;
- provider access failure does not reduce branch importance.

Tests:
- zero hits -> broader escalation, not de-prioritization;
- one strategy only -> add diversity;
- high candidate stability but missing plausible provider -> no saturation;
- budget exhausted -> stop as budget;
- access blocked -> explicit branch failure;
- already diverse/high-yield branch may deepen before broadening again.

- [ ] Implement.
- [ ] Commit.

---

### Task 12: Implement stopping and saturation logic

**Files:**
- Create: `src/novelty_harness/research/adaptive/stopping.py`
- Create: `tests/unit/research/adaptive/test_stopping.py`
- Create: `docs/architecture/decisions/ADR-018-adaptive-stopping.md`

**Contracts:**

```python
class StopReason(str, Enum):
    CONTINUE = "CONTINUE"
    SATURATED = "SATURATED"
    BUDGET_STOPPED = "BUDGET_STOPPED"
    ACCESS_BLOCKED = "ACCESS_BLOCKED"

class StopAssessment(ContractModel):
    reason: StopReason
    signals: dict[str, JsonValue]
    unresolved_gaps: list[str]
```

Saturation may consider:
- marginal new-candidate yield by round;
- overlap/convergence across genuinely distinct strategies;
- stability of strongest candidate clusters;
- citation-expansion yield;
- provider diversity;
- unresolved access gaps;
- applicable-family coverage;
- optional capture-recapture diagnostic.

Hard rules:
- one provider cannot establish saturation for a family configured to require multiple meaningful providers;
- one retrieval mechanism with many paraphrases cannot establish multi-strategy convergence;
- any material unresolved access gap blocks `SATURATED`;
- budget exhaustion overrides saturation labeling when the search stopped because budget prevented the next reasonable action;
- capture-recapture cannot alone establish saturation.

Tests:
- true diminishing-yield convergence;
- false monoculture saturation;
- budget-before-convergence;
- blocked provider;
- one strong source plus unexplored branches;
- all branches screened but citation neighborhood still yielding.

- [ ] Implement.
- [ ] Document ADR.
- [ ] Commit.

---

### Task 13: Build end-to-end Phase 4 research pipeline

**Files:**
- Create: `src/novelty_harness/research/adaptive/pipeline.py`
- Create: `tests/integration/test_phase4_retrieval_pipeline.py`
- Create: `tests/integration/test_phase3_slice_with_phase4_research.py`
- Create: `tests/fixtures/phase4.py`

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class ResearchResult:
    batches: tuple[RetrievalBatch, ...]
    fused_candidates: tuple[FusedCandidate, ...]
    chronology: dict[str, CandidateChronology]
    branch_states: tuple[BranchState, ...]
    stop_assessments: tuple[StopAssessment, ...]
    coverage_matrix: CoverageMatrix

async def run_adaptive_research(
    *,
    assessment: AssessmentRecord,
    mcus: Sequence[MCU],
    reviewed_plan: SearchPlan,
    provider_registry: ProviderRegistry,
    coverage_policy: CoveragePolicy,
    budget_controller: BudgetController,
    trace_sink: TraceSink,
    ...
) -> ResearchResult:
    ...
```

Required flow:
1. consume reviewed Phase 3 plan;
2. execute screening results as starting batches;
3. deepen paginated lexical retrieval where warranted;
4. invoke semantic retrieval where provider capability supports it;
5. execute relationship/historical/adjacent strategies distinctly;
6. fuse candidate lists using RRF;
7. expand strongest candidates through citations/related/entity paths within budget;
8. capture chronology;
9. update branch state after each round;
10. call adaptive controller for next action;
11. stop each branch only with explicit reason;
12. update coverage matrix with depth and stopping state.

Persist/emit:
- retrieval batches;
- fused candidates;
- expansion events;
- chronology;
- branch states;
- stopping decisions;
- updated coverage matrix;
- complete trace.

The full vertical slice must still reach `REPORTED/COMPLETED` using:
- real Phase 2 understanding;
- real Phase 3 planning;
- real Phase 4 retrieval/adaptive research;
- Phase 5+ evidence processing fixture-backed.

- [ ] Write integration tests first.
- [ ] Implement.
- [ ] Commit.

---

### Task 14: Implement known-item retrieval benchmark

**Files:**
- Create: `tests/benchmarks/test_known_item_retrieval.py`
- Create: `tests/fixtures/known_items/`
- Add `src/novelty_harness/evaluation/known_item.py` only if a production-neutral helper is useful.

Each benchmark case contains:
- disguised/paraphrased input;
- expected decisive source identity;
- allowed provider identities;
- attack type;
- target `K`.

Difficulty classes:
- canonical terminology;
- paraphrase;
- renamed established concept;
- abstract mechanism;
- cross-domain phrasing;
- translated phrasing hook where supported.

Metrics:
- Recall@K;
- reciprocal rank;
- retrieval path(s) that recovered source;
- provider/strategy diversity.

Do not hardcode a universal production threshold yet. Record the baseline distribution for later release criteria.

Required deterministic assertion:
- the engine recovers designated sources through multiple attack/path types, including lexical, semantic, and expansion/alternate-strategy recovery across the corpus.

Live benchmark metrics may be recorded but MUST NOT make CI flaky.

- [ ] Implement benchmark suite.
- [ ] Commit.

---

### Task 15: Add Phase 4 adversarial/metamorphic retrieval suite

**Files:**
- Create: `tests/adversarial/test_phase4_retrieval_attacks.py`

Mandatory cases:
1. exact terminology missing, semantic retrieval succeeds;
2. semantic retrieval misses, lexical historical term succeeds;
3. same provider with many paraphrases does not count as many independent strategies;
4. one strategy finds nothing, another finds close source -> escalation;
5. later paper points to earlier predecessor -> predecessor expansion;
6. post-cutoff source excluded from historical negation;
7. duplicate provider records collapse at candidate level;
8. similar titles but distinct works stay separate;
9. provider score-scale attack has no cross-provider fusion effect beyond ranks;
10. citation explosion constrained by budget;
11. blocked provider prevents false saturation;
12. budget exhaustion cannot become saturation;
13. sparse branch receives more research effort;
14. citation neighborhood still yielding -> continue;
15. candidate discovered from multiple paths retains all discovery routes;
16. empty field -> escalation, not novelty;
17. mature field -> pagination/depth without universal exhaustiveness claim;
18. multilingual hook remains explicit if unavailable rather than silently covered.

- [ ] Implement.
- [ ] Commit.

---

### Task 16: Traceability, architecture guards, and Phase 4 acceptance

**Files:**
- Create: `docs/traceability/phase-4.yaml`
- Create: `docs/phase-4-completion.md`
- Modify: `README.md`
- Extend architecture/import guards.

Traceability must cover:
- FR-RET-001 through FR-RET-003;
- FR-ARC-001 through FR-ARC-003;
- FR-EXP-001 through FR-EXP-003;
- Section 21 multilingual/adjacent-domain hooks;
- Section 22 stopping;
- Section 50 known-item retrieval benchmark;
- INV-01, INV-06, INV-10, INV-11, INV-12, INV-13 as architecturally relevant;
- explicit deferral of Phase 5+ evidence semantics.

Architecture guards:
- no provider-local score enters RRF;
- no `SATURATED` branch with unresolved material access gap;
- no budget-stopped branch serialized as saturated;
- no Phase 4 module assigns novelty verdict;
- no Phase 4 source becomes verified evidence merely by retrieval;
- chronology retains multiple date fields;
- default tests remain network-blocked;
- no production imports from test fixtures.

Final verification:
```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

Perform fresh-checkout verification if practical.

- [ ] Write completion report.
- [ ] Commit.

---

## Phase 4 Acceptance Gate

Phase 4 is accepted only when all are true:

1. Phase 3 accepted baseline passes before changes.
2. Final full verification passes.
3. Retrieval candidates retain provider, strategy, query, rank, and provider-local score separately.
4. Lexical, semantic, relational, historical, adjacent-domain, citation, related-work, and entity strategies are distinguishable.
5. OpenAlex semantic retrieval works through recorded/provider contract tests.
6. OpenAlex citation and related-work directions are correct.
7. Semantic Scholar retrieval/citation adapter passes contract tests.
8. Crossref cursor pagination works.
9. GitHub repository pagination/entity expansion works within declared scope.
10. RRF uses ranks only and is deterministic.
11. Candidate dedup preserves discovery-path diversity.
12. Chronology retains multiple relevant date types and applies `as_of`.
13. Post-cutoff evidence is marked temporally invalid for historical novelty negation.
14. Adaptive controller broadens sparse/unresolved branches rather than rewarding absence.
15. Provider/access failures remain explicit.
16. Budget exhaustion produces `BUDGET_STOPPED`.
17. Saturation cannot be produced by one monoculture strategy/provider when policy requires diversity.
18. Material unresolved access gaps block saturation.
19. Citation/entity expansion is budgeted and traceable.
20. High-apparent-novelty branches trigger additional falsification effort.
21. Coverage matrix reflects actual depth and stop state.
22. Known-item retrieval benchmark runs deterministically.
23. Benchmark captures Recall@K and retrieval paths.
24. All Phase 4 adversarial cases pass.
25. Full vertical slice reaches `REPORTED/COMPLETED` with Phase 2–4 real and Phase 5+ fixture-backed.
26. No source normalization/provenance/evidence graph was implemented beyond candidate-level identity.
27. No evidence equivalence/support verification was implemented.
28. No prosecutor/defender/adjudication was implemented.
29. No retrieval score is presented as novelty/confidence probability.
30. README/traceability accurately state implemented/deferred behavior.
31. Phase 5 has not started.

If any gate fails, do not begin Phase 5.

---

## Self-Review Against Master Spec

### Phase 4 coverage
- lexical/search-native retrieval -> Tasks 2, 3, 5;
- semantic retrieval -> Tasks 3–4;
- relational/function execution -> Task 2;
- RRF -> Task 6;
- dynamic depth -> Tasks 10–13;
- citation/entity expansion -> Tasks 3–5, 8;
- chronology -> Task 9;
- saturation vs budget stop -> Tasks 10–12;
- high-novelty escalation -> Task 11;
- known-item retrieval -> Task 14;
- adversarial robustness -> Task 15.

### Explicitly deferred
- canonical source normalization/provenance/evidence graph -> Phase 5;
- passage-grounded evidence mapping/support verification -> Phase 6;
- prosecutor/defender/adjudication -> Phase 7;
- full narrative report -> Phase 8;
- broad robustness/security release hardening -> Phase 9;
- empirical calibration -> Phase 10.

## Execution Handoff

Recommended execution: **isolated worktree + task-gated/subagent-driven implementation**. Phase 4 materially affects whether later absence-based novelty conclusions can be trusted, so retrieval-path correctness, stopping semantics, and benchmark evidence deserve independent review.

Do not start Phase 5 until this phase has been reviewed and explicitly accepted.
