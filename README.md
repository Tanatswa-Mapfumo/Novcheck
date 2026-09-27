# Novelty Assessment Harness

A phase-gated, evidence-grounded novelty assessment project.

The authoritative behavior is in [the master specification](docs/specs/master-design-spec.md).
Implementation follows [the Phase 0 plan](docs/superpowers/plans/2026-09-26-phase-0-repository-governance-contracts.md)
[the Phase 1 plan](docs/superpowers/plans/2026-09-26-phase-1-deterministic-thin-vertical-slice-implementation-plan.md)
and [the Phase 2 plan](docs/superpowers/plans/2026-09-26-phase-2-intake-sufficiency-robust-mcu-engine-implementation-plan.md),
followed by [the Phase 3 plan](docs/superpowers/plans/2026-09-27-phase-3-research-planner-provider-infrastructure-implementation-plan.md),
and [the Phase 4 plan](docs/superpowers/plans/2026-09-27-phase-4-multi-strategy-retrieval-adaptive-research-implementation-plan.md),
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

See [Phase 0 traceability](docs/traceability/phase-0.yaml),
[Phase 1 traceability](docs/traceability/phase-1.yaml),
[Phase 2 traceability](docs/traceability/phase-2.yaml),
[Phase 2 completion](docs/phase-2-completion.md) and
[architecture decisions](docs/architecture/decisions/) for scope and decisions.
