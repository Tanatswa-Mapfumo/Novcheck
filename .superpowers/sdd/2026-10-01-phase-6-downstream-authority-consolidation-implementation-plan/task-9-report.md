# Task 9 report — view-aware fixture and report path

Implemented the Phase 6 fixture adjudicator port and deterministic report compiler. The compiler reloads the requested assessment snapshot through `EvidenceGraphRepository`, requires exact equality with the supplied view, and checks each frozen decisive `edge_…` ID against the repository-authorized graph projection, target MCU, committed source/version, direct classification, and supported/decisive eligibility. It renders exact verifier-cited passage text, source version, scoped partial support, evidence limitations, and coverage limitations from repository-loaded records. It does not convert the view to `EvidenceEdge` or derive a new novelty verdict. The legacy Phase 1 report compiler keeps its existing inputs and output structure.

Files changed:

- `src/novelty_harness/application/phase6_fixture.py`
- `src/novelty_harness/reporting/minimal.py`
- `tests/unit/test_minimal_report_compiler.py`

Tests cover repository-authorized direct evidence, missing and foreign decisive IDs, a stale caller-built view, passage text/version, scoped partial support and limitations, and the existing Phase 1 report behavior.

Verification:

- `uv run pytest tests/unit/test_minimal_report_compiler.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/integration/test_phase1_vertical_slice.py -q` — 36 passed.
- `uv run pyright` — 0 errors, 0 warnings.
- `uv run ruff check src/novelty_harness/application/phase6_fixture.py src/novelty_harness/reporting/minimal.py tests/unit/test_minimal_report_compiler.py` — passed.
- `uv run ruff format --check src/novelty_harness/application/phase6_fixture.py src/novelty_harness/reporting/minimal.py tests/unit/test_minimal_report_compiler.py` — passed.

Scope note: the real Phase 6 vertical-slice consumer remains for Task 10; the old adapter and Phase 7 boundary remain untouched. The pre-existing modified review and untracked design/plan files were preserved.
