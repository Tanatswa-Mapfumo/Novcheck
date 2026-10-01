# Task 5 implementation report

Implementation commit: `abbb4815693f5dce34da319380c59a9806d249d8`

## Scope and requirements

Implemented only Task 5, “Bind multi-source and patent context to committed inputs,” from the approved Phase 6 downstream authority consolidation plan.

- Master spec §25 / FR-PROV-001: lineage roots are sourced only from the exact Phase 5 clusters also present unchanged in the repository; unknown lineage is surfaced as a coverage limitation.
- Master spec §29 and §1476, “Patent/prior-art screening lens”: derived patent screening retains its existing single-reference versus multi-reference distinction.
- Plan Task 5 and existing R11/R12 publication constraints: multi-source and patent records bind to committed edge, classification, and commit IDs, assessment cutoff, method version, and lineage roots. Derived success trace events are emitted only after the snapshot ledger write succeeds.

When persisted lineage is missing, multi-source output is withheld; patent multi-reference combination output is withheld. Single-reference patent screening may still be recorded with an explicit lineage limitation. No new precedent calculator was introduced; the existing `summarize_multi_source` and `screen_patent_references` remain the only calculators.

## Files changed

- `src/novelty_harness/evidence/phase6_pipeline.py`
- `src/novelty_harness/evidence/graph/assessment_ledger.py`
- `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`
- `tests/integration/test_phase6_evidence_pipeline.py`
- `tests/adversarial/test_phase6_r11_authoritative_publication.py`

The pre-existing modified `docs/reviews/phase-6-final-review.md` and the untracked approved design/plan documents were preserved and excluded from the Task 5 commit.

## Tests and verification

TDD RED was observed: the new derived-ledger integration regression failed because the pipeline persisted no derived records (`1 failed, 23 passed, 2 deselected` at that stage).

Passing commands after implementation:

- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pytest tests/integration/test_phase6_evidence_pipeline.py tests/unit/evidence/precedent/test_patent.py -q -k 'ledger or lineage or patent'` — 24 passed, 3 deselected.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pytest tests/integration/test_phase6_evidence_pipeline.py -q -k 'derived_success_is_not_published_when_snapshot_finalization_fails'` — 1 passed, 9 deselected.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pytest tests/adversarial/test_phase6_r11_authoritative_publication.py -q` — 21 passed.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run ruff check src/novelty_harness/evidence/phase6_pipeline.py src/novelty_harness/evidence/graph/assessment_ledger.py src/novelty_harness/evidence/graph/sqlalchemy_repository.py tests/integration/test_phase6_evidence_pipeline.py tests/adversarial/test_phase6_r11_authoritative_publication.py` — all checks passed.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run ruff format --check src/novelty_harness/evidence/phase6_pipeline.py src/novelty_harness/evidence/graph/assessment_ledger.py src/novelty_harness/evidence/graph/sqlalchemy_repository.py tests/integration/test_phase6_evidence_pipeline.py tests/adversarial/test_phase6_r11_authoritative_publication.py` — 5 files already formatted.
- `git diff --check` — passed before commit.

The R11/R12 suite includes distinct partial patent roots, duplicate-family behavior, future versus eligible references, direct single-reference behavior, and rejected-candidate exclusion. Integration assertions verify exact dependency IDs and persisted lineage roots.

## Limitations and deferred work

Task 6 owns the trusted reader that revalidates persisted derived dependencies before exposing the snapshot. This task writes and validates the dependency records; it does not implement a new assessment reader or change patent/multi-source calculation semantics. Full repository verification was not run; the approved Task 5 checks and Pyright were run.
