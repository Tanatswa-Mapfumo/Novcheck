# Local 8 GB verification remediation proposal

**Status: user approved test-only tranches A+B and bounded diagnostics. C/D/E production changes require separate approval. Implementation execution remains subject to native memory preflight and exact RED/GREEN gates.**

**Date:** 8 October 2026. **Source checkpoint:** `fa7feb5daad3ab340c96f04413bfe79e11abe3fe`.

**Goal:** Make the complete required recovered Novcheck verification run reliably on the existing 8 GB Mac, preserving every semantic, security, authority, provenance and acceptance check. GitHub remains existing source control/backup only. No Actions, cloud compute, external runners, paid service or additional hardware will be configured or proposed.

**Governing inputs:** current user instruction; [master specification](../../specs/master-design-spec.md) §§44,47–49,54–57; [approved Phase 8 design](../specs/2026-10-05-phase-8-full-report-compiler-design.md) §§5,10–13,18,22–27; [Phase 8 implementation plan](2026-10-05-phase-8-full-report-compiler-implementation-plan.md); [recovery plan](2026-10-08-recovery-validation-performance-plan.md); [measured investigation](../../recovery/2026-10-08-guarded-validation-results.md); AGENTS.md. This proposal changes execution strategy, not findings or acceptance criteria.

## 1. Preserved state and present safety result

- Clean `fa7feb5` and public validation branch match. The earlier independent fetch verified exact tree `8baf1bd3a0dc93604bb7fb3d60ccc7c79eb44d2b`, 513 tracked blob bytes/modes, Git integrity and unchanged other remote refs. A fresh read of remote heads confirms the same checkpoint.
- The complete local bundle SHA `dfdd4b3d7a7690cd0ad8089a168e4bafed951b6b7b3bf642a914f48bfdbc7cc6` matches its independent restore receipt. Original stable/recovery branches, forensic inputs, encrypted copy, manifest and historical test records remain preserved.
- Local-only encrypted forensic backup is an explicitly accepted exception, not a blocker or an off-device resilience claim. No confidential upload is permitted.
- Three fresh native reads reported warning pressure level 2 and 4,844,620,349 bytes swap. The smallest 16-ref/4,096-character construction probe then **REFUSED** launch: level 2, 1,568,522,240 bytes estimated headroom, 4,718,791,229 bytes swap. Zero application/profile children launched; no fresh measurement or pass is claimed.
- Earlier 26 small passes and 15 bounded projection observations retain their original source/recipe evidence. They do not qualify native full-report capacity. Eight golden artifacts remain unresolved, original `1f50323` equivalence unproved, and the recovered functional baseline remains OPEN.

## 2. Resource policy for this proposal

| Workload | Initial soft limit | Hard limit | Dispatch policy |
| --- | ---: | ---: | --- |
| Small controls/contracts and synthetic projections | 256,000,000 B | 384,000,000 B | One fresh child; existing conservative guard |
| Incremental medium probes | 512,000,000 B | 768,000,000 B | Only after the smaller recipe completes and scaling is reviewed |
| Proven larger native test or heavyweight node | 1,500,000,000 B | 2,000,000,000 B | One node per isolated subprocess; no parallel test execution |

Pass these limits explicitly to the verified supervisor; its existing generic 2.5/3 GB defaults are not permission to use larger thresholds. Both RSS and native physical footprint/lifetime peaks enforce the limit. Keep 0.1s sampling, three stable normal-pressure preflight samples, minimum 1.5 GB estimated free-plus-inactive headroom, maximum 2 GB swap and maximum 0.2s collection latency. These headroom estimates are not guaranteed allocatable RAM. Before dispatching a larger workload, review observed headroom relative to that workload's measured peak and retain headroom for macOS; passing the minimum alone does not authorize it. Tighten limits if needed. Any relaxation needs recorded capacity evidence and review.

Every child records source/file-mode identity, recipe/test IDs, locked versions, elapsed time, peak RSS/footprint, system headroom/pressure/swap series, timeout/termination cause and cleanup. Record measured peaks from the child as well as the sampled supervisor where available. Sampling can miss transient allocations; exclude known unsafe recipes even if preflight is normal. REFUSED/ABORTED/timeout results remain incomplete, never passes. No retry with a bypassed guard or inflated allowance.

Save application buffers and use a normal manual restart if warning pressure persists. The agent will not restart/quit user apps or clear swap. After restart, collect fresh safety evidence; do not assume recovery. No unbounded waiting/repeated refused launches are useful.

## 3. Highest-cost paths: evidence and hypotheses

| Priority | Inspected path | Observed amplification | Measurement still required |
| --- | --- | --- | --- |
| 1 | `reporting/fallback.py`, nested `add()` | Full block text is also normalized assertion and every basis proposition; one comparison block can have many refs. `_record_text()` embeds complete public record fields in quoted JSON. | Native block length/ref counts, byte partition and construction peak |
| 1 | `reporting/rendering.py` | Strict wrapper roundtrip, canonical JSON, parsed mapping, YAML and Markdown coexist. Parity calls the renderer again, parses both formats and dumps another report mapping. Digests serialize entire strings again. | Separate per-format/parity peak; time and allocation traces in separate runs |
| 2 | `reporting/ir.py` | Each AcceptedBlock stores claims/bases; global collections repeat them on wire. IR validation reparses, rebuilds VerifiedSections and a second complete expected IR. Artifact validation repeats serialization. | Unique live object/string counts versus serialized bytes, rebuild peak |
| 2 | `graph/report_validation.py`, `report_store.py` | Proposal roundtrip, native upstream/artifact closure, IR recomputation, complete render/parity and storage serialization can overlap. Load parses stored JSON and re-enters these checks. | Acceptance/load timeline, SQL/row sizes, retained caller/ORM/Pydantic objects |
| 3 | `runtime/tracing/hashing.py` | `model_dump`, recursive canonical mappings, full JSON string and UTF-8 bytes are created for hashing. Sorting/set semantics are part of identity. | Exact-byte streaming prototype versus original hash at bounded sizes |
| 3 | test fixture caches | `_candidate_snapshots` / `_accepted_snapshots` retain whole serialized report strings globally. Module fixture retains a ReportCase; per-test loads add native models. Other fixtures rebuild native authority repeatedly. | Cache retention after tests, setup/copy/native reload cost and isolation |
| 4 | `NonBlank` validation | Prior real-contract probe constructed separate normalized strings despite identical input string. JSON parsing creates another set. | Benefit/cost of sharing after validation; avoid changing normalization |

Previously measured 128 refs × 4,096 chars: 645,651-byte basis JSON, 524,288 repeated proposition bytes (81.2%); block/global double projection 1,291,346 bytes. These are bounded synthetic topology observations. Historical Q3 basis links were 97.7% of one expanded payload, not a fresh recovered-report partition. The lost 53.8 MB report and 9.7 GB crash cannot be attributed exactly now. No optimization/speedup has yet been measured.

## 4. Staged profiling before changes

- [ ] **P0: safety and instrumentation.** Preserve checkpoint/receipts; confirm guard refuses unsafe launch. Diagnostic-only additions need focused controls and immutable recipe/output records. SQL counters and timers must observe, never monkeypatch validation or change evidence.
- [ ] **P1: bounded scaling.** Fresh children at 16 then 32/64/128 refs and 1/4/16 KB text, one stage at a time: construction, model dump, JSON roundtrip, canonical hash, YAML. Current CLI supports only 16/128 and at most 8 KB; extension requires controlled diagnostic tests, not undocumented flags. Each step proceeds only if previous native peak and system conditions give margin. Do not jump to the historical oversized recipe.
- [ ] **P2: minimum native authority.** Run `tests/unit/reporting/test_bundle.py::test_bundle_revalidates_one_exact_authority_closure` alone, unchanged, under 256/384 MB and initial 60s timeout. Then separately profile real Phase 6/7 construction, freeze, frozen reload and bundle reload. A timeout is not a test failure; extend time only from partial stage/time evidence while retaining memory limits. No report compiler/render invocation yet.
- [ ] **P3: single fallback section.** Use the same native closure, render one question per fresh child, inspect Q1 before Q3 and then every Q1–Q9. Stream counts/byte accounting, not large report prints. Assert native findings, obligations and basis joins remain exact. Keep no complete second report merely for measuring it.
- [ ] **P4: canonical/report stages.** Only after section capacity is known: citations, IR construction, IR validation, JSON, YAML, Markdown and parity in separate guarded children. Load input from preserved test-owned artifacts, retain locators/native revalidation, and include this input preparation in process peaks. Do not manufacture accepted authority from JSON.
- [ ] **P5: real transactions.** Small native acceptance, authoritative load, export and safe generative/repair cases, each separately. Only valid committed artifacts and repository entrypoints. Measure cumulative stage peaks without summing sequential process lifetimes. Keep caller/persistence/provenance semantics intact.

Paired before/after comparisons use identical source-independent scenario recipes, hardware, locked environment, native inputs/provenance and monitoring settings. Timings without tracemalloc establish ordinary runtime; separate allocation-traced runs explain allocations. Compare stage-local Python peaks and whole-process native peaks explicitly. Refuse traced runs that do not fit. Require reproducible reductions with correctness checks; no extrapolated full-suite claim.

## 5. Prioritized changes proposed for approval

### A. Disk-based native fixture baselines and cache lifetime (first implementation tranche)

**Candidate owners:** `tests/fixtures/phase8.py`, store/bundle/slice test helpers and new `tests/unit/test_phase8_fixture_isolation.py`.

Build each genuinely committed/sealed/frozen baseline once per compatible recipe into a test-owned persistent cache; close/dispose engines and obtain a coherent SQLite backup. Cache locators and a small integrity manifest on disk rather than full accepted/proposed report strings or live models. Clone to a private writable DB for each test, using SQLite backup or a coherent closed image; never hard-link writable databases. Reopen and run native authority validation. Keep rejected/repaired execution artifacts where the scenario requires them.

Baseline provenance key: source/test recipe digests and relevant dependency/version/configuration identities; schema; exact native assessment/context/snapshot/adjudication/report locators; expected database checksum and table/closure metadata. Preserve original observations. Do not replace explicit locators with latest records. Failed or partially built baselines cannot publish into cache; changed key creates a new baseline. No cache can certify authority or be used to skip read/accept/load validation. No stale model JSON from a prior corrupted clone may leak into another test.

Required exact RED/GREEN tests: baseline unchanged after clone mutation; second clone unaffected; wrong checksum, schema, scope and recipe rejected; WAL/coherent copy and rollback/reopen; revoked/deleted authority still rejected by native load; corrupt accepted manifest cannot be rescued by cache; interrupted baseline creation never reused. Preserve existing mutation, migration, concurrency and construction tests' independent setup. Keep explicit large-input/bundling stress coverage; do not shrink all inputs to hide production cost.

**Expected gain:** setup cost changes from N native builds to one build plus N copy/native loads per compatible group. Saving formula is `(N−1) × (build time−copy time)`, minus manifest work; native load remains. Historical 27.53s build / millisecond copy leads need fresh measurements. Dropping global serialized caches reduces retained process memory, not necessarily peak of one report. Compatibility risk is fixture contamination/stale provenance; isolation controls are a prerequisite, not optional.

### B. Sequential execution and complete node accounting (same tranche, after A)

**Candidate owners:** new local diagnostic/verification runner, `scripts/verify.py` optional local-batch mode, narrowly scoped runner tests. Keep the normal verification entrypoint; no remote workflow.

Capture the exact pytest collection inventory with its full parameterized node IDs, marker policy and locked source identity under a guard. AST counts are not proof of collection. Run each heavyweight node alone in a new guarded subprocess; group only measured small tests into bounded batches. Do not use xdist or hidden child concurrency. Disk baselines prevent isolated nodes from rebuilding upstream work every time. Release engines/objects at fixture teardown and rely on subprocess termination for allocator lifetime isolation.

Use argument arrays and node-ID files, not shell interpolation. Require expected/actual inventories to match: zero missing, duplicated or unexpected required nodes; preserve the existing five opt-in network exclusions explicitly and do not add exclusions for memory. Aggregate failures, skips, refusal and timeouts separately. Any required non-pass means the complete gate is incomplete/failed. Resume completed nodes only for exactly matching full source/tests/lock/runner/recipe identity with retained receipts; mutations invalidate reuse. Final clean detached gate executes the complete required inventory afresh in persistent worktrees. Ruff/format/Pyright remain complete gates, also guarded sequentially.

Runner controls must prove child/timeout/monitor cleanup, lock exclusion, Unicode/parameterized selection, exact inventory accounting, exit-code aggregation and unchanged pytest socket/plugin policy. Optional batch mode must produce equivalent required coverage to `scripts/verify.py`; review that plan deviation explicitly before using it as final evidence.

**Expected gain:** bounded process lifetime prevents accumulation across tests and avoids unchanged post-commit suite repetition. Isolation alone can increase setup time; approve it together with disk baseline reuse, not as a claimed speedup by itself. No required assertion changes.

### C. Exact streaming hashing and format processing (second tranche, production review required)

**Candidate owners:** scoped reporting helpers first; shared hashing changes only after independent Phase 6/7 compatibility evidence; renderer, authoritative validator and export helper where reproduced.

Prototype hashing canonical encoder chunks rather than materializing a whole UTF-8 byte string, preserving exact current canonical bytes/digests. This alone still leaves `_canonical_value` and Pydantic dumps; measure it rather than calling it a complete fix. A lazy canonical traversal requires differential tests for sorted mappings, tuples, sets, Unicode/ASCII escaping, UTC/dates, enum/identifier values, floats including negative zero, nonfinite rejection and all model exclusions. Existing hashes, artifact/report identities and persisted bytes cannot change.

Stage JSON/YAML/Markdown to private temporary output files for validation/export; consume and release one representation at a time. Keep the existing public `ReportRenditions` API as a compatibility adapter where callers request all strings. Native acceptance/load may use an internal bounded validator only if it performs every current exact rendered-content and safe parse check. Do not turn parity into comparing IDs or a subset of fields. Deterministic recomputation must still reject omitted headings/table cells/limits, altered citations, unsafe YAML tags, links and injected markup. No trust in a caller-supplied render digest/certificate.

Streaming YAML must match current scalar/type/escaping behavior and preserve existing byte/digest policy; safe event-wise comparison needs an explicit design and malicious-input tests. Do not assume a different loader/dumper is drop-in or remove format checking from acceptance. If emitted bytes change, obtain a render-version/compatibility decision rather than silently relabel v1. Persisting SQLite Text still needs one complete stored string; streaming exports alone will not make the database stage bounded.

**Expected gain:** remove transient encoding copies and simultaneous duplicate format strings/maps, with unknown total until native measurement. Risks: canonical drift, YAML type/security changes, incomplete public-content parity and divergence of compatibility adapter/internal path. Exact v1 bytes and independent corruption controls are release gates.

### D. Bounded proof recomputation, sharing and revalidation (third tranche)

**Candidate owners:** `reporting/ir.py`, `artifacts.py`, `evidence/graph/report_validation.py`, `report_store.py`, `models.py` only if justified.

Compare expected blocks/sections/dependencies incrementally within the same explicit transaction instead of retaining a second complete expected IR. Preserve full field/order/duplicate/extra/missing checks, fallback recomputation, summary recomputation, rejected-call execution closure and final identity. Validate all content strictly at each authority boundary. No `model_construct`, disabled validators or globally trusted caller objects.

Use validated immutable shared in-memory data only after checking equality and scope; retain required duplicated v1 wire collections and exact identity. Frozen Pydantic models can contain mutable containers, so frozen alone is not a trust argument. Consider bounded transaction-local hash/projection reuse keyed to exact validated content, with mutation/conflict tests; never a global cache across input, acceptance, load or successor context. No caching of semantic support decisions across different text/basis/permission hashes.

String sharing is a secondary experiment: preserve whitespace normalization, schema errors and output semantics; avoid a process-global intern pool retaining arbitrary evidence forever. Reusing a raw input string does not currently prevent `NonBlank` copies. Introducing custom validators or post-validation sharing requires explicit review and adversarial revalidation tests. Keeping duplicate collections as references internally will not remove their repeated wire bytes.

**Expected gain:** fewer full expected graphs and repeated temporary dumps, without removing checks. Risks: stale transaction state, mutable-field aliasing, bypassed proposal revalidation or weakened exact-closure equality. Measure lifetime/validation counts before altering any boundary.

### E. Clause-sized fallback basis and possible normalized wire representation (separate ADR decision)

The largest structural cost is whole paragraph copied into every basis proposition. Propose one independently accountable factual clause/record unit per claim with precise per-ref supported proposition, exact public spans and all relevant limitations. Each source remains separate; descriptive synthesis never establishes a combination precedent. Mandatory local adjacency and Q9 coverage remain. Upstream prose stays safely attributed, not silently summarized into inferred fact.

This changes realized fallback claim/text/basis content and IDs. It is **not** a transparent memory-only v1 patch. Require an approved ADR and versioned fallback/identity registry/support plan, keeping v1 validation pinned to its original transformations. No historical backfill or Phase 6/7 change. Independently validate direct/partial/residual/potential/mixed/unassessable/M1, Q7 prospective needs, Q8 ceilings and Q9 actual uncertainty. Regenerated goldens must be labeled and checked against frozen semantics, never updated merely to pass.

Eliminating duplicate IR wire collections or changing `ClaimBasisLink.proposition` to a reference would additionally change public/persisted contracts. That is a contingency for separate schema/version review, not selected in this tranche. Preserve current output compatibility until a decision; a legacy workload that still cannot fit stays explicitly blocked locally rather than being executed unsafely or silently withdrawn.

**Expected gain:** for B text bytes shared across R refs, duplicated proposition content is approximately `B×R` today. Clause-specific propositions can reduce it only if exact support/meaning is preserved. Do not claim an 81% full-report or 9.7 GB reduction from the small synthetic measurement. Risks: lost qualifications, basis misbinding, changed scientific explanation and version incompatibility; independent semantic/authority controls precede rollout.

## 6. Required correctness and compatibility gates

Every tranche: exact RED → minimal implementation → GREEN → nearby variants → measured before/after → owning component/relevant upstream regressions → task commit. Assertions stay intact. Pure performance fixes must preserve complete native projections, serialized bytes and canonical IDs, except explicitly reviewed/versioned content changes in E. Keep:

- `test_supported_claim_cannot_drop_material_limitation`, hidden headings/table assertions and complete extraction dispositions;
- `test_synthesis_does_not_establish_combination` positive/negative controls;
- exact recovery audit/instruction checks, one-repair origin, no reset, composition fallback;
- `test_all_semantic_ports_unavailable_produces_full_report`, M1/Q7/Q8/Q9 and all six lens/summary parity;
- `test_canonical_dependency_transplant_fails_load`, missing/extra dependency rows, source-version/context/target rebinding and revocation;
- transactional bundle/freeze/accept/load, terminal replay, migration/rollback/reopen/FKs, execution/rejected-call closure;
- malicious markup/URL/YAML, real-citation-wrong-proposition and capability/import/network guards.

No optimization claims without paired native peaks/time. No full pass from partial batches or historical 377/23 results. Retain full recovered-baseline owning suites, eight golden artifact integrity/independent provenance, strict typing, exact clean detached local verification and one independent whole-phase review. No Task 22 feature work or Tasks 23–24 until recovery readiness prerequisites pass.

## 7. Approval and next action

**Recommended first approval:** A+B test-only infrastructure and P0–P2 diagnostic work, gated by safe macOS conditions and isolation/provenance tests. C/D production changes require their concrete differential design after stage measurements; E requires a separate ADR/version decision. This proposal does not authorize any tranche by its existence.

Today only static inspection, Git/checkpoint verification and guarded refusal ran. Once normal memory conditions return, start the unchanged minimum native bundle node sequentially. If it exceeds its provisional budget, preserve partial logs and investigate the measured stage without inflating limits to force a pass. All blocked workloads remain local remediation work; no external execution destination is proposed.


## 8. Approved A+B execution and wall-clock measurement protocol

The user explicitly approved A+B on 8 October 2026, emphasizing both memory and total verification time. Under two hours for equivalent historical coverage is aspirational; it does not authorize omissions or relaxed safety. No C/D/E production work is approved.

### Separate timing and construction-frequency ledger

Every representative recipe and complete batch ledger must record, without logging evidence prose:

| Stage | Timer boundary / accounting |
| --- | --- |
| Interpreter/import/collection | Child start to completed pytest collection; recorded separately from test setup |
| Fixture construction | Native builder enter/exit, number of native constructions and failure outcome |
| Publication/cache validation | Coherent snapshot creation, schema/recipe/locator/hash checks and mandatory native validation |
| Private database copy | SQLite backup start/finish, source/destination bytes and baseline key |
| Native validation | Frozen/bundle/artifact/report load calls separately; no validation disabled or borrowed from cache |
| Pytest setup | Full pytest setup phase; includes nested construction/copy/validation intervals, not additive to them |
| Execution | Pytest call phase, preserving every assertion and expected result |
| Teardown | Pytest teardown plus engine disposal/subprocess reap; interrupted teardown remains incomplete |
| Monitoring/orchestration | Parent guard and runner overhead; total start-to-final-receipt wall time |

Nested stage times are labeled and not summed twice. Include baseline cache creation/checksum I/O, guard/collection/startup cost, resume bookkeeping, slow regressions and failed/refused attempts in end-to-end cost reporting. Count native builds, cache hits/misses, private copies, validation calls and subprocess starts; do not infer fewer native calls from a cache-hit label.

Keep a reproducible original path (cache disabled) for the same representative nodes/recipes, locked code/environment and monitoring configuration. When this is unsafe, the existing historical 27,497.48s/377-test record, 27.53s setup lead and 0.004–0.015s copy / 3.33–3.56s reload leads are explicitly non-equivalent historical evidence, not a fresh before measurement. Record fixture identities and outcome/provenance so mismatched scenarios cannot become a before/after pair. No historical setup/execution/teardown partition is invented.

Report absolute and percentage savings for matching before/after recipes: `(before−after)` and `100×(before−after)/before`, alongside peaks and build/validation counts. End-to-end complete-suite time is measured only for the complete required inventory. A forecast from per-node timings must label collection/startup/shared construction/teardown/copy costs, measured versus unknown nodes and uncertainty; no complete expected-suite duration from a small selection. Compare cache creation plus all reuse costs against repeated construction before retaining an optimization. If an isolated test is slower, keep isolation for required safety but record its cost; do not advertise it as a speedup. Roll back optional changes with no demonstrated net benefit without weakening checks.

Historical-to-aspirational arithmetic only: 27,497.48 seconds down to 7,200 seconds would require 20,297.48 seconds (73.8%) less elapsed time. This is a target gap, not a prediction or measured saving. A+B may leave intrinsic single-report costs dominant; their measured remainder informs a separate C/D/E approval.

### Incremental execution gates

1. Preserve `18eb3ec` and its complete bundle; GitHub `fa7feb5` remains the verified source backup. The newer checkpoint is local until expressly approved for push. Originals/forensic receipts unchanged.
2. Prepared first mechanical cache and accounting regressions in `test_recovery_sqlite_baselines.py` and `test_recovery_sequential_accounting.py`. Toy SQLite controls are expressly not native authority evidence. Helpers remain unimplemented until an exact safe RED is observed. Existing fixture routes and `scripts/verify.py` remain unchanged.
3. The exact primary cache-control RED launch was **REFUSED**, warning pressure level 2, before any pytest child. This is neither RED nor GREEN. Static parsing is not a test result. Native/global performance claims remain pending.
4. When the guard permits execution, observe primary RED; implement the test-only cache mechanics minimally, GREEN/variants, then add native isolation/provenance/schema/revocation/reload controls and measured original/cached scenarios. Route only proven beneficial compatible report fixtures, preserving construction/migration/concurrency owners' independent setup.
5. Capture inventory and source/environment/policy identity; implement accounting, immutable receipts and timings before invoking batches. Group measured lightweight cohorts whose aggregate peak fits the small limits; unmeasured nodes stay individually guarded. Unknown resource demand is not lightweight based on directory/name.
6. Add independent resume tests for source/config/mode/new-file changes, missing/altered receipt/report bytes, wrong environment/plugins/socket policy, duplicates, skips, collection failure, child timeout/refusal and incomplete teardown. A fabricated complete flag or zero exit does not suffice. Runner checkpoint and outcome hashes must resolve to actual complete guard/pytest records.
7. Only after focused controls and representative capacity/cost proof, use safe local batches for complete recovered-baseline verification. Final fresh detached inventory still runs afresh. Complete coverage requires the same required nodes, explicit network exclusions, full static gates, no required skips/refusals/failed nodes and exact artifact/golden readiness.

Actual A+B speedup, peak improvement and complete-suite forecast are **not yet available**. All existing assertions/tests, production modules, contracts and dependencies remain unchanged during this preparation checkpoint.
