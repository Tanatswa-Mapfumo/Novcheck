# Recovery validation investigation — 8 October 2026

**Status: source integrity audited; functional validation and performance remediation OPEN. Task 22 feature development and Tasks 23–24 remain on hold.**

Work occurs only in the persistent recovery worktree, on `recovery/validation-performance-20261008`. Local and public `recovery/d058976` remain the immutable checkpoint. Stable branches and forensic evidence are preserved. No production files, assertions, dependencies or report semantics were changed in this investigation.

## Fresh integrity measurement

The standard-library-only `scripts/recovery/audit_baseline.py` read the existing 518-path manifest and hashed the recovered files. It imported no application code and launched no tests. Python 3.12.13 ran with isolated/no-site/no-bytecode flags.

- Checkpoint: `d0589769407061b6bf00b8f7f4fadb3c966ac1dc`.
- Manifest SHA-256: `b985a4d3c88407c712307429392a1f9cdad54f6ca5c3e48517ca6986b1bff0ae`.
- **Zero file/hash mismatches; 402 Python source/test files parsed, zero syntax errors.**
- Audit body: **2.5083s**; `/usr/bin/time -l`: **2.75s wall**, **37,044,224 bytes peak RSS**, **26,313,920 bytes peak physical footprint**, zero swaps reported for this process.
- After final audit-script formatting: **3.39s wall**, **37,339,136 bytes peak RSS**, **26,608,832 bytes peak physical footprint**, again 0 mismatches and 0 syntax errors. This variation is not an optimization result.
- These measurements describe the small read-only audit, not pytest, Pydantic report validation or production compilation.

The complete output and invocation log are preserved under the ignored `.superpowers/recovery-validation/20261008/` directory in this worktree. The confidential original report and full manifest remain separately preserved in the forensic directory.

| Manifest classification | Files | Limit |
| --- | ---: | --- |
| Exact surviving baseline | 375 | Full Phase 6 blob match |
| Exact recorded final Phase 7 review files | 2 | Full recorded SHA-256 match |
| Complete recorded dependency-file diff | 2 | Abbreviated recorded blob witnesses; full final original hash missing |
| Complete recorded Markdown projection golden | 1 | No independent final hash; public-format projection, not full report |
| Reconstructed with final-tree uncertainty | 125 | Recorded reconstruction; original tested-tree equivalence unproved |
| Missing/partial goldens | 8 | No complete final content found |
| Tasks 23/24 not yet implemented | 5 | Future work, not crash loss |

Phase 7 and Phase 8 Tasks 1–21 plus seven Task 22 changed paths are reconstructed source. A clean hash audit proves preservation of that reconstruction, not semantic correctness or equality to lost `1f50323`. Original 377-test/27,497.48s and 23-test/110.59s records remain historical evidence for their original tree only. The formerly missing three tree closures are recovered exactly; their missing original commit identities remain an acceptance provenance limitation.

## Confidential off-device backup

The two principal forensic directories occupy approximately **341 MiB** on disk in total, measured by `du -sk`; logical archive size may differ. All originals remain read only. No sensitive records have been published, encrypted or transmitted in this stage. A complete streamed inventory now covers **15272 regular files**, **310769433 logical bytes**, directories and symlinks. Its private member/hash manifest is ignored by Git; encryption, transfer and restore verification remain pending.

Only the internal startup volume is currently mounted under `/Volumes`. No external encrypted drive is available. A private destination and key custody are required; the user has been asked for them. `hdiutil` is available, but `age`/GPG and the normal `uv` executable are absent from the current PATH.

Preferred options are an existing encrypted external volume, or an encrypted container/file sent to a private destination. Apple's supported encrypted disk-image workflow is available: [Disk Utility encrypted images](https://support.apple.com/en-gb/guide/disk-utility/-dskutl11888/mac). If a cloud destination is chosen, encryption must happen before upload. No password/private key belongs in chat, shell arguments, tracked files or execution logs. The decryption secret must be recoverable independently of this Mac.

Completion requires a complete member/hash manifest, encrypted destination bytes verified, independent decrypt/restore and exact file/mode/hash checks, recovered tree closure/fsck checks, and a receipt. An encrypted file left on this Mac is not an off-device backup. Do not erase/reformat a drive or retire originals to achieve this step. Do not publish even the confidential backup payload to the public GitHub repository.

## Eight missing goldens

Still unavailable:

- `tests/golden/phase8/{direct,partial_negative,potential,mixed,unassessable,m1}.json`.
- `tests/golden/phase8/rendering-public.json` and `rendering-public.yaml`.

The previous bounded investigation examined **1,917 surviving blobs including unreachable objects**, six archive inventories and structured-record locations; it found no complete missing artifact. The rendering JSON has a 7,423-byte partial prefix, whose SHA-256 is `ed8d88605964cd61ed6154a69909ac53889d8df2db941ab2be3762d7e690fe6f`. That prefix and generator records cannot establish the missing tail. The current source GitHub checkpoint also omits all eight files. No new historical source has been identified; no replacement was generated.

If no additional historical archive is supplied, regeneration is necessary. It will be labeled **REGENERATED**, with source SHA, scenario recipe, exact native authority locators/digests, normalization rules, renderer version and output hashes. Preserve the old partial prefix separately and compare any matching portion, without treating that as full historical equality.

Expected semantics must be checked independently against the approved specification and real frozen upstream records: all nine questions/targets; direct versus strong partial and complete residual; scoped potential; mixed/unassessable distinctions; M1 attributed advantage and missing assessed value; target-specific Q8 ceilings; local limitations plus Q9; exact source/version/passage ancestry; prospective Q7; and JSON/YAML parity. Existing rejection and perturbation controls remain. Copying the current renderer output into a golden and observing equality is insufficient independent verification. Generation remains gated by backup, safety and fresh native validation.

## Bottlenecks: evidence and proposed scope

| Evidence | Observed cost | Interpretation |
| --- | --- | --- |
| Historical Task 21 regression | 377 tests, 27,497.48s | Repeating an unchanged tree is expensive; recovered tree still needs fresh verification |
| Historical instrumented upstream factory | 38.58s, 111 million calls | Repeated construction/validation/serialization dominates setup; profiler overhead included |
| Historical SQLite copy then native reload | 0.004–0.015s copy; 3.33–3.56s reload | Immutable native baseline/private-copy reuse is promising; authority reload stays mandatory |
| Historical primary native setup | 27.53s; three targets/comparisons | Small target count still carries large history/limitations |
| Historical accepted report | 53,815,435 bytes; DB about 79 MB | Original DB lost; a new byte partition/profile is still required |
| Historical expanded Q3 | 329,229,489 bytes; basis links 321,715,598 bytes | Basis propositions occupy **97.7%** of the artifact; repeated paragraph payload is a measured amplification |
| Historical primary Task 22 footprint | About 9.7 GB | Unsafe on 8 GB Mac; RSS under swapping was not a safe peak measurement |

Static data flow confirms these hotspots:

1. `reporting/fallback.py` assigns whole public paragraph text to the block, normalized claim and every `ClaimBasisLink.proposition`. Recorded native limitations included 222,632 characters and 87 refs; the expanded case repeated roughly 698 KB paragraphs across 114–119 refs. Real production fallback follows this code, so this is more than fixture overhead.
2. `reporting/ir.py` embeds claims/bases in each accepted block and also in global material claim/basis collections. Full JSON and Pydantic round trips repeat the resulting representation.
3. `reporting/rendering.py` revalidates a serialized report, constructs JSON plus parsed payload plus YAML plus Markdown, and `validate_rendition_parity` renders again and parses both formats. Correctness boundaries must be retained; cost cannot be called redundant solely because it is repeated.
4. Artifact identity/semantic projections and authoritative acceptance/load perform further dumps/revalidation/hashes. `report_validation.py` is an authority boundary, not an optional test shortcut.
5. `tests/unit/reporting/test_bundle.py::frozen_case` rebuilds a native frozen fixture for every test. Report store/slice tests already contain module baselines/private copies, but `_accepted_snapshots` also retains large serialized report strings and has no separately verified general isolation/cache-invalidation contract.
6. Full research/history prose becomes uncertainty and attached limitations, increasing valid payload size; removing those facts would violate reporting completeness.

The AST inventory found, in reporting production modules alone, 83 `model_dump`, 21 `model_validate`, seven JSON-validation, seven JSON-dump and 72 hash call sites. These are **static sites**, not invocation counts or proof that any check is unnecessary. Thirteen `deepcopy` sites exist across source/tests; no allocation share is attributed to them without runtime evidence.

There is **no measured after-fix improvement**. The optimization plan first profiles fixture setup separately from native production report stages, then tests one change at a time. Representation changes affecting public text, canonical IDs or persisted v1 contracts require a version/support decision and ADR; do not silently reinterpret old records.

## Current resource and validation gates

macOS reports **memory pressure level 2**, 8,589,934,592 bytes physical RAM and **4,058.81 MB swap used** at stage entry. Pytest/Pyright and native report profiling were not launched. No known 9.7 GB workload will run on this machine to reproduce a crash.

The existing diagnostic watchdog has verified only launch refusal, not successful process-tree stop behavior. It needs an exclusive process lock, controlled low-allocation failure/cleanup tests, streamed measurements and OS headroom safeguards before heavy use. Target roughly 2 GB, preempt near 2.5 GB, hard process-tree RSS/physical footprint threshold 3,000,000,000 bytes; sample oversight cannot guarantee prevention of transient overshoot.

Required progression is recorded in the [validation plan](../superpowers/plans/2026-10-08-recovery-validation-performance-plan.md). Unsafe comprehensive gates move to higher-memory hardware with approval, never to fewer assertions. No substantial performance refactoring or heavyweight execution is approved by this investigation report.
