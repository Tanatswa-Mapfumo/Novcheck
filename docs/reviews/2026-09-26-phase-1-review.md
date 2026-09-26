# Phase 1 whole-branch review and fix record

Review range: 8d272ec..2304469. Read-only independent reviewer; no edits, index or
branch changes and no further reviewer agents. Reviewed the approved plan,
master specification, ADR-006/007 and the implementation. Independent full test
run: `.venv/bin/python -B -m pytest -p no:cacheprovider`, 650 passed.

## Findings

No Critical or Minor findings. Three Important findings, all reproduced and
closed in one regression-driven fix pass:

| ID | Finding | Correction and regression evidence |
| --- | --- | --- |
| P1-R01 | Normalizer can mutate its request validation baseline | Pass an independent deep copy; retained request remains authoritative. Both mutation/replacement and mutation/valid-result tests observed RED then GREEN. |
| P1-R02 | Reviewer can change filters after plan persistence | Hash the authoritative snapshot before review and pass a deep copy. Mutated-snapshot approval is rejected before search; original-snapshot approval executes exactly saved filters. Both cases observed RED then GREEN. |
| P1-R03 | Duplicate MCU findings and dangling coverage MCU/query references | Reject duplicate finding IDs and coverage references outside the run graph/plan before freezing. Three independent structural cases observed RED then GREEN. |

Fix verification:

`uv run pytest tests/integration/test_phase1_vertical_slice.py -q --tb=short -k 'mutat or persisted_plan_snapshot or ambiguous_or_dangling'`
initially failed all seven cases. Per-finding focused runs then passed 2, 2 and
3 cases, followed by the full gate: `uv run python scripts/verify.py`, 657 passed,
Ruff lint/format clean, strict Pyright zero errors/warnings. No Phase 0 interface,
artifact shape, dependency or novelty semantics changed. No second reviewer pass;
the fixes are validated by observed RED/GREEN and the complete suite.

## Scope rulings

The reviewer deliberately set aside these behaviors. Executor rulings preserve
the approved Phase 1 boundary, not hidden exemptions:

- Real sufficiency, MCU decomposition, equivalence, chronology, source quality
  and verdict correctness remain later semantics. Cost: synthetic output cannot
  assess real novelty; those future engines need their own semantic tests.
- Prosecutor/defender, robustness reasoning, adaptive saturation, budgets and
  numerical scoring are unauthorized later work. Cost: no real search sufficiency
  or strong-verdict permission can be established by this slice.
- Synthetic support states and narrative findings are injected test data, not
  factual judgments. Cost: passing transport tests does not establish evidence truth.
- Full report ranking and semantic citation verification remain later report/
  evidence work. Cost: minimal reports provide artifact references, not a complete
  human evidence review or source-date/ranking narrative.
- Retry/resume, partial-branch recovery, multi-file transactions and hostile
  concurrent filesystem mutation remain documented deferred capabilities. Cost:
  interrupted/storage-failed runs may retain partial files; this is a local writer.
- UUID4 IDs and their derived run-bound hashes are explicitly volatile. Cost:
  comparisons must account for these fields rather than require byte-identical runs.
- The review excluded pending completion-document status and parent-owned fresh
  packaging verification. Executor separately verifies/documented these before
  completion. Cost: stale packaging/docs would invalidate a completion claim.

All three Important findings are closed; no review minor is deferred. No real
intelligence was introduced in resolving the findings. Phase 2 has not started.
