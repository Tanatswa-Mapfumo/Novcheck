# Phase 0 completion record

Scope: Phase 0 only. All twelve Phase 0 acceptance criteria pass. Phase 1 has not started.

## Tasks and commits

| Task | Deliverable | Commit |
| --- | --- | --- |
| 1 | Governance, package, lockfile, quality gate | 6f5ef81 |
| 2 | Canonical enums and opaque typed IDs | 350ce8d |
| 3 | Versioned assessment contracts and UTC timestamps | fd77f69 |
| 4 | Pure audited stage/status transitions | 124573c |
| 5 | Safe configuration and unset budget limits | 70df5c2 |
| 6 | Six abstract async provider ports and shared contract helpers | be5eabc |
| 7 | Canonical hashes, append-only traces, redaction, JSON logging | a9e3af1 |
| 8 | Deterministic fixture providers and network isolation | e348b49 |
| 9 | Lifecycle smoke, import boundaries, traceability, final gate | e44489c |
| Review fixes | Redaction, finite JSON, serialized lifecycle validation | b819476 |

Each task was verified before the next implementation task. Deterministic
production behavior was tested first: missing package version, enum/ID modules,
base/assessment contracts, lifecycle logic, settings, provider DTOs, traces, and
mocks failed before their implementations. Task 9's integration checks passed
immediately on the already tested contracts; no additional production glue was needed.

## Files created or modified

The supplied AGENTS.md, master spec, and approved phase plan were added to the
initial commit without modifying their contents. The master spec matches the
supplied root original byte-for-byte. Created files (some revised in later tasks):

```text
.gitignore
README.md
docs/architecture/decisions/ADR-001-tooling-stack.md
docs/architecture/decisions/ADR-002-lifecycle-stage-and-status.md
docs/architecture/decisions/ADR-003-provider-call-audit.md
docs/architecture/decisions/ADR-004-serialized-contract-validation.md
docs/architecture/decisions/ADR-005-reranker-candidate-mapping.md
docs/traceability/phase-0.yaml
pyproject.toml
scripts/verify.py
src/novelty_harness/__init__.py
src/novelty_harness/domain/__init__.py
src/novelty_harness/domain/assessment.py
src/novelty_harness/domain/base.py
src/novelty_harness/domain/enums.py
src/novelty_harness/domain/ids.py
src/novelty_harness/domain/lifecycle_policy.py
src/novelty_harness/domain/state_machine.py
src/novelty_harness/ports/__init__.py
src/novelty_harness/ports/citations.py
src/novelty_harness/ports/content.py
src/novelty_harness/ports/embeddings.py
src/novelty_harness/ports/llm.py
src/novelty_harness/ports/models.py
src/novelty_harness/ports/reranking.py
src/novelty_harness/ports/search.py
src/novelty_harness/runtime/__init__.py
src/novelty_harness/runtime/config/__init__.py
src/novelty_harness/runtime/config/loader.py
src/novelty_harness/runtime/config/models.py
src/novelty_harness/runtime/logging.py
src/novelty_harness/runtime/tracing/__init__.py
src/novelty_harness/runtime/tracing/hashing.py
src/novelty_harness/runtime/tracing/models.py
src/novelty_harness/runtime/tracing/sinks.py
tests/__init__.py
tests/conftest.py
tests/contract/__init__.py
tests/contract/provider_contracts.py
tests/contract/test_mock_provider_contracts.py
tests/fixtures/__init__.py
tests/fixtures/providers.py
tests/integration/test_phase0_smoke.py
tests/unit/test_assessment_models.py
tests/unit/test_base_contracts.py
tests/unit/test_config.py
tests/unit/test_enums_and_ids.py
tests/unit/test_import_boundaries.py
tests/unit/test_logging.py
tests/unit/test_network_isolation.py
tests/unit/test_port_models.py
tests/unit/test_state_machine.py
tests/unit/test_tracing.py
uv.lock
docs/phase-0-completion.md
```

Existing START_HERE.md and the original root design-spec file remain unmodified
and untracked. An unrelated docs/.DS_Store also remains untracked.

## Requirements

Implemented within the explicitly scoped Phase 0 boundary: Sections 0.2/0.4,
8, 42, 54, 58-62; FR-PROV-003 metadata infrastructure and mock audit;
FR-SEC-003 credential-free settings and trace-key redaction; FR-AUD-001
append-only trace sinks. See traceability/phase-0.yaml for files, tests, and scope.
Enums for later requirements do not implement their semantics. Evidence cutoff
processing, stable source/passage IDs, provider failure orchestration, novelty
invariants' semantic enforcement, and verdict/report logic remain deferred.

## Verification evidence

Commands executed successfully after implementation:

- `uv sync --dev`: PASS in the working checkout and a fresh local clone at
  `/private/tmp/novcheck-phase0-clean.oKOYhB`, with a new virtual environment.
  After review fixes, also PASS in fresh clone `/private/tmp/novcheck-phase0-final.PRGGz2`.
- `uv run python scripts/verify.py`: PASS in both checkouts; Ruff lint, format,
  strict application Pyright, and 494 pytest cases passed without warnings.
  After review fixes, the final fresh clone and working-tree gates passed 515 tests
  without warnings, with zero Pyright errors/warnings.
- `uv run pyright src/novelty_harness/ports tests/contract/provider_contracts.py tests/unit/test_port_models.py`:
  PASS, zero errors/warnings.
- `uv run pyright tests/fixtures/providers.py tests/contract/provider_contracts.py tests/contract/test_mock_provider_contracts.py`:
  PASS, zero errors/warnings.
- `uv run pytest tests/contract/test_mock_provider_contracts.py -v`: 7 passed.
- `uv run pytest tests/unit tests/contract -q`: 483 passed at Task 8; the initial
  intentional socket-blocking warnings were subsequently explicitly captured.
- `uv run pytest tests/integration/test_phase0_smoke.py tests/unit/test_import_boundaries.py -v`:
  11 passed. Smoke emitted 21 trace events and reached REPORTED/COMPLETED.
- Focused TDD runs used `uv run pytest` on each of
  `tests/unit/test_base_contracts.py`, `test_enums_and_ids.py`,
  `test_assessment_models.py`, `test_state_machine.py`, `test_config.py`,
  `test_port_models.py`, and `test_tracing.py`, with `-q` or `-v`.
  All final runs passed; observed RED results are recorded in the execution history.
- `git diff --check 6f5ef81 HEAD`: PASS.
- `cmp docs/specs/master-design-spec.md novelty_assessment_harness_design_spec_v0.1.md`:
  PASS, byte-identical.

The verification script runs `ruff check .`, `ruff format --check .`,
`pyright`, and `pytest` in order within uv's activated environment.
Formatting and import-sort commands were also run during implementation.
The execution skill's task-done wrapper used `.venv/bin/pytest` because invoking
uv inside that shell wrapper was blocked from its global cache by the sandbox.
The required ordinary uv verification commands were still run successfully.

The review fix command was
`uv run pytest tests/unit/test_tracing.py tests/unit/test_port_models.py tests/unit/test_assessment_models.py -q --tb=short`:
21 regression failures and 49 passes before fixes. After fixes,
`uv run pytest tests/unit/test_tracing.py tests/unit/test_port_models.py tests/unit/test_assessment_models.py tests/unit/test_state_machine.py -q --tb=short`
passed all 450 focused cases, followed by the full 515-test gate.

## Decisions and deviations

- Worked in the initial checkout on phase-0-foundation: an unborn repository has
  no HEAD from which to create a worktree. Cost: branch isolation only.
- Added Hatchling build configuration, .gitignore, and test package markers so
  clean installation and shared test imports work. No unused runtime SDKs added.
- Excluded Markdown from Ruff formatting to preserve supplied authoritative
  documents. Disabled UP042 to retain the plan's specified str/Enum base.
  Cost: Markdown formatting relies on document review.
- Allowed local Unix sockets for asyncio wakeups after seven async setup errors
  demonstrated the need. IPv4/IPv6 TCP and UDP remain blocked; no hosts allowed.
  Cost: local IPC is possible during tests (ADR-001).
- Metadata-less planned DTOs remain unchanged. Every configured mock operation
  records supplied metadata in a call history; envelopes also return it.
  Cost: future consumers needing metadata on every DTO require versioned changes
  (ADR-003). Concrete adapters must audit all their calls through tracing.
- Task 9 passed on first integration run; no artificial failure or unused service
  was introduced. Cost: remaining integration edges need future regression tests.

ADRs: ADR-001 tooling/installation/network policy, ADR-002 stage/status and UTC
representation, ADR-003 metadata audit interpretation, ADR-004 serialized
lifecycle/finite JSON validation and credential token suffixes. No novelty semantics changed.
ADR-004 adds structural validation to the plan's string-valued lifecycle fields
without changing their wire shape or transition policy. Existing state-machine
test fixtures for COMPLETED were corrected to start at REPORTED; assertions were
not relaxed. Cost: invalid interim, unreleased 0.1 payloads now fail validation.

## Limitations

No real providers, CLI, persistence service, MCU extraction, research, evidence
analysis, adjudication, calibrated scores, or reporting. IDs use UUID4, not stable
source/content identities. Trace locking is process-local. Redaction only detects
sensitive keys, not credentials embedded in arbitrary prose. Frozen model fields
do not recursively freeze metadata; trace sinks store isolated snapshots.
DTO validation establishes transport structure, not an arbitrary LLM task schema.
Later concrete adapters must implement audit and failure behavior and pass contracts.

## Review and follow-up fixes

A fresh read-only reviewer inspected the complete Phase 0 implementation and
bootstrap tooling through e44489c. No Critical findings. Three Important findings
were reproduced and fixed in one TDD pass: credential token redaction, non-finite
nested JSON, and serialized lifecycle/audit validation. Fixes were verified by
focused regressions and the full suite; no second reviewer pass was performed.

Two Minor findings were initially deferred and did not fail a documented Phase 0 criterion:

- Reranker candidate-ID mapping is unspecified, and the shared helper does not
  assert candidate membership, uniqueness, or rank validity. Define the mapping
  by ADR before adding those behavioral rules.
- JSON logging emits the required fields but omits exception traceback diagnostics.
  A future logging improvement should add logger.exception coverage.

Both findings are now closed in the Phase 0 follow-up, with no Phase 1 work:

- ADR-005 defines candidate IDs as exact input strings, unique returned IDs, and
  unique one-based ranks within the input count. The abstract port documents the
  rule and the shared helper checks it without changing signatures or DTOs.
  Reordered, partial, and empty responses remain valid; no score or novelty
  behavior is introduced. Six malformed-response regressions failed before the
  fix and pass after it, alongside three valid-response preservation cases.
- JSON logs include an optional exception field formatted with the standard
  library's traceback and cause/context-chain formatting. Existing fields and
  plain log output remain unchanged; exception diagnostics are JSON-escaped to
  keep one physical line per record. Three logger.exception regressions failed
  on the missing exception field before the fix and now pass, covering traceback
  details, explicit causes, implicit context, and a subsequent plain log.

Follow-up verification commands:

- `uv run pytest tests/contract/test_mock_provider_contracts.py -q --tb=short`:
  six expected regression failures before the fix; 16 passed after it.
- `uv run pytest tests/unit/test_logging.py -q --tb=short`:
  three expected missing-exception-field failures before the fix.
- `uv run pytest tests/unit/test_logging.py tests/unit/test_tracing.py -q --tb=short`:
  31 passed after the fix.
- `uv run pyright src/novelty_harness/ports/reranking.py tests/contract/provider_contracts.py tests/contract/test_mock_provider_contracts.py`:
  zero errors/warnings.
- `uv run pyright src/novelty_harness/runtime/logging.py tests/unit/test_logging.py`:
  zero errors/warnings.
- `uv run python scripts/verify.py`: Ruff lint/format and strict Pyright passed;
  all 527 tests passed without warnings.
- `git diff --check`: passed.

No dependencies were added. ADR-005 is the only new decision; it clarifies the
review's unspecified mapping rather than changing serialized artifact shapes.
No novelty semantics or later-phase functionality changed. Existing limitations
above still apply; future concrete adapters must pass these strengthened checks.

A read-only follow-up reviewer inspected the two fixes, ADR, and regressions
against 9c31b00 and found no actionable issues. Independent focused verification
with `.venv/bin/python -B -m pytest -p no:cacheprovider tests/contract/test_mock_provider_contracts.py tests/unit/test_logging.py tests/unit/test_tracing.py -q --tb=short`
passed all 47 cases. Coverage remains fixture-based until later concrete adapters.

Rulings on everything the reviewer declined to judge:

- Novelty analysis/MCU/research/adjudication/reports remain later phases.
  Cost: this foundation cannot yet assess an idea.
- Concrete provider behavior and requested LLM schema validation remain deferred
  until adapters/consumers exist. Cost: future consumers must validate task schemas.
- Automatic persistence, replay, and failure orchestration remain later services.
  Cost: callers currently must persist returned events themselves.
- Stable content IDs and cross-process locking remain deferred as planned.
  Cost: IDs are opaque, and concurrent cross-process trace writers are unsupported.
- Recursive request immutability and monotonic timestamp policy are not added.
  Cost: nested metadata may mutate and supplied timestamps may be backdated;
  sinks isolate stored snapshots and UTC validation is enforced.

## Exit criteria

| Acceptance gate | Result and evidence |
| --- | --- |
| 1. Clean checkout install | PASS: fresh clone, new environment, uv sync --dev |
| 2. Full quality gate | PASS: lint, format, strict Pyright, 527 tests after follow-up |
| 3. JSON round trips | PASS: domain enums/IDs, assessments, events, provider DTOs |
| 4. Invalid transitions | PASS: dedicated logged errors; invalid artifacts rejected |
| 5. Stage/status independence | PASS: partial and abstained progress/resume tests |
| 6. Neutral async provider ports | PASS: six protocols and 16 mock contract cases after follow-up |
| 7. No network in tests | PASS: default IP socket blocking, no host allowances; Unix IPC documented |
| 8. Auditable traces | PASS: JSONL append, concurrent threads, canonical hash, redaction, snapshots |
| 9. Safe settings | PASS: no credential fields or invented research thresholds |
| 10. Independent domain | PASS: AST import-boundary suite, including relative imports |
| 11. Canonical smoke flow | PASS: 21 events, REPORTED/COMPLETED, no providers or sockets |
| 12. Accurate traceability | PASS: Phase 0 scope only, later semantics explicitly deferred |

All master-spec Phase 0 exit criteria and the plan's eight manual exit checks
also pass. Work is committed locally on phase-0-foundation; no remote publication
or later-phase implementation was performed.
