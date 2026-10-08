# Recovery Validation and Test Performance Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute the preserved Native method task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a confidentially backed-up, freshly validated recovery baseline and measured safe test execution without weakening evidence/report authority.

**Architecture:** Audit immutable source identity first, then validate a separate resource supervisor, measure fixture and production stages independently, and apply only reproduced optimizations. Immutable native SQLite snapshots use private per-test copies and native revalidation. Substantial refactoring and unsafe/heavy runs require the user's review before execution.

**Tech Stack:** Python 3.12+, existing locked uv/Pydantic/SQLAlchemy/pytest/Ruff/Pyright; stdlib audit/supervision; native macOS RSS/physical footprint/pressure counters. No production dependency is added by this plan.

**Spec:** Current recovery/resource instructions; [master specification](../../specs/master-design-spec.md) §§44,47,49,54–57; [approved Phase 8 design](../specs/2026-10-05-phase-8-full-report-compiler-design.md) §§5,13,18,22–27; [Phase 8 plan](2026-10-05-phase-8-full-report-compiler-implementation-plan.md). Measurements and uncertainty are in [the investigation](../../recovery/2026-10-08-validation-investigation.md).

## Global constraints

- Work only in the persistent recovery worktree on `recovery/validation-performance-20261008`; preserve local/public `recovery/d058976`, stable branches and every forensic input. Source/worktrees never live in temporary directories.
- Confidential backup requires an independently recoverable key and verified private off-device destination. No secret in chat, argv, Git or logs; no public forensic payload. No erase/reformat/retirement of originals.
- Phase 7/8 authority, mandatory material limitations, exact dependency closure, actual executions and all assertions remain unchanged. No caches confer authority or survive across input/accept/load transactions.
- Missing goldens are unresolved until exact recovery or explicitly labeled, independently checked regeneration. Never manufacture original commit identities or transfer historical passes to reconstructed source.
- Mac has 8 GB RAM. One intensive child process tree at a time; normal pressure and OS headroom required. Target approximately 2 GB, preempt at 2.5 GB, absolute RSS/physical footprint limit 3,000,000,000 bytes. Stop/abort means incomplete, not PASS.
- Known unsafe workloads require higher-memory hardware. No full suite or heavy reproduction now; no paid provisioning/workflow/upload without approval.
- Every optimization has a concrete failure or measured hypothesis, minimal change, relevant semantic/authority regression and before/after measurement. No deletion/skips/assertion weakening for performance.
- Task 22 feature implementation and Tasks 23–24 remain held until the explicit prerequisite gate below. One independent whole-phase acceptance review remains after final full/detached verification.
- Public remote backup of new commits happens only at approved exact checkpoints; prepare and audit a concrete commit before seeking approval. Never force-push.

## Review focus

1. Supervisor misses child allocation or leaves an orphan after interruption: RV2 process-tree/cleanup tests.
2. Immutable snapshot cache serves a mutated/foreign baseline: RV4 isolation, checksum and scope-invalidation tests; native authority always reloads.
3. A new golden merely blesses generated output: RV5 independent expected-semantics checks and retained perturbation controls.
4. Smaller fixture hides real production report duplication: RV3 separates setup from compile/accept/load/render; RV6 includes a real native case.
5. A speedup changes canonical IDs, drops a decisive limitation or permits stale authority: RV6 identity/parity/completeness and corruption/revocation regressions.

## RV1 — Confidential evidence backup and integrity checkpoint

**Files:** `docs/recovery/2026-10-08-validation-investigation.md`; private receipts/manifests under ignored `.superpowers/recovery-validation/20261008/`. Existing forensic inputs remain read only. No production interface.

- [x] Audit 518 manifest paths with `scripts/recovery/audit_baseline.py`; 0 mismatches, 402 syntax checks; measurement is not functional verification.
- [x] Preserve uncertainty: 125 reconstructed, two diff-only witnesses, one complete recorded projection without final hash; eight missing/partial goldens and five unimplemented later files.
- [ ] Obtain private independent destination and encryption/key custody. There is currently no mounted external drive; destination is required, not inferred.
- [ ] Inventory both forensic directories, all evidence/archives/object stores/scripts/checkpoints and modes/hashes using streamed reads. Keep all sensitive manifests inside encryption or ignored local receipts.
- [ ] Encrypt without logging a passphrase/private key. Copy/upload only to the approved confidential destination. Verify destination ciphertext hash, independently decrypt/restore, compare exact members/hashes/modes and tree closures; record receipt. No local-only file counts as off-device completion.

## RV2 — Tested resource supervisor

**Files:** Create `scripts/recovery/resource_guard.py`, `tests/unit/test_recovery_resource_guard.py`. Production reporting/store files untouched.

**Interfaces:** Frozen `ResourceLimits` (soft/hard bytes, pressure/headroom/swap thresholds), `ResourceSample` (monotonic time, tree RSS/footprint/lifetime peak, OS pressure, available-headroom estimate, swap usage), and `RunReceipt` (command identity, checkpoint, state, exit, elapsed, peaks and log identity). `stop_reason(sample: ResourceSample, limits: ResourceLimits) -> str | None`; `run_guarded(command: tuple[str,...], *, cwd: Path, limits: ResourceLimits, output: Path) -> RunReceipt`. OS collection is injectable for tests; implementation imports no report/application module. CLI records one receipt per run and refuses overwrite.

- [ ] **RED:** `test_warning_or_unknown_pressure_prevents_child_launch`, `test_child_tree_peak_triggers_stop`, `test_second_intensive_run_cannot_acquire_lock`, `test_monitor_failure_and_interrupt_reap_child_group`, `test_aborted_run_never_reports_pass`. Use mocked OS samples and small child allocations; never allocate 3 GB to prove the threshold.
- [ ] Run the exact named tests, record actual RED; implement the minimal supervisor with process-group cleanup, lock, stream samples, fail-closed monitoring and a bounded terminate/kill grace.
- [ ] Exact GREEN then nearby variants: already-exited child races, descendant accounting, simulated swap/headroom exhaustion, zero/invalid limits, SIGINT/failure cleanup. Default cadence at most 0.2s; monitoring overhead measured. Sampled limits cannot guarantee zero transient overshoot.
- [ ] Run `uv run pytest tests/unit/test_recovery_resource_guard.py -q` and selected Ruff/Pyright as appropriate only after stable safe launch prerequisites. Demonstrate normal tiny child and intentionally stopped low-threshold child, each with receipt; no heavy tests.
- [ ] Commit supervisor separately after green; no claims about report memory yet.

## RV3 — Fresh small baseline, then separate stage measurements

**Files:** Create diagnostic `scripts/recovery/profile_report_stages.py`; update investigation/receipts. Use existing `tests/fixtures/phase8.py`, report IR/store/rendering fixtures. No production change.

**Interfaces:** `StageObservation(stage: str, source_sha: str, elapsed_seconds: float, peak_rss_bytes: int, peak_footprint_bytes: int, payload_bytes: int, outcome: str)` and diagnostic `measure_stage(stage: str, recipe: str, output: Path) -> StageObservation`. Stages execute in fresh isolated children under RV2; no fabricated authority/model shortcuts.

- [ ] Restore locked uv environment/Python 3.12+, including missing typing dependencies; setup failure is not a check failure.
- [ ] After stable normal pressure, start sequential shape-only reporting/base contracts, AST architecture/import guards, and `tests/integration/test_phase8_slice.py::test_report_request_is_immutable_and_refuses_export_seed`. Inspect fixture dependencies before choosing a node; directory names do not establish resource cost.
- [ ] Run locked Ruff/format and strict Pyright sequentially with receipts. No full suite at this step. Investigate every red gate honestly.
- [ ] Measure smallest native upstream construction, SQLite copy, frozen/bundle load, individual Q1–Q9 fallback, citations/IR, acceptance/load, JSON/YAML/Markdown and parity. Record call counts/SQL counts where useful; distinguish fresh profiling overhead from ordinary runs.
- [ ] Partition reproduced accepted-report bytes into public text, normalized assertions, basis proposition repeats, repeated IR collections, history and executions. Original 53.8 MB DB is lost; this is a new profile, not the same fixture.
- [ ] Native full compiler/slice execution requires reviewed measured capacity. If a stage is unsafe locally, preserve incomplete output and move to approved higher-memory hardware. Do not run known 9.7 GB case locally.

## RV4 — Native snapshot fixture reuse, only after approval/evidence

**Files:** Candidate changes `tests/fixtures/phase8.py`, `tests/unit/reporting/test_bundle.py`, `tests/unit/evidence/graph/test_report_store.py`, `tests/integration/test_phase8_slice.py`; create `tests/unit/test_phase8_fixture_isolation.py` if a shared helper is justified. Scope chosen from RV3, not all files at once.

**Interface:** Test-only `clone_authoritative_baseline(baseline: Path, destination: Path, *, expected_sha256: str) -> Path`; closed/coherent SQLite backup, per-test writable destination, baseline hash verified. Native repository load remains at each copy's boundary.

- [ ] **RED:** `test_mutation_in_clone_does_not_change_baseline_or_second_clone`, `test_changed_baseline_checksum_rejected`, `test_foreign_scope_or_schema_cannot_reuse_snapshot`, `test_reopened_private_copy_keeps_native_authority_checks`.
- [ ] Measure original selected setup; implement one baseline/private-copy improvement; dispose engines and handle WAL coherently. Keep construction/migration/concurrent transaction tests building their own states.
- [ ] Exact GREEN, isolation/rollback/reopen variants, owning report bundle/store and Phase 6/7 mutation/authority regressions. No deserialized caller shape creates authority.
- [ ] Before/after identical node/scenario/hardware measurements; retain native equality/digests and counts. Commit only a demonstrated safe improvement. Large serialized global caches must be measured, not presumed efficient.

## RV5 — Restore or regenerate goldens with independent semantic evidence

**Files:** Eight `tests/golden/phase8/*.json|yaml` paths listed in investigation; new `tests/golden/phase8/RECOVERY_PROVENANCE.md`; owning `tests/golden/test_phase8_reports.py` only for additional independent checks, never weaker comparisons.

- [ ] Prefer any newly supplied historical archive; match full recorded/object hashes where available. Known sources have been exhausted; don't repeat broad searches without new evidence.
- [ ] If regeneration is required, obtain disposition approval and operate only after backup, RV2 safety and native fixture validation. Preserve partial original separately; label every new artifact REGENERATED with input/method/source/output hashes.
- [ ] Independently check all scenario expectations directly from native frozen targets/Gates/limitations, the approved contract and distinct negative controls. Validate direct/strong-partial residual/potential/mixed/unassessable/M1, all question/target coverage, Q7/Q8/Q9 and source-version-passages.
- [ ] Verify surviving Markdown projection and partial JSON prefix where comparable. Neither comparison proves full historical equality.
- [ ] Run full owning golden and fallback/wording/value/uncertainty/citation/parity tests sequentially under proven capacity, or on larger hardware. Generated-output equality alone is not acceptance. Commit reviewed regenerated artifacts separately from performance fixes.

## RV6 — Production duplication/copy remediation, measured and reviewed

**Files:** Only reproduced-defect owners among `reporting/fallback.py`, `claims.py`, `uncertainty.py`, `ir.py`, `rendering.py`, `artifacts.py`, `evidence/graph/report_validation.py`; exact owning unit/adversarial tests. ADR if content/ID/persistence versions change.

- [ ] Present RV3 byte/allocation evidence and concrete smallest change before substantial refactoring. Investigate exact clause-sized propositions, reuse of pure projections within one validated scope/transaction, or fewer temporary representations. Do not infer entailment from IDs or remove mandatory validations.
- [ ] **RED:** reproduced amplification plus preserved authority/meaning invariants. Existing controls include `test_supported_claim_cannot_drop_material_limitation`, `test_synthesis_does_not_establish_combination`, `test_canonical_dependency_transplant_fails_load`, `test_all_semantic_ports_unavailable_produces_full_report` and native revocation/missing-execution/parity tests.
- [ ] Exact minimal GREEN, nearby attacks, owning component and Phase 6/7 authority regressions. Public text/identity/contract changes need an approved ADR/version-support decision before implementation; no silent v1 reinterpretation.
- [ ] Before/after native representative time/RSS/footprint and bytes, on identical hardware/recipes. Keep real production path alongside small diagnostic cases. If not safely improved, record it and move necessary verification to higher-memory hardware.
- [ ] Commit each measured correction; audit and seek approval for exact remote backup checkpoints, preserving d058976.

## Explicit prerequisite gate before Task 22 features or Tasks 23–24

All must be evidenced:

1. Confidential off-device evidence backup independently restored; source checkpoint/public backup and immutable manifests remain intact.
2. Eight goldens exactly recovered or regenerated with reviewed independent expected semantics; original commit equivalence remains unproved and alternative provenance accepted explicitly at final review.
3. Locked dependencies, fresh Ruff/format/strict Pyright and contract/architecture gates pass.
4. RV2 supervisor launch/stop/cleanup is verified; representative native workloads have measured safe local bounds or an approved suitable larger environment.
5. Fresh Phase 7 authority/permission/execution/freeze tests and Phase 8 Tasks 1–21 owning report/store/port/compiler/adversarial/golden gates pass for the recovered tree, including fallback and safe generative happy paths, illegal repair/provenance, scope/source transplantation, missing dependencies, revocation and format/summary/lens parity. Record exact commands/node inventories, counts, failures, peak memory and source identity. Any red gate keeps the hold.
6. No original result is counted as recovered-tree verification. No incomplete run is represented as a suite pass.

This prerequisite establishes recovery/development readiness, not Phase 8 independent acceptance.

## Tiered verification and tested-tree ruling

- **Focused development:** exact RED/GREEN and variants for the changed behavior; shape-only fast gates when appropriate.
- **Task gate:** owning component and relevant upstream authority regressions; native checks remain. No unchanged multi-hour suite repeated merely because a commit occurred.
- **Comprehensive:** fresh required recovered-baseline gate and designated final suites; all approved assertions/adversarial/golden tests retained. Capacity proof/high-memory approval precedes heavy execution.
- **Final detached:** complete approved Task 24 command sequence and `uv run python scripts/verify.py` again at exact implementation SHA in a clean detached checkout under `~/Documents/Novcheck-Worktrees/`; locked sync, clean status, whitespace and logs retained.
- **Independent acceptance:** one fresh whole-phase reviewer after implementation verification; provenance limitation and any critical/important defect stay explicit.

Avoid redundant post-commit reruns only when complete file/mode/config/test/generated-input evidence proves the tested tree equals the commit. Keep actual full pre-commit pass plus focused post-commit smoke and deferred final gate. A source/config/test change invalidates that equivalence. This exception cannot reuse historical 1f50323 passes for d058976.

## Self-review and approval boundary

Coverage includes every current recovery priority, confidential evidence, eight artifacts, identity uncertainty, native authority, fixture isolation, production memory, measured gates and checkpoint preservation. Scope is recovery/performance, not later-phase features. No optimization is claimed from static call counts. Before/after native measurements remain pending because OS pressure is warning level 2.

Native execution method is preserved. The investigation/plan checkpoint can be committed now after scoped static/document checks. A confidential destination/key, any new off-device transfer, regeneration disposition, substantial production refactoring and heavyweight/higher-memory execution remain concrete approval/input boundaries under the user's current instructions.
