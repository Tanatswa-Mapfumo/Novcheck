# Phase 4 completion record

Scope: Multi-Strategy Retrieval and Adaptive Research only. Accepted baseline:
`da34f36`. Worktree: `/private/tmp/novcheck-phase4.WORKTREE`, branch
`phase-4-adaptive-retrieval`. Phase 5 has not started. No merge or push performed.

Status: implementation Tasks 1-16 are present; final whole-branch review, live
smokes and independent-checkout verification are pending at this checkpoint.
This checkpoint is not a final Phase 4 acceptance claim.

## Tasks and commits

| Task | Commit | Implemented scope |
| --- | --- | --- |
| 1 | 24b14ab | Versioned retrieval contracts, strategy/mechanism separation, ADR-016 |
| 2 | 3055be0 | Provider-neutral text/perspective executor |
| 3 | 06cf9b2 | OpenAlex semantic, references, forward citations, related work |
| 4 | fe0b610 | Semantic Scholar relevance/metadata/graph/author adapter, ADR-019 |
| 5 | 9a74877 | Crossref cursor and GitHub pages/entity paths |
| 6 | eacad2f | Rank-only deterministic RRF, ADR-017 |
| 7 | c414d5c | Conservative candidate clusters, complete discovery retention |
| 8 | cef69e2 | Explicit bounded citation/entity expansion requests |
| 9 | afaefe5 | Provisional eight-field chronology/cutoff, ADR-020 |
| 10 | d5679f7 | Hard budgets and projected action costs |
| 11 | 79a05b1 | Sparse/apparent-novelty falsification action routing |
| 12 | 05e7cbf | Convergence/budget/access stopping, ADR-018 |
| 13 | 29fb7ca | Native budgeted screening/adaptive pipeline and real slice, ADR-021 |
| 14 | 17ce0a3 | Actual-engine known-item benchmark and observed baseline |
| 15 | d1ca90d | Mandatory 18 attacks plus Crossref partial-date regression |
| 16 | See branch log | Architecture guards, README, provider matrix, traceability, this report |

## Files and requirements

New production modules: `research/retrieval/{__init__,models,executor}.py`,
`research/fusion/{__init__,rrf,clustering}.py`,
`research/expansion/{__init__,citations,entities,chronology}.py`,
`research/adaptive/{__init__,models,controller,escalation,stopping,pipeline}.py`,
`runtime/budgets/{__init__,controller}.py`, `evaluation/{__init__,known_item}.py`,
`ports/{retrieval,retrieval_audit}.py`,
`providers/{_retrieval,openalex_semantic,semantic_scholar,crossref_pagination,github_expansion}.py`,
`application/research_phase4.py`.
Modified production: `providers/http.py`, `application/vertical_slice.py`.
New tests: focused retrieval, provider, fusion, expansion, budget and adaptive
tests; `test_phase4_retrieval_pipeline.py`, `test_phase3_slice_with_phase4_research.py`,
`test_known_item_retrieval.py`, `test_phase4_retrieval_attacks.py`,
`test_phase4_architecture_guards.py`, opt-in native smoke suite, Phase 4/known-item
fixtures. Existing Phase 3 architecture guard is scoped to its accepted modules
while preserving global SDK/fixture bans and its no-SATURATED screening contract.
Documentation: ADR-016 through ADR-021, approved Phase 4 plan copy, README, provider
matrix, `docs/traceability/phase-4.yaml`, this completion record.

Requirement mapping: FR-RET-001..003, FR-ARC-001/003, FR-EXP-001..003;
sections 18-22, 42, 45-47, 50, 54 and 60 Phase 4. INV-01/06/10/12/13 are guarded
architecturally. FR-ARC-002/INV-11 are preserved by explicit deferral: only later
verified direct earlier precedent can justify fast negative stopping, not retrieval
or an RRF score. See the detailed traceability file for implemented versus deferred.

## Deterministic verification

Accepted baseline before changes: `uv sync --dev`,
`uv run python scripts/verify.py`, `git diff --check`: PASS,
936 deterministic tests, 3 live cases deselected; Ruff/format/Pyright clean.
Each task had focused tests and a full verification gate before its commit.
Latest pre-acceptance full gate: 1,072 deterministic tests, 5 network cases
deselected; Ruff lint/format and strict Pyright pass; diff whitespace clean.
Final commands/count and fresh-checkout results will be recorded after final review.

## Benchmark baseline

All six controlled cases recovered their designated work at K=10 through the
real pipeline, real adapters and MockTransport (no live network).

| Attack type | Recall@10 | Reciprocal rank | Observed recovery |
| --- | --- | --- | --- |
| Canonical | 1.0 | 1.0 | OpenAlex text perspectives, nine paths |
| Paraphrase | 1.0 | 1.0 | OpenAlex native semantic, one path |
| Renamed concept | 1.0 | 1.0 | Semantic Scholar alternate corpus, nine text paths |
| Abstract mechanism | 1.0 | 0.5 | OpenAlex backward predecessor, one path |
| Cross-domain | 1.0 | 1.0 | OpenAlex adjacent-domain, one path |
| Translated hook | 1.0 | 1.0 | Explicit French query, lexical/semantic, two paths |

Macro Recall@10: 1.0; mean reciprocal rank: 0.9166666666666666.
Metrics retain query or seed, provider, strategy and local rank. Negative/missing
case records zero. `tests/fixtures/known_items/baseline.json` records observations,
not a universal release threshold. This corpus tests architecture/path recovery;
it does not measure production semantic translation, corpus recall or live quality.

## Provider and operational behavior

OpenAlex implements text cursors, semantic <=2000 chars/50 results without semantic
pagination, backward references, forward citations and related neighborhoods.
Semantic Scholar implements relevance offsets (<=1000 rank window), metadata,
references/citations and explicit author traversal; embeddings stay provider-local.
Crossref is bibliographic only, with opaque cursors and original date precision.
GitHub implements repository search (<=1000 window), numeric repository lookup and
public owner/user/org repositories. No code, contents, history or releases are fetched.
Other providers remain planned, never implicitly implemented or applicable-family
exclusions. Provider registry presence remains separate from applicability.

HTTP uses injected httpx, serial pacing, response-derived limits/cooldowns,
bounded exponential retries only for idempotent transient failures, safe attempt
records, known-value/key redaction and explicit failures. GitHub secondary throttles
without timing headers wait at least 60 seconds. Guards run after pacing and before
each physical request, so retries and partial hydration obey call/elapsed budgets.
Returned documents are counted separately; page-size parameters are clamped to
remaining budget. No credentials/error body/raw transport exception is persisted.
Fallback is never automatic or silent. Default deterministic tests block sockets.

## Fusion, chronology and allocation

RRF never reads raw/local provider scores: only positive local ranks and configurable
rank constant enter the formula. Pagination/alias lists from the same provider,
query, strategy and seed share a stream and cannot double-credit a document.
Fusion is scoped to one MCU/family. Candidate identity uses stable provider IDs,
explicit DOI, guarded exact URL or conservative full bibliography; titles alone
never merge. Every original observation/provider/strategy/query/seed survives;
conflicting metadata and earliest/latest observed dates remain available.
This is not Phase 5 provenance or independent-evidence clustering.

Eight chronology fields stay distinct, with original metadata retained. Full
public-disclosure dates are inclusive at `as_of`; partial dates are not guessed.
Creation/priority do not establish disclosure. Post-cutoff context is retained,
but `predates_cutoff=false` disallows historical negation. Unknown stays unknown.
Observation-hash keys preserve disagreeing dates, not a single overwritten cluster date.

Sparse/unresolved branches request additional real mechanisms/providers;
apparent-novelty is an external hypothesis requiring stronger falsification, never
an inferred score. Discovered top candidate seeds add explicit bounded graph/entity
actions. Deeper expansion requires configured approval. Translated intents can
travel through the reviewed plan; automated multilingual coverage is unavailable
and traced, optionally configured as a material access gap.

SATURATED requires all configured operational gates: successful provider and genuine
mechanism floors; clean applicable-family screening floor; diminishing new candidate
yield over the configured window; nonempty stable top clusters; observed cross-
mechanism overlap; explored major neighborhoods; and citation convergence when
required. At least two observations are required. Threshold values are explicit
caller settings, not novelty/confidence defaults. Material access gaps block
saturation. Budget preventing the next reasonable action yields BUDGET_STOPPED
with precedence; access gaps yield ACCESS_BLOCKED. Remaining unresolved work is
CONTINUE, not fabricated saturation. Retrieval candidates are routing proxies,
not verified relevant evidence or authority for later positive novelty conclusions.

## Decisions, deviations and limitations

ADRs: 016 retrieval boundaries, 017 RRF streams, 018 adaptive stopping,
019 Semantic Scholar capabilities, 020 provisional chronology,
021 native screening integration and wire budgets.
Provider implementation stays in the established `providers/` package, not an
optional nested provider directory. Rich ResearchPlan replaces the lossy legacy
SearchPlan at the new pipeline boundary. ResearchResult is a versioned Pydantic
artifact rather than an unvalidated dataclass. Phase 3 coverage stays immutable in
meaning; Phase 4 depth/stopping are sidecars. These decisions preserve accepted
interfaces and are documented instead of changing semantics silently.

Implementation used task-by-task inline TDD/full gates, one provider-documentation
sidecar and a final independent whole-branch reviewer, rather than fresh implementer/
reviewer agents per task. Temporary worktree preserves accepted checkouts; no merge.
No new dependencies. Provider adapters remain independent of concrete SDKs.

Known limits: operational candidate relevance proxies; metadata chronology remains
provisional; bounded native corpora/results; no canonical source/provenance/passages,
support verification, equivalence, prosecutor/defender or novelty adjudication.
No automated translation, archive/patent/web/standards/regulatory integration.
No deployed LLM or guaranteed live provider availability. The nine-question report
is the accepted minimal frozen-findings compiler, not later narrative intelligence.
All source/evidence/adjudication continuation artifacts are synthetic Phase 5+
fixtures. Retrieval never promotes a source to verified evidence by itself.

## Acceptance gates

| Gate | Evidence | Checkpoint result |
| --- | --- | --- |
| 1 | Accepted baseline 936 deterministic tests | PASS |
| 2 | Final full verification after final changes | PENDING |
| 3 | Retrieval model/path/rank/score tests | PASS |
| 4 | Nine labels and four mechanisms | PASS |
| 5 | OpenAlex native recorded/provider contracts | PASS |
| 6 | Directional references/cites/related tests | PASS |
| 7 | Semantic Scholar shared search/graph contracts | PASS |
| 8 | Crossref continuation tests | PASS |
| 9 | GitHub page/user/org tests | PASS |
| 10 | Rank-only RRF/metamorphic guards | PASS |
| 11 | Cluster/rekey/fusion discovery path tests | PASS |
| 12 | Eight-field chronology and cutoff tests | PASS |
| 13 | Post-cutoff temporal eligibility regression | PASS |
| 14 | Empty/sparse broader controller and pipeline tests | PASS |
| 15 | Safe failures, partial expansions and request events | PASS |
| 16 | Physical retries/budget stopping regression | PASS |
| 17 | Monoculture/provider-floor stopping tests | PASS |
| 18 | Material access gap stops, artifact validator | PASS |
| 19 | Budgeted graph/entity requests and trace | PASS |
| 20 | Apparent-novelty falsification routing tests | PASS |
| 21 | Actual depth/stop sidecar matrix, missing PATENT blocked | PASS |
| 22 | Deterministic actual-engine known-item benchmark | PASS |
| 23 | Recall@10, reciprocal rank and query/seed/provider paths | PASS |
| 24 | All 18 attacks plus partial Crossref regression | PASS |
| 25 | Real Phase 2-4 slice REPORTED/COMPLETED | PASS |
| 26 | Phase 4 candidate-only architecture guards | PASS |
| 27 | No equivalence/support evidence engine | PASS |
| 28 | No prosecutor/defender/adjudication engine | PASS |
| 29 | Rank/benchmark metrics never novelty probabilities | PASS |
| 30 | README, provider matrix and traceability | PENDING FINAL REVIEW |
| 31 | No Phase 5 implementation | PASS |
