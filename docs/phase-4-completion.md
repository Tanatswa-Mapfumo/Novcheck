# Phase 4 completion record

Scope: Multi-Strategy Retrieval and Adaptive Research only. Accepted baseline:
`da34f36`. Worktree: `/private/tmp/novcheck-phase4.WORKTREE`, branch
`phase-4-adaptive-retrieval`. Phase 5 has not started. No merge or push performed.

Status: Tasks 1-16 and all 31 Phase 4 acceptance gates pass. The independent
review's seven Important findings are closed by regression-tested fixes.
No Critical or Minor findings were reported. The review and author rulings are
recorded in [the Phase 4 review](reviews/phase-4-review.md). The branch remains
isolated and unmerged for the user; this is not authorization for Phase 5.

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
| 16 | a8d48a3 | Architecture guards, README, provider matrix, traceability, this report |

Post-task corrections: `7e09d7c` fixes deployed OpenAlex semantic-filter syntax
without relaxing local historical eligibility; `7d845a4` closes all seven
independent review findings, with 11 review regression cases and a committed
review record. This completion record is committed separately after verification.

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
matrix, `docs/traceability/phase-4.yaml`, independent review record, this completion
record. In total, 71 paths differ from accepted baseline `da34f36`.

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
After the final code/review corrections, both the isolated implementation
worktree and an independent local clone at `7d845a4` passed:

```text
uv sync --dev                 PASS; 25 packages resolved, 24 checked
uv run python scripts/verify.py
  Ruff check                PASS
  Ruff format --check       PASS; 190 files formatted
  Pyright                   PASS; 0 errors, 0 warnings, 0 informations
  Pytest                    PASS; 1,090 passed, 5 opt-in network cases deselected
git diff --check            PASS; no whitespace errors
```

Default unit/contract/integration/benchmark/adversarial tests remained fully
network-isolated. The 18 mandatory Phase 4 adversarial cases, one additional
Crossref partial-date case and 11 independent-review regression cases all pass.
The review cases cover depth-deferred top neighborhoods, final-round wire work,
elapsed cooldown/in-flight limits, overflow dates, opaque DOI-like IDs, malformed
native IDs, both OpenAlex hydration directions and missing S2 edge rank spans.
The actual-engine six-case benchmark also passes in both worktrees.

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
without timing headers wait at least 60 seconds. Guards run after bounded pacing
and before each physical request, so retries and partial hydration obey budgets.
In-flight requests have remaining-deadline timeouts. Logical deep-search rounds
are charged once; per-wire guards still enforce every other physical budget.
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
Required, completed and depth-deferred major neighborhoods are tracked separately;
the configured depth cap cannot turn skipped exploration into SATURATED. Provider
rank spans include missing graph targets, which remain incomplete access gaps.

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

## Live smoke checkpoint

Executed only through the marked, explicitly enabled network suite:
`NOVCHECK_LIVE_SMOKE=1 uv run pytest tests/network -m network --force-enable-socket -v -rs`.
Initial result: 3 passed, 1 failed (OpenAlex semantic BAD_REQUEST), 1 skipped
(Semantic Scholar RATE_LIMITED). Root cause was isolated with bounded anonymous
opt-in diagnostics: semantic `to_publication_date` is unsupported by the deployed
API, while `publication_year:<2027` succeeded. Commit `7e09d7c` fixes that syntax
and records its coarse-year limitation; a RED-to-GREEN regression retains a
same-year post-cutoff candidate as ineligible. Exact local `as_of` is not weakened.
Re-run: 4 passed, 1 skipped, exit 0. OpenAlex text/semantic, Crossref and GitHub
passed; Semantic Scholar live availability was rate-limited, not claimed verified.
All deterministic Semantic Scholar contracts remain required and passed.
After review corrections, the same opt-in command again exited 0: 4 passed
(OpenAlex text and native, Crossref, GitHub), 1 skipped (Semantic Scholar
RATE_LIMITED). This does not claim live S2 availability. The final deterministic
and fresh-clone count is 1,090 passed with 5 network cases deselected.

## Rulings and costs

- Inline sequential execution with TDD/full task gates and one independent final
  reviewer preserves the critical path; cost: no fresh reviewer per task.
- Temporary isolated worktree preserves the original/accepted checkouts; cost:
  implementation is outside the IDE's original checkout.
- Existing concrete-provider ownership stays in `providers/`; cost: some optional
  plan file-map paths differ, without changing domain interfaces.
- Keep Phase 3 coverage semantics unchanged and add Phase 4 sidecars; cost: a
  separate adaptive coverage artifact.
- Inherit reviewer model under tool restrictions; cost: inherited model expense,
  rather than an explicitly selected model override.
- Rich reviewed ResearchPlan, versioned Pydantic ResearchResult, native screening
  and neutral wire-budget/audit hooks follow ADR-021; cost: new optional boundary
  and artifact types while legacy entry points remain supported.
- Creation/priority are not silently public disclosure and full dates alone
  establish provisional eligibility (ADR-020); cost: conservative unknown dates
  until later source verification.
- Supported semantic year filter plus exact local cutoff (ADR-020) corrects a live
  API contract mismatch; cost: same-year later context is retained but ineligible,
  and the coarse provider-side filter is explicitly traced.
- Seven Important review findings were accepted and corrected without broadening
  Phase 4 into source truth, evidence support or adjudication. Exact rulings,
  consequences and declined-to-judge costs are in `docs/reviews/phase-4-review.md`.
- A safety guard rejected temporarily disabling the in-flight deadline solely
  to reproduce the new timeout regression's RED phase. The safeguard remained
  intact; its passing test and the earlier reproduced cooldown RED case cover
  this deadline boundary. No broader implementation was blocked.

## Acceptance gates

| Gate | Evidence | Checkpoint result |
| --- | --- | --- |
| 1 | Accepted baseline 936 deterministic tests | PASS |
| 2 | Full verification after review fixes, implementation and independent local clone: 1,090 pass | PASS |
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
| 30 | README, provider matrix, traceability and committed independent review | PASS |
| 31 | No Phase 5 implementation | PASS |

## Exact changed paths

```text
README.md
docs/architecture/decisions/ADR-016-retrieval-strategy-taxonomy.md
docs/architecture/decisions/ADR-017-rank-fusion.md
docs/architecture/decisions/ADR-018-adaptive-stopping.md
docs/architecture/decisions/ADR-019-semantic-scholar-provider.md
docs/architecture/decisions/ADR-020-provisional-chronology.md
docs/architecture/decisions/ADR-021-adaptive-integration-and-budgets.md
docs/phase-4-completion.md
docs/providers/provider-matrix.md
docs/reviews/phase-4-review.md
docs/superpowers/plans/2026-09-27-phase-4-multi-strategy-retrieval-adaptive-research-implementation-plan.md
docs/traceability/phase-4.yaml
src/novelty_harness/application/research_phase4.py
src/novelty_harness/application/vertical_slice.py
src/novelty_harness/evaluation/__init__.py
src/novelty_harness/evaluation/known_item.py
src/novelty_harness/ports/retrieval.py
src/novelty_harness/ports/retrieval_audit.py
src/novelty_harness/providers/_retrieval.py
src/novelty_harness/providers/crossref_pagination.py
src/novelty_harness/providers/github_expansion.py
src/novelty_harness/providers/http.py
src/novelty_harness/providers/openalex_semantic.py
src/novelty_harness/providers/semantic_scholar.py
src/novelty_harness/research/adaptive/__init__.py
src/novelty_harness/research/adaptive/controller.py
src/novelty_harness/research/adaptive/escalation.py
src/novelty_harness/research/adaptive/models.py
src/novelty_harness/research/adaptive/pipeline.py
src/novelty_harness/research/adaptive/stopping.py
src/novelty_harness/research/expansion/__init__.py
src/novelty_harness/research/expansion/chronology.py
src/novelty_harness/research/expansion/citations.py
src/novelty_harness/research/expansion/entities.py
src/novelty_harness/research/fusion/__init__.py
src/novelty_harness/research/fusion/clustering.py
src/novelty_harness/research/fusion/rrf.py
src/novelty_harness/research/retrieval/__init__.py
src/novelty_harness/research/retrieval/executor.py
src/novelty_harness/research/retrieval/models.py
src/novelty_harness/runtime/budgets/__init__.py
src/novelty_harness/runtime/budgets/controller.py
tests/adversarial/test_phase4_retrieval_attacks.py
tests/adversarial/test_phase4_review_regressions.py
tests/benchmarks/test_known_item_retrieval.py
tests/fixtures/known_items/README.md
tests/fixtures/known_items/__init__.py
tests/fixtures/known_items/baseline.json
tests/fixtures/known_items/cases.json
tests/fixtures/phase4.py
tests/fixtures/provider_responses/semantic_scholar/search.json
tests/integration/test_phase3_slice_with_phase4_research.py
tests/integration/test_phase4_retrieval_pipeline.py
tests/network/test_phase4_live_provider_smoke.py
tests/unit/providers/test_deep_pagination.py
tests/unit/providers/test_openalex_retrieval.py
tests/unit/providers/test_semantic_scholar.py
tests/unit/research/adaptive/__init__.py
tests/unit/research/adaptive/test_controller.py
tests/unit/research/adaptive/test_stopping.py
tests/unit/research/expansion/test_chronology.py
tests/unit/research/expansion/test_controller.py
tests/unit/research/fusion/test_clustering.py
tests/unit/research/fusion/test_rrf.py
tests/unit/research/retrieval/test_executor.py
tests/unit/research/retrieval/test_models.py
tests/unit/runtime/__init__.py
tests/unit/runtime/budgets/__init__.py
tests/unit/runtime/budgets/test_controller.py
tests/unit/test_phase3_architecture_guards.py
tests/unit/test_phase4_architecture_guards.py
```
