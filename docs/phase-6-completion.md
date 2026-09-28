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

1389 deterministic tests pass (5 opt-in network cases deselected); baseline was
1259, so Phase 6 adds 130 tests (including 21 adversarial and 2 benchmark
tests).

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
