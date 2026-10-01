# Task 9 report — view-aware fixture and report path

Implemented the Phase 6 fixture adjudicator port and deterministic report compiler. The compiler reloads the requested assessment snapshot through `EvidenceGraphRepository`, requires exact equality with the supplied view, and checks each frozen decisive `edge_…` ID against the repository-authorized graph projection, target MCU, committed source/version, direct classification, and supported/decisive eligibility. It renders exact verifier-cited passage text, source version, scoped partial support, evidence limitations, and coverage limitations from repository-loaded records. It does not convert the view to `EvidenceEdge` or derive a new novelty verdict. The legacy Phase 1 report compiler keeps its existing inputs and output structure.

Files changed:

- `src/novelty_harness/application/phase6_fixture.py`
- `src/novelty_harness/reporting/minimal.py`
- `tests/unit/test_minimal_report_compiler.py`

Tests cover repository-authorized direct evidence, missing and foreign decisive IDs, a stale caller-built view, passage text/version, scoped partial support and limitations, and the existing Phase 1 report behavior.

Verification:

- `./.venv/bin/pytest tests/unit/test_minimal_report_compiler.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/integration/test_phase1_vertical_slice.py -q` — 40 passed after review fixes.
- `uv run pyright` — 0 errors, 0 warnings.
- `uv run ruff check src/novelty_harness/application/phase6_fixture.py src/novelty_harness/reporting/minimal.py tests/unit/test_minimal_report_compiler.py` — passed.
- `uv run ruff format --check src/novelty_harness/application/phase6_fixture.py src/novelty_harness/reporting/minimal.py tests/unit/test_minimal_report_compiler.py` — passed.

Scope note: the real Phase 6 vertical-slice consumer remains for Task 10; the old adapter and Phase 7 boundary remain untouched. The pre-existing modified review and untracked design/plan files were preserved.

## Independent review follow-up

The independent review found that the fixture-only path could render a production-looking verdict and that a direct decisive citation could disagree with its MCU finding state. Added RED regressions for both issues, then enforced `provenance.kind="fixture"`, overall and per-MCU `UNASSESSABLE`, and `DIRECT_PRECEDENT` finding state whenever a direct decisive relation is cited. This is fixture contract validation only; it adds no Phase 7 decision logic. The valid direct fixture remains accepted, and the Phase 1 compiler is unchanged.

Follow-up verification:

- `uv run pytest tests/unit/test_minimal_report_compiler.py -q` — 23 passed.
- `./.venv/bin/pytest tests/unit/test_minimal_report_compiler.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/integration/test_phase1_vertical_slice.py -q` — 40 passed. `uv run` could not initialize its user cache in the sandbox on this invocation; the repository virtualenv ran the same pytest suite successfully.
- `uv run pyright` — 0 errors, 0 warnings.
- `uv run ruff check src/novelty_harness/reporting/minimal.py tests/unit/test_minimal_report_compiler.py` — passed.
- `uv run ruff format --check src/novelty_harness/reporting/minimal.py tests/unit/test_minimal_report_compiler.py` — passed.
