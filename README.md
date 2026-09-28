# Novelty Assessment Harness

A phase-gated, evidence-grounded novelty assessment project.

The authoritative behavior is in [the master specification](docs/specs/master-design-spec.md).
Implementation follows [the Phase 0 plan](docs/superpowers/plans/2026-09-26-phase-0-repository-governance-contracts.md)
[the Phase 1 plan](docs/superpowers/plans/2026-09-26-phase-1-deterministic-thin-vertical-slice-implementation-plan.md)
and [the Phase 2 plan](docs/superpowers/plans/2026-09-26-phase-2-intake-sufficiency-robust-mcu-engine-implementation-plan.md),
followed by [the Phase 3 plan](docs/superpowers/plans/2026-09-27-phase-3-research-planner-provider-infrastructure-implementation-plan.md),
[the Phase 4 plan](docs/superpowers/plans/2026-09-27-phase-4-multi-strategy-retrieval-adaptive-research-implementation-plan.md),
and [the Phase 5 plan](docs/superpowers/plans/2026-09-27-phase-5-source-normalization-provenance-evidence-graph-implementation-plan.md),
with [AGENTS.md](AGENTS.md).

Phase 0 provides versioned Pydantic contracts, canonical enums and opaque IDs,
pure audited lifecycle transitions, credential-free settings with unset budget
limits, six abstract async provider ports, deterministic test fixtures, canonical
hashing, append-only JSONL traces with secret-key redaction, and JSON logging.

Python 3.12+ and uv are required. Install and verify:

```bash
uv sync --dev
uv run python scripts/verify.py
```

The gate runs Ruff lint, Ruff format checks, strict Pyright application checks,
and pytest. Unit, contract, and integration tests block IPv4/IPv6 sockets; local
Unix sockets are allowed for asyncio wakeups. The `network` marker alone does not
enable network access. Opt-in provider smoke tests are described in Phase 3 below.

## Phase 1: Deterministic thin vertical slice

Phase 1 adds versioned CIR, sufficiency, MCU/combination, research, evidence and
deeply frozen adjudication contracts; nine replaceable async semantic-component
ports; an atomic per-file artifact writer; a deterministic nine-question report
compiler; and complete lifecycle orchestration. It does not assess real novelty.

Run the synthetic end-to-end fixture with the default network block:

```bash
uv run pytest tests/integration/test_phase1_vertical_slice.py -v
```

`run_vertical_slice` in `application/vertical_slice.py` accepts a request,
injected components, abstract search/content providers, trace sink, artifact
writer and clock. Production code never imports test fixtures. The fixture lives
only in `tests/fixtures/phase1.py`; production has no default semantic engine.

Each run retains the original request, CIR, sufficiency, MCU graph, reviewed
search plan, source/passages, verified edge snapshots, frozen adjudication,
`assessment.json`, `report.json`, `report.md`, `assessment_record.json` and
append-only `trace.jsonl`. Successful runs reach REPORTED/COMPLETED. The report
copies frozen verdicts and value maturity, records the adjudication hash, and
answers all nine canonical questions without providers or new novelty decisions.

**Fixture-backed/deferred:** normalization, sufficiency judgments, MCU
decomposition/reconciliation, query planning/review, evidence interpretation and
adjudication. Adaptive research, prosecutor/defender and robustness stages are
explicitly deferred in the trace. An empty coverage matrix is not saturation;
fixture support states and verdicts are synthetic test data, not real conclusions.
Source wrapping copies transport data and hashes exact content, without semantic
normalization, fuzzy deduplication, source-quality judgments or chronology checks.
Unknown source type/access completeness stay unknown. No novelty/confidence
scores, numerical thresholds, budgets or real external providers were added.

There is no CLI, database service, retry/resume or general partial-failure service
yet. Writes are atomic individually, not as a multi-file transaction. Assessment
and lifecycle/trace IDs remain opaque UUID4 IDs; transport source/passages use
stable exact-identity/content hashes (not semantic source identity resolution).
Trace writes are locked within one process, not across processes.
Redaction covers sensitive mapping keys, not secrets embedded in arbitrary prose.
The accepted Phase 1 snapshot is retained; Phase 2 extends understanding as below.

## Phase 2: Intake, sufficiency and robust MCU engine

Phase 2 adds real provider-independent, model-assisted understanding behind the
four existing intake/sufficiency/MCU ports. Strict structured validation, extractive
material-field grounding and explicit unknowns preserve original input. Structural
sufficiency ceilings do not use length/fluency or inferred novelty. Missing/withheld
mechanisms stay unassessable; claimed advantages remain CLAIMED.

Independent A/B prompts share only CIR/original input, never the other's result.
Alignment compares feature concepts, directed relationships and material scope;
semantic alias proposals must pass structural checks. Reconciliation retains
resolutions/disagreements and separate combinations. All six structural tests run.
Material unresolved instability caps affected contributions at EXPLORATORY and
reduces aggregate sufficiency before research; it does not decide a novelty verdict.

`understand_idea` in `intake/pipeline.py` accepts a request, SemanticRunner wrapping
the abstract LLMProvider, optional artifact writer/assessment ID and clock. It
returns frozen CIR/sufficiency, A/B, reconciliation and an immutable MCUVersion.
`UnderstandingComponents` is a fresh request-scoped adapter for the four existing
vertical-slice ports. It publishes A/B, alignment, critic, version and semantic-call
audits; initial CIR/sufficiency remain retained when final bindings/ceilings change.

```bash
uv run pytest tests/integration/test_phase1_slice_with_phase2_components.py -v
uv run pytest tests/adversarial/test_phase2_mcu_attacks.py -v
```

Default responses are recorded test data; production never imports fixtures.
No vendor SDK, live model, literature/web/patent search, evidence-family planner,
search critic, RRF, adaptive controller, prior-art equivalence, evidence support
reasoning, prosecutor/defender or novelty adjudication is implemented. Later
research/evidence/adjudication remain fixture-backed in the end-to-end tests.

Overrides use strict operation payloads and return new content-hashed versions
with actor/reason/time, parent and before/after graph audit. Merge/split explicitly
update affected combinations; dangling references reject the edit. No in-place
API, implicit cascading edit, database or UI. Rollback selects a retained parent.
Old structural ceilings are not erased by an override.

Span/schema checks do not prove semantic entailment or deployed model robustness.
Fixtures prove safeguards and architectural flow, not general model intelligence.
No real novelty assessment is possible yet. Phase 3 extends research as below.

## Phase 3: Research planner and provider infrastructure

Real provider-independent family applicability, multi-query strategy, independent
criticism and bounded revision now feed configurable screening coverage. All nine
families are assessed per MCU; unsupported exclusions remain unresolved. Missing
providers block coverage, never semantic applicability. Eleven query families
include functional, mechanistic, relational, historical, adjacent-domain and
separate combination intent. Every omission is available to the critic.

OpenAlex Works, Crossref bibliographic matching and GitHub repository search have
deterministic compilers and async HTTP adapters. Unsupported features fail explicitly;
Crossref is not an OpenAlex Boolean/full-text engine. HTTP attempts, delays, rate
metadata and failures are recorded without request credentials. No cross-provider
score comparison, deduplication/independence inference or saturation is performed.
Screening is bounded to one page per planned query/provider; zero hits are not novelty.

```bash
uv run pytest tests/integration/test_phase2_slice_with_phase3_planner.py -v
uv run pytest tests/adversarial/test_phase3_search_strategy_attacks.py -v
```

The first command runs real Phase 2 understanding and Phase 3 planning/screening
with recorded semantic outputs and MockTransport, without network access. The
accepted slice preserves its legacy artifacts; richer research artifacts live in
phase3/. An explicit fixture continuation receives screening hits. Source/passages,
evidence verification and adjudication remain synthetic, traced as fixture-backed.
The lifecycle still reaches REPORTED/COMPLETED and the report only copies frozen findings.

Default verification deselects all network tests and blocks sockets. Optional live
smokes issue one bounded request per implemented provider, validate contracts only,
and skip with a safe reason if credentials, network or quota are unavailable:

```bash
NOVCHECK_LIVE_SMOKE=1 uv run pytest tests/network -m network --force-enable-socket -v -rs
```

Optional environment references: OPENALEX_API_KEY, CROSSREF_MAILTO, GITHUB_TOKEN.
Do not place values in configuration/artifacts or command arguments. See the
[provider matrix](docs/providers/provider-matrix.md),
[Phase 3 traceability](docs/traceability/phase-3.yaml) and
[Phase 3 completion report](docs/phase-3-completion.md).

The retained Phase 3 path has no fusion, adaptive research or saturation.
No real evidence equivalence, adversarial reasoning, novelty adjudication,
scores or probabilities are implemented. Production still requires an injected
abstract LLMProvider; no vendor-specific model integration is supplied.

## Phase 4: Multi-strategy retrieval and adaptive research

Real native retrieval extends the reviewed Phase 3 plan: lexical, relational,
historical and adjacent-domain perspectives; OpenAlex semantic search and
directional citations/related works; Semantic Scholar relevance, references,
citations and author traversal; Crossref cursors; and GitHub repository pages and
explicit owner/org lineage. Providers remain async, HTTP-injected and SDK-free.

Rank-only RRF has a configurable constant and never reads provider-local scores.
Conservative candidate dedup preserves every provider/query/strategy/seed path,
raw metadata and conflicting dates; it is not canonical source normalization
or independent-evidence provenance. Chronology retains eight distinct date types;
unknown/partial dates stay unknown. Post-cutoff sources remain context only for
historical negation. Creation/priority alone do not establish public disclosure.

`run_adaptive_research` consumes an assessment-bound, independently PASS-reviewed
ResearchPlan, registry, coverage/budget/stopping policies and trace sink. Native
screening batches start the same budgeted flow. Sparse unresolved branches broaden
falsification; explicit apparent-novelty hypotheses require stronger research.
Wire guards count retries and partial expansions after pacing, before requests.
Coverage records actual depth and distinct SATURATED/BUDGET_STOPPED/ACCESS_BLOCKED
states. Saturation requires configured real provider/mechanism diversity and all
convergence gates; zero results, access gaps or budget stops never establish it.
Operational settings are not novelty or probability thresholds.
Depth-deferred major neighborhoods remain unresolved, not explored. Elapsed budgets
bound cooldown waits and in-flight requests. Missing citation targets retain wire
rank gaps and explicit incomplete-access records.

```bash
uv run pytest tests/integration/test_phase3_slice_with_phase4_research.py -v
uv run pytest tests/adversarial/test_phase4_retrieval_attacks.py -v
uv run pytest tests/benchmarks/test_known_item_retrieval.py -v
```

The slice reaches REPORTED/COMPLETED with real Phase 2-4 code and synthetic HTTP
recordings. Phase 4 batches, fusion, expansions, chronology, branch/stop/coverage
artifacts and request audits are persisted under phase4/. Source/passages,
support verification and adjudication remain explicitly Phase 5+ fixture-backed.
The nine-question report still copies frozen findings without a new novelty decision.

The six-case known-item baseline records Recall@10 and recovery paths through
lexical, semantic, alternate-corpus, predecessor, adjacent-domain and explicitly
translated-query paths. It tests architecture under controlled synthetic responses,
not live search quality or a universal release threshold. Automated translation
and multilingual coverage remain unavailable and traced. Patent/web/archive and
other future providers remain unimplemented; applicable families stay blocked.

Default tests remain network-blocked. The opt-in command above also runs bounded
Phase 4 native smokes; optional SEMANTIC_SCHOLAR_API_KEY is resolved at HTTP time.
See [Phase 4 completion](docs/phase-4-completion.md),
[traceability](docs/traceability/phase-4.yaml), [provider matrix](docs/providers/provider-matrix.md)
and [known-item baseline](tests/fixtures/known_items/baseline.json).
No Phase 5 source/provenance/evidence engine or later novelty intelligence is implemented.

## Phase 6: Evidence mapping, support verification and precedent classification

Phase 6 turns the Phase 5 evidence substrate into passage-grounded, independently
verified and locally classified source-to-MCU evidence. It performs no Phase 7
adjudication, prosecutor/defender reasoning or novelty verdict.

Four stages remain separate. MCU comparison profiles preserve mechanism,
relationships and control flow separately and never invent absent dimensions
(ADR-026). The mapper proposes dimension matches with exact passage citations
and is validated deterministically (ADR-026). Passage selection starts only
from the mapper's exact same-source/version passages; bounded context expansion
stays inside that source/version and records explicit blocks (ADR-027). The
blinded independent verifier receives only the proposition, material
commitments, claimed dimensions, exact passage text/locator and minimal
source/version identity — never a verdict, precedent proposal, prosecutor or
defender role, quality tier, retrieval rank, provider score, user novelty claim
or report wording (ADR-027). Commitment-level aggregation is deterministic:
`SUPPORTED` requires every material commitment, `PARTIALLY_SUPPORTED` records
the remainder, contradictions dominate, and insufficient evidence abstains and
names the missing context.

Chronology and quality gates run after verification and never change its state
(ADR-028). Local precedent classification covers direct, strong partial,
component-only, analogous, superficial, no-local-match, contradictory,
unresolved and unassessable states; `NO_DIRECT_PRECEDENT_IDENTIFIED` is local
only. Direct precedent requires exactly one eligible source/version with every
material commitment including contribution-bearing relationships and
configuration verified. Multi-source component evidence is summarized as
`MULTI_SOURCE_COMBINATION_ONLY` with stitching structurally forbidden; lineage
duplicates count once. Patent mode distinguishes one-reference
anticipation-like screening from multi-reference combination context and
retains claim/specification locators, priority and publication dates
(ADR-029).

```bash
uv run pytest tests/integration/test_phase5_slice_with_phase6_evidence.py -v
uv run pytest tests/adversarial/test_phase6_equivalence_attacks.py -v
uv run pytest tests/benchmarks/test_phase6_support_verifier.py -v
```

The slice reaches REPORTED/COMPLETED with real Phases 2-6; Phase 7+
adjudication stays visibly fixture-backed and consumes the real verified
edges. Phase 6 persists `phase6/profiles.jsonl`, `propositions.jsonl`,
`mappings.jsonl`, `support_claims.jsonl`, `support_verifications.jsonl`,
`context_expansions.jsonl`, `verified_edges.jsonl`,
`precedent_classifications.jsonl`, `multi_source_assessments.jsonl`,
`patent_screenings.jsonl` and `phase6_result.json`, and extends the SQLite
evidence graph with MCU, evidence-proposition and verified/precedent edges that
carry eligibility references. The deterministic support-verifier benchmark is
a diagnostic baseline, not calibration. Phase 6 is **not accepted** until the
mandatory independent GPT-6 Sol High semantic review is closed; see
[traceability](docs/traceability/phase-6.yaml) and
[completion record](docs/phase-6-completion.md).

### Earlier phases at a glance

## Phase 5: Source normalization, provenance and evidence graph

Phase 5 turns retrieved candidates into an auditable evidence substrate. It is
not Phase 6 equivalence/support reasoning and creates no adjudicated findings.

Canonical identity is derived from normalized stable identifiers with a fixed
ranking (DOI, patent number, GitHub repository, arXiv base id, OpenAlex,
Semantic Scholar, other, canonical URL, then a conservative discovery
fallback). Titles never establish identity. Same DOI across providers becomes
one source while every provider/query/strategy/seed discovery path is retained.
Disagreeing identifiers, titles, authors and dates are recorded as conflicts
and unresolved fields instead of guessed.

Versions are linked rather than counted: arXiv `vN`, preprint/journal and
repository releases carry deterministic content hashes; changed content creates
a new version with an explicit predecessor, never a silent overwrite. Passages
are exact, normalized, hashed slices of resolved content or abstracts with
structured locators; metadata, titles and search snippets cannot become
passage evidence. Access stays explicitly full-text, abstract-only,
metadata-only or blocked.

Provenance relations (`CITES`, `DERIVES_FROM`, `REPOSTS`, `VERSION_OF`,
`PATENT_FAMILY_OF`, `IMPLEMENTS`, `DOCUMENTS`, `FOUND_BY`) carry their evidence
and a categorical `CONFIRMED`/`POSSIBLE` lineage level. Only confirmed
dependency relations collapse lineage; citation and discovery never do. Lineage
clusters count independent roots, so a press release plus fifty confirmed
derivatives is one root, patent-family members do not inflate independence, and
circular dependencies keep clusters ambiguous and conservative. Quality and
relevance remain separate contracts; source type alone never decides a tier and
relevance can never raise quality.

`run_evidence_normalization` consumes the real `ResearchResult`, an optional
injected content resolver and an evidence-graph repository. It persists
`phase5/sources.jsonl`, `phase5/source_versions.jsonl`, `phase5/passages.jsonl`,
`phase5/provenance_edges.jsonl`, `phase5/lineage_clusters.jsonl`,
`phase5/source_quality.jsonl`, `phase5/source_relevance.jsonl`,
`phase5/provenance_cycles.jsonl`, `phase5/evidence_normalization.json` and the
SQLAlchemy/SQLite `phase5/evidence_graph.sqlite3`. Domain graph models stay
Pydantic and storage-independent; the repository returns domain models only;
batch writes are transactional with foreign keys and versioned schema.

```bash
uv run pytest tests/integration/test_phase4_slice_with_phase5_evidence.py -v
uv run pytest tests/adversarial/test_phase5_provenance_attacks.py -v
```

The slice reaches REPORTED/COMPLETED with real Phase 2-5 code; Phase 6+
mapping, support verification and adjudication stay visibly fixture-backed over
the real Phase 5 sources and passages. Phase 5 reserves but never creates
`SUPPORTS`, `CHALLENGES`, `DIRECT_PRECEDENT`, `STRONG_PARTIAL_PRECEDENT`,
`COMPONENT_PRECEDENT`, `ANALOGOUS`, `NO_MATCH` or `CONTRADICTS` edges. There is
no prosecutor/defender, novelty score or probability. See
[Phase 5 completion](docs/phase-5-completion.md) and
[traceability](docs/traceability/phase-5.yaml).

See [Phase 0 traceability](docs/traceability/phase-0.yaml),
[Phase 1 traceability](docs/traceability/phase-1.yaml),
[Phase 2 traceability](docs/traceability/phase-2.yaml),
[Phase 3 traceability](docs/traceability/phase-3.yaml),
[Phase 4 traceability](docs/traceability/phase-4.yaml),
[Phase 5 traceability](docs/traceability/phase-5.yaml),
[Phase 2 completion](docs/phase-2-completion.md),
[Phase 3 completion](docs/phase-3-completion.md),
[Phase 4 completion](docs/phase-4-completion.md),
[Phase 5 completion](docs/phase-5-completion.md) and
[architecture decisions](docs/architecture/decisions/) for scope and decisions.
