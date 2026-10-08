# Phase 7 final independent acceptance re-review of the corrected implementation

**Decision: FAIL.** This is the explicitly authorized final independent re-review of the corrected implementation, not a rewrite of the original FAIL report. Two Important Phase 7 defects remain. Passing tests do not confer semantic acceptance.

Reviewed exact HEAD **`ef601119eb4962152ebe3eaa844f60076df77550`** in `/private/tmp/novcheck-phase7.WORKTREE`; correction commit `54fb701454c0c2e5298837349d29045da7debd54`; frozen accepted Phase 6 baseline `e4dd4e09699f755dd0fe7b7bc3dd8be4e11f7ee1`. Initial `git rev-parse HEAD` matched and `git status --short` was empty. The reviewer had no implementer history, spawned no agents, made no implementation/test edits or commits, and owns only this document. Scratch scripts, databases, and logs are under `/private/tmp`. Internet sockets were disabled; Unix sockets used by asyncio were allowed. No live provider was called.

Read AGENTS.md, the master specification (especially INV-01–15, §§9–12, 29–37 and Phase 7 exit criteria), the approved Phase 7 design and implementation plan, completion handoff, ADR-037, and the **complete original** `docs/reviews/phase-7-independent-acceptance.md`. The approved contracts govern this review. Phase 6 is not reopened; Phases 8–10 are not implemented or required here.

## Original Important finding closure

Each original failure was inspected against its original locations and corrected call chain. Owning regressions were included in the fresh focused run. Independent nearby probes below are separate from the exactly ten fresh attacks in the next section.

| Original finding | Correction and regression evidence | Independent nearby variant and actual result | Disposition |
| --- | --- | --- | --- |
| I1 — neutral judging skipped on agreement | `neutral_review_issues` creates a neutral scope-review issue for comparable agreement; orchestration and freeze/load independently rederive it. ADR-037 conservatively treats the unbounded issue as HIGH_IMPACT. `test_clear_direct_reduced_path_skips_unneeded_steps`, `test_agreed_substantive_partial_still_receives_neutral_adjudication`, and omission rejection tests exercise this. | A real undisputed direct run froze/reloaded the scoped negative with **two actual committed judge runs**, rather than zero. The agreed-partial regression retains potential; unsupported targets remain explicit. C-I1's artifact count is not a call count: the authoritative judge-run count is two. | **CLOSED** |
| I2 — omitted independent residual authorizes false negative | `validate_counterfactual` now requires equality with the complete Phase 6 residual set minus the removed element; Gate D cannot accept an unresolved remainder. `test_counterfactual_cannot_omit_independent_remaining_difference` and `test_real_freeze_rejects_omitted_independent_residual` cover the original fault. | The nearby real committed fixture adds an independent causal feedback interlock alongside logging, and omission is rejected. Fresh A06 additionally **inverts which residual is removed**, retaining the same single-source STRONG_PARTIAL authority: removal of the alleged small causal interlock cannot erase logging. | **CLOSED** |
| I3 — dangling IDs and no typed need route | Roles, rebuttals, and judges now carry exact typed companions; `validate_proposed_needs`, the coordinator, and freeze/load join them to immutable needs/gaps/dispositions. `test_role_rejects_dangling_need_references`, semantic input/research stage tests, and changed-state tests cover the original route. | C-I3 fabricated IDs without typed companions fail with `Need/gap references must exactly match typed proposed content`. An input need appearing **only in B,A** is retained and abstains (A05). However A01 can disguise missing user meaning as D research, and the C-I3 version companion probe admits obsolete role prompts and mislabels their trace. | **SUPERSEDED BY MORE GENERAL DEFECTS F1/F2**. The literal dangling-ID hole is closed; the complete semantic/authority boundary is not. |
| I4 — all LIMITED input unassessable | Policy separates meaningful bounded comparison from ASSESSABLE strong-positive eligibility; missing fields or unstable decomposition still deny comparison. `test_limited_complete_target_permits_scoped_negative` and `test_limited_unstable_claim_meaning_cannot_permit_negative` cover both sides. | C-I4 reseals the actual snapshot with EXPLORATORY sufficiency and runs the real application: complete `mcu_control` freezes/reloads a negative; missing `mcu_status` and combination remain UNASSESSABLE. LIMITED cannot enter the strong-positive branch. | **CLOSED** |
| I5 — escalation spends the full original budget again | `remaining_research_allowance` intersects sealed/configured caps and subtracts maximum prior usage in every dimension. Dispatch persists its reserved allowance; the reviewed adapter supplies it to Phase 4, then outcome validation checks cost. The actual Phase 4 near-cap regression and all-dimension allowance tests cover the original fault. | A09/C-I5 execute **two actual zero-source dispatches** across successors with stale configured usage zero and tighter caps in all seven dimensions. Allowances are 2 then 1, prior usage is cumulative; both runs supersede/restart with fresh roles. The third request is BUDGET_STOP with no third port call. | **CLOSED** |

C-I1/I3/I4 and the residual nearby setup are in `/private/tmp/phase7-final-review-attacks.json`. Authoritative I4, active-context variants, complete cumulative dispatch, and the independent Phase 6 AST comparison are in `/private/tmp/phase7-final-review-nearby.json`. The additional I3 correction-version probe is in `/private/tmp/phase7-final-review-version-nearby.json`. These closure variants are **not** extra numbered fresh attacks.

## Exactly ten fresh semantic and authority attacks

A01–A10 are the ten counted attacks. Their subvariants strengthen the same attack; they do not create additional counted attacks. They span routing, evidence/read authority, context identity, missing information, residuals, judge reconciliation, projection, cumulative budgets/restarts, and rebuttal bounds. A01, A05, A08 and A09 cross subsystem boundaries. A02 and A03 each perturb one authority dependency after an accepted happy path. A05 attempts stronger permission despite newly missing input; A06 attempts an incorrect negative over incomplete residuals; A07 attempts manufactured judge consensus. None is merely a fixture rename. Existing-test execution and original-finding closure probes are separately identified above.

| Attack | Setup and attempted violation | Actual result | Governing contract |
| --- | --- | --- | --- |
| **A01** | Real first-pass prosecutor returns a typed D/ACCESS request with a valid existing version string but explicitly asks external research to infer missing **user control meaning**. No typed control clarification accompanies it. | **Violation F1:** one actual research dispatch; the same-context true-noop response is retained, then `mcu_control = NOT_NOVEL_AT_CLAIMED_LEVEL` freezes and authoritatively reloads. The frozen input needs concern other targets, not this missing control meaning. | Design §§12, 19, 22, 38; plan Tasks 4/8/12; INV-05; Gate A never repaired by research. |
| **A02** | Accept and authoritatively reload a real direct negative, copy its scratch DB, change only decisive SOURCE_VERSION graph-node `attributes.content_hash`; retain the otherwise valid frozen JSON. | Fail closed: `Phase7AuthorityError`, candidate version descriptor differs from stored authority. No plausible downgraded verdict returned. | Sole Phase 6 authority; design §§2, 32; exact content ancestry. |
| **A03** | Accept a real frozen result, separately seal a valid same-snapshot successor with changed provider/NO_NEW_YIELD state, and replace only the old context document with that valid successor document. | Fail closed on inconsistent persisted context/manifest identity. Valid-looking replacement data does not authorize the old frozen export. | Design §§8, 14, 32; exact sealed world. |
| **A04** | Bind a new repository-sealed same-snapshot provider/stop context. Reuse old prosecutor, defender, rebuttal, judge, Gate A and frozen artifacts; repeat GateFinding/frozen reuse after complete successor first passes and transition to JUDGING. | All rejected. Active-run GateFinding rejects artifact/run/content identity; active frozen proposal rejects foreign run/context/snapshot scope. Thus state prechecks are not the only protection. | Design §§14, 32–33; old artifacts cannot cross worlds. |
| **A05** | Both judge orders have identical C/D/basis; only **B,A** supplies a typed enabling-condition input need. Attempt to treat it as harmless order variation and retain the direct negative. | Real freeze/load yields **UNASSESSABLE** and retains the need. Collecting both actual outputs preserves the missing-information ceiling despite normalized C/D agreement. | INV-05/12; design §§15, 17, 19, 30. |
| **A06** | One actually committed STRONG_PARTIAL source has logging and a separate causal feedback interlock. Reverse the original omission attack: remove the **causal interlock** as alleged small implementation noise and omit logging from remaining differences. | Rejected before negative freeze: `Counterfactual must completely account for remaining Phase 6 differences`. The Phase 6 class remains STRONG_PARTIAL. The first text-varied setup is the I2 nearby probe; this inverted removal is the counted attack. | INV-03/12; design §§21–23, 29; complete residual accounting. |
| **A07** | Primary positive/negative reversed pair plus one positive alternate attempts **2-of-3** stronger permission. Also invoke an unstable alternate beside a stable positive primary to obtain **3-of-4** positive outputs. | A lone alternate is rejected because a full comparison pair is required. The second case remains unresolved with UNASSESSABLE ceiling despite three positive outputs. | Design §§16–18; Task 16 six reconciliation rules; no voting/preferred provider authority. |
| **A08** | Add typed control-direction clarification and a decisive case-level limitation that is omitted from both A/B projections. The scripted judge still proposes the same direct negative. | The display omits that limitation, but real freeze yields **UNASSESSABLE**, retains the exact typed need and frozen limitation. Projection omission cannot grant stronger permission on this path. | Design §§8, 15, 19, 31–32; material meaning retained by authority closure. |
| **A09** | All seven dimensions start consumed; configured caps are tighter than sealed caps and configured usage is stale zero. Two actual zero-source actions consume one in each dimension and change queries/provider/NO_NEW_YIELD state; request a third. | Actual dispatch allowances **2 → 1** across fresh successor contexts; cumulative prior usage is visible, both old attempts supersede, fresh both-role passes occur, third request BUDGET_STOP without a third dispatch. Direct Gate C authority survives the research limitation. | INV-01/06/11; design §§13–14, 20; cumulative resources and restart. |
| **A10** | After a valid paired rebuttal, submit different-content additional artifacts for **both** roles, then memory-source and foreign-context variants. | Second prosecutor and defender artifacts rejected by run-wide role cap. New source and successor-context rebuttal variants rejected. No third debate or reply-to-reply authority. | Design §§11, 14, 36; bounded debate and packet citations. |

Scratch authority artifacts: A01 DB `/private/tmp/p7-final-A01-o_60q4cm/asm_research/phase5/evidence_graph.sqlite3`; accepted baseline DB `/private/tmp/p7-final-base-okwcgkwh/asm_research/phase5/evidence_graph.sqlite3`; A02 copy `/private/tmp/p7-final-A02-v6s6u07p/db.sqlite`; A03 copy `/private/tmp/p7-final-A03-0zaqcv9l/db.sqlite`; A06 committed partial DB under `/private/tmp/p7-final-A06-696k8jgj`. Exact setup/results are retained in the scratch JSON/logs, not repository fixtures.

## Findings

### Critical

None assigned.

### Important F1 — typed Gate D gaps can still research missing user meaning

**Locations:** `src/novelty_harness/adjudication/needs.py:98`–119 and 226–234; `src/novelty_harness/application/phase7_research.py:302`–345; coordinator first-pass and post-judging dispatch paths.

The boundary validates scope and comparison/argument membership, and checks a D request has one of ACCESS/CHRONOLOGY/CONTRADICTORY_EVIDENCE plus a nonempty `missing_prior_art_reference`. It never establishes that the named reference represents a genuinely missing external fact affecting contribution significance. Allowed enums and a nonempty string are sufficient to authorize dispatch.

A01 supplied these actual typed fields:

```text
material_gate = "D"
gap_type = "ACCESS"
missing_prior_art_reference = "srcv_6c7784ab6427698e26d002ae8787b447bdd2412edf9ee977ba650b54fdabc852"
reason = "The user's mechanism is not specified; the proposal does not tell us which control condition it means"
research_hypothesis = "Search historical implementations to determine what the user intended by control"
stop_condition = "Recover the missing user mechanism from external sources"
```

The version is already present in the loaded packet; it is not evidence that the user's omitted meaning is an external prior-art access problem. The request had no linked comparison/argument and no control `InputClarificationNeed`. A real research port was called **once**. Its deterministic true-noop response introduced no evidence. The real coordinator nevertheless froze the control negative, and authoritative load returned it. Schema validity, successful repository replay, and a prompt saying never research user meaning do not enforce this routing invariant.

This is an Important existing Phase 7 defect, not a request for live-model calibration or a new architecture. The approved hybrid materiality boundary must distinguish a missing external prior-art fact from missing target meaning before it grants research permission. The existing disguised-input regression uses the **invalid** enum INPUT_SPECIFICATION; rejecting that enum does not reject A01's schema-valid disguise.

**Smallest remediation:** validate a D request's external-fact basis against the sealed packet/context before dispatch and on authoritative freeze/load; reject a request whose purpose is to supply user meaning, and require typed clarification/abstention for that issue. Do not treat an arbitrary version string as proof of a missing external fact. Add the schema-valid D/ACCESS regression at the real dispatch/freeze boundary and nearby chronology/contradiction variants. Preserve existing Phase 6 labels and authority. No fix was implemented in this review.

Evidence: `/private/tmp/phase7-final-review-A01.json`, `/private/tmp/phase7-final-review-probes.py`, `/private/tmp/phase7-final-review-probes.log`.

### Important F2 — stale role prompt versions acquire frozen authority and audit reports the wrong version

**Locations:** `src/novelty_harness/adjudication/roles.py` proposal `prompt_version` fields and validators; `src/novelty_harness/evidence/graph/phase7_store.py` role revalidation on write/freeze/load; `src/novelty_harness/application/phase7.py:664`–681 prompt-version trace mapping.

The I3 correction-version nearby probe returns current v2 proposal shapes with explicitly stale `p7-prosecutor-v1` / `p7-defender-v1` prompt versions. Both cases are accepted for every target. The real coordinator freezes/reloads `mcu_control = NOT_NOVEL_AT_CLAIMED_LEVEL`. Retained role artifacts honestly contain v1, but `publish_frozen_phase7_trace` reports v2 from current constants rather than the committed cases.

This violates the required stale-prompt fail-closed authority check, canonical method/prompt provenance, and ADR-037's correction-version boundary. Valid schema/citation joins cannot establish that the approved role protocol was used. The discrepancy is observable through real repository authority and trace publication, not a theoretical vendor risk.

**Smallest remediation:** reject unsupported role prompt versions in shared proposal validation repeated at write/freeze/load; keep current-contract validation consistent with registered prompt versions. Trace committed prompt provenance rather than substituting current constants. Add a v2-shaped/stale-v1-prompt regression through real freeze/load and verify retained versus published prompt versions. No Phase 6 or later-phase change is needed. No fix was implemented in this review.

Evidence: `/private/tmp/phase7-final-review-version-nearby.py`, matching `.log` and `.json`; frozen locator `p7frozen_2aa3481a2958bc4897f284b979241745c2afac3f004e6771641b13b69bcd7c69` in the accepted baseline scratch DB.

### Minor M1 — value/significance arrays remain empty; authoritative information survives

Regraded from actual effect, without inheriting the original severity. A real frozen result has empty `value_findings` and `novelty_significance`. Its sealed CIR still retains the advantage **“Reduce operator checks” / CLAIMED**, and every target retains a Gate D reference with its exact committed finding and counterfactual dependency where applicable. The repository can reconstruct significance and the original value claim without rerunning adjudication. No value field enters Gate C/D or verdict permission, and no authoritative maturity or significance information was destroyed.

This is **Minor** output completeness under approved design §§27/31, not an acceptance blocker or a demand for Phase 8 prose. The minimal future correction is to populate the separate arrays from already validated Gate D and sealed value facts with explicit scope. Do not invent evidence maturity or re-decide significance. Evidence: `M1_effect` in `/private/tmp/phase7-final-review-nearby.json`.

## Required semantic and authority coverage

This table combines fresh probes, owning-suite evidence and inspected implementations; named tests alone were not used to establish acceptance.

| Required area | Disposition and evidence |
| --- | --- |
| 1. Sole Phase 6 authority; frozen baseline | **Intact.** Packet is a complete view projection; repository reloads it transactionally. Source/support/chronology/classification/graph semantics were not rewritten. Independent AST comparison finds **41 identical** loader validation statements against accepted Phase 6. A02 verifies an actual dependency loss. Pure caller-shaped packets confer no repository authority. |
| 2. Immutable world; old artifacts and replacement context | **Intact.** Scope/content checks at application and repository; A03/A04 include prosecutor, defender, rebuttal, judge, GateFinding, frozen dependency and active successor state. Snapshot/assessment equality also enforced. |
| 3. Changed zero-source state; strict no-op | **Intact.** Complete manifest/view digest equality plus zero-cost/no-attempt checks govern resume. Query/provider/access/coverage/stop/budget changes seal successors and supersede. A09 and focused restart/access/no-op integration cases exercise this; zero-yield is not sufficiency or universal absence. |
| 4. Gate A versus B/C/evidence-dependent D | **FAIL F1.** Deterministic missing mechanism/direction/topology/decomposition and explicit typed input needs abstain without research, including A05/A08. Schema-valid disguised missing meaning still dispatches as D. |
| 5. Independent first passes and retry | **Intact.** Separate concurrent role calls receive the identical immutable authoritative packet, with no other response. Adapter recovery retains the same packet and does not insert earlier role output. Inspected actual context blocks and focused isolation/retry tests. |
| 6. One rebuttal per role; no third debate | **Intact.** Repository caps the role across the entire run; selected first-pass links and exact evidence enforced. A10 rejects both additional roles, new source and foreign context. Typed needs/gaps exist at rebuttal stage. |
| 7. Complete nearest-source residuals | **Intact after I2 fix.** Full packet retains support/scoped remainders, relationship/control-flow/configuration/context/chronology/contradictions. Counterfactual requires all classification residuals, and Gate D cannot accept remaining unresolved differences. A06 is a real single-source causal residual omission attempt; partial class is unchanged. |
| 8. Neutral packet/projection; omission ceiling | **Authority ceiling intact for tested omission.** Full authoritative packet and neutral A/B projections, including bounded rebuttal semantics, reach judging; role/provider provenance is not a verdict. Case-level typed needs/limitations are not all in A/B display, but A08 proves their exact retained authority prevents stronger freeze. Residual role cues are recorded, not claimed absent. |
| 9. Complete two candidates or unbounded marker | **Intact.** Repository rederives current disputes from committed positions/rebuttals. Exactly two distinct bounded candidates or no pair; changed/caller-trimmed/duplicate/foreign candidates reject. Unbounded/missing baseline conservatively HIGH. No classifier-created prior-art evidence. |
| 10. Deterministic HIGH consequence check | **Intact.** C/D changes, target permission/assessability/language and negative/potential permission are checked before judging; unbounded/unsafe defaults HIGH. Cost, confidence and source counts are absent from this authority decision. |
| 11. Mandatory identical reversed primary pair | **Intact.** Run IDs bind exact packet, arguments, evidence, rubric/config and order; both actual findings are retained and recomputed at freeze/load. Missing second run blocks authority. Agreement scope reviews also use both orders. |
| 12. Alternate pairs and non-voting reconciliation | **Intact.** Pair validation, pre-registered primary/alternate identity and all six reconciliation rules inspected and exercised. A07's 2/3 and 3/4 stronger attempts fail; stable conflict, invoked alternate instability and fabricated citation cannot create consensus. Stable alternate may resolve unstable primary only with retained limitation. |
| 13. Per-target A levels and LIMITED policy | **Intact after I4 fix.** Phase 2 INSUFFICIENT cannot upgrade. Meaningful complete LIMITED gets bounded permission; missing fields/unstable meaning abstain. Real C-I4 freeze/load preserves every target. Strong branch still requires ASSESSABLE. |
| 14. Cumulative B budget/stopping | **Intact after I5 fix.** A09 actual sequential actions cover all seven implemented resource dimensions and remaining allowance with tighter cap/stale configuration. Request history remains cumulative; budget/access/no-yield remain limitations and do not erase verified direct evidence. Actual reviewed Phase 4 near-cap test is in focused suite. |
| 15. Single-source Gate C; relationships versus terms | **Intact.** Gate C requires eligible supported exact source/version chronology, target and authorized graph membership; no stitching or semantic-only graph upgrade. Existing accepted Phase 6 relationship/terminology behavior remains unchanged; A02 plus focused graph/chronology/source-joining cases verify downstream boundary. Wording does not authorize or defeat equivalence. |
| 16. Gate D significance, not value | **Intact for validly routed semantic proposals; F1 affects gap routing.** Exact packet/bound judge counterfactual; absent/unresolved proposals cannot synthesize significance. Terminology/parameter/provider/model/cosmetic-order versus mechanism/control-flow/constraint/topology cases are in owning suite; A06 checks apparently small causal residual omission. |
| 17. Deterministic permission; qualifications; abstention | **Intact except F1's lost clarification ceiling.** Models cannot grant verdicts; scoped direct/partial negatives and meaningful potentials are intersections. Production future qualification issuers remain absent and caller/fixture qualification cannot freeze strong positive. UNASSESSABLE freezes semantic reasons; operational failures remain FAILED. |
| 18. Value separation and M1 | **Intact novelty authority; Minor completeness.** Value excluded from C/D and policy; high-value direct and weak-value substantive fixtures retain their independent novelty states. Actual M1 reconstruction evidence above retains sealed value maturity and Gate D authority. |
| 19. MCU/combination composition | **Intact.** Exact target universe, mixed negative MCU/potential combination and unassessable targets persist; no vote/mean/source count. Whole negative requires modeled whole-configuration target and its one-source support. Focused composer/policy/full-slice cases and real C-I4 preserve target distinctions. |
| 20. Adversarial freeze/load dependencies and versions | **FAIL F2 for stale role prompts.** Canonical content/exact dependency sets, context/relation/qualification/pair/gate/policy/supersession checks otherwise fail closed; A02/A03/A04 exercise accepted-path perturbations. Caller export cannot restore lost authority. Role prompt versions are currently unchecked and trace overwrites their provenance. |
| 21. v7→v8 migration, replay, transactions and joins | **Intact.** Empty additive tables, no historical fixture backfill, unchanged Phase 6 rows, strict context/run/artifact joins, idempotence/reopen/exact replay and rollback inspected and exercised in fresh focused store suite. FKs supplement semantic checks; they do not replace them. |
| 22. Phase 8 boundary | **Intact.** `summarize_frozen_phase7` accepts a locator, authoritatively reloads, and displays only frozen target verdicts. It performs no research/adjudication or language strengthening; fixture authority is distinct. Full narrative remains deferred. |

## Actual verification and limitations

The commands below ran at exact HEAD. All scratch scripts set `pytest_socket.disable_socket(allow_unix_socket=True)` before fixtures. No repository tests were added or changed by this review.

Reviewer focused command (log `/private/tmp/phase7-final-review-focused.log`):

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-sync pytest -p no:cacheprovider --basetemp=/private/tmp/p7-final-review-focus tests/unit/adjudication tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py tests/integration/test_phase7_slice.py tests/unit/test_phase7_architecture_guards.py -x -q
```

**Result: exit 0; 262 passed in 2021.11s (0:33:41).** Fresh owning regressions and surrounding Phase 7 suites pass; F1/F2 remain independently reproduced outside that test coverage.

Independent scratch commands, each with the same environment prefix and working directory:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-sync python /private/tmp/phase7-final-review-probes.py
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-sync python /private/tmp/phase7-final-review-attacks.py
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-sync python /private/tmp/phase7-final-review-nearby.py
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-sync python /private/tmp/phase7-final-review-version-nearby.py
```

All completed scratch runs exited **0** and recorded actual results, including the **accepted invalid behavior** in F1/F2; exit 0 is not semantic acceptance. The initial multi-attack harness used a nonexistent `source_versions` SQL table and exited 1 before attacking. It was corrected outside the checkout to perturb SOURCE_VERSION `graph_nodes` and reuse the already accepted baseline; the successful run and setup error are both retained in its log. No failed setup was counted as attack evidence. A06's initial text-varied residual fixture is closure evidence, while its subsequent inverted removal is the fresh attack.

Root independently ran required full quality verification in the implementation worktree and a **new clean detached checkout of exact ef601119eb4962152ebe3eaa844f60076df77550**. The reviewer inspected both completed full logs and the detached environment setup logs. The results below are fresh root-run verification, not implementer-supplied counts.

| Checkout / exact command | Actual result | Log |
| --- | --- | --- |
| Implementation worktree: `UV_CACHE_DIR=/private/tmp/uv-cache uv sync --dev` | Exit 0, 26 resolved / 25 checked | Root live result |
| Implementation worktree: `UV_CACHE_DIR=/private/tmp/uv-cache uv run python scripts/verify.py` | Exit 0; Ruff check passed, 340 files formatted, Pyright 0 errors / 0 warnings; **2,008 passed, 5 deselected in 2290.69s (0:38:10)** | `/private/tmp/phase7-final-acceptance-work-verify.log` |
| New detached `/private/tmp/novcheck-phase7-final-acceptance-ef60111`: `UV_CACHE_DIR=/private/tmp/uv-cache uv sync --dev` | **Setup failed**: PyPI DNS while fetching hatchling; not a test failure or a successful gate | `/private/tmp/phase7-final-acceptance-clean-sync.log` |
| Same new detached checkout: `UV_CACHE_DIR=/private/tmp/uv-cache uv sync --dev --offline` | Exit 0; 26 resolved / 25 installed in a new environment from cache | `/private/tmp/phase7-final-acceptance-clean-sync-offline.log` |
| Same new detached checkout: `UV_CACHE_DIR=/private/tmp/uv-cache uv run python scripts/verify.py` | Exit 0 in the offline-created environment; Ruff check passed, 340 files formatted, Pyright 0 errors / 0 warnings; **2,008 passed, 5 deselected in 2279.87s (0:37:59)** | `/private/tmp/phase7-final-acceptance-clean-verify-offline-env.log` |

`scripts/verify.py` runs Ruff check, Ruff format check, Pyright, and pytest. Five explicitly opt-in network tests remain excluded; this review makes no live-model accuracy, recall, calibration, prompt-injection-rate or future qualification quality claim. No optional later-stage work is an acceptance blocker.

Final repository checks passed: `git diff --check` and `git diff --no-index --check /dev/null docs/reviews/phase-7-final-review.md` produce no errors. Both checkout HEADs equal the exact reviewed commit; the detached checkout is clean and implementation status contains only `?? docs/reviews/phase-7-final-review.md`. The original report object hash is `6b0e19ac09631d281225a94e10fb355cff1d8f3a`, identical to its exact-HEAD blob. Only this review document is changed; no ADR is added. F1/F2 require bounded existing Phase 7 corrections, not a redesign or Phase 6 reopening.

## Final decision

I1, I2, I4 and I5 are closed. The literal dangling references and missing typed companions in I3 are corrected, but its full boundary is superseded by the reproduced F1/F2 defects. There is no independent acceptance PASS. Phase 7's semantic/authority exit criteria remain unmet, regardless of clean quality checks. Preserve the original FAIL document and keep Phase 8 blocked.

Phase 7 independent acceptance review: FAIL — Phase 7 remains incomplete; Phase 8 is blocked.
