# Phase 8 focused recovery readiness and Task 22 assessment

**Date:** 8 October 2026. **Tested implementation:** `562f63e2542f387b275c85b364fea082a44ae2fe`, clean tree; source/file-mode digest `e7f1c066a3808308afe50dc01ba55aaafe4466ac708364098ae6331f4f67db93`.

**Status: INCOMPLETE — historical focused selection remains 52/69; 17 native readiness nodes remain pending. Task 22 cleanup corrections have resumed with focused RED/GREEN proof; native integration assertions remain unverified.** This is a development readiness gate, not recovered-baseline or Phase 8 acceptance.

## Authorization and preserved state

The user now prioritizes original Phase 8 completion. The latest user instruction permits safe Task 22 implementation while heavyweight readiness remains blocked. Task 22 required completion gates must pass before Tasks 23–24 proceed under the [approved implementation plan](../superpowers/plans/2026-10-05-phase-8-full-report-compiler-implementation-plan.md). General A+B cache expansion is paused; its verified routes and supervisor remain. Test infrastructure work is appropriate only when it directly unblocks required Phase 8 coverage. Contract-changing performance work still needs a separate decision.

This ruling supersedes the earlier blanket Task 22–24 hold. It does not waive full final authority, semantic, security, provenance, adversarial, golden, strict typing, fresh detached-checkout or independent review gates. Missing goldens and original-tree equivalence are final acceptance limitations, rather than reasons to prevent an otherwise passing targeted development gate.

`562f63e` and its independently verified GitHub checkpoint, complete local bundle and restore receipts remain preserved. Earlier recovery and forensic checkpoints are untouched. Only this Mac executes tests; GitHub remains reviewed source backup.

## Task 22 against its approved plan

The historical plan checks RED, its exact RED command and IMPLEMENT; GREEN, variants, regression and task commit remain unchecked. Reconstructed files cannot prove exact equivalence to the lost pre-crash tree. The following describes present source and historical recorded progress separately from fresh execution proof.

| Planned responsibility | Present reconstructed implementation | Fresh status |
| --- | --- | --- |
| Frozen `ReportCompilationRequest` and explicit real branch | `application/models.py` validates options/ports; `vertical_slice.py` requires real Phase 7 and exclusive real Phase 6 | Request immutability/export-seed and fixture-branch rejection pass |
| Compile after native freeze/reload; separate report operation | Real branch invokes coordinator after frozen summary, returns `Phase8VerticalSliceResult`; standalone compilation uses explicit adjudication locator | Native freeze/bundle boundaries pass; complete branch remains unproved |
| Locator-loaded JSON/YAML/Markdown exports | `phase8_exports.py` loads authoritatively, renders and uses safe writer under `reports/<report_id>/` | Native accepted-report/export execution pending |
| Preserve adjudication/summary on operational failure | Report-specific error wraps operational exceptions; authority errors propagate; upstream summary is written first | Both generation/export failure cases pending |
| Retry export, completed lifecycle, separate paths, corrupt authority | All named tests exist in `test_phase8_slice.py`; accepted baseline/private SQLite copies exist | Seven of nine slice nodes pending |
| Legacy fixture/summary compatibility | Original routes remain present | Complete minimal-report suite passes; real summary-only slice remains pending |
| Task completion evidence | No completed Task 22 GREEN/regression/commit evidence in recovered record | OPEN |

No new production defect is established by this static review. Before closing Task 22, make its tests explicitly observe no semantic dispatch during export retry, unchanged Phase 7 rows and separate attempt scope in the real branch, and accepted-report loadability of the baseline after clone corruption. These checks must use native accepted authority.

The export-copy fixture also opens the repository and performs native loads before entering its `try/finally`, and SQLite connection contexts do not explicitly close connections. Add focused cleanup failure controls before correcting this fixture; this is directly relevant test lifetime work, not general cache expansion. Do not claim a reproduced failure from inspection alone.

## Focused gate definition and exact accounting

The protected `phase8-focused-readiness-01.json` fixes **69 exact parameterized node IDs**, joined to the actual collected inventory, job/pytest/guard/log/sample bytes. Completed receipts were reopened and independently re-accounted. Every completed node has passing setup, call and teardown, successful supervisor exit and cleanup. No skip, refusal, abort or historical pass counts as a fresh pass.

| Required boundary | Fresh result |
| --- | --- |
| Phase 7 verdict/permission recomputation, missing frozen dependency, revoked graph authority, atomic freeze rollback | 4 native tests pass |
| Phase 8 native input: exact closure in one read transaction | 1 native test passes |
| Strict reporting contracts, method/configuration identity, Phase 7 capability guards; Task 22 request and fixture exclusion | 12 tests pass |
| Planner cannot omit decisive material; actual recovery audit/instruction; material limitation; positive/negative synthesis; heading/table extraction and empty extraction controls | 6 tests pass |
| Legacy minimal report compiler and inert untrusted prose/citation text | 29 tests pass |
| Native complete fallback and generative coordinator paths; acceptance proof/rollback; authoritative load transaction; CONTEXT/SOURCE_VERSION transplant rejection; one-repair origin; all-format parity; compact-summary strength | 10 nodes pending |
| Remaining Task 22 real branch, generation/export failure, retry, completed lifecycle, corrupt export authority, separate export paths | 7 nodes pending |

The collection contains **2,541 required nodes and the existing five network exclusions**. The focused gate is a subset, never a replacement for that full inventory or future Task 23–24 additions. Missing/duplicated/unexpected readiness nodes prevent progression. Final full verification runs afresh in a clean detached checkout.

### Commands and measurements

Execution used the existing `scripts.recovery.local_batches.run_batch` API with exact collected node IDs and `.venv/bin/python -B -m scripts.recovery.pytest_child <immutable-job.json>`, supervised sequentially. Native/contract jobs used 192,000,000 B soft / 256,000,000 B hard limits, 1 GB minimum estimated headroom, warning-permitted v2 risk monitoring and 90s timeout; request/legacy jobs completed within their 60–90s bounds. No application test ran outside the supervisor. Internet socket/plugin/marker policy was unchanged.

Protected receipt groups: `phase8-readiness-request-01`, `phase8-readiness-authority-01` through `04`, `phase8-readiness-freeze-rollback-01`, `phase8-readiness-report-contract-01` through `06`, and `phase8-readiness-legacy-safety-01`. Their machine ledger retains every exact command and node ID.

The 13 jobs passed **52 tests**, taking **289.642s** including per-job guard/startup/reap/bookkeeping. Aggregate pytest setup was **97.844s**, call **130.418s**, teardown **0.00790s**, with **13.374s** import/collection. These phase totals do not add to end-to-end time: parent and monitoring overhead remain included separately. Nested fixture stages are not added twice. Maximum sampled process RSS was **173,309,952 B**; native footprint/lifetime peak **157,877,888 B**.

Actual execution-audit primary: 64.953s end-to-end, 19.090s setup and 41.587s call. The planner/limitation/synthesis native primaries each took 25.603–26.987s. These identify real readiness cost; they do not establish a complete-suite forecast or a before/after speedup. No new optimization was applied during this gate. Previously measured A+B savings remain 25.6% for the nine-node native cohort and 80.0% for five lightweight controls; substantial native memory savings were not demonstrated.

## Capacity blockers and next execution

1. The **input-only Task 22 slice capacity probe** used the verified normal-pressure supervisor with tightened 256/384 MB caps and a 90s timeout. It was **REFUSED/MEMORY_PRESSURE** at level 2, 1,838,858,240 B estimated headroom and 4,202,042,490 B allocated swap. No child launched. Allocated swap was not the veto. A single refusal does not prove harmful paging or measure slice capacity.
2. A separate **already-qualified minimum native-input partition probe** was **ABORTED/SUSTAINED_PAGING** after 4.569s, at 92,389,376 B sampled RSS / 80,397,632 B footprint. Its approximate three-second window showed 50.1 MB/s output paging and headroom near 1.19 GB, below minimum-plus-soft-cap margin. Cleanup completed. No partition output or test pass exists; the supervisor stopped during setup.
3. The historical Task 22 primary reached about 9.7 GB. It was **not dispatched unchanged**. Current source presence, small contract passes and A+B savings do not qualify that recipe. Before rerunning, obtain native input size/closure measurements, then section/IR/format/accept/load capacity proof with bounded children. Any fixture adjustment must preserve all assertions, targets, unsearched-family limitations, real upstream execution and full nine-question coverage. If a production operation itself blocks completion, record its measured stage and seek any required separate optimization/contract decision.

There are no automatic retry loops and no raised caps. Editing and static analysis continue normally; small measured tests did execute at warning pressure. Return to the pending native capacity step when conditions give measured margin, then run the 17 pending nodes. A failure is fixed with its exact regression before declaring readiness. The 9 October instruction supersedes the implementation hold: safe Task 22 cleanup/assertion work proceeds now, with exact native GREEN/variants/compatibility/static checks outstanding. Neither this partial increment nor the earlier selection closes Task 22.

## Tasks 23–24 and eight goldens

Task 23 post-commit trace projection and new Phase 8 architecture guards are not implemented. Task 24 integrated adversarial closure and traceability/completion handoff remain outstanding. Follow their approved named RED/GREEN cases after Task 22; do not conflate existing adversarial cases with these missing integrated tests.

The six semantic fallback JSONs (`direct`, `partial_negative`, `potential`, `mixed`, `unassessable`, `m1`) and two rendering projections (`rendering-public.json`, `rendering-public.yaml`) remain missing. Previous recovery searches found no complete originals. Preserve the recovered Markdown, original partial prefix and forensic receipts. Regenerated files must be labeled separately, with source/recipe/native locators/digests, normalization/version/output hashes and independent expected-semantic checks before adoption. Copying current output into a golden is not verification. See the [existing artifact investigation](2026-10-08-validation-investigation.md#eight-missing-goldens).

Full strict typing, final owning/upstream/adversarial/golden suites, `uv run python scripts/verify.py`, exact clean detached verification and whole-phase independent review remain OPEN. Original `1f50323` equivalence remains unproved and must be disclosed at final acceptance.


## 9 October: Task 22 cleanup increment and native capacity evidence

The preserved starting checkpoint is `2ed48c3b131dee642a1ea4643e119bbfd40eadd4`, independently verified on GitHub. No production implementation, dependency, schema, golden or supervisor threshold changed in this increment. General A+B expansion remains paused.

`exported_case` now protects copying, repository creation, both native reloads and the yield with cleanup. Both SQLite copy connections close before native loading; setup failure/interruption closes the repository and removes the private database and sidecars. Database removal still executes if repository disposal raises. The remaining failure-recovery SQLite read connection closes explicitly. Six toy SQLite lifetime controls preserve exact source bytes and prove these mechanics; they do not certify accepted native authority.

The exact original cleanup primary failed on both frozen/bundle load variants because the repository remained open. After the fixture fix, all six lifetime controls passed. A later current-source selection passed those six plus the two existing request/branch controls: **eight tests, 5.273s supervised elapsed, 126,533,632 B peak sampled RSS and 111,035,904 B footprint**. Private receipts are `task22-cleanup-red-01`, `task22-cleanup-green-01`, and `task22-focused-controls-02`. Final checkpoint checks are recorded separately; these measurements are not a paired performance claim.

The native integration tests now assert zero compiler/semantic dispatch on export retry; partial JSON publication followed by YAML failure and native accepted-report reload; unchanged upstream rows and independent attempt token/scope in the real branch; and accepted baseline loadability before and after private-clone corruption. Existing assertions remain. The summary-only result and observation-only native models are released after their assertions, before compilation. These strengthened native assertions are **prepared, not passed**.

Actual current collection captured **2,547 required parameterized nodes and the same five network exclusions**, including the six added cleanup controls (`task22-current-inventory-01`, 7.511s end to end). Collection is not a suite pass. Source changes invalidate old execution/resume identities; the previous 52 passes retain their original source identity and are not claimed as current-tree regression proof.

Fresh read-only observations found warning pressure with 1.413–1.481 GB estimated headroom and approximately 75 KB/s output paging. Automatic approval review initially rejected a repeat of the earlier paging-aborted minimum-input probe; after this changed-condition evidence, it approved a single guarded attempt with unchanged caps. That qualified minimum native recipe completed (`task22-minimum-input-partition-01`): **22.646s supervised elapsed, 131,629,056 B sampled RSS, 126,551,424 B footprint**. Construction took 12.997s, freeze 1.419s, frozen reload 1.414s and bundle reload 1.946s; these nested intervals are not added twice. Exact bundle digest: `f0438ad7ffefd1be428964910d537a5a7acc6c5db0f7c4c9b2d92ebc945e6a67`. This is native-input proof, not report compilation or real-slice capacity proof.

The subsequent single-Q1 probe completed private copying (0.00757s) and native bundle reload (1.999s), then was **ABORTED/SUSTAINED_PAGING** before another completed stage or section result. Its final three-second window showed approximately 85.1 MB/s output paging, headroom falling from 1.366 to 1.269 GB, and 123,387,904 B sampled process peak; cleanup completed. No Q1 output/capacity or production-memory defect is established by this environmental abort. The pending generation-failure node was separately **REFUSED/MEMORY_PRESSURE** under normal-pressure 256/384 MB caps and 1.5 GB minimum headroom; no child launched. Neither attempt counts as a functional failure or a readiness pass. No unchanged unsafe recipe or retry loop was launched.

Small focused tests used:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m scripts.recovery.resource_guard --small-workload --soft-bytes 192000000 --hard-bytes 256000000 --timeout 60 --output <new-receipt.json> -- .venv/bin/python -B -m pytest -p pytest_socket -p pytest_asyncio.plugin tests/unit/test_phase8_export_fixture_cleanup.py tests/integration/test_phase8_slice.py::test_fixture_report_cannot_masquerade_as_real_report tests/integration/test_phase8_slice.py::test_report_request_is_immutable_and_refuses_export_seed -q
```

The protected ledger retains exact commands, logs, samples and source/file-mode identities. Full-tree Ruff lint and formatting checks passed (425 formatted Python files); their protected receipts are `task22-ruff-check-02` and `task22-format-check-02`. The final-source collection recheck was ABORTED/SUSTAINED_PAGING after 4.636s, at 89,309,184 B sampled RSS / 91,932,160 B footprint, with cleanup complete (`task22-final-inventory-01`). It produced no final inventory or test passes; the earlier successful collection and eight passes keep their own source identities. Test dispatch stopped rather than retrying the paging condition. Backup receipts accompany this partial milestone. Strict typing, all 17 native nodes, full owning/upstream/adversarial/golden suites, `scripts/verify.py`, fresh detached acceptance and independent review remain OPEN. Tasks 23–24 have not begun. There is no new speedup or memory-saving claim; the prior measured A+B results remain unchanged.
