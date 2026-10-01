# Task 7 implementation report

Implementation commit: `7f3a892354e2c540b9590cec0b9ba7f98c782075`

## Scope and requirements

Implemented Task 7, “Enforce R15 graph authority in the assessment loader,” from the approved Phase 6 downstream authority consolidation plan.

- Plan Task 7; design §§7, 11, 15, 16, 18; master specification invariants INV-12 and INV-14.
- Derive the expected proposition and relation fragment for each assessed candidate inside the loader's existing single SQLite read transaction.
- Require exact relation/node membership for the candidate's commit, verified edge, and classification. Validate rows through `_authoritative_graph_node` and `_authoritative_graph_edge`, then verify their derived content and graph IDs.
- Return `GRAPH_AUTHORIZED`, `SEMANTIC_ONLY`, or `NONRELATIONAL_STATUS` explicitly. A semantic-only record must say so in the candidate ledger and have no expected projection row or membership. The loader does not invent precedent relations for nonrelational classifications.
- Convert missing, malformed, foreign, or corrupt required projection state to `Phase6AssessmentAuthorityError`; a resolvable semantic receipt cannot recreate graph authority.

The R10–R14 gate exposed a Task 6 ledger issue while validating the downstream read: content authority rejection candidates could not be durably recorded because their deliberately mismatched descriptor was treated as trusted input. The ledger now requires an explicit limitation for `AUTHORITY_REJECTED` at `CONTENT_AUTHORITY`. Only that state may retain a hash/access mismatch as an untrusted audit claim; the repository still requires source/version nodes, correct node kinds, and version ownership. All other candidate states retain strict descriptor checks. This bounded correction was necessary for the required R11 publication suite to pass.

## Files changed

- `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`
- `src/novelty_harness/evidence/graph/assessment_ledger.py`
- `src/novelty_harness/evidence/phase6_pipeline.py`
- `tests/adversarial/test_phase6_r15_assessment_authority.py`
- `tests/integration/test_phase6_assessment_view.py`

The pre-existing modified final review and untracked approved design/plan documents were preserved and excluded from the implementation commit.

## Tests and verification

TDD RED was observed: before the loader gate, the valid graph-backed snapshot test failed at the Task 6 placeholder. The required R11 suite then exposed the rejected-descriptor persistence regression; the narrow state/limitation rule corrected it.

Passing commands after the final implementation change:

- `UV_CACHE_DIR=/private/tmp/uvcache uv run pytest tests/adversarial/test_phase6_r10_content_authority.py tests/adversarial/test_phase6_r11_authoritative_publication.py tests/adversarial/test_phase6_r13_commit_receipt_authority.py tests/adversarial/test_phase6_r14_graph_authority.py tests/adversarial/test_phase6_provenance_hardening.py tests/adversarial/test_phase6_r15_assessment_authority.py tests/unit/evidence/provenance tests/unit/evidence/graph/test_assessment_view.py tests/unit/evidence/graph/test_sqlalchemy_repository.py tests/integration/test_phase6_assessment_view.py -q` — 173 passed.
- `UV_CACHE_DIR=/private/tmp/uvcache uv run pytest tests/adversarial/test_phase6_r15_assessment_authority.py tests/integration/test_phase6_assessment_view.py -q` — 14 passed.
- `UV_CACHE_DIR=/private/tmp/uvcache uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `UV_CACHE_DIR=/private/tmp/uvcache uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/private/tmp/uvcache uv run ruff format --check .` — 301 files already formatted.
- `git diff --check` — passed.

The tests cover direct relation replay, expected relation IDs across generated graph relation kinds, explicit semantic-only status, exact node/edge membership, deleted membership and graph rows, citation corruption, malformed graph JSON, foreign manifest association, v5 migration without membership backfill, and an attempted second-connection membership deletion during the pinned snapshot read.

## Limitations and deferred work

- This implementation is evidence for independent review; R15 remains open until the independent Stage-1 review and subsequent Gate-30 process.
- Task 8 parity, Tasks 9–12 downstream migration/documentation, and Phase 7 remain unstarted.
- The full repository verification script was not run; the focused R10–R15/provenance/graph suite, Pyright, Ruff, format check, and diff check were run.
