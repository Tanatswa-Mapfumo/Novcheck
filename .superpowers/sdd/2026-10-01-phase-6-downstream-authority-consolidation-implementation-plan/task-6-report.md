# Task 6 implementation report

Implementation commit: `9239442d5123028eabdb90ec3fe3e764d7f5343a`

## Scope and requirements

Implemented only Task 6, “Load one consistent semantic assessment snapshot,” from the approved Phase 6 downstream authority consolidation plan.

- Master spec §§20, 25–27: preserve the assessment cutoff, lineage context, committed classifications and verifier-cited passage facts.
- Design §§10–11 and 15: add a repository-derived read model with explicit snapshot identity; validate candidate, target, derived, commit and lineage references; preserve R10 content authority and R13 manifest resolution.
- Plan Task 6: add `load_phase6_assessment(assessment_id, *, snapshot_id)` and assemble it inside one explicit SQLite read transaction using one `Session`. The loader issues a database-level `BEGIN` before its first query; it does not call nested public repository reads.

The loader validates exact ledger row IDs and immutable snapshot identity, reuses `_resolve_phase6_commit_in_session`, checks content authority, binds assessed candidates to exact semantic commits, validates derived input identities and lineage roots, and returns targets, candidate outcomes, bounded coverage, derived records, lineage and audit references. Verifier-cited passages are taken unchanged from the resolved chain, with commitment IDs retained.

Graph-backed comparisons intentionally raise `Phase6AssessmentAuthorityError` until Task 7 implements graph membership validation. They are never relabeled `SEMANTIC_ONLY`. Zero-comparison and non-assessed ledger snapshots can load. Semantic-only assessed comparisons can load only when their projection intent is explicit and their classification has no graph relation.

## Files changed

- `src/novelty_harness/evidence/graph/repository.py`
- `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`
- `tests/unit/evidence/graph/test_assessment_view.py`
- `tests/integration/test_phase6_assessment_view.py`

The pre-existing modified `docs/reviews/phase-6-final-review.md` and untracked approved design/plan documents were preserved and excluded from both Task 6 commits.

## Tests and verification

TDD RED was observed: the initial zero-comparison and missing/foreign locator tests failed because `load_phase6_assessment` was absent (`2 failed, 4 passed`).

Passing commands after the final implementation change:

- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pytest tests/unit/evidence/graph/test_assessment_view.py tests/integration/test_phase6_assessment_view.py tests/unit/evidence/graph/test_assessment_ledger.py tests/adversarial/test_phase6_r10_content_authority.py tests/adversarial/test_phase6_r13_commit_receipt_authority.py -q` — 65 passed.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run ruff format --check .` — 298 files already formatted.
- `git diff --check` — passed.

The suite covers zero-comparison snapshots, missing/foreign locators, two-target snapshot reference ordering, a second-connection ledger mutation attempt between snapshot and ledger reads, a complete ledger with no assessed candidates, and fail-closed behavior for a completed graph-backed run. Existing R10 and R13 adversarial suites passed.

## Limitations and deferred work

- Task 7 must implement proposition and graph-edge membership validation and then enable graph-backed views. The intermediate loader is not a trusted production input.
- Graph-backed citation, chronology, scoped-support, combination-profile and all-five-verifier-state loader matrix cases are deferred to the Task 7/8 R15 and parity suites because Task 6 intentionally rejects graph-dependent snapshots before constructing their downstream view.
- Full repository verification was not run; Task 6 focused suites, R10/R13 suites, Ruff, format check, Pyright and diff check were run.
- R15 and Phase 6 acceptance remain open for independent review.
