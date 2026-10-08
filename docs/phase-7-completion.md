# Phase 7 implementation and verification handoff

Status: **Phase 7 accepted and complete** by the fresh narrow independent remediation confirmation of exact implementation `0cef9f7`. Both remaining Important findings are CLOSED; 2,037 deterministic tests passed in the implementation worktree and clean detached checkout. Original FAIL reviews at `4a4b0a7` and `ef60111` remain intact as acceptance history. Phase 8 may begin, but no Phase 8 work was performed. M1 remains deferred Minor. See [independent confirmation](reviews/phase-7-remediation-review.md).

Approved scope: Phase 7 adversarial review and neutral adjudication only. Accepted Phase 6 baseline `e4dd4e09699f755dd0fe7b7bc3dd8be4e11f7ee1` and its Gate 30 record remain frozen. Branch `phase-7-adversarial-adjudication`; worktree `/private/tmp/novcheck-phase7.WORKTREE`. No push, merge or publication.

## Implementation

Distinct immutable Phase 7 contracts, schema-v8 tables, sealed input/research contexts, deterministic repository-derived packet, independent role passes, one rebuttal per role, typed bounded Phases 3–6 escalation and changed-state restart; categorical Gates A–D; deterministic permission policy; explicit two-candidate HIGH_IMPACT classification; primary and optional alternate reversed-order pairs reconciled without voting; target-specific aggregation; atomic authoritative freeze and read; real application slice beside earlier fixtures; post-commit retryable traces and architecture guards.

Requirement coverage: master §§31–37; INV-01/02/03/05/06/07/09/11/12/13/14/15, FR-EQ-004, FR-EVID-004, FR-ARC-001/002, FR-AUD-001/002, FR-SEC-001/002, FR-OBS-001/002; approved design §§1–45. Exact mappings in `docs/traceability/phase-7.yaml`.

## Task 22 adversarial closeout

The two required integrated tests passed on their initial run (2 passed in 40.09s), as the plan explicitly allows; no failure was manufactured. Zero-yield retrieval changes budget, coverage and query/stop history, supersedes the old run, reruns independent cases, judges both argument orders, freezes only the successor and reloads repository authority. Heterogeneous probes require a full alternate pair; two stable models that materially disagree remain unresolved.

Two fresh existing-invariant defects were reproduced with failing regressions before their fixes:

- `test_authoritative_load_rejects_canonical_illegal_transition_jump`: canonical hashes and valid frozen dependencies concealed a forged CASE_BUILT→FROZEN chain. Load now validates every transition against the same state rules used by writes.
- `test_counterfactual_list_order_is_nonmaterial`: reordering remaining differences created material order instability. Normalization now treats that list as a semantic set while retaining both actual findings.

Fresh bounded attacks (12 passed in 3.93s): missing input routes only to Gate A; disguised Gate A research schema rejects; foreign context rejects; first-pass cross-role payload forbids; wrong source revision rejects; reply-to-reply extra field forbids; invoked unstable alternate remains unresolved; foreign-target direct judge rejects; asserted value cannot change novelty; mixed aggregation retains unassessable targets; candidate omission rejects; caller frozen shapes confer no authority. Citation, rebuttal persistence, frozen dependency mutation and heterogeneous single-call/vote attacks also remain in their owning suites.

Phase 6 authority rerun found three schema-metadata fixtures still selecting/expecting v7. Only those fixture downgrade selectors and current-schema assertions changed: intended v1/v3 legacy states are now actually exercised under v8. Exact migration regression: 3 passed (0.72s); authority suite: 208 passed (91.42s). No Phase 6 semantic behavior changed.

## Changed files and tests

Runtime changes are grouped under `adjudication/`, `ports/adjudication.py`, `application/phase7*.py`, schema-v8 `evidence/graph/phase7_{models,store}.py` and delegation/migration support in the existing graph repository. The real vertical slice, application result types, domain reporting summary and minimal report boundary retain fixture compatibility. Existing Phase 6 test changes are current-schema metadata only; Phase 1/5 architecture guards admit the approved read port and exact storage paths.

New tests: `tests/unit/adjudication/test_{contracts,context,packet,roles,needs,gates,judge,policy,frozen}.py`, `tests/unit/evidence/graph/test_phase7_store.py`, `tests/integration/test_phase7_slice.py`, `tests/adversarial/test_phase7_authority_semantics.py` and `tests/unit/test_phase7_architecture_guards.py`. Documentation: approved plan/design, README, Phase 7 traceability and this handoff.

## Verification

Focused complete Phase 7 regression: 236 passed (1,274.84s). Owning judge/storage regressions and new defect cases: 94 passed (664.08s). Phase 6 authority regression: 208 passed (91.42s). Full fixture/real slices: 49 passed (453.33s). Architecture/report compatibility regression after the final runtime correction: 64 passed (119.82s).

Final full quality gate at implementation commit `9b2df02d6e93733c34d5a7d76762b351fe23b958`: **1,985 passed, 5 network tests deselected** in the implementation worktree (2,028.51s) and clean detached checkout (2,025.12s); both commands exited 0. This is 240 more deterministic tests than the accepted Phase 6 baseline. Both checkouts were clean and `git diff --check` passed. Logs: `/private/tmp/phase7-full-verify-resumed.log` and `/private/tmp/phase7-clean-verify-resumed.log`. Deterministic pytest configuration disables sockets and excludes opt-in `network` tests. `uv sync --dev --offline` resolved 26 packages and checked 25. Ruff check passed; 340 files formatted; Pyright 0 errors/warnings. Exact closeout commands are recorded below.

## Limits

No live-model entailment, live search robustness or empirical calibration is established by these deterministic fixtures. Production strong-positive permission remains unavailable without genuine repository-validated robustness and domain qualification from future trusted issuers. Historical unvalidated upstream state stays UNKNOWN. Phase 8 narrative compiler, Phase 9 live robustness, Phase 10 calibration, probabilities/scores, legal patent opinions and polished UX remain deferred.

## Versions

`p7-prosecutor-v2`, `p7-defender-v2`, `p7-rebuttal-v2`, `p7-judge-rubric-v2`, `phase7-verdict-permission-v2`, `phase7-gates-v2`, `phase7-case-builder-v1`, `phase7-real-slice-v1`.

## Execution rulings

- Task 15: Ruling: EvidenceJudgePort declares a read-only model_config_id property, and the model adapter hashes its provider/configuration. The locked judge call signature stays unchanged. This makes the required otherwise-identical configuration check explicit; cost if wrong: a new scripted port must supply its identity.
- Task 15: Ruling: The two RoleArgument records project validated first-pass positions plus the committed bounded rebuttal points and references, keeping role mapping internal. Wording/stable identifiers may reveal a role, recorded as a blinding limitation. Cost if wrong: projection could omit semantic content; the rebuttal-display regression asserts both sides remain present under both orders.
- Task 16: Ruling: Judge proposals contain semantic Gate C/D effects, not hypothetical final verdicts. Reconciliation leaves positive-compatible unresolved probes without resolved semantics and applies a POTENTIALLY_NOVEL ceiling only as an upper bound; it cannot confer positive permission. Negative/positive, insufficient or unsafe outcomes have an UNASSESSABLE ceiling. The later policy/freeze must still satisfy all factual gates. Cost if wrong: conservative abstention may require another assessment.
- Task 16: Ruling: Pure comparison/reconciliation functions validate the retained pair and normalized semantics but cannot establish citation membership from a digest alone. Membership is checked on every judge output and repository write; freeze/load must repeat it against the repository packet. A fabricated alternate is rejected before its comparison can be committed. Cost if wrong: a caller-shaped pure comparison remains nonauthoritative.
- Task 17: Ruling: A COMBINATION kind alone does not prove it covers the whole configuration. TargetFinding adds whole_configuration as structured claim-scope metadata, derived by the deterministic policy from the sealed graph (all MCU members, or the sole MCU with no combination). Composition requires this marker plus decisive support for whole negativity; Task 18 freeze re-evaluates it from repository topology. Cost if wrong: caller-shaped metadata remains nonauthoritative and cannot replace repository checks.
- Task 18: Ruling: Add typed JudgeProbeRegistration as immutable protocol provenance before each configured judge's calls. Primary versus alternate is not chosen from outcomes: rule 4 and rule 6 have different semantics, so freeze must reject posthoc swapped comparison references. This adds no voting or verdict field. Cost if wrong: another run is required for a differently configured probe sequence.
- Task 18: Ruling: JudgeFinding now carries an optional typed counterfactual proposal. Its semantic digest participates in counterbalance normalization; freeze requires the committed localization to equal the resolved retained judge proposal. Shape-valid independent caller localization cannot grant Gate D permission. Cost if wrong: conservative unresolved contributions until semantic probes supply the typed removal effect.
- Task 18: Phase6 shared loader validation AST is unchanged (excluding transaction opening/commit). Focused store/judge/R15 authority run: 133 passed, one RED stale schema-version assertion (7 versus approved 8); no semantic assertion failed. Ruling: update that migration return assertion to 8 while retaining actual v5 downgrade and the deleted graph-membership rejection. This is Phase7 migration compatibility metadata, not a Phase6 semantic change. Cost if wrong: the v8 migration tests and full verification remain required gates.
- Task 19: R10–R15 authority suites: 142 passed, one RED stale schema-version expectation in the v4 replay test. Ruling: change that expected current schema to approved v8, retaining the exact semantic replay/no invented commit checks. R14 fixtures now downgrade the sole schema row unconditionally, preserving the intended legacy migration precondition under v8 (the old WHERE version=7 was a no-op). Phase6 runtime semantics and Gate30 history remain unchanged. Cost if wrong: authority fixture gates and full repository verification must still pass.
- Task 20: Ruling: add an immutable per-target role-port mapping and optional adapter target selector while retaining complete identical packet inputs and the locked propose(packet) signatures — one case per target needs explicit multi-target selection. Cost if wrong: target isolation and exact universe gates reject mismatched output before freeze.
- Task 20: Ruling: expose repository-validated superseded context locators through a read helper sharing the freeze history validator — the coordinator needs authoritative history to produce the required frozen shape. Cost if wrong: freeze/read still recompute the exact history in their own transaction.
- Task 20: Ruling: real slice binds CIR target locator lists to its already-reconciled graph at the Phase7 handoff, preserving original input and semantic fields — legacy fixture handoffs did not consistently carry these IDs. Cost if wrong: repository exact profile/universe joins reject the context. No Phase6 classification or authority semantics changed.

## Task-by-task gates



## Exact closeout commands

All `uv` commands use `UV_CACHE_DIR=/private/tmp/uv-cache`. Offline synchronization avoids live network; the pytest configuration excludes `network` tests and disables sockets.

```bash
uv run pytest tests/adversarial/test_phase7_authority_semantics.py::test_full_slice_zero_yield_counterbalance_freeze_replay tests/adversarial/test_phase7_authority_semantics.py::test_heterogeneous_majority_vote_cannot_upgrade_result -q
uv run pytest tests/adversarial/test_phase7_authority_semantics.py::test_fresh_phase7_boundary_variants -q
uv run pytest tests/adversarial/test_phase7_authority_semantics.py::test_authoritative_load_rejects_canonical_illegal_transition_jump tests/adversarial/test_phase7_authority_semantics.py::test_counterfactual_list_order_is_nonmaterial tests/unit/adjudication/test_judge.py tests/unit/evidence/graph/test_phase7_store.py -q
uv run pytest tests/unit/adjudication tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py tests/integration/test_phase7_slice.py -q
uv sync --dev --offline
uv run pytest tests/adversarial/test_phase6_r10_content_authority.py tests/adversarial/test_phase6_r11_authoritative_publication.py tests/adversarial/test_phase6_r13_commit_receipt_authority.py tests/adversarial/test_phase6_r14_graph_authority.py tests/adversarial/test_phase6_r15_assessment_authority.py tests/adversarial/test_phase6_r15_public_graph_consistency.py tests/adversarial/test_phase6_sol_review_regressions.py tests/adversarial/test_phase6_contract_consolidation.py -q
uv run pytest tests/integration/test_phase1_vertical_slice.py tests/integration/test_phase1_slice_with_phase2_components.py tests/integration/test_phase2_slice_with_phase3_planner.py tests/integration/test_phase3_slice_with_phase4_research.py tests/integration/test_phase4_slice_with_phase5_evidence.py tests/integration/test_phase5_slice_with_phase6_evidence.py tests/integration/test_phase7_slice.py -q
uv run python scripts/verify.py
git diff --check
```

The full quality gate runs `ruff check .`, `ruff format --check .`, `pyright`, and `pytest`. Its clean detached checkout is at `9b2df02d6e93733c34d5a7d76762b351fe23b958`, `/private/tmp/novcheck-phase7-verify-architecture`, with a newly created offline-synchronized environment.

## Architecture closeout

The first worktree and detached full quality gates at `a433276` each passed 1,983 tests and failed two architecture guards (5 network tests deselected). An exact RED run reproduced both. `Phase7FrozenSummary` moved to the existing domain reporting contract module, retaining the application import as a compatibility re-export; the report module now imports that domain contract directly. Read-only report ports and the two planned graph storage modules were added to explicit architecture allowlists; SQL permission is restricted by exact graph-relative paths. Exact GREEN: 2 passed (0.68s). Surrounding Phase 1/5/6/7 architecture, report, fixture/real slice regression: 64 passed (119.82s). No prior-art or verdict semantics changed in this correction.

The pre-review implementation commit was `9b2df02d6e93733c34d5a7d76762b351fe23b958`; both pre-review full gates passed from it. The review correction implementation commit is `54fb701454c0c2e5298837349d29045da7debd54`. The earlier interrupted runs ended without results and were not counted as passes.

### Additional execution ruling

- Task 22: Ruling: Move Phase7FrozenSummary to the existing domain.reporting contract module and re-export it from application.models — reports may depend on domain contracts and repository read ports, never application services. Add only the approved Phase7 repository read port and exact graph/phase7_models.py and graph/phase7_store.py storage paths to older architecture guards — preserves semantic/provider bans. Cost if wrong: compatibility/report and all architecture gates must still pass.

## Independent acceptance handoff

The single read-only, fresh-context whole-phase review ran after Task 22 was green, against the accepted Phase 6 baseline through `4a4b0a7`. It returned FAIL; the original report is retained in `docs/reviews/phase-7-independent-acceptance.md`. The one implementer fix pass follows the executing-plans workflow; no second review was scheduled. Implementer tests alone cannot close acceptance.

## Decisions and deferred work

ADR-037 records the review correction contracts and dispatch boundaries. The single independent review returned FAIL with I1–I5 Important and M1 Minor; its original report is retained. The one bounded fix pass is verified by regressions and full repository gates, without a second reviewer. Acceptance remains OPEN because no independent acceptance PASS has been issued. No external push, merge or publication was performed.

## Independent review corrections

Original review: [Phase 7 independent acceptance](reviews/phase-7-independent-acceptance.md),
FAIL at `4a4b0a7`. Corrections implement approved design §§9–15, 19, 21–23, 29,
36–37; INV-03/06/07/12 and FR-ARC-001/002, FR-AUD-001/002. See ADR-037.

- I1: neutral scope review remains required for assessable agreement, including
  direct negatives and agreed substantive partials. Unbounded interpretation
  requires a full pair; omitted witnesses fail closed at write/freeze/load.
- I2: removal exactly accounts for remaining Phase 6 differences. A real
  two-independent-residual fixture rejects omission before freezing a negative.
- I3: typed needs with exact reference joins at every semantic stage. Input
  clarification never reaches research; external gaps retain dispositions and
  dependencies, with restart after changed state and conservative unresolved permission.
- I4: complete LIMITED input permits bounded scoped findings; missing fields and
  unstable claim meaning still abstain, and LIMITED cannot authorize strong positive.
- I5: intersect cumulative caps and subtract prior usage before reviewed Phase 4
  execution; enforce every bounded dimension and record the allowance/disposition.

Initial owning RED: three semantic failures (28.43s) and four needs/budget
failures (31.03s; two nearby passes). Owning GREEN: 13 passed (176.11s);
stage dispatch variants: 4 passed (117.86s). Nearby agreed-partial and real
residual regressions: 2 passed (2.37s). Three further boundary RED cases
(8.81s) became GREEN (8.17s): unstable LIMITED meaning, tighter cap versus
sealed usage, terminal research writes. Old-contract reinterpretation RED
became GREEN with the contracts suite: 3 passed (0.18s).

The first broad review regression ended with 184 passed/one stale test expecting
zero neutral calls, then was interrupted. That expectation contradicted I1 and
was corrected to require rejection of omitted neutral review. It is not counted
as a successful gate.

### Correction verification

Final runtime/test correction commit: `54fb701454c0c2e5298837349d29045da7debd54`.
The subsequent documentation handoff preserves the original independent FAIL.

All commands use `UV_CACHE_DIR=/private/tmp/uv-cache`:

| Command | Result | Log |
| --- | --- | --- |
| `uv run pytest tests/unit/adjudication tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py tests/integration/test_phase7_slice.py tests/unit/test_phase7_architecture_guards.py -x -q` | 262 passed; 1670.81s | `/private/tmp/phase7-review-focused-complete.log` |
| `uv run pytest tests/unit/adjudication/test_needs.py tests/unit/evidence/graph/test_phase7_store.py -q` | 49 passed; 425.43s | `/private/tmp/phase7-review-budget-store-green.log` |
| `uv run pytest tests/integration/test_phase7_slice.py -q` | 34 passed; 650.97s, before adding the real Phase 4 variant | `/private/tmp/phase7-review-integration-green.log` |
| `uv run pytest 'tests/integration/test_phase7_slice.py::test_reviewed_research_adapter_seals_zero_yield_phase4_result[False-1-True]' -q` | 1 passed; 8.78s, actual Phase 4, one mocked call from two-query plan with one prior call | `/private/tmp/phase7-review-real-budget-green.log` |
| `uv run pytest tests/integration/test_phase5_slice_with_phase6_evidence.py tests/unit/test_minimal_report_compiler.py -q` | 28 passed; 109.01s | `/private/tmp/phase7-review-vertical-regression.log` |
| `uv run pytest tests/integration/test_phase5_slice_with_phase6_evidence.py::test_vertical_slice_has_explicit_real_phase7_handoff -q` | 1 passed; 78.08s | `/private/tmp/phase7-review-vertical-explicit-green.log` |
| `uv run python scripts/verify.py` | PASS: Ruff check, 340 formatted files, Pyright zero errors/warnings; 2008 passed, 5 network deselected; 1851.89s | `/private/tmp/phase7-review-final-worktree-verify.log` |
| `git diff --check` | PASS | No whitespace errors |

The preceding stable full run reported 2007 passing tests and one stale scripted
real-handoff fixture that prohibited neutral judging (1879.86s). That fixture
now supplies exact scoped findings and checks both orders; Phase 6 runtime
semantics remain unchanged. The final full gate above includes its corrected
case. A later Ruff line-length failure was fixed by splitting a literal string;
the final gate includes that formatting change.

Before the final completion response, repeat `uv sync --dev --offline` and
`uv run python scripts/verify.py` in a fresh detached checkout of the exact
handoff commit. Checkout: `/private/tmp/novcheck-phase7-verify-review-final`.
Full log: `/private/tmp/phase7-review-final-clean-verify.log`. The append-only
local result record at `/private/tmp/phase7-review-final-verification.md` records
the exact handoff commit, actual detached count, exit status and clean-tree checks
after execution. This avoids a self-referential commit ID or a preclaimed pass.
Five opt-in network tests remain excluded; deterministic tests disable sockets.

### Deferred minors

M1: real frozen value/significance arrays remain empty. CIR advantages and Gate D
findings remain retained; value cannot change novelty permission. This was graded
Minor and deferred under the single-review workflow.

### Additional execution rulings

- Final: Ruling: live-model accuracy, search recall, injection rates and calibration
  remain unmeasured — Phase 9/10 are outside approval — cost if wrong: deterministic
  results do not establish live quality.
- Final: Ruling: nine-question narrative and polished UX stay deferred — approved
  Phase 7 only provides structured handoff — cost if wrong: users need the minimal summary.
- Final: Ruling: future qualification issuers stay absent — production strong
  positive stays closed — cost if wrong: strong conclusions need a later phase.
- Final: Ruling: neutral agreement uses an unbounded scope-review marker and both
  orders — no complete validated alternative pair exists — cost if wrong: extra
  judge calls compared with an optional one-call reduced path.
- Final: Ruling: typed companions and reserved allowance extend proposal contracts
  while public port signatures stay fixed; affected contracts/prompts/methods use v2
  (ADR-037) — immutable versions prevent reinterpretation — cost if wrong: preacceptance
  v1 Phase 7 runs must be rerun; Phase 6 remains readable.
## Targeted final-review remediation — 5 October 2026

This section follows the explicitly authorized targeted remediation of the two
Important findings in the final independent FAIL at `ef60111`. It preserves both
historical FAIL records. The final review document remains byte-identical with
SHA256 `bf23058b91100fa7162a7be757a7326485462f4500790bc9bd12b6515eb0a026`.
The user authorized a fresh **narrow** independent confirmation after the
implementation became green; no new broad ten-attack review was scheduled.

### Implementation commits and authority changes

- Finding A/F1: `af28c258bc36816e589dbc93f35b339df480b2d1`,
  `fix(phase7): reject input meaning disguised as external research`.
  ADR-038 records the v3 research-gap contract and typed external-fact basis.
  Gate D requires a Gate-A-comparable defined contribution and a bound external
  fact demonstrable from packet coverage, chronology or contradiction records.
  An unproved semantic gap becomes an input clarification before dispatch;
  persisted malformed requests fail at continuation, ancestor validation,
  freeze and authoritative load. Legitimate inaccessible-source, uncertain
  chronology and specific external contradiction controls still permit research.
- Finding B/F2: `0cef9f7f407c44f4682edfe0befe3e1fcc5c30cc`,
  `fix(phase7): bind semantic artifacts to executed prompt provenance`.
  ADR-039 records v2 artifact envelopes and pre-call scoped method/configuration
  records in the existing schema-v8 artifact table. Actual SemanticRunner
  request, raw response, validated proposal and invocation hashes remain
  distinct. Scripted ports explicitly use `PORT_PROTOCOL`; they do not claim
  an LLM call. Write/freeze/load join every decisive role/rebuttal/primary or
  alternate judge envelope to approved method/configuration and exact scope.
  Trace publication projects repository execution provenance; a contradictory
  audit cannot label a committed request. Old v1 semantic artifacts require a
  fresh current execution and receive no automatic backfill or upgrade.

No Phase 6 support, chronology, classification or graph authority semantics were
changed. The schema remains v8; no second truth store was added. No Phase 8,
future qualification issuer, live provider, push, merge or publication work was
performed. Closed I1/I2/I4/I5 regressions remain in the focused and full gates.
M1 remains deferred Minor: real frozen value/significance arrays are empty,
while sealed value facts and exact Gate D dependencies remain authoritative;
value cannot change novelty permission.

### RED/GREEN and bounded attack evidence

New owning tests:
`tests/unit/adjudication/test_gate_d_research_origin.py` (13 collected cases),
`tests/unit/adjudication/test_execution_provenance.py` (16 collected cases).
Existing fixture adjustments execute actual recorded semantic ports rather than
inserting unproven raw role outputs; authority checks were not weakened.

- A initial RED: 3 failed, 30.67s. Exact GREEN: 3 passed, 31.50s.
  Routing/display gate: 40 passed, 106.97s; component gate: 52 passed,
  106.89s; repository/lifecycle variants: 35 passed, 67 deselected, 615.01s.
  Direction, control-flow and combination-topology disguises route to input;
  exact source/version and comparison joins reject foreign fact bases;
  inaccessible-source, chronology and actual contradiction positive controls
  remain research. Persisted misrouting and post-research continuation attacks
  fail closed. The role display exposes copyable bound fact bases rather than
  asking a model to invent identifiers or hashes.
- B initial RED: 5 failed, 40.98s. First exact GREEN: 5 passed, 24.81s.
  Nearby freeze/load gate: 12 passed, 119.22s. Recovery/shared-runner actual
  audit variants: 2 passed, 11.63s. Trace contradiction/model metadata variants:
  2 passed, 19.21s. Exact invocation trace projection RED: 1 failed, 18.56s;
  GREEN: 1 passed, 17.69s. Variants include defender/rebuttal/judge v1,
  correct label with wrong instruction hash, wrong model configuration,
  foreign target/run configuration, successful schema recovery and shared
  SemanticRunner role isolation. Hash/FK-consistent post-freeze tampering is
  rejected on provenance rather than only a generic ID mismatch.
- Independent original stale-load condition was separately reproduced against
  `ef60111`: a canonically rehashed v1 role dependency loaded as authority.
  The corrected implementation rejects that same coherent rewrite with
  `Proposal prompt version differs from actual execution`.
  Logs: `/private/tmp/phase7-remediation-B-load-red.log` and
  `/private/tmp/phase7-remediation-B-load-final-green.log`.
- Diagnostic interrupted runs were not counted as green: A's earlier combined
  run reported two fixture failures; B's component attempt reported 2 failed/
  124 passed and its isolation attempt 1 failed/25 passed. The first final
  focused attempt reported 1 stale fixture failure/228 passed. Their owning
  fixtures/unfinished-target registration were corrected through exact gates;
  the fresh complete focused gate below supersedes those attempts.

### Exact final verification

All uv commands use `UV_CACHE_DIR=/private/tmp/uv-cache`; deterministic tests
make no Internet calls. Five opt-in network tests are excluded by repository
policy. Test collection is 2,037/2,042, reflecting exactly 29 additional cases
above the reviewed 2,008/2,013 baseline.

| Checkout / command | Actual result | Evidence |
| --- | --- | --- |
| Implementation `0cef9f7`: `uv run pytest tests/unit/adjudication tests/unit/evidence/graph/test_phase7_store.py tests/adversarial/test_phase7_authority_semantics.py tests/integration/test_phase7_slice.py tests/unit/test_phase7_architecture_guards.py -q` | 291 passed, 2118.64s | `/private/tmp/phase7-remediation-focused-final2.log` |
| Implementation: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`, `git diff --check` | PASS; 345 files formatted, zero typing errors/warnings | Actual final component output before B commit |
| Implementation `0cef9f7`: `uv sync --dev` | Exit 0; 26 packages resolved, 25 checked | `/private/tmp/phase7-remediation-work-sync.log` |
| Implementation `0cef9f7`: `uv run python scripts/verify.py` | Exit 0; Ruff PASS, 345 files formatted, Pyright zero errors/warnings; 2,037 passed, 5 deselected, 2360.91s (0:39:20) | `/private/tmp/phase7-remediation-work-verify.log` |
| Implementation `0cef9f7`: `git diff --check` and HEAD/status checks | PASS; exact commit, no tracked changes during verification | Actual post-run output |

### Independent confirmation status

The fresh narrow independent reviewer issued **PASS** at exact implementation
`0cef9f7f407c44f4682edfe0befe3e1fcc5c30cc`. Both remaining Important findings
are **CLOSED**. Original attack replays and five fresh variants passed; closed
I1/I2/I4/I5 regressions remain green. The reviewer independently executed the
focused and full gates and confirmed clean HEAD/status, frozen authority,
and 41 unchanged Phase 6 loader-validation statements. No Critical or Important
finding remains; M1 remains deferred Minor. The complete report is retained
in [the separate remediation review](reviews/phase-7-remediation-review.md).


| Independent detached checkout / command | Actual result | Evidence |
| --- | --- | --- |
| `/private/tmp/novcheck-phase7-remediation-independent-0cef9f7`: `uv sync --dev` | Exit 1: PyPI DNS/hatchling environment setup failed; no test verdict inferred | `/private/tmp/phase7-remediation-independent-sync.log` |
| Same exact checkout: `uv sync --dev --offline` | Exit 0; 26 packages resolved, 25 installed from cache | `/private/tmp/phase7-remediation-independent-sync-offline.log` |
| Focused new owning and exact closed-finding pytest selection | Exit 0; 46 passed, 431.80s (0:07:11); exact command in the review | `/private/tmp/phase7-remediation-independent-focused.log` |
| `uv run python scripts/verify.py` | Exit 0; Ruff PASS, 345 files formatted, Pyright zero errors/warnings; 2,037 passed, 5 deselected, 2449.18s (0:40:49) | `/private/tmp/phase7-remediation-independent-full-verify.log` |
| Original A/B attacks and five fresh variants | Exit 0; all assertions passed | `/private/tmp/phase7-remediation-independent-probes.json` |
| `git diff --check`, `git status --porcelain=v1`, `git rev-parse HEAD` | Exit 0; clean detached checkout at exact implementation commit | `/private/tmp/phase7-remediation-independent-final-evidence.json` |

The same independent reviewer resumed after the usage-limit interruption. Its
full-verification process survived and completed; no partial run was counted as
passing and no extra review stage was introduced. Implementation source, tests,
scripts and dependency files remain exactly those of `0cef9f7`; the subsequent
handoff commit changes only documentation. Historical final review SHA256 remains
`bf23058b91100fa7162a7be757a7326485462f4500790bc9bd12b6515eb0a026`;
independent confirmation SHA256 is
`0fcbf2172466d91acbb6055624d0829fd03c96ada9d8a2f5dd926f367850499e`.

Phase 7 independent remediation re-review: PASS — the two remaining Important findings are closed. Phase 7 is accepted and complete; Phase 8 may begin.
