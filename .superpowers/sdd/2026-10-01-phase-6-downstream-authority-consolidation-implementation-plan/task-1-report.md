# Task 1 implementation report

## Scope

Implemented Task 1 only: immutable Phase 6 assessment view and ledger contracts, plus focused unit tests. No repository persistence, SQL schema, adapters, pipeline changes, or Phase 7 behavior were added.

## Files changed

- `src/novelty_harness/evidence/graph/assessment_view.py`
- `src/novelty_harness/evidence/graph/assessment_ledger.py`
- `tests/unit/evidence/graph/test_assessment_view.py`
- `tests/unit/evidence/graph/test_assessment_ledger.py`

## Requirements addressed

- Task 1 contract interfaces from the approved implementation plan.
- Frozen, versioned `Phase6AssessmentView` and component contracts, with `extra="forbid"` inherited from `ContractModel`.
- Kept semantic comparisons/statuses distinct from the authorized graph relation collection. The models explicitly document that construction does not grant repository authority.
- Retained the complete `ClassifiedComparison` chain and exact `PassageRecord` values. Passage commitment IDs are checked against the verification record's passage citations.
- Checked that each authorized graph relation's commit, verified edge, classification, graph edge ID, and proposition node match a graph-authorized committed comparison.
- Added the Phase 6 snapshot, target, candidate, coverage, and derived ledger contracts required by Task 2, including candidate `projection_intent` and snapshot `lineage_cluster_ids`.
- Added the `Phase6AssessmentAuthorityError(ValueError)` fail-closed signal.

## RED evidence

Before implementation, ran:

```text
uv run pytest tests/unit/evidence/graph/test_assessment_view.py -q
```

Result: collection failed at import with `ModuleNotFoundError: No module named 'novelty_harness.evidence.graph.assessment_view'`. This confirmed the new contract was missing.

During initial GREEN setup, two tests also exposed invalid fixture identities (assessment and version did not match the verified edge); those fixtures were corrected to use the verified edge's assessment and source version. This was test setup correction, not a production behavior change.

## GREEN evidence

After implementation and final formatting, ran:

```text
uv run ruff check src/novelty_harness/evidence/graph/assessment_view.py src/novelty_harness/evidence/graph/assessment_ledger.py tests/unit/evidence/graph/test_assessment_view.py tests/unit/evidence/graph/test_assessment_ledger.py
All checks passed!

uv run pytest tests/unit/evidence/graph/test_assessment_view.py tests/unit/evidence/graph/test_assessment_ledger.py -q
5 passed in 0.18s

uv run pyright
0 errors, 0 warnings, 0 informations
```

The focused tests cover version rejection and freezing, semantic-only status without graph authority, exact passage preservation and scoped commitment citation IDs, graph identity mismatch rejection, candidate projection intent, and snapshot lineage IDs.

## Limits and deferred work

- These constructors are data contracts only; they do not validate repository persistence, content authority, or current graph membership. The loader in a later task must provide that authority.
- Ledger persistence, canonical snapshot hashing/record IDs, and broader schema joins remain for Task 2.
- Full repository verification was not run because Task 1 requires focused tests and Pyright; no claim is made about later task or phase exit criteria.
- No ADR or user decision was needed.

## Review follow-up: verifier citation completeness

The Task 1 review identified that exactness was checked for supplied cited passages, but an empty or incomplete `cited_passages` collection could omit passages present in verifier commitment citations. Added a regression and changed the local validator to require the supplied passage ID set to equal the verifier-cited passage ID set, while retaining exact `PassageRecord` equality and scoped commitment ID checks.

RED command and result:

```text
UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pytest tests/unit/evidence/graph/test_assessment_view.py -q -k omitted_verifier
1 failed: Failed: DID NOT RAISE ValidationError
```

GREEN verification after the fix:

```text
UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pytest tests/unit/evidence/graph/test_assessment_view.py tests/unit/evidence/graph/test_assessment_ledger.py -q
6 passed in 0.20s

UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run pyright
0 errors, 0 warnings, 0 informations
```
