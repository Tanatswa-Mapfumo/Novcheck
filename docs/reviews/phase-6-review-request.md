# Phase 6 — mandatory independent semantic review request

**Reviewer required: GPT-6 Sol High. Status: REQUIRED — NOT YET COMPLETED.**

Phase 6 was implemented by DeepSeek V4.1 Flash Max under the approved plan
(`docs/superpowers/plans/2026-09-28-phase-6-evidence-mapping-support-verification-precedent-classification-implementation-plan.md`).
Per the plan and the user's instruction, Phase 6 must not be accepted from
implementer self-review. This file records the review scope and the current
pending status.

## Review scope (plan Task 16)

The reviewer must examine:

1. mapper/verifier separation;
2. verifier blindness (exact input surface, no verdict/role/quality/rank/score);
3. relationship/control-flow preservation;
4. single-source direct-precedent rule;
5. multi-source anti-stitching and duplicate-lineage counting;
6. chronology gates (post-cutoff cannot be decisive);
7. same-source context expansion and exhaustion;
8. patent single-reference anticipation-like versus multi-reference semantics;
9. graph-edge eligibility and repository rejection of ineligible edges;
10. benchmark behavior and its diagnostic-only framing;
11. all 20 adversarial cases;
12. Phase 7 leakage (no prosecutor/defender/adjudication/verdict/probability).

## Key artifacts

- `src/novelty_harness/evidence/mapping/` (dimensions, mapper, prompts);
- `src/novelty_harness/evidence/context/` (selection, expansion);
- `src/novelty_harness/evidence/verification/` (models, gates, verifier, prompts);
- `src/novelty_harness/evidence/precedent/` (models, gates, counterfactuals, patent);
- `src/novelty_harness/evidence/graph/phase6_mapping.py`, `graph/models.py`;
- `src/novelty_harness/evidence/phase6_pipeline.py`;
- `src/novelty_harness/application/evidence_phase6.py`, `application/vertical_slice.py`;
- `docs/architecture/decisions/ADR-026` … `ADR-029`;
- `tests/unit/evidence/{mapping,context,verification,precedent}`, `tests/unit/evidence/graph/test_phase6_mapping.py`, `tests/unit/test_phase6_architecture_guards.py`;
- `tests/integration/test_phase6_evidence_pipeline.py`, `tests/integration/test_phase5_slice_with_phase6_evidence.py`;
- `tests/adversarial/test_phase6_equivalence_attacks.py`;
- `tests/benchmarks/test_phase6_support_verifier.py` and `tests/fixtures/phase6_support_benchmark.json`;
- `docs/traceability/phase-6.yaml`.

## Required follow-up for findings

For every Important/Critical finding: reproduce with a regression test where
possible, fix, run focused tests, run full verification
(`uv sync --dev`, `uv run python scripts/verify.py`, `git diff --check`),
then document the finding and resolution in
`docs/reviews/phase-6-final-review.md`. Only after that review is closed and
the user explicitly accepts Phase 6 may Phase 7 begin.
