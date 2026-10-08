# Guarded recovery validation — 8 October 2026

**Status: verified A+B partial rollout retained; focused Phase 8 readiness INCOMPLETE. Safe Task 22 implementation is authorized while native readiness is blocked; Tasks 23–24 await Task 22 completion gates; final recovered-baseline acceptance remains OPEN.**

**Current storage policy:** Reviewed source uses existing GitHub; confidential forensic evidence stays encrypted on this Mac. The user explicitly accepted complete local device/storage-failure risk on 8 October 2026. Off-device forensic backup is no longer a recovery prerequisite. Earlier pending-destination entries below are historical and superseded by the accepted exception at the end of this report.

## Preserved checkpoints and confidential backup

The approved `baaf64c3a5cab3c253dd4808428d2b1b66ea461a` was pushed without force to `recovery/validation-performance-20261008` in the existing public repository. A fresh independent bare fetch verified that SHA, tree `d3e4fe347ccc21f813dfa705276d7e10bed717ad`, all 509 tracked file modes/blob IDs and `git fsck --full --strict`. The two existing remote branches are unchanged. No private evidence ref, raw forensic record, archive or member manifest was pushed. The final outgoing review found only two commits adding three diagnostic/documentation files; checkpoint history was previously reviewed.

Both original forensic directories are preserved. A streaming archive comparison verified **17,398 members**, including 15,272 regular files, exact file hashes, modes and symlink targets. AES-256 encryption completed through a local Terminal password prompt; neither the agent nor command arguments/logs received the passphrase. The encrypted disk image is **93,126,144 bytes**. A read-only decrypted mount verified the archive SHA and every member again. Ciphertext SHA-256: `5db24dc2c14837da2793338f529a701519ca2714fbfa99d463ea3a657ebfe349`. This is a **local encrypted preparation**, not an off-device backup. At that recording point, private destination approval, independent key custody and destination restore verification remained required; the later explicit backup exception supersedes that destination requirement. Nothing confidential was uploaded. Original evidence and the local verified plaintext staging copy remain preserved in protected locations.

Private receipts are under ignored `.superpowers/recovery-validation/20261008/`; public source contains only summarized findings. The immutable 518-file forensic manifest remains unchanged. Its categories remain 375 exact baseline, two full recorded hashes, two diff witnesses, one recorded projection without final hash, 125 reconstructed/unproved, eight missing/partial goldens and five future unimplemented paths. New supervisor/probe files are recovery instrumentation, not historical reconstructions. Original `1f50323` identity and recovered-tree equivalence remain unproved. The historical 377-test and 23-test results are not reused.

## Resource controls and actual gates

`scripts/recovery/resource_guard.py` imports no application. It reserves separate immutable receipt/output/sample records, binds current source bytes/modes (including new files), uses an exclusive lock shared by Git worktrees, and samples process descendants including observed separate sessions. It captures RSS and native physical footprint/lifetime peaks from SDK `RUSAGE_INFO_V4`, macOS pressure, free-plus-inactive headroom estimate and swap use. It requires three stable preflight samples, refuses warning/unknown pressure, enforces maximum 0.2s collector latency, and terminates/reaps children on resource/time limits, monitoring failure, SIGTERM or interruption. Sampling cannot guarantee zero transient overshoot or observe a descendant that starts and exits entirely between samples; known unsafe workloads remain excluded.

Default intensive limits are 2.5 GB preemption and 3.0 GB hard threshold; initial CLI probes use **256 MB preemption / 384 MB hard**, minimum 1.5 GB estimated headroom, maximum 2 GB swap, and 0.1s sampling. These limits do not alter test assertions or report authority.

TDD/control evidence is retained: initial missing supervisor; SIGTERM orphan reproduction; nonfinite timeout/swap-limit bypass reproduction; separate-session descendant failure; slow-monitor launch failure; native exit-race and cumulative nonoverlapping-peak failures. Fixes affect only diagnostics. Live unreadable processes still abort; an unreadable process is ignored only after an independent check confirms it has exited/is a zombie. Peak aggregation now counts current children rather than adding sequential child lifetimes.

| Fresh gate | Result | Guard elapsed | Peak tree RSS | Peak footprint |
| --- | --- | ---: | ---: | ---: |
| Native tiny child | PASS, exit 0 | 0.898s | 14,893,056 B | 6,145,152 B |
| 16 MB allocation, 20 MB stop threshold | ABORTED, SIGTERM, cleanup complete | 0.945s | 30,834,688 B | 22,135,936 B |
| Supervisor pytest controls | 14 passed, eight subtests; cleanup complete | 11.615s | 110,395,392 B | 67,228,288 B |
| Strict report contract primary | 1 passed | 5.215s | 101,138,432 B | 75,549,184 B |
| Small component/contract/architecture selection | 12 passed | 13.444s | 144,818,176 B | 118,000,256 B |

The primary is included in the 12-test selection: **26 unique tests** after adding the nonfinite-limit regression; the primary is a repeated execution, not another unique test. The earlier monitored supervisor pytest attempt **ABORTED** at 102,203,392 B RSS with a native sampling race; four progress dots do not constitute a pass. Its partial log/receipt remain preserved. A real native gate previously refused pressure level 2. After OS recovery, three observed normal-pressure samples had approximately 2.22 GB headroom and 1.85 GB swap; native collector reads took 0.023–0.028s.

The controlled stdlib suite also ran independently: final pre-native 11-test run, 10.35s wall, 28,196,864 B peak RSS, 17,237,184 B peak physical footprint. That result covers controls, not application correctness.

## Isolated environment and exact commands

An isolated uv 0.9.0 tool was restored from its official pinned PyPI wheel and checked against the registry SHA-256. `uv sync --locked --dev --offline` failed because the required wheel cache was unavailable; **setup failure is not a test result**. Subsequent locked synchronization succeeded. All 27 applicable installed package versions match unchanged `uv.lock`; Windows-only colorama is inapplicable. Python is 3.12.13. Application discovery resolves to this persistent worktree, with no forensic editable binding. `pyproject.toml`, `uv.lock`, production code and existing assertions remain unchanged.

The locked uv binary lives in ignored local tooling. Each test command below ran sequentially through `resource_guard.py`, with plugin autoload disabled and explicit socket/async plugins:

```bash
uv run --no-sync --offline python -B -m pytest -p pytest_socket -p pytest_asyncio.plugin tests/unit/test_recovery_resource_guard.py -q
uv run --no-sync --offline python -B -m pytest -p pytest_socket -p pytest_asyncio.plugin tests/unit/reporting/test_contracts.py::test_report_contracts_are_strict_scoped_and_distinct -q
uv run --no-sync --offline python -B -m pytest -p pytest_socket -p pytest_asyncio.plugin tests/unit/reporting/test_contracts.py tests/contract/test_mock_provider_contracts.py::test_mock_llm_provider_contract_is_fixture_only tests/integration/test_phase8_slice.py::test_report_request_is_immutable_and_refuses_export_seed tests/unit/test_phase7_architecture_guards.py -q
```

The existing pytest configuration disables Internet sockets. These selected nodes use shapes, mock providers and AST guards; no native assessment/compiler fixture is requested. The Task 22 request-shape test verifies recovered code already present; feature implementation remains held. Scoped Ruff check and format checks pass for diagnostic scripts/tests. Fresh full-tree Ruff check also passed (0.12s Ruff wall, 33,275,904 B process peak RSS, 21,513,472 B footprint; the short-lived child finished between guard samples). Full-tree formatting also passed; its exact log is retained. Full strict Pyright, upstream authority suites and `scripts/verify.py` remain pending under the user's explicit prohibition on comprehensive testing now.

## Measured representation amplification

`scripts/recovery/profile_report_stages.py` runs real `ClaimBasisLink`/`AuthorityRef` Pydantic contracts and the actual canonical serializer/hash utility in bounded, synthetic projection cases. Each stage has a fresh guarded child. It creates **no native repository fixture, accepted ReportIR, adjudication or golden**. All fifteen observations passed their native guards; their basis JSON hashes agree for each recipe, including traced/untraced pairs. No optimization was applied.

The same 4,096-character paragraph supplied to every basis link produces:

| Measurement | 16 refs | 128 refs |
| --- | ---: | ---: |
| Distinct live proposition strings after construction | 16 | 128 |
| Distinct strings after JSON revalidation | 16 | 128 |
| Basis JSON | 80,695 B | 645,651 B |
| Repeated proposition bytes | 65,536 B | 524,288 B |
| Block/global double collection JSON | 161,434 B | 1,291,346 B |
| Python allocation peak, construction | 101,578 B | 805,786 B |
| Python allocation peak, model dump | 17,648 B | 146,288 B |
| Python allocation peak, canonical JSON | 133,086 B | 917,923 B |
| Python allocation peak, JSON validation | 132,529 B | 1,094,033 B |
| Python allocation peak, canonical hash | 181,208 B | 1,318,168 B |

Repeated proposition characters account for about **81.2%** of these small basis JSON payloads. There is duplication before serialization: `NonBlank` uses Pydantic whitespace normalization and independent validation constructs separate strings even for the identical input object. `model_dump` adds mappings; canonical serialization materializes repeated characters; JSON validation creates another model/string set. This demonstrates multiple-stage amplification without fixture rebuilding or `deepcopy`.

Probe peak RSS ranged **69,648,384–77,938,688 B**, peak footprint **56,329,472–64,455,936 B**, including imports, setup and byte-accounting work. Per-stage Python allocation peaks exclude preparatory inputs; native process peaks include them. The extra collection byte comparison models the actual block/global storage topology without constructing a repository-authoritative IR.

| Timing observation | Traced | Untraced |
| --- | ---: | ---: |
| YAML, 16 refs | 3.491s | 0.239s |
| YAML, 128 refs | 21.489s | 1.085s |
| Canonical JSON, 128 refs | 0.0512s | 0.0123s |

Allocation tracing substantially amplifies serializer time, especially YAML. These are paired instrumentation measurements, **not before/after optimization results**. YAML's timed stage also includes its import; absolute times must not be extrapolated to a full accepted report.

### Root cause and limits of the conclusion

Production fallback copies whole paragraph text into the block, normalized assertion and **every** basis proposition. Accepted blocks and global IR collections both carry claims/bases; canonical JSON repeats both even if Python references were shared. Rendering serializes/revalidates the wrapper, creates JSON, decoded mappings, YAML and Markdown; parity renders again and parses formats. Native authoritative acceptance/load also revalidate/hashes these structures. Fixture setup expands research/history prose and rebuilds upstream states repeatedly. Together these are several sources of cost; eliminating fixture rebuilding alone cannot remove production representation duplication.

The lost 53,815,435-byte accepted report cannot be partitioned exactly now. Historical expanded Q3 evidence attributed 321,715,598 of 329,229,489 bytes (**97.7%**) to basis links, with roughly 698 KB paragraphs repeated across over 100 refs. That historical evidence and the bounded fresh probes identify pathological duplication alongside legitimate content. They do **not** assign an exact percentage of the full report or the historical 9.7 GB footprint to each stage. Full native ReportIR/rendering/acceptance/loading memory remains unmeasured on the recovery baseline. No claim of a 2–3 GB full-test peak or achieved speedup is made.

## Next safe scope and remaining gates

1. Preserve the verified encrypted forensic backup and originals locally under the accepted backup exception; continue reviewed source backups to existing GitHub. Do not upload confidential evidence or pursue another storage destination.
2. Keep eight goldens missing until backup, native fixture validation and independent semantic regeneration provenance are ready. No replacement was generated in this stage.
3. Profile one minimum native upstream fixture and frozen/bundle reload in isolation under the proven conservative guard, then review capacity before ReportIR/compile/render/accept/load cases. Known 9.7 GB and comprehensive cases remain blocked locally until measured remediation establishes safe capacity; the current user instruction excludes external execution/additional hardware.
4. Investigate immutable test-only SQLite baselines/private copies first, preserving native transactional load/accept/read revalidation. Isolation/hash/schema/context/reopen/mutation tests are mandatory before cache reuse. Historical copy/reload timings remain leads, not a measured recovery speedup.
5. Propose a separate, contract-aware production remedy for repeated basis text and simultaneous representations. Preserve proposition support/completeness, exact dependencies, v1 identity/version compatibility and parity. No validation is removed solely because it repeats; persisted-contract changes require an ADR/version decision. No such refactor has begun.
6. Retain fresh full recovered-baseline checks, final complete/detached verification in persistent worktrees and one independent whole-phase review. Original commit provenance remains an explicit final acceptance limitation even though the three historical tree closures were recovered.

**Earlier ruling (superseded for storage only):** User authorization permitted local encryption and RV2/small RV3 checks while destination approval was pending; off-device backup was then a feature-release prerequisite. The explicit local-only exception below replaces that prerequisite. Explicit user safety limits override generic skill/AGENTS full-suite advice at this investigation stage. Full gates remain required later. Exact tested source/config identity will permit focused post-commit smoke instead of an unchanged multi-hour rerun; historical lost-tree results do not establish that identity. No assertions, adversarial controls or authoritative findings were removed or weakened.


## Approved checkpoint upload and storage ruling

The user-approved `e8006f26630d43fb19ddbea3af08c01275c98e95` was pushed without force to `recovery/validation-performance-20261008`. Final review covered the one outgoing commit and exactly five diagnostic/documentation paths; no production changes, confidential evidence or unintended files were included. A new independent bare fetch verified the exact commit, tree `28605c0d2f2f7564a4d60c6afc0ea389d899bae5`, all 513 tracked blob contents/modes, no object alternates, and `git fsck --full --strict` exit 0. The empty bare repository's unborn default HEAD notice does not affect the verified named branch. All other remote branches/tags are unchanged.

The user cancelled Google Drive work and restricted storage choices to the existing GitHub repository and this Mac. Drive inspection stopped; no folder or upload was created. Source checkpoints are backed up publicly only after review and exact approval. The encrypted forensic backup remains local: its 93,126,144 bytes and ciphertext SHA-256 were rechecked successfully. The immutable 518-file manifest hash also remains unchanged. Confidential off-device transfer, independent destination restore and key custody remain **OPEN**; this ruling does not waive the feature-release prerequisite or authorize publishing forensic material to GitHub.

The next selected native gate is the unchanged `test_bundle_revalidates_one_exact_authority_closure`, whose fixture creates real Phase 6/7 authority, freezes/reloads it and checks one transactional bundle closure. It does not compile/render/accept a report. The 60-second supervisor gate, 256 MB preemption / 384 MB hard limits, **REFUSED** launch due to native warning pressure level 2. Its sample recorded 1,521,369,088 bytes estimated headroom and 4,162,584,576 bytes swap use; no child PID, exit code or test result exists. The receipt binds the clean `e8006f2` source tree digest `da25fbc6340d05e9a7c649af806ac377ca6abeb1862c9b3de2f9390fde2bdcd9`. This is a safety refusal, not a functional failure or pass. An earlier sandbox-denied native read was retried with approved native-read permissions; no monitor or threshold was bypassed.

The previous 26 passing small tests and their records are preserved. No new application test/profile ran. Eight goldens remain unresolved; full native memory measurements, fresh authority verification and final comprehensive/detached gates remain pending. No production refactor or Task 22–24 feature work resumed.


## Explicitly accepted local-only forensic backup exception

On 8 October 2026 the user explicitly selected only the existing GitHub repository and this Mac for storage, and accepted that confidential forensic evidence could be lost through complete local device or storage failure. This is an **accepted backup exception**, not an off-device backup or a claim of resilience. Recovery validation will not be blocked on another destination or repeatedly request one. Google Drive, external drives and other providers will not be pursued. No confidential forensic records or encrypted forensic archive may be uploaded to the public source repository.

The previously verified local encrypted container, original forensic directories and immutable 518-file manifest remain preserved. Passphrases remain locally prompted and excluded from chat, source control, command arguments and logs. Reviewed source checkpoints continue to use the existing approved GitHub branch. The source checkpoint `e8006f2` remains independently fresh-fetch verified; subsequent documentation commits are local until explicitly approved for push.

This explicit decision supersedes the earlier pending-destination/transfer prerequisite and prerequisite 1 of the recovery plan. It changes no functional, security, provenance or acceptance requirement. Eight missing goldens, unproved original-commit equivalence, fresh native authority checks, measured memory capacity, complete final/detached verification and independent whole-phase review remain required. Task 22 feature work and Tasks 23–24 remain held by those verification gates.

The next native gate was rechecked against the unchanged supervisor: **REFUSED**, `MEMORY_PRESSURE`, level 2, estimated headroom 1,835,466,752 bytes, swap 4,559,208,448 bytes. The 60-second gate retains 256 MB preemption / 384 MB hard thresholds, 1.5 GB minimum estimated headroom and 2 GB maximum swap. No application process was launched, no test executed, and no profile result is claimed. Its receipt binds clean commit `974f3a299f676406d2bd59eb3c59b004cc0ec258`. The existing 26 unique small-test passes and original receipts are preserved. Once all native launch prerequisites pass, run the single bundle-authority primary sequentially before profiling report construction or formats; known high-memory/full workloads remain excluded pending measured capacity.


## Local 8 GB remediation investigation checkpoint

The user requires development and complete verification locally on the existing 8 GB Mac. GitHub is source control/backup only; no external compute, Actions, external runner, paid service or additional hardware will be pursued. The accepted local-only forensic storage exception remains satisfied. Current clean `fa7feb5` and its complete local bundle are preserved; fresh remote head inspection matches the independently verified GitHub checkpoint.

A new [local remediation proposal](../superpowers/plans/2026-10-08-local-8gb-verification-remediation-plan.md) prioritizes disk-based native fixtures and subprocess lifetime isolation, exact streaming/staged formats, bounded proof recomputation and a separately versioned basis-content remedy. It records compatibility risks and mandatory isolation/authority/parity/identity controls. No speedup or production fix is claimed. No assertion, existing test, production contract or stored schema changed.

The smallest bounded 16-ref construction probe **REFUSED** launch under the unchanged guard: warning pressure level 2, estimated headroom 1,568,522,240 bytes, swap 4,718,791,229 bytes. No application/profiling child ran and no native report capacity measurement exists. Heavyweight future gates will initially use explicit 1,500,000,000-byte soft / 2,000,000,000-byte hard limits; small probes retain 256/384 MB. All normal-pressure/headroom/swap/cleanup requirements remain. Full/known unsafe workloads and feature work remain held. Source/recipe/receipt identity and all previous evidence are preserved.


## A+B approval and static preparation

The user approved test-only immutable SQLite baseline reuse and resource-safe sequential execution, requiring both memory efficiency and substantial total-wall-time reduction. The [approved execution addendum](../superpowers/plans/2026-10-08-local-8gb-verification-remediation-plan.md#8-approved-ab-execution-and-wall-clock-measurement-protocol) specifies separate construction/copy/native validation/setup/call/teardown/orchestration timers, setup frequency, paired before/after savings and complete-inventory forecasting. Under two hours is aspirational, not a coverage or safety exception. C/D/E remain separately approval-gated.

The current `18eb3ec` source checkpoint and verified complete local bundle are preserved. Memory readings still show warning pressure and roughly 5.18 GB swap. First exact cache-control RED launch **REFUSED** before any child: no test failure/pass was observed. Two new test files contain prepared mechanical clone-isolation/provenance checks and exact phase/inventory/resume accounting controls. AST syntax parsing passed for 13 test functions; parameterized cases are not claimed as collected or executed. Toy databases establish no native authority. No cache helper, runner, existing fixture route, production code or verification command was changed.

Actual before/after speedup and memory improvement remain unmeasured. Historical 377-test duration remains original-tree evidence. Achieving the two-hour aspiration would require 20,297.48 seconds / 73.8% less than that historical elapsed time; no such saving is claimed. Native fixture rebuilds, global serialized cache retention and intrinsic report duplication remain separate bottlenecks. Further execution waits for safe preflight; a normal manual restart remains advisable after saving other app buffers. The disk checkpoint and records are preserved; the agent will not restart the Mac or bypass thresholds.

## A+B implementation draft under the unchanged safety gate

Following explicit authorization to continue non-test implementation without restarting, A+B helpers and controls were prepared in the persistent recovery worktree. These are **unexecuted candidates**, not a verified optimization milestone. The earlier preparation checkpoint `f846b43` and its bundle remain preserved; GitHub still advertises the previously verified `fa7feb5` validation checkpoint. No new push occurred.

- Test-only SQLite images use coherent backup, ready-last publication, streamed checksums, exact provenance/scope/schema manifests and independent private copies. Each native copy uses the real transactional report bundle loader and exact upstream digest; models or serialized reports are not cached globally by the new adapter.
- The opt-in runner captures actual pytest collection and setup/call/teardown, keeps socket/plugin/marker policy explicit, rejects missing/duplicate/extra/nonpassing nodes, verifies native safety samples and proof-file hashes on resume, and invalidates source/mode/new-file/lock/interpreter/package/environment changes. Only collection is CLI-enabled; the final verification entry point remains unchanged.
- A bounded native fixture profiling recipe records upstream construction, freeze, frozen reload, bundle reload, publication, copying, native validation and teardown. Nested timings are not additive. Original and cached recipes must retain identical bundle digests before a paired saving is reported. No compiler/render/accept workload or golden generation is included.
- Regressions cover mechanical copying/publication, durable evidence tampering, invalid durations, identity changes and unsafe limit configurations. Real native cache tests are separate and pending minimum-fixture capacity evidence. Existing assertions and independently constructed mutation/migration/concurrency fixtures remain intact.

Initial memory observation was warning level 2 with 1,709,654,016 bytes headroom and 2,792,095,744 bytes swap. Three later observations remained level 2; headroom ranged 1,616,084,992–1,620,180,992 bytes, with 4,171,434,557 bytes swap. No application/test/profile child launched and no RED/GREEN result exists. This is not a swap-only refusal; no safety policy was relaxed. Source formatting and syntax parsing were editing/static preparation only, not Ruff/Pyright or functional gate results.

**Measured A+B speedup and memory improvement: unavailable.** Existing cache routes still operate unchanged until native isolation/provenance and paired end-to-end measurements pass. The original large report representation, renderer and accepted-report caches remain performance risks; this draft does not establish that their workloads fit the local ceiling. The eight missing goldens, unproved original-commit equivalence and complete recovered-baseline/detached/review gates remain open. The accepted local-only forensic backup exception remains in effect.

## Resume from `65ff775`: backup verified, native execution still held

The user approved the reviewed `65ff7751db6042562a7f6065e9b06a84fdc938ab` upload. It was pushed without force to the existing validation branch. Review covered all five outgoing commits and 16 changed documentation/test/diagnostic paths, including intermediate file versions; no credential or confidential-payload findings were found. A new independent bare fetch verified exact tree `54ca0c83ae64a387cee14780b06561ea63bd3596`, all **526** blob contents/modes, no alternates and `git fsck --full --strict` exit 0. All other remote branch/tag refs are unchanged. This backs up the draft source, not a functional pass.

Five native observations over approximately eight seconds all reported warning pressure level 2, with 1,536,835,584–1,564,672,000 bytes estimated headroom and 4,063,630,458–4,080,407,674 bytes swap. Native cumulative Swapins increased by 427, Pageouts by 31, and Swapouts did not increase during that window. Existing swap can persist without new swap-outs, but **normal RAM pressure was not observed**. A later read still reported level 2, 1,627,684,864 bytes headroom and 4,505,731,072 bytes swap. Thus the absolute swap threshold is not the sole launch blocker. Neither pressure/headroom nor swap policy was relaxed. Read-only process inspection identified large Brave renderer footprints; the user was asked to close unused tabs/windows voluntarily. No processes were terminated.

Static review corrected two remaining test-infrastructure defects: a backup destination-constructor failure could leak the already-open SQLite source connection; resume proof joins did not independently bind the guard command hash to the actual interpreter/module/job invocation. Cleanup now covers constructor failure, schema-query connections close deterministically, and collection/batch/resume paths verify the exact invocation. Focused regressions were prepared. These corrections remain **unexecuted**, with no RED/GREEN or regression result claimed.

Additional inspection identified six single-question call sites in `test_fallback.py` that currently render all nine questions before selecting one. This is an avoidable construction candidate, not a measured saving. Full nine-question/coverage cases must remain intact. No owning fixture route or per-question test body was activated/changed; native integrity and paired measurements remain prerequisites.

**A+B fully operational: no. Actual percentage speedup: unmeasured. Measured test-memory savings: unmeasured.** Current blockers are unsafe native preflight, pending mechanical/coordinator controls, native authority/cache-isolation/provenance regressions, real collection/outcome/cleanup checks, and matching before/after fixture benchmarks. Original report representation costs, missing goldens and full recovered-baseline/final detached/review gates remain unresolved. The historical 377/23 results remain evidence only for their original trees. No production refactoring or feature work resumed.


## Risk-based A+B verification and measured activation

The user superseded blanket warning-pressure/allocated-swap refusal with workload-specific risk monitoring. Supervisor v2 observes actual paging rates, available headroom and process growth together. Small measured jobs may run at warning pressure within calibrated caps; allocated swap alone does not block. Critical/unknown pressure, low headroom, sustained dangerous paging, memory caps and monitoring failure still terminate/refuse. Heavy jobs remain sequential and normal-pressure-only under provisional 1.5/2 GB caps. No historical 9.7 GB workload ran. Detailed calibration and boundaries are in the local 8 GB remediation plan §11.

Verified local milestone `d77f8bd` was independently restored from its full bundle and all 527 tracked file bytes/modes checked. A v2 source archive corrects an initially failed Git archive-mode preparation; both preparations are retained. Its preservation record hashes 123 execution records. GitHub remains at approved fresh-fetch-verified `65ff775`; newer milestones require reviewed exact push approval. Forensic originals/encrypted backup/manifest remain preserved locally under the accepted exception.

Fresh evidence now includes the preserved missing-helper primary RED/current GREEN; 97 infrastructure controls plus eight nested subtests; six route-selection RED/GREEN controls; unchanged native bundle primary; native clone isolation/deleted-authority rejection/schema/scope/digest/reopen/reuse controls; and two independently built exact observation-clock closures. Every test was guarded. Earlier 26 small passes and 15 synthetic observations remain preserved and are not relabeled as current full-suite evidence.

Actual full collection exposed a module-name collision and passed after adding three test package markers. The captured required inventory contains 2,541 parameterized nodes plus the five existing excluded opt-in network nodes. Exact accounting, fresh replay and actual-disk-evidence resume passed a real five-node cohort and correctly left full coverage incomplete.

The same five controls took 18.720s as five isolated children versus 3.740s grouped: **14.980s / 80.0% saved**, approximately unchanged 49.6 MB RSS. The same nine obligation/uncertainty nodes passed on original and cached routes with matching native bundle digests. Cold publication, all private copies and native validation included: **40.398s → 30.072s**, saving **10.327s / 25.6%**; including separate inventory capture, **48.115s → 37.374s**, saving **22.3%**. Upstream constructions fell from two to one; cache callbacks still validate publication and both private copies. Peak RSS fell **0.9%** (137,740,288 → 136,478,720 B), while native footprint increased **4.4%** (130,188,800 → 135,972,928 B). This establishes a bounded time benefit, not a substantial memory improvement or full-suite forecast.

Only the two verified projection owners now default to reusable upstream baselines; each gets a private DB and native transactional authority reload. Other shared-fixture importers and construction/mutation/migration/concurrency owners construct independently. Protected nested-stage and pytest-phase ledgers remain separate. `NOVCHECK_PHASE8_BASELINE_MODE=original` retains a reproducible independent route. No production code, persisted contract, assertion, mandatory gate or golden changed.

A later standalone cached-profile attempt aborted on maximum collector latency, with cleanup complete; it is not a pass or a paired timing result. All earlier refused/aborted/failed attempts remain retained. Required full typing/inventory/static/fresh-detached/independent review and eight golden readiness gates remain pending. A+B has a verified selected rollout, not full recovery acceptance. C/D/E and Tasks 22–24 remain held.


The first post-activation collection recheck refused before any child because live output paging was approximately 76 MB/s with a 226 MB headroom drop over three seconds. This refusal is preserved, not counted as a test failure or pass; the supervisor was not bypassed. Static public-content review continued while execution was unsafe.


## Focused Phase 8 readiness — revised development priority

General A+B expansion is paused. The user authorizes completing Task 22 after a focused readiness gate, then Tasks 23–24 according to the approved plan. The [new assessment](2026-10-08-phase8-focused-readiness.md) supersedes earlier blanket feature holds, while preserving complete final acceptance and original/regenerated evidence distinctions.

At clean `562f63e`, 13 sequential supervised jobs passed **52 selected tests / 289.642s**. Essential native Phase 7 permission, dependency, graph-revocation and rollback checks and the transactional Phase 8 bundle primary passed. Selected plan/execution-audit/semantic/extraction contracts, legacy compatibility and two Task 22 boundary tests passed. Peak RSS **173,309,952 B**, native footprint peak **157,877,888 B**. The exact focused ledger has **69 required nodes: 52 pass, 17 pending**; the full collected inventory remains 2,541 required nodes plus five opt-in network exclusions. This is not a full gate pass or new speedup measurement.

The input-only Task 22 capacity probe was REFUSED before launch at warning pressure. A minimum native-input partition probe subsequently ABORTED on approximately 50 MB/s output paging with headroom near 1.19 GB; cleanup completed. Neither produced capacity proof. The historical 9.7 GB Task 22 primary was not rerun unchanged. Pending accepted-report/native export coverage prevents development resumption; no production refactor or feature change was made. No retries bypassed the supervisor. Raw source-bound commands, nodes, phase times and hash-bound dependencies remain protected locally.


## 9 October Task 22 partial implementation

The latest user instruction supersedes the blanket implementation hold. The [focused readiness record](2026-10-08-phase8-focused-readiness.md#9-october-task-22-cleanup-increment-and-native-capacity-evidence) records reproduced export-fixture cleanup RED/GREEN, eight focused current-source passes, exact 2,547-node collection, qualified native-input timing/peaks, and a subsequent Q1 paging abort. Native export/retry/provenance assertions are strengthened but remain pending. The 17 required native readiness nodes, full acceptance and eight goldens remain open; no production optimization or Task 23–24 work began.
