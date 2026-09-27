# Phase 2 completion record

Scope: Intake, Sufficiency, and Robust MCU Engine only. Phase 3 has not started.
Base: accepted Phase 1 commit 6be737a. Isolated worktree:
`/private/tmp/novcheck-phase2.WORKTREE`, branch `phase-2-understanding-engine`.
Original checkout and accepted Phase 1 worktree remain untouched; no merge/push.

## Tasks and commits

| Task | Deliverable | Commit |
| --- | --- | --- |
| 1 | Strict versioned semantic calls and audit | 2b0383a |
| 2 | Faithful extractive normalization | ecf3037 |
| 3 | Structural sufficiency ceilings | 25c830c |
| 4 | Independently prompted MCU A/B | b3598fd |
| 5 | Structural alignment and checked semantic mappings | 96eef30 |
| 6 | Reconciliation and all six structural tests | 08988ad |
| 7 | Immutable MCU versions and user overrides | e670460 |
| 8 | Understanding pipeline and accepted-slice integration | 0c6c189 |
| 9 | Adversarial/metamorphic suite and combination link regression | 3678099 |
| 10 | Traceability, architecture guards and acceptance record | 959ec19 |

Final review safeguards and 13 regression cases: 1d463ac. The independent review
found six Important issues, all closed in one TDD fix pass; no Critical or Minor
findings. Review evidence and exhaustive scope rulings are recorded in
`docs/reviews/2026-09-27-phase-2-review.md`. This completion-record update follows
that fix commit; no merge/push was performed.

Tasks executed in order, with focused and full gates before commits/next tasks.
New target tests were written before implementation and first failed collection
because modules were absent. Additional behavioral RED/GREEN checks reproduced
ambiguous alignment, missing invalid-call failure trace and dropped combination
relationships. Task 9's other new assertions and Task 10's guards passed existing
implemented behavior; no artificial runtime change was made to manufacture RED.

## Files changed

```text
README.md
docs/architecture/decisions/ADR-008-phase2-semantic-prompt-versioning.md
docs/architecture/decisions/ADR-009-mcu-version-and-override-model.md
docs/architecture/decisions/ADR-010-phase2-grounding-and-assessment-ceilings.md
docs/architecture/decisions/ADR-011-phase2-vertical-slice-artifact-handoff.md
docs/architecture/decisions/ADR-012-phase2-review-safeguards-and-retirements.md
docs/phase-2-completion.md
docs/reviews/2026-09-27-phase-2-review.md
docs/traceability/phase-2.yaml
docs/superpowers/plans/2026-09-26-phase-2-intake-sufficiency-robust-mcu-engine-implementation-plan.md
src/novelty_harness/application/understanding.py
src/novelty_harness/application/vertical_slice.py
src/novelty_harness/intake/__init__.py
src/novelty_harness/intake/models.py
src/novelty_harness/intake/normalization.py
src/novelty_harness/intake/pipeline.py
src/novelty_harness/intake/prompts.py
src/novelty_harness/intake/sufficiency.py
src/novelty_harness/mcu/__init__.py
src/novelty_harness/mcu/alignment.py
src/novelty_harness/mcu/critic.py
src/novelty_harness/mcu/decomposition.py
src/novelty_harness/mcu/models.py
src/novelty_harness/mcu/overrides.py
src/novelty_harness/mcu/prompts.py
src/novelty_harness/mcu/reconciliation.py
src/novelty_harness/runtime/semantic/__init__.py
src/novelty_harness/runtime/semantic/structured.py
tests/fixtures/phase2.py
tests/adversarial/test_phase2_mcu_attacks.py
tests/adversarial/test_phase2_review_regressions.py
tests/integration/test_phase1_slice_with_phase2_components.py
tests/integration/test_phase2_understanding_pipeline.py
tests/unit/intake/test_normalization.py
tests/unit/intake/test_sufficiency.py
tests/unit/mcu/test_alignment.py
tests/unit/mcu/test_critic.py
tests/unit/mcu/test_decomposition.py
tests/unit/mcu/test_overrides.py
tests/unit/mcu/test_reconciliation.py
tests/unit/runtime/test_structured_semantic_calls.py
tests/unit/test_import_boundaries.py
tests/unit/test_phase2_architecture_guards.py
```

AGENTS.md, master specification, accepted domain/provider contracts, pyproject.toml
and uv.lock are unchanged. Supplied plan copied without content changes. No dependency
added. New semantic/result/version contracts are separate schema-version 0.1 artifacts.

## Requirements

FR-IN-001/002: accepted text intake without mandatory fields; uploading/parsing files
and structured-document transport are deferred, not claimed complete input adapters.
FR-IN-003/004/005/006: structural states, partial dimensions, no length gate, explicit
missing/withheld mechanism. FR-MCU-001 through FR-MCU-005: meaningful granularity,
directed relationships, anti-bundling/fragmentation and separate combinations.
FR-MCU-006: explicit instability and affected-contribution ceiling; future verdict
permission remains Phase 7. FR-MCU-007: auditable versioned overrides.
INV-03/05/12, FR-AUD-001/002, FR-PROV-003, FR-OBS-002 and FR-SEC-001 are covered
within the Phase 2 understanding/audit boundary. Sections 9-12, 44, 46-49, 60 Phase 2,
61-62 and Appendix E.1 map to `docs/traceability/phase-2.yaml`.

## Verification

Baseline before Phase 2 edits: `uv sync --dev` and
`uv run python scripts/verify.py` PASS at 6be737a, 657 tests.
Task 10 gate: 775 tests (118 additional cases). Final review-fix gate: 788 tests
(131 additional cases), no warnings; Ruff lint clean, 97 files formatted; strict
Pyright zero errors/warnings. Required commands:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

All exited zero. Focused task commands/results:

| Command suffix after uv run pytest | Result |
| --- | --- |
| tests/unit/runtime/test_structured_semantic_calls.py -q | 7 passed |
| tests/unit/intake/test_normalization.py -q | 12 passed |
| tests/unit/intake/test_sufficiency.py -q | 10 passed |
| tests/unit/mcu/test_decomposition.py -q | 6 passed |
| tests/unit/mcu/test_alignment.py -q | 9 passed |
| tests/unit/mcu/test_reconciliation.py tests/unit/mcu/test_critic.py -q | 20 passed |
| tests/unit/mcu/test_overrides.py -q | 15 passed |
| tests/integration/test_phase2_understanding_pipeline.py tests/integration/test_phase1_slice_with_phase2_components.py -q | 6 passed |
| tests/adversarial/test_phase2_mcu_attacks.py -v --tb=short | 15 passed |
| tests/adversarial/test_phase2_review_regressions.py -q | 13 passed |
| tests/unit/test_import_boundaries.py tests/unit/test_phase2_architecture_guards.py -q | 34 passed |

Full per-task gate totals: 664, 676, 686, 692, 701, 721, 736, 742, 757, 775.
Initial lint/typing failures were corrected; none are waived. A fixture correction
changed erroneous all-output resolutions to the intended one-to-one component
mapping after the combination-preservation regression exposed it; contracts and
expectations were not weakened. Fresh-checkout/final review results are recorded below.

## Semantic and version behavior

Independent A/B classes have only runner constructors and CIR-taking methods;
distinct instructions and prompt versions are constructed from defensive CIR copies.
B is called before any alignment/reconciliation and never sees A candidates/results.
Provider calls contain no shared conversation history. A provider that ignores this
abstract request contract is outside the verified guarantee.

Every critic executes removal, independence, relationship-preservation, merge,
paraphrase-stability and specificity. False/null tests never become passes because
of low model severity. Material unresolved interpretations cap affected IDs at
EXPLORATORY; aggregate sufficiency takes the lower state before research, retaining
initial sufficiency and explicit trace correction. Missing mechanisms do not create
novelty. No numerical novelty/confidence policy or prior-art verdict was introduced.

Overrides return new frozen MCUVersion objects with canonical hashes, parent IDs,
UTC dates and actor/reason. Strict payloads support all eight approved operation
kinds. Audit retains canonical payload, previous graph and before/after hashes.
Merge/split explicit combination updates are atomic within the new version;
duplicate IDs, dangling endpoints/members and invalid payloads reject the operation.
REMOVE/MERGE/SPLIT payload version 0.2 additionally supports explicit audited
combination retirements; version 0.1 behavior is preserved without implicit deletion.
Rollback selects a retained parent. Prior reconciliation and ceilings are not erased.

## Adversarial and metamorphic coverage

15 cases cover vague ideas, buzzword inflation, renamed established concepts,
giant bundles, fragmented causal relationships, arbitrary specificity, components
with meaningful combinations, performance-only claims, withheld mechanisms,
contradictions, full paraphrased equivalent runs, differentiator removal,
different terminology with checked relationship mappings, same words/reversed
relationships and dropped combination links. Assertions compare structural
properties and resolution ceilings, not brittle report prose. All pass.
The six structural tests also have 12 false/unknown ceiling regressions.

## Decisions and deviations

- ADR-008: strict semantic audit/versioning and conservative extractive drafts;
  optional callback preserves required runner signature. Cost: verbatim material
  grounding may reject useful paraphrases; schema/span checks are not entailment.
- ADR-009: frozen audit record stores canonical payload_json rather than a mutable
  nested dictionary; strict explicit combination updates and upsert operation.
  Cost: separate audit contract and full-snapshot history storage growth.
- ADR-010: explicit source/resolution safeguards and EXPLORATORY material ceiling.
  Cost: conservative aggregate ceiling can understate an assessable subset.
- ADR-011: optional artifact/ceiling handoff without changing required Phase 1 ports
  or persisted schemas. Cost: request-scoped adapter, no general retry/resume.
- ADR-012: conservative predicate/text safeguards, cross-stage normalization blockers,
  mapped combination disagreement and explicit override payload version 0.2 retirement.
  Cost: lexical/extractive checks can reject valid synonyms, and users must specify
  retirements; these checks do not prove semantic entailment.
- Inline execution with one final independent review instead of per-task agents.
  Cost: no fresh reviewer at each task. Tmp worktree avoids original-checkout churn;
  cost: Phase 2 files live outside the initial IDE root.
- Intake drafting and fixture scaffolding introduced when their first consumers
  needed them; full adversarial combinations exercised in Task 9. Cost: corpus
  coverage arrives later than initial individual component tests.
- Task 9 corrected the intended fixture mapping rather than relaxing a contract;
  cost: deterministic recordings still require human interpretation review.
- New Phase 2 combination, candidate-resolution and affected-ID contracts extend
  the understanding boundary without changing accepted Phase 1 schemas. Cost:
  incompatible future changes require explicit schema migration.
- Task 10 guards verified already-implemented behavior without manufacturing a
  failing implementation change. Cost: AST guards cover enumerated boundaries,
  not every possible indirect dependency.

## Remaining fixture-backed stages and limitations

Real understanding is model-assisted plus deterministic safeguards, not a default
live LLM. Test providers/semantic responses are recorded fixtures only. Later query
planning/review, search/content transport, evidence mapping/support and adjudication
remain synthetic in the integrated slice. Adaptive research, provenance reasoning,
prosecutor/defender and robustness remain deferred. Full report ranking is deferred;
the accepted nine-question compiler still renders only frozen findings.

Span/schema validation does not prove that a model interpreted quoted instructions,
contradictions, relationships or semantic entailment correctly. Deterministic fixtures
prove contracts/safeguards, not performance of an actual deployed model. Alignment is
conservative about synonyms/material qualifiers; disagreements cannot vanish to obtain
consensus. No real novelty assessment, providers, research, scoring or probabilities.
No file upload parser, CLI, UI, database, retry/resume or cross-process transaction.
Per-file persistence/trace/redaction retain Phase 1 limitations. Callers retain parent
versions; overrides require explicit downstream reassessment before relaxing ceilings.

## Acceptance gates

| Gate | Evidence |
| --- | --- |
| 1. Accepted Phase 1 baseline | 6be737a, 657 tests before edits |
| 2. Full final verification | Required gate passes; final results below |
| 3. Faithful original input/grounding | Normalization unit rejection and exact-input integration |
| 4. Structural sufficiency | Deterministic signal ceiling and metamorphic cases |
| 5. Missing/withheld mechanisms | Explicit unassessable dimensions, no inferred MCUs |
| 6. Independent A/B | Distinct prompts/versions, request capture and signature guards |
| 7. Relationships preserved | MCU and combination link-preservation regressions |
| 8. Separate combinations | Meaningful configuration adversarial fixture |
| 9. Structural alignment | Reversal, subsumption, qualifiers, ambiguity and checked aliases |
| 10. Disagreement retained | Opposing interpretations retained with material ceiling |
| 11. Six structural tests | Mandatory complete critic contract and executed results |
| 12. Instability lowers ceiling | Twelve false/unknown checks and unstable integration |
| 13. Immutable overrides | Eight operation variants and mutation regression |
| 14. Invalid edits rejected | Strict payload, duplicate IDs and dangling endpoint tests |
| 15. Adversarial/metamorphic suite | 15 passing cases |
| 16. Accepted slice still completes | Real ports, later fixture stages, REPORTED/COMPLETED |
| 17. No later intelligence | SDK/research/verdict dependency and operation guards |
| 18. No live network | Existing IP socket block and mock-only providers |
| 19. Accurate scope docs | README, traceability, ADRs and completion record |
| 20. No Phase 3 | No research planner/provider implementation |

User acceptance/review remains separate from implementation verification. Phase 3
requires new explicit authorization; successful gates do not authorize it.

## Final review and fresh checkout

Fresh local checkout `/private/tmp/novcheck-phase2-fresh` at 959ec19 independently
ran `uv sync --dev`, `uv run python scripts/verify.py` and `git diff --check`.
All exited zero: Ruff clean, 96 files formatted, Pyright zero errors/warnings,
775 tests passed. The repeated September 27 run passed all 775 tests in 1.48s.

Final whole-branch review was interrupted by an agent usage limit and resumed
September 27 against the unchanged implementation at 959ec19. Six Important findings
were reproduced and closed in 1d463ac; see the review record for each RED/GREEN
regression, scope rulings and residual limitations. No second review was dispatched.

Both the isolated worktree and fresh local checkout at 1d463ac ran all three required
commands after the fix: all exited zero, Ruff clean, 97 files formatted, Pyright zero
errors/warnings, 788 tests passed in 1.70s. The final documentation snapshot is also
subject to the same complete required gate before completion is reported.

All 20 Phase 2 acceptance gates pass within their documented Phase 2 scope.
Implementation and review-fix verification are complete; user acceptance/integration
remain separate. The branch/worktree are retained, and Phase 3 has not started.
