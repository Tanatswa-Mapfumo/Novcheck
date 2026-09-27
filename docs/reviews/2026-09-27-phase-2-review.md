# Phase 2 final review and closure

Base: accepted Phase 1 6be737a. Reviewed implementation: 959ec19.
Independent read-only reviewer: Goodall, agent 01a0dfd7-2eae-7fe2-9c08-9d0933a0ef1f.
The initial review was interrupted by a usage limit and resumed against unchanged
production code. No reviewer checkout edits or additional agents were used.

## Findings and closure

The reviewer reported no Critical or Minor findings and six Important findings.
Their grades stand: each affects faithful representation, sufficiency, disagreement
or usable human correction. All entered one author fix pass, committed at 1d463ac.
No second review was dispatched; each closure is verified by an observed RED/GREEN
regression and a green full suite, not a second-review claim.

| Finding | Reproduced failure | Fix | Regression in tests/adversarial/test_phase2_review_regressions.py |
| --- | --- | --- | --- |
| 1. Invented relationship | Sensor/Relay words alone accepted CONTROLS | Predicate and endpoint concepts must share original-input support, with conservative surface inflections | test_input_components_do_not_ground_an_invented_relationship_predicate |
| 2. Lost restriction | Critic dropped only above 50 degrees, retained stable HIGH_RESOLUTION | Preserve material text across mapped outputs or reject scope broadening | test_reconciliation_cannot_remove_a_supported_operating_restriction |
| 3. Lost mechanism blocker | Later positive signals overrode null mechanism/retained withheld unknown | Apply immutable normalization absence independently of later signals, preserving unknowns in missing information | test_later_positive_signals_cannot_remove_normalized_mechanism_blocker |
| 4. Combination false consensus | Opposing directed combinations remained stable | Compare mapped combination signature sets, retain disagreement and EXPLORATORY ceiling | test_opposing_combination_graphs_cannot_acquire_stable_consensus |
| 5. Unusable complete merge | No operation could retire existing combination | Explicit payload-version 0.2 retirements, validated and audited without parent mutation | test_user_can_explicitly_retire_a_combination_while_merging_all_members |
| 6. False material disagreement | Shared full-paragraph citations created cross-pair disagreement | Disjoint cross-pairs with unique equivalent counterparts are unrelated, not unresolved alternatives | test_shared_paragraph_does_not_make_identical_independent_units_disagree |

Additional coverage rejects unknown/duplicate retirement IDs, retirement/update
collisions and unversioned retirement. A one-letter hostile predicate exposed an
empty-stem exception during the fix pass; its regression now rejects with a grounding
error. All 13 new parametrized cases pass. The 15 original adversarial/metamorphic
cases, including split causal structure and passive paraphrase, also pass unchanged.
The attack recording now faithfully includes a mechanism attribution when its
supplied scenario says one is present; no test assertion or contract was weakened.

Required gates at 1d463ac in the isolated worktree and fresh local checkout:
`uv sync --dev`, `uv run python scripts/verify.py`, `git diff --check` all exited zero.
Ruff clean, 97 files formatted, Pyright zero errors/warnings, 788 tests passed
(1.70s in both recorded full verification runs). Baseline remains 657 tests.

## Rulings on all declined review areas

These are explicit scope/limitation decisions, not claims that the omitted behavior
has been verified. They retain the approved phase boundary and recorded ADRs.

1. Real-model accuracy/calibration/latency/cost/vendor schema compatibility remains
   unverified without an authorized deployed provider. Cost: fixture success does
   not predict real-model quality or interoperability.
2. Universal entailment and complete prompt-injection resistance are not proved by
   schema/span/lexical checks. Concrete grounding failures were fixed. Cost: semantic
   interpretation still depends on the provider; conservative gates can reject valid
   synonyms or rewritten material clauses.
3. Provider-internal conversation leakage is outside the abstract request guarantee.
   B requests contain no A output. Cost: a misbehaving future adapter could violate
   isolation internally and must be tested in its own contract suite.
4. Search planning/retrieval/saturation/provenance/support/equivalence/novelty/value
   reasoning remains later-phase work. Cost: the slice provides no real novelty finding.
5. Ranked report reasoning and scoring remain deferred; the compiler only renders
   frozen findings. Cost: report content remains deliberately synthetic/minimal.
6. Upload/JSON/YAML transport parsing, CLI/UI, database, retry/resume and partial-run
   recovery remain deferred. Cost: this is an API-level request-scoped understanding
   engine, not a complete operator-facing service.
7. Conservative aggregate ceilings and false/null critic downgrades stand under
   ADR-010; unrelated-pair false disagreement was fixed separately. Cost: an assessable
   subset may have a stronger justified ceiling than the conservative aggregate.
8. Automatic override reassessment, parent storage and rollback UI remain caller-owned
   or deferred. Cost: callers must retain parent snapshots and explicitly reassess
   before lifting the source reconciliation ceiling.
9. Full-snapshot growth, cross-process transactions, filesystem races and prose-secret
   redaction retain documented Phase 1 limits. Cost: no production persistence or
   universal prose-secret detection guarantee is made.
10. Semantic-call audit VALIDATED means schema-validated, not grounding-validated
    (ADR-011). Later grounding failure remains an exception/failed lifecycle. Cost:
    audit consumers must distinguish these stages rather than treating one flag as
    semantic success.
11. Original-checkout untracked user files were preserved. Final completion docs are
    author-maintained evidence, not independently reviewed prose. Cost: author
    documentation may contain mistakes even when runtime regressions pass.

ADRs 008-012 explain material policy/interface decisions. No minors were deferred.
All six findings are closed by the author with regression evidence; user acceptance
and integration remain separate. Phase 3 has not started and is not authorized.
