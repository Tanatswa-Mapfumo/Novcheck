# Phase 7 independent remediation confirmation

**Decision: PASS.** The two remaining Important findings A/F1 and B/F2 are closed. This is the explicitly authorized narrow remediation confirmation, including the required regressions for the previously closed findings. No broad review, source/test modification, child agent, Phase 6 redesign, Phase 8 implementation, merge, push or publication occurred.

## Exact target and independence

Reviewed implementation **`0cef9f7f407c44f4682edfe0befe3e1fcc5c30cc`**, including A commit `af28c258bc36816e589dbc93f35b339df480b2d1` and B commit `0cef9f7f407c44f4682edfe0befe3e1fcc5c30cc`, against the final historical FAIL target `ef601119eb4962152ebe3eaa844f60076df77550`. The accepted Phase 6 baseline remains `e4dd4e09699f755dd0fe7b7bc3dd8be4e11f7ee1`.

The fresh reviewer created `/private/tmp/novcheck-phase7-remediation-independent-0cef9f7` as a detached exact-commit checkout. Its initial HEAD matched and status was empty. The old/dirty user checkout was not used for execution or editing. The same review continued after the usage-limit interruption; the original full-verification process survived and was resumed, not replaced or counted twice.

Read the exact user remediation request, AGENTS.md, governing master invariants and §§31–37/Phase 7 exit criteria, approved Phase 7 design/plan, completion handoff, ADR-037/038/039, original independent acceptance report, and complete final historical FAIL. The latter remains byte-identical: SHA-256 `bf23058b91100fa7162a7be757a7326485462f4500790bc9bd12b6515eb0a026`.

## Blocker confirmation

| Finding | Independent evidence and authority inspection | Disposition |
| --- | --- | --- |
| **A/F1: research infers missing user meaning** | Replayed the original D/ACCESS attack with the original reason, hypothesis and stop-condition wording and a real packet source-version reference. Actual research calls: **0**. The control target becomes **UNASSESSABLE**, retains input clarification, freezes and authoritatively reloads. Additional typed-basis, real dispatch/continuation and canonical frozen-load variants below also behaved correctly. | **CLOSED.** Original and fresh variants reject the violation; focused and full gates pass. |
| **B/F2: stale prompt provenance freezes and is mislabeled in trace** | Replayed both stale v1 role outputs under current execution; rejected with `Prosecution prompt version is stale`, with **0 frozen manifests**. New owning tests cover write/freeze/load, wrong hash/config/rubric, rebuttal, actual SemanticRunner calls and repository-derived traces. Actual alternate execution and order variants below reject substitution. | **CLOSED.** Original and fresh variants reject the violation; focused and full gates pass. |

For A, the typed basis is a dispatch justification rather than new evidence. `validate_gate_d_external_basis` requires comparable Gate A meaning; exact assessment/context/snapshot/target and complete target-profile digest; an existing defined contribution; exact source/version and comparison references; and a Phase 6 exclusion, uncertain chronology, or verified contradiction. A D enum or prose alone cannot establish externality. Unproved untrusted proposals normalize to `InputClarificationNeed`; persisted malformed gaps are rejected. The classifier, policy, dispatch write, ACCEPT disposition, post-research continuation, frozen dependency validation and superseded ancestor path repeat the relevant joins. Continuation also forbids changing CIR, sufficiency or the target graph. Freeze and authoritative load share the same transactional validator; load does not trust exported JSON. The owning positive controls for unassessed/inaccessible implementation, chronology and verified contradiction are included in the focused run.

For B, application code registers scoped approved method/configuration records before invoking roles/judges in the existing Phase 7 artifact table. The semantic artifact wrapper carries the application execution envelope separately from untrusted proposal fields. Current method versions, instruction hashes, configuration/provider identity, invocation mode, proposal hash and judge rubric/config are joined on write and again during freeze/load. Actual SemanticRunner adapters select the matching runtime invocation audit using its request hash and task, retain actual raw response and validated proposal hashes separately, and retain the successful recovery instruction hash when used. Old v1 wrappers/proposals do not acquire current authority by deserialization. `PORT_PROTOCOL` identifies the actual scripted port implementation/configuration and is explicitly labeled as protocol metadata; it does not claim an LLM/provider execution. Trace fields derive from committed repository execution records, and contradictory supplied operational audits are rejected. Trace delivery is not an authority source.

Relevant locations: `adjudication/needs.py`, `adjudication/execution.py`, `adjudication/models.py`, `application/phase7_execution.py`, `application/phase7_model_adapter.py`, `application/phase7_roles.py`, `application/phase7_research.py`, `application/phase7.py`, and `evidence/graph/phase7_store.py` under `src/novelty_harness/`.

## Fresh bounded variants

These are independent scratch probes, not renamed added tests. They exercise only A/B invariants. Internet sockets were disabled with `pytest_socket.disable_socket(allow_unix_socket=True)`; all providers/ports were deterministic.

| Variant | Attempt and actual outcome |
| --- | --- |
| **A1 — valid fact basis rebound to undefined relationship** | Copied a real SOURCE_CHRONOLOGY basis, rebound its target/scope/profile digest/contribution to the undefined status target, cleared its comparison references, and used innocuous historical-terminology prose in the **defender**. Classified as INPUT_MEANING_GAP; **0 research calls**; the exact normalized clarification was retained through real freeze/reload. |
| **A2 — legitimate external fact positive control** | Defender proposed a source-specific chronology request for the already defined control target using the authoritative uncertain comparison. **1 actual research dispatch**, genuine true-no-op continuation, retained request, successful freeze and authoritative reload. Existing direct evidence still supports the control-scoped negative; other undefined targets remain UNASSESSABLE. Legitimate D research was not disabled. |
| **A3 — frozen fact binding substitution** | After A2 successfully froze/reloaded, replaced only the persisted gap's target-profile digest. Recomputed canonical artifact/frozen IDs and updated dependency foreign keys consistently. Authoritative load rejected: `Gate D external fact basis does not bind a defined contribution`. The failure is semantic binding, not a generic bad ID/hash/FK. |
| **B1 — alternate configuration changes on reversed order** | A complete valid primary pair preceded an alternate that changed its declared model/config identity only while returning the second order. **2 primary + 2 alternate calls** occurred; the application rejected the changed configuration and left **0 frozen manifests**. |
| **B2 — real alternate execution envelope substituted into primary** | A real run completed **4 judge executions** under two distinct current configurations, froze and reloaded. Both configurations were faithfully represented in committed traces. Replaced a primary envelope with the real alternate envelope, adjusting the proposal hash and recomputing canonical artifact/frozen IDs/FKs. Authoritative load rejected: `Judge rubric/model differs from actual execution`. An existing legitimate alternate configuration does not authorize a primary artifact. |

Original attack replays plus all five variants completed with assertions satisfied, **exit 0**. Evidence: `/private/tmp/phase7-remediation-independent-probes.py`, `.json` and `.log`. Scratch database locations are recorded in the JSON. No repository fixtures or tests were altered.

## Previously closed findings and Phase 6

The independent focused run passed **46 tests in 431.80s**, comprising the **29 new owning cases** and **17 exact closed-finding regressions**:

| Closed finding | Required retained behavior checked |
| --- | --- |
| **I1** | Direct agreement and agreed substantive partial still receive neutral adjudication; omission of neutral judging or the required high-impact pair is rejected. |
| **I2** | Complete residual accounting and real freeze rejection when an independent surviving difference is omitted. |
| **I4** | Meaningful complete LIMITED input permits a scoped negative; unstable LIMITED meaning cannot. |
| **I5** | All cumulative resource dimensions, tighter configured cap versus sealed usage, successor cumulative budget, zero-yield restart/freeze/replay, and all five reviewed Phase 4 allowance variants, including the real pipeline with a mocked network transport one call below cap. |

The full gate also includes the complete required Phase 7 component/integration suite and existing Phase 6 authority suites. It is not inferred from the implementer's 291-case run.

An independent AST comparison against accepted Phase 6 found **41 identical loader validation statements**, excluding only docstring and transaction setup/commit surrounding the extracted helper. The remediation evidence/domain diff against `ef60111` changes only `evidence/graph/phase7_store.py`; no Phase 6 semantic module changed. Broader Phase 7 differences from Phase 6 are the additive repository delegation/schema and frozen-summary boundary already accepted in the historical review. Evidence: `/private/tmp/phase7-remediation-independent-phase6.py` and `.json`.

## Actual verification

All commands below ran in the fresh detached checkout and used `UV_CACHE_DIR=/private/tmp/uv-cache`.

| Command | Actual result | Log |
| --- | --- | --- |
| `uv sync --dev` | **Exit 1: setup failure**, PyPI DNS while resolving hatchling build requirements. No test verdict inferred. | `/private/tmp/phase7-remediation-independent-sync.log` |
| `uv sync --dev --offline` | **Exit 0**, 26 packages resolved, 25 installed in the fresh environment from cache. | `/private/tmp/phase7-remediation-independent-sync-offline.log` |
| Focused pytest command below | **Exit 0; 46 passed in 431.80s (0:07:11).** | `/private/tmp/phase7-remediation-independent-focused.log` |
| `uv run python scripts/verify.py` | **Exit 0; 2037 passed, 5 deselected in 2449.18s (0:40:49).** Ruff check passed; 345 files formatted; Pyright 0 errors/warnings/informations. | `/private/tmp/phase7-remediation-independent-full-verify.log` |
| `uv run --offline --no-sync python /private/tmp/phase7-remediation-independent-probes.py` with `PYTHONDONTWRITEBYTECODE=1` | **Exit 0**, original attacks blocked, all five fresh variants met their assertions. | `/private/tmp/phase7-remediation-independent-probes.log` |
| `uv run --offline --no-sync python /private/tmp/phase7-remediation-independent-phase6.py` | **Exit 0**, 41 unchanged authority statements. | `/private/tmp/phase7-remediation-independent-phase6.json` |
| `uv run --offline --no-sync python /private/tmp/phase7-remediation-independent-M1.py` | **Exit 0**, retained sealed value claim/Gate D facts. | `/private/tmp/phase7-remediation-independent-M1.log` |
| `git diff --check`; `git status --porcelain=v1`; `git rev-parse HEAD` | **Final exit 0**, empty status, exact `0cef9f7f407c44f4682edfe0befe3e1fcc5c30cc`. | `/private/tmp/phase7-remediation-independent-final-evidence.json` |

Exact focused command:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-sync pytest -p no:cacheprovider --basetemp=/private/tmp/p7-remediation-independent-focused tests/unit/adjudication/test_gate_d_research_origin.py tests/unit/adjudication/test_execution_provenance.py tests/unit/adjudication/test_policy.py::test_counterfactual_cannot_omit_independent_remaining_difference tests/adversarial/test_phase7_authority_semantics.py::test_real_freeze_rejects_omitted_independent_residual tests/integration/test_phase7_slice.py::test_clear_direct_reduced_path_skips_unneeded_steps tests/integration/test_phase7_slice.py::test_agreed_substantive_partial_still_receives_neutral_adjudication tests/unit/adjudication/test_judge.py::test_clear_direct_reduced_path_cannot_omit_neutral_judging tests/unit/evidence/graph/test_phase7_store.py::test_freeze_rejects_missing_high_impact_pair tests/unit/adjudication/test_policy.py::test_limited_complete_target_permits_scoped_negative tests/unit/adjudication/test_policy.py::test_limited_unstable_claim_meaning_cannot_permit_negative tests/unit/adjudication/test_needs.py::test_remaining_allowance_intersects_all_cumulative_dimensions tests/unit/adjudication/test_needs.py::test_gap_policy_intersects_tighter_cap_with_sealed_usage tests/unit/adjudication/test_context.py::test_escalation_manifest_keeps_cumulative_budget_above_latest_pass tests/adversarial/test_phase7_authority_semantics.py::test_full_slice_zero_yield_counterbalance_freeze_replay tests/integration/test_phase7_slice.py::test_reviewed_research_adapter_seals_zero_yield_phase4_result -x -q
```

`scripts/verify.py` runs `ruff check .`, `ruff format --check .`, `pyright`, and `pytest` in the uv environment. Pytest disables Internet sockets and excludes opt-in network tests. The root's completed 291-case focused run and 2037-case full run were inspected as supplementary evidence, not substituted for reviewer execution. An initial read-only M1 inspection used the wrong CIR attribute (`advantages`); corrected inspection used `claimed_advantages`. That scratch setup error was not counted as a product failure or passing check.

## Findings and limits

**Critical:** none reproduced. **Important:** none remain; both original blockers are closed, and no nearby violation was reproduced in the completed independent attack set. **Minor:** M1 remains deferred. Actual reload retains empty `value_findings`/`novelty_significance`, the sealed **“Reduce operator checks” / CLAIMED** advantage, and all three target Gate D dependencies. The remediation does not change its effect or expose a new authority violation. No Phase 8/value UX work is required here.

Deterministic fixtures do not establish live-model accuracy, recall, calibration or prompt-injection success rates. Five opt-in network tests remain outside the standard gate. Production strong-positive qualification issuers and Phase 8–10 work remain deferred. No reviewer ADR, source change or test was added; only this report and scratch evidence were created. ADR-038/039 document the authorized corrections; no additional decision is requested.

## Final decision

Both Important defects are closed, I1/I2/I4/I5 remain closed, Phase 6 authority remains intact, and the reviewer-executed focused and full gates pass at the exact clean implementation commit. The historical FAIL documents remain intact. No additional review stage or later-phase implementation is required for this acceptance.

Phase 7 independent remediation re-review: PASS — the two remaining Important findings are closed. Phase 7 is accepted and complete; Phase 8 may begin.
