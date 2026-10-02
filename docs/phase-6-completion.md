# Phase 6 completion record

Scope: Evidence Mapping, Support Verification, and Precedent Classification
only. Accepted baseline: `3974b4c`. Worktree:
`/private/tmp/novcheck-phase6.WORKTREE`, branch `phase-6-evidence-verification`.
Phase 7 has not started. No merge or push performed.

Status: Tasks 1-15 complete and all implementation-side Phase 6 acceptance
gates pass; 1389 deterministic tests pass with 5 opt-in network cases
deselected, and Ruff/format/strict Pyright are clean. **Phase 6 is NOT
accepted**: acceptance gate 30 requires the mandatory independent **GPT-6 Sol
High semantic review**, which has not yet been performed. See
[the review request](reviews/phase-6-review-request.md).

## 1. Tasks completed

| Task | Scope | Commit |
| --- | --- | --- |
| prereq | Phase 5 baseline gate on `3974b4c`; plan copy | `a318696` |
| 1 | Mapping/verification/precedent contracts | `bd07113` |
| 2 | MCU comparison profiles + ADR-026 | `96e4271` |
| 3 | Passage-grounded candidate mapper | `96e4271` |
| 4 | Passage selection and same-source context expansion | `88bb774` |
| 5 | Blinded independent support verifier + ADR-027 | `cbbdbac` |
| 6 | Bounded context-retry loop | `cbbdbac` |
| 7 | Verified-edge eligibility gates | `b04fe56` |
| 8 | Constrained precedent classification + ADR-028 | `b04fe56` |
| 9 | Single-source direct rule, anti-stitching, counterfactual | `b04fe56` |
| 10 | Patent single-reference screening + ADR-029 | `8f840eb` |
| 11 | Phase 6 graph persistence + repository eligibility guard | `b5a1adb`, `745795b` |
| 12 | Phase 6 pipeline and real slice integration | `b5974ad` |
| 13 | Deterministic support-verifier benchmark | `1cff179` |
| 14 | 20-case adversarial suite | `1cff179` |
| 15 | Architecture guards, traceability, README | final Task 15 commit |
| 16 | Independent GPT-6 Sol High review | **REQUIRED, not yet performed** |

## 2. Commits

`a318696`, `bd07113`, `96e4271`, `88bb774`, `cbbdbac`, `b04fe56`, `8f840eb`,
`b5a1adb`, `745795b`, `b5974ad`, `1cff179`, plus the Task 15 commit and this
record's commit on `phase-6-evidence-verification`.

## 3. Files changed

59 paths differ from `3974b4c` (+10,645/−52) on the
`phase-6-evidence-verification` branch.

New production packages: `evidence/mapping/{models,dimensions,mapper,prompts}.py`,
`evidence/context/{selection,expansion}.py`,
`evidence/verification/{models,gates,verifier,prompts}.py`,
`evidence/precedent/{models,gates,counterfactuals,patent}.py`,
`evidence/phase6_pipeline.py`, `evidence/graph/phase6_mapping.py`,
`application/evidence_phase6.py`. Modified: `evidence/graph/models.py`,
`evidence/graph/sqlalchemy_repository.py`, `application/vertical_slice.py`,
`domain/ids.py`, `tests/unit/test_phase5_architecture_guards.py`. New tests:
module tests under `tests/unit/evidence/{mapping,context,verification,precedent}`,
`tests/unit/evidence/graph/test_phase6_mapping.py`,
`tests/unit/test_phase6_architecture_guards.py`, both Phase 6 integration
tests, the adversarial suite, the benchmark and its baseline fixture. Docs:
ADR-026…029, `docs/traceability/phase-6.yaml`, README section, review request,
this record, plan copy.

## 4. Requirement IDs implemented

FR-EVID-001…005; FR-EQ-001…004; FR-EXP-002/003 chronology gates; sections
27-30, 39.1 patent lens, 24 quality separation, 26/44 graph persistence,
60 Phase 6. Full mapping in `docs/traceability/phase-6.yaml`.

## 5. Total tests

1389 deterministic tests passed at the reviewed commit `e4683fd` (5 opt-in
network cases deselected); baseline was 1259, so Phase 6 added 130 tests then.
After the F01-F11 remediation the suite is **1426 tests** (37 review-derived
regressions added). The final code commit `ebb398f` was also verified from a fresh local
clone (`git clone --branch phase-6-evidence-verification`): `uv sync --dev`
and `uv run python scripts/verify.py` passed with 1389 tests and clean
Ruff/format/Pyright, and `git diff --check` was clean. This record's finalizing
documentation commit contains no code changes.

## 6. Support-verifier benchmark results

`tests/benchmarks/test_phase6_support_verifier.py` runs eight claim/evidence
cases through the real verification pipeline with a documented lexical baseline
judge (diagnostic baseline, **not** calibration):

| Case | Expected | Observed |
| --- | --- | --- |
| support | SUPPORTED | SUPPORTED |
| contradiction | CONTRADICTED | CONTRADICTED |
| insufficient evidence | INSUFFICIENT_CONTEXT | INSUFFICIENT_CONTEXT |
| special case only | INSUFFICIENT_CONTEXT | INSUFFICIENT_CONTEXT |
| negative qualifier (context retry) | CONTRADICTED | CONTRADICTED |
| conditional claim | INSUFFICIENT_CONTEXT | INSUFFICIENT_CONTEXT |
| population/context mismatch | NOT_SUPPORTED | NOT_SUPPORTED |
| dispersed relationship | NOT_SUPPORTED | NOT_SUPPORTED |

Metrics recorded in `tests/fixtures/phase6_support_benchmark.json`: support-state
accuracy 1.0, SUPPORTED precision 1.0, contradiction recall 1.0,
insufficient-context abstention 1.0, passage/rationale faithfulness 1.0.

## 7. Adversarial test results

`tests/adversarial/test_phase6_equivalence_attacks.py`: all 20 mandatory cases
plus a Phase 7 leakage guard pass (21/21), including same-nouns/different-
relation, terminology-independence, abstract-without-proposition, special
cases, hidden negation, post-cutoff ineligibility, three-source stitching,
components-without-configuration, missing constraint, analogy inflation,
self-claimed novelty, high-quality unsupported evidence, low-quality supported
evidence, contradictory passages, version changes, stitched patents, prompt
injection, quality/order blindness, mapper-invented relationships and
passage/locator/version mismatch.

## 8. Mapper/verifier separation

Separate packages, contracts and prompts: `EvidenceMapperV2` produces only a
proposal (`SourceMCUMapping`) from proposition + passages; `IndependentSupportVerifier`
consumes only a `BlindedVerificationInput` built by `build_blinded_input`; the
classifier consumes mapping + verification deterministically. Architecture
guards assert the verifier signature is exactly `{self, bundle, clock}` and
that Phase 6 modules never import or name Phase 7 adjudication concepts.

## 9. Exact verifier inputs

`BlindedVerificationInput` contains only: claim id, source id, source version
id, proposition statement, material commitments, claimed dimensions, claimed
relationships, exact passage text + locator, and a fixed `blinded=True` marker.
It uses `extra="forbid"`; tests assert the exact field set and reject injected
verdict/precedent/role/quality/rank/score/report fields.

## 10. Context expansion

Only `INSUFFICIENT_CONTEXT` triggers `expand_passage_context`, which finds a
wider stored passage of the same source **and version** containing the original
text, slices a bounded window (default 600 chars), creates a new hashed
passage, and records the origin linkage. Blocked expansions carry an explicit
reason; retries are capped (default 2) and exhausted expansion stays
insufficient. Contradictions are final unless passage integrity fails.

## 11. Single-source direct precedent

`PrecedentClassification.single_source` is `Literal[True]`, so combining
sources is structurally impossible. Direct precedent requires verified
`SUPPORTED` for every material commitment of one source/version, including
contribution-bearing relationships/configuration, plus decisive pre-cutoff
eligibility. The graph boundary independently requires a decisive eligibility
ref for `DIRECT_PRECEDENT` edges, and the repository re-checks it.

## 12. Multi-source stitching prevention

`summarize_multi_source` reports `MULTI_SOURCE_COMBINATION_ONLY` with
`stitched_direct_forbidden=True` whenever two or more independent lineage roots
contribute without a single direct-eligible source. `independent_root_of`
collapses versions/mirrors/family duplicates to one contributing root.

## 13. Chronology gates

`assess_chronology` uses public-disclosure fields only (publication,
first public version, first release, patent publication, product launch,
archive capture); priority/creation dates cannot make a source pre-cutoff.
Post-cutoff or uncertain chronology blocks decisiveness and turns an
otherwise-direct match into `UNRESOLVED`.

## 14. Patent one-reference screening

`screen_patent_references` emits `SINGLE_REFERENCE_ANTICIPATION_LIKE` only for
exactly one decisive direct-classified reference (earliest by priority
deterministically), `MULTI_REFERENCE_COMBINATION_LIKE` for two or more partial
references (never relabeled), and `LIMITED`/`UNASSESSABLE` with explicit
not-absence language when evidence is missing. Priority and publication dates
stay separate and claim/specification locators are retained. Fixed disclaimer:
`patent-screening-not-legal-advice-v1`.

## 15. Verified graph-edge eligibility

Phase 6 edge kinds require an `EdgeVerificationRef`; `DIRECT_PRECEDENT`
requires decisive fully-supported evidence, `SUPPORTS` requires full support,
`CONTRADICTS` requires a verified contradiction, and partial precedent kinds
require partial/full support. Phase 5 provenance edges must not carry
verification refs. The SQLAlchemy repository rejects ineligible Phase 6 edges
even if constructed outside the domain validators. No verdict is stored.

## 16. ADRs

ADR-026 mapping dimensions, ADR-027 independent support verification,
ADR-028 precedent classification and anti-stitching, ADR-029 patent
single-reference screening.

## 17. Deviations

- Precedent classification is deterministic over mapping + verification rather
  than a separate classifier LLM call; the plan's "constrained classification"
  is satisfied with stronger guarantees, and ADR-028 documents it.
- `ContextExpansion` carries the window `PassageRecord` instead of only an id
  so retries remain self-contained.
- The Phase 6 graph fragment emits MCU and evidence-proposition nodes in
  addition to verified edges (required so edges cannot dangle).
- `RESERVED_EDGE_KINDS` is retained as a Phase 6 alias for backwards
  compatibility; Phase 5 guards were re-scoped to Phase 5 semantic packages
  because the shared graph domain now references Phase 6 kinds behind
  eligibility refs.
- The benchmark uses a documented lexical baseline judge (offline) rather than
  a live model; it is explicitly a diagnostic baseline.

## 18. Remaining fixture-backed stages

Phase 7 prosecutor/defender, counterbalanced adjudication, four gates, verdict
permission matrix, abstention and final novelty verdict; Phase 8 narrative
report. The accepted slice keeps `PHASE7_FIXTURE_BOUNDARY` and a fixture
adjudicator over the real Phase 6 verified edges.

## 19. Acceptance gates 1-29 (implementation-side)

| Gate | Evidence | Result |
| --- | --- | --- |
| 1 | Phase 5 baseline clean (1259 tests) | PASS |
| 2 | Final full verification (1389 tests, Ruff/format/Pyright clean) | PASS |
| 3 | Profiles preserve relationship/control-flow structure | PASS |
| 4 | Mappings are exact-passage grounded | PASS |
| 5 | Mapping never verifies support | PASS |
| 6 | Verifier blinded from verdict/prestige | PASS |
| 7 | SUPPORTED requires all material commitments | PASS |
| 8 | Partial support states the remainder | PASS |
| 9 | Insufficient context expands same-source context | PASS |
| 10 | Unsupported evidence cannot create decisive edges | PASS |
| 11 | Contradictions remain contradictions | PASS |
| 12 | Passage/source/version integrity enforced | PASS |
| 13 | Post-cutoff evidence cannot negate historical novelty | PASS |
| 14 | Direct precedent requires one eligible source/version | PASS |
| 15 | Stitching cannot create direct combination precedent | PASS |
| 16 | Component precedent separate from combination precedent | PASS |
| 17 | Relationship mismatch defeats direct equivalence | PASS |
| 18 | Terminology mismatch alone cannot defeat equivalence | PASS |
| 19 | Analogy cannot become direct without relationship support | PASS |
| 20 | Patent mode preserves the one-reference distinction | PASS |
| 21 | Quality/relevance cannot alter blinded support state | PASS |
| 22 | Verified edges retain exact passages and mappings | PASS |
| 23 | Benchmark runs deterministically | PASS |
| 24 | All adversarial cases pass (21/21) | PASS |
| 25 | Slice reaches REPORTED/COMPLETED with Phases 2-6 real | PASS |
| 26 | No prosecutor/defender implemented | PASS |
| 27 | No final novelty verdict/gates implemented | PASS |
| 28 | No novelty probability/scalar confidence added | PASS |
| 29 | README/traceability correctly defer Phase 7+ | PASS |

## 20. Phase 7 status

Not started. No prosecutor, defender, counterbalanced adjudication, final gate
logic, final novelty verdict, strong-positive novelty permission or novelty
probability exists. Phase 6 modules are guard-tested against Phase 7 symbols.

## 21. Required independent review

**Phase 6 must not be marked accepted.** Acceptance gate 30 requires the
mandatory independent **GPT-6 Sol High semantic review**; gate 31 (Phase 7 has
not started) is satisfied. The review scope and required follow-up are recorded
in [the review request](reviews/phase-6-review-request.md); findings must be
reproduced, regression-tested, fixed, fully re-verified and documented in
`docs/reviews/phase-6-final-review.md` before acceptance.

## Semantic review remediation (F01–F11, M01)

The mandatory GPT-6 Sol High review of commit `e4683fd` returned **FAIL** with
findings F01–F11 and minor observation M01
(`docs/reviews/phase-6-final-review.md`, preserved unmodified). The
remediation plan (`docs/superpowers/plans/2026-09-28-phase-6-semantic-review-remediation-plan.md`)
was implemented in its recommended order. Fix commits: F05/F06/F07 `6e416a4`;
F02/F04 `f54917c`; F01 `bdcd688`; F10 `266aa00`; F03 `07d892d`; F09 `9f39ccc`;
F08 `e2722d9`; F11 `e952ad1`; M01 `f4a6f93`. Regression suite:
`tests/adversarial/test_phase6_sol_review_regressions.py` (37 stable
reproductions, one or more per finding), plus the strengthened accepted slice
test and the updated benchmark fixture.

Summary of fixes:

- **F01** — uncovered material statement content becomes an explicit
  `statement:material` CONSTRAINTS commitment; no relationship is fabricated
  and an unsupported condition blocks direct precedent (ADR-026 amendment).
- **F02** — the cited source version's public disclosure date governs
  eligibility, combined conservatively with source-level dates; unknown
  version timing stays uncertain.
- **F03** — bounded same-source/same-version context-completeness precheck
  before the first judgment; ADR-030 records the policy change.
- **F04** — bounded source/version coverage is recorded explicitly
  (`phase6/coverage.json`, `unassessed_sources`, `unassessed_versions`) and a
  documented oldest-first multi-version policy assesses relevant versions.
- **F05** — evidential judgments require at least one cited passage; decisive
  or support-bearing edges use verifier-cited passages only.
- **F06** — complete source/version/MCU/proposition/mapping/claim identity
  joins at the aggregation, edge, classifier and patent boundaries.
- **F07** — schema v2 `verified_edges` table; graph persistence resolves and
  validates every verification reference against a real artifact
  transactionally.
- **F08** — only known pre-cutoff publication dates can challenge the cutoff,
  and multi-reference context counts distinct eligible lineage roots
  (ADR-029 amendment).
- **F09** — functional analogy requires independently verified functional
  commitments; unresolved mapper conflicts block direct until resolved.
- **F10** — commitment-level scoped partial support preserves the supported
  subset and the unsupported broader remainder (nondecisive).
- **F11** — the slice identity bridge accepts explicit Phase 6 combination
  targets and context-expansion passage IDs while still rejecting foreign
  identities; the accepted slice now carries a real combination contribution
  through `REPORTED/COMPLETED`.
- **M01** — benchmark metric renamed to
  `citation_presence_and_bundle_integrity` and documented as
  citation/reference integrity only, not model faithfulness or calibration.

Post-remediation verification in this worktree: `uv sync --dev`,
`uv run python scripts/verify.py` (Ruff, Ruff format, Pyright 0 errors,
**1426 passed, 5 network cases deselected**) and `git diff --check` all pass.
A fresh local clone at the final repair commit (`git clone --branch phase-6-evidence-verification`) also passed `uv sync --dev`, `uv run python scripts/verify.py` (1426 tests, Ruff/format/Pyright clean) and `git diff --check`.

**Gate 30 remains OPEN.** Phase 6 is not accepted: a fresh GPT-6 Sol High
re-review must confirm all Critical and Important findings are closed before
Phase 6 can be accepted. Phase 7 has not started.

## Round-2 semantic remediation implementation

The independent re-review of `c41b11f` returned **FAIL**: F01-F10 had open
semantic variants and N01 identified assessment-dependent edge collisions.
The original review and the first remediation record remain historical; the
Round-2 implementation is pending a new independent semantic re-review.

- **F01:** Exact ordered statement coverage replaces token-union coverage;
  uncovered MCU and combination-member meaning becomes an independently
  verifiable material commitment, with no invented relationship.
- **F02:** A cited version object and its source owner are mandatory; the
  version's public date controls eligibility, unknown timing abstains, and
  contradictory decisive/chronology facts are rejected.
- **F03:** Explicit complete/truncated/unavailable/unknown context status;
  locator-aware same-version inspection and bounded neighbors; incomplete
  context cannot support a decisive edge.
- **F04:** Unversioned passages beside known versions are explicitly unassessed
  rather than inheriting the parent's date; bounded source/version work
  remains visible. Standalone unversioned sources retain source-level dates.
- **F05-F07:** Canonical verifier citations, exact proposition/mapping/claim
  joins and a reconstructible semantic chain; graph schema v3 persists and
  transactionally resolves the chain and cited passages. Unsafe legacy Phase
  6 edges block migration.
- **F08:** Patent screening uses the cited version's verified chronology and
  counts only distinct eligible lineage roots.
- **F09:** Mapper-only semantic assertions no longer choose precedent class;
  independently verified commitment states control it.
- **F10:** Scoped subset support and unsupported remainder survive into local
  classification, remain nondecisive, and coexist with contradictions.
- **N01:** Edge and proposition-node IDs include stable assessment/chronology
  context, permitting two cutoff-specific artifacts to coexist append-only.

`tests/adversarial/test_phase6_sol_rereview_regressions.py` plus focused
mapping, context, verification, precedent, patent, graph and full-slice tests
exercise the repaired boundaries. The full lifecycle now tests a combination
target and verifier-cited expanded passage together through
`REPORTED`/`COMPLETED`. F11 and M01 remain closed. Contracts and migration are
documented in ADR-030 through ADR-032; ADR-026/029 have amendments. The
Round-2 plan path named in the request was absent from the checkout, so the
attached user instruction supplied its approved scope; no Phase 7 work was
inferred from that absence.

The deterministic benchmark remains a fixture diagnostic, not empirical
model accuracy or calibration. A live verifier's semantic entailment and
prompt-injection resistance remain unproven. Round-2 worktree verification:
`uv sync --dev`, `uv run python scripts/verify.py` (Ruff/format clean,
Pyright 0 errors/warnings, **1471 passed, 5 network tests deselected**) and
`git diff --check` passed. Implementation commit
`54364bac8a58493ccbd87e26867d4f419be94226` was verified from a fresh
local checkout with the same 1471/5 result and clean Ruff/format/Pyright and
`git diff --check`; details are appended to the review record.

**Gate 30 remains OPEN pending a fresh independent GPT-6 Sol High semantic
re-review. Phase 7 has not started.**

## Final bounded semantic-contract consolidation

The independent review of `75cee5e` returned **FAIL** with F02, F03, F06,
F07, F10 and N02 open. The prior review records remain historical. This
implementation addresses those six contract classes; only a fresh independent
GPT-6 Sol High/Max review can close them.

- **F02:** `CitedDisclosure` binds eligibility to the owned cited version and
  marks a conflict with source-wide `first_public_version` uncertain. An
  independently cited earlier preprint remains eligible despite a later
  sibling/journal publication (ADR-033).
- **F03:** passage extractors attest explicit evidence-unit boundaries.
  Context completeness requires both limits of the relevant unit; one-sided
  neighbors, truncated windows, unknown continuation and zero budget cannot
  make support decisive. Complete abstracts remain abstract-only (ADR-033).
- **F10:** aggregate verifier state is derived from commitment records and
  serialized state must match. Direct classification requires aggregate
  `SUPPORTED`; scoped partial coverage remains visible (ADR-033).
- **F06:** `VerifiedComparison` reconstructs the complete semantic chain and
  owns exact identities, chronology, context and verified commitment facts.
  The public classifier requires that artifact for verified classifications;
  `ClassifiedComparison` re-derives identity and basis (ADR-034).
- **F07:** graph schema v4 stores authoritative classifications and the
  repository derives Phase 6 graph attributes from the validated chain.
  Supplied citation/classification mutation fails transactionally. Bare
  verified edges cannot persist without a resolved chain. Unsafe legacy
  Phase 6 edges block migration (ADR-034).
- **N02:** semantic edge content and append-only verification observations
  are stored separately. Two observation times share one semantic edge;
  exact replay is idempotent, and distinct cutoffs or assessments retain
  distinct identities (ADR-035).

The new `tests/adversarial/test_phase6_contract_consolidation.py` includes
fresh boundary attacks, rollback/migration checks, multi-passage and
combination projections, and observation reopen. The real full slice now
combines version-specific disclosure, expanded citation, scoped partial
support and a combination target through `REPORTED`/`COMPLETED`; Phase 7
remains fixture-backed. Existing Sol regressions, benchmark and Phase 6
integration suites remain present. Large excerpts without proven unit
boundaries can remain nondecisive, and deterministic fixtures do not measure
live verifier entailment or calibration.

Final consolidation worktree verification: `uv sync --dev` passed;
`uv run python scripts/verify.py` passed Ruff check, Ruff format (288 files),
Pyright (0 errors/warnings), and **1498 passed, 5 opt-in network tests
deselected**; `git diff --check` passed. Fresh exact-commit checkout
verification is recorded with the implementation handoff.

Gate 30 remains OPEN pending fresh independent GPT-6 Sol High/Max semantic re-review.

## Provenance hardening implementation after the `47021af` FAIL review

The 30 September independent review remains a **FAIL** record. The bounded
R01-R09 implementation now introduces `ResolvedVersionContent` and
`PassageAttestation` (ADR-036). Phase 5 normalization resolves the owned
source/version content hash before extraction. The attestation retains the
normalized parent, exact offsets, passage digest and extractor-proven unit
limits. Semantic-chain and graph persistence reject a cited passage whose
parent digest differs from the cited version hash. Caller-declared complete
unit flags cannot make a short excerpt decisive. Complete abstracts retain
their abstract-only access limitation; numbered patent claims, paragraphs and
Markdown sections have checked boundaries.

Public semantic gates revalidate Pydantic instances, including copied
verifications, comparisons, classifications and patent entries. Verifier
judgments must cover each material commitment exactly once. Routing now
prioritizes sources without hiding eligible unrouted sources. Each candidate
keeps its chain and classification together; invalid mapping produces an
explicit `UNASSESSABLE` result and the pipeline continues. Patent eligibility
comes from `ClassifiedComparison` and its cited disclosure. Multi-source
summaries validate the target MCU, target kind, combination identity and
assessment when given authenticated comparisons. The v2/v3 legacy verified
artifact migration guard requires reprocessing.

`tests/adversarial/test_phase6_provenance_hardening.py` covers R01-R09,
including content mismatch, forged completeness, duplicate/copy attacks,
coverage, failure continuation, patent chronology and migration. A new full
slice test combines authenticated direct graph persistence, scoped partial
support, contradiction, mapper failure, combination target, expanded context
and patent screening through `REPORTED`/`COMPLETED`. The existing Phase 7
adjudicator remains a fixture, and no Phase 7 logic was added. The offline
benchmark still measures deterministic fixture behavior only; live semantic
entailment and prompt-injection resistance remain unmeasured.

The final implementation commit and exact-commit fresh-checkout verification
are recorded in the handoff. **Gate 30 remains OPEN pending fresh independent
semantic re-review. Phase 6 is not accepted; Phase 7 has not started.**

## R10 persisted content-authority remediation

The independent Stage-1 review of `bcd4b830` remains a **FAIL**. This bounded
repair makes the already stored source/version graph node the immutable content
authority for Phase 6 persistence. The repository checks owner, content hash
and access state for the cited version, and matches the passage's attested
parent to that authority. Unversioned evidence is checked against the stored
source content hash and access state. Concurrent same-ID authority nodes are
also compared, and a conflict rolls back the complete semantic transaction.
Verified-edge replay, classification-only writes and Phase 6 graph replay
recheck the same authority. Chain-only classifications remain provisional
until repository persistence validates their content ancestry (ADR-036).

`tests/adversarial/test_phase6_r10_content_authority.py` covers existing and
same-batch version conflicts, copied authority, unversioned conflict, owner
and access mismatch, rollback, replay paths, exact matches, a genuine
subspan, a complete document, and positive new-version/unversioned writes.
The earlier R01–R09 adversarial suite remains in place. This implementation
does not change chronology, context, coverage, patent, anti-stitching or
Phase 7 behavior. Deterministic tests do not establish live-model entailment.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance re-review.

## R13 persisted commit-receipt authority remediation

The Stage-1 R13 **FAIL** at `6abaefc7` remains open pending independent
re-review. This implementation adds a schema-v5 `phase6_commits` manifest in
the same transaction as each classified comparison. A public receipt names
that manifest but never establishes authority by itself. Repository resolution
checks exact verified edges, chains, classifications, passage nodes and
source/version content authority. Legacy projection requires that repository
resolution and projects its stored artifacts after checking caller-result
agreement. The pipeline resolves a receipt before publishing semantic events.
Existing v4 semantic rows require validated replay to gain a manifest;
unrelated Phase 6 semantics and Phase 7 behavior were not changed.

The new R13 adversarial suite reproduces the old fabricated-receipt bypass
before the repair and tests forged, copied, deserialized, foreign and stale
receipts, caller mutations, authority tampering, migration/replay and positive
semantic polarities. The focused R10–R13/provenance suites passed **84 tests**.
ADR-036 records the receipt authority rule. Full and fresh-checkout results
are reported in the implementation handoff.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance/publication re-review.

## R15 downstream authority consolidation implementation record

The independent R15 **FAIL** in `docs/reviews/phase-6-final-review.md`
remains open. This bounded implementation introduces the repository-derived
`Phase6AssessmentView` and schema-v7 append-only assessment ledger. The view
includes complete target profiles, bounded candidate and failure coverage,
context attempts, committed classified chains and cited passages, lineage,
and dependency-bound multi-source and patent summaries. A semantic commit
authorizes its comparison; schema-v6 edge and proposition membership
separately authorizes graph relations. Deliberately semantic-only commits and
nonrelational classifications are visible as statuses without relation
authority. Missing membership for an expected graph projection fails closed.

The repository loads the exact snapshot in one SQLite read transaction.
Migration from an older schema does not fabricate candidate coverage;
`HISTORICAL_LEDGER_UNAVAILABLE` requires validated replay. The production
vertical slice now loads the view by snapshot ID, and the legacy
`project_verified_edges` production adapter has been retired. Its fixture
adjudicator and minimal report revalidate repository authority, but still
carry fixture provenance and do not implement Phase 7. Earlier Phase 1/4
`EvidenceEdge` fixtures remain available. The
`phase6/assessment_view.json` run artifact labels itself a derived export
requiring repository revalidation; it cannot transfer authority when
deserialized. The future Phase 7 input contract is the rich repository view,
with decisive IDs checked again at frozen findings. No Phase 7 code was added.

The deterministic parity, R15 authority, architecture, pipeline and full
slice tests provide implementation evidence. Live-model entailment,
calibration, recovered historical coverage without replay, and independent
Stage-1/Gate-30 acceptance remain outside this implementation record.
