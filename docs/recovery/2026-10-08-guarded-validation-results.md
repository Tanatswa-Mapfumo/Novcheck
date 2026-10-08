# Guarded recovery validation — 8 October 2026

**Status: resource supervisor and small checks verified; recovered functional baseline OPEN. Task 22 feature work and Tasks 23–24 remain held.**

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
3. Profile one minimum native upstream fixture and frozen/bundle reload in isolation under the proven conservative guard, then review capacity before ReportIR/compile/render/accept/load cases. Known 9.7 GB and comprehensive cases require suitable higher-memory hardware unless measured remediation establishes safe capacity.
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
