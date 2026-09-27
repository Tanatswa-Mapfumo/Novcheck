# Phase 3 completion and verification record

Status: Implementation verified; fresh-checkout verification and final independent
review are pending. This report does not yet declare final phase acceptance.

## Scope and tasks

Base: accepted Phase 2 commit 558a22a. Isolated branch: phase-3-research-planner.
Implementation worktree: /private/tmp/novcheck-phase3.WORKTREE. Original checkout
and accepted Phase 2 worktree were not modified. Phase 4 has not started.

Tasks 1-13 are completed in plan order with focused tests and full verification.
Task 14 provider documentation, architecture guards and opt-in smoke tests are
implemented; final verification/review closure is pending. The supplied Phase 3
plan was committed without content changes (cmp exit 0 against original).

| Task | Commit | Implemented |
| --- | --- | --- |
| 1 | 898f0bc, e3b9f60 | Versioned rich contracts and eleven-family query taxonomy |
| 2 | 4b17ce5 | Provider-independent per-MCU family applicability |
| 3 | 612d5c4 | Multi-family neutral strategy and explicit omissions |
| 4 | d537403 | Independent critic, deterministic guards, bounded revision |
| 5 | c1a20fb | Configurable operational floors and truthful coverage states |
| 6 | 798ebd6 | HTTP failures/retries/rate metadata and registry |
| 7 | 69fa7b1 | Safe provider-compilation boundary |
| 8 | f1b8ba2 | OpenAlex Works screening |
| 9 | 3caf9f7 | Crossref bibliographic screening |
| 10 | 73aa035 | GitHub repository screening |
| 11 | 6967c08 | Reviewed-plan execution, coverage and screening artifacts |
| 12 | 97460ba | Real Phase 2/3 lifecycle with explicit later fixtures |
| 13 | 35de5b3 | Fifteen mandatory adversarial cases |
| 14 | Pending final closure | Provider matrix, traceability, opt-in smokes and final gates |

## Files

Created research/: __init__.py, models.py, query_taxonomy.py, applicability.py,
prompts.py, planning.py, critique.py, revision.py, coverage.py, provider_queries.py,
screening.py. Created providers/: __init__.py, errors.py, http.py, registry.py,
_base.py, openalex.py, crossref.py, github.py. Created application/research.py,
ports/search_audit.py, runtime/config/search.py. Modified application/vertical_slice.py.
No master specification or accepted domain/port contracts were changed.

Created tests/unit/research/: test_query_taxonomy.py, test_search_planning.py,
test_applicability.py, test_strategist.py, test_search_critique.py,
test_coverage_floor.py, test_provider_query_compilation.py. Created tests/unit/providers/:
test_http_runtime.py, test_registry.py, test_openalex.py, test_crossref.py, test_github.py.
Created tests/unit/test_phase3_architecture_guards.py. Modified only the explicitly
obsolete Phase 1 whole-production provider prohibitions in test_phase1_architecture_guards.py;
domain/network isolation, no SDK/test imports and no later semantic logic remain enforced.

Created tests/fixtures/phase3.py and synthetic provider_responses/{openalex,crossref,github}/
JSON fixtures. Created integration/test_phase3_screening_pipeline.py,
integration/test_phase2_slice_with_phase3_planner.py,
adversarial/test_phase3_search_strategy_attacks.py and network/test_phase3_live_provider_smoke.py.

Created ADR-013, ADR-014, ADR-015-phase3-provider-set.md, docs/providers/provider-matrix.md,
docs/traceability/phase-3.yaml, this report and the supplied Phase 3 plan.
Modified README.md, pyproject.toml and uv.lock (httpx is the only new direct dependency).
Paths above are relative to src/novelty_harness/, tests/ or docs/ as appropriate.

## Requirements

Implemented Phase 3 subsets of FR-EV-001/002; FR-SRCH-001/002/003/004;
FR-PROV-003/004; FR-OBS-001/002; FR-SEC-001/002/003/004. FR-EV-003 has extensible
family/context contracts only: discovery-triggered activation/escalation is deferred.
Sections 13-17, 42, 45-47, 54-56, 60 Phase 3, 61-62 are mapped in phase-3.yaml.
No strong positive novelty permission, real evidence equivalence or calibrated probability
is claimed. This is research planning and screening infrastructure, not novelty intelligence.

## Verification

Accepted baseline before edits: uv sync --dev PASS; uv run python scripts/verify.py
PASS (788 tests, Ruff clean, Pyright 0 errors); git diff --check PASS.

Latest implementation verification: uv sync --dev PASS (25 resolved, 24 checked);
uv run python scripts/verify.py PASS (137 formatted files, Ruff clean, Pyright 0
errors/warnings, 901 passed / 3 live tests deselected); git diff --check PASS.
904 total tests are collected. Task 13 adversarial suite: all 15 Phase 3 cases PASS;
all Phase 2/3 adversarial tests: 43 PASS. Full integration suite reaches
REPORTED/COMPLETED without network, with real Phase 2/3 components.

Opt-in command only: NOVCHECK_LIVE_SMOKE=1 uv run pytest tests/network -m network
--force-enable-socket -v -rs. Result: OpenAlex PASS, Crossref PASS, GitHub PASS;
3 passed in 3.97s. No pagination/deep research or model API was used in these smokes.
Live success does not establish corpus coverage; future unavailable credentials,
quota or network produces explicit skips, never weaker deterministic assertions.

Fresh checkout: pending. Final fresh-context independent review: pending.

## Architecture and safeguards

The implemented adapters and capability limitations are detailed in provider-matrix.md.
Neutral intent remains distinct from actual provider syntax. SearchProvider stays async
and unchanged. Provider-local scores remain scoped; duplicate DOIs are not independent
evidence. Known resolved credentials are removed from returned JSON and excluded from
compiled requests and attempt records. External response schemas validate used fields
strictly and ignore unknown provider metadata as documented interoperability policy.

HTTP requests are serialized/paced; timeout defaults to 20s, retry limit to three,
backoff to 1s exponential. Retry-After/reset metadata is honored. Only idempotent
transient requests retry; 400/401/ordinary 403 are explicit terminal failures.
Attempts and logical query IDs persist even when a retry eventually succeeds;
such a run is DEGRADED. Fallback events require explicit primary/fallback/reason.

The strategist and critic use separate versioned semantic task requests. Critic
context is only CIR, MCUs, applicability and persisted plan, without strategist
private context or call history. A complete checklist is required. Deterministic
guards can overrule an optimistic model PASS. Revisions are bounded and re-reviewed;
exhaustion is BLOCKED. Screening revalidates the hash-bound PASS artifact.

Every MCU has nine applicability assessments independently of registry availability.
Exclusions require rationale, semantic-incompatibility basis and grounded input support;
provider/user absence claims and unsupported exclusions remain UNRESOLVED. Semantic
grounding is not proof of entailment; the critic also examines family omissions.
Missing providers yield BLOCKED_NO_PROVIDER, never family irrelevance. Actual successes,
failures, diversity and complete query/provider pairs determine coverage states.

## ADRs and deviations

ADR-013 preserves accepted legacy schemas via a new rich ResearchPlan and projection,
and confines httpx to providers. ADR-014 documents configurable operational floors.
ADR-015 documents the provider set and explicit fixture boundary (first written at
Task 12, when that material integration decision was needed; finalized/named at Task 14).

Task 1 initially committed with a failing test fixture identifier (query_control instead
of the accepted qry_ prefix) due to an orchestration error after polling verification.
The task ledger refused completion. e3b9f60 corrected the fixture; full verification
passed before Task 2 code began. No contracts/tests were weakened. Subsequent task
commits were conditional on a verified zero exit code. Inline TDD execution used one
whole-phase final review rather than per-task subagents, per executing-plans workflow.

## Acceptance gates

| Gate | Result / evidence |
| --- | --- |
| 1 | PASS: accepted baseline verified before edits |
| 2 | PASS: worktree verification 901 deterministic tests |
| 3 | PENDING: fresh checkout |
| 4 | PASS: all nine families for every MCU |
| 5 | PASS: assessor has no registry/provider availability input |
| 6 | PASS: plausible branches screened or explicitly blocked/degraded |
| 7 | PASS: eleven QueryFamily values |
| 8 | PASS: diverse, purpose-bearing real plans |
| 9 | PASS: neutral/compiled contracts and separate translators |
| 10 | PASS: independent critic can revise/block |
| 11 | PASS: screening requires bound PASS, detects changed plan |
| 12 | PASS: documented configurable operational policy, not confidence |
| 13 | PASS: missing providers remain explicit blockers |
| 14 | PASS: timeout/transport/retry/rate/terminal-4xx tests |
| 15 | PASS: OpenAlex shared/recorded contracts |
| 16 | PASS: Crossref shared/recorded contracts |
| 17 | PASS: GitHub shared/recorded contracts |
| 18 | PASS: synthetic credential redaction and external credential refs |
| 19 | PASS: provider-local scores/ranks, no fusion/comparison |
| 20 | PASS: OpenAlex failure + Crossref success yields DEGRADED |
| 21 | PASS: zero hits do not generate novelty/saturation |
| 22 | PASS: PATENT stays plausible and explicitly blocked |
| 23 | PASS: structured artifacts persisted with schema-validated models |
| 24 | PASS: fifteen Phase 3 adversarial cases |
| 25 | PASS: real Phase 2/3 slice reaches REPORTED/COMPLETED |
| 26 | PASS: default tests block live sockets |
| 27 | PASS: isolated opt-in network marker, three smokes pass |
| 28 | PASS: implemented/planned provider matrix truthful |
| 29 | PASS: README and traceability document scope |
| 30 | PASS: Phase 4 has not started |

## Remaining limitations

Planning/applicability/criticism are model-assisted via an injected abstract LLMProvider;
recordings prove deterministic safeguards, not deployed model robustness. No production
model adapter is supplied. No patent/general-web/standards/regulatory/archive provider
exists yet. Metadata and repository timestamps are not verified chronology. Screening
is deliberately first-page only and does not establish independent evidence or absence.
Adaptive/fusion/citation/entity/saturation stages remain deferred; source/provenance,
equivalence/support reasoning, prosecutor/defender, adjudication and full later report
semantics remain fixture-backed/deferred. The minimal nine-question compiler copies
frozen findings. No Phase 4 work is authorized or implemented.
