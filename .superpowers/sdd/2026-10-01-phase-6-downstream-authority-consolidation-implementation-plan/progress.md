# SDD ledger — plan: docs/superpowers/plans/2026-10-01-phase-6-downstream-authority-consolidation-implementation-plan.md

Baseline: `750917734fbed622f785f96e3d1d443dea166fe7`, branch `phase-6-evidence-verification`, linked worktree `/private/tmp/novcheck-phase6.WORKTREE`. Pre-existing modified R15 review and untracked approved design/plan are reserved for Task 12. Baseline `uv run python scripts/verify.py`: 1607 passed, 5 deselected, Ruff/format/Pyright clean.

## Preflight task consistency scan

| Task | Its tests against code/files | Finding |
| --- | --- | --- |
| 1 | Contract model tests before two new contract files | Coherent; ledger contracts are defined here for Pyright. |
| 2 | Ledger persistence tests before four schema-v7 tables and port | Historical-loader assertion precedes loader in Task 6; defer that assertion, test absence of fabricated rows now. |
| 3 | Candidate/target recording tests before pipeline write | Coherent; Task 2 writer is available. |
| 4 | Failure/context tests before pipeline transitions | Coherent; retain R11/R12 postcommit trace rule. |
| 5 | Derived dependency tests before pipeline summaries | Coherent; capture only committed comparison inputs. |
| 6 | Snapshot tests before loader | Graph/membership interleaving assertion precedes Task 7; test single semantic/ledger transaction here, extend to graph in Task 7. |
| 7 | R15 tests before graph authority loader gate | Coherent; do not downgrade corrupt graph to no-direct. |
| 8 | Parity tests before loader corrections | Coherent; old adapter remains until Task 11. |
| 9 | View fixture/report tests before new protocol/compiler | Coherent; compiler revalidates through repository. |
| 10 | Full slice tests before consumer migration | Coherent; fixture adapter is injected, not real Phase 7. |
| 11 | Architecture guard before adapter removal | Task 10 already removes production call; guard must assert removal of production definition, not only calls. |
| 12 | Documentation check before ADR/traceability update | Coherent; final exact-commit checkout after commit. |

## Shared file/interface scan

| Tasks | Interface crossing | Finding |
| --- | --- | --- |
| 1/2 | `assessment_ledger.py` types to SQL rows and repository port | Type names/signatures align. |
| 1/6 | `assessment_view.py` types to snapshot loader | Loader must construct validated immutable view. |
| 1/7 | `projection_status` to graph validator | Graph-backed state requires v6 membership. |
| 1/8 | Rich fields to parity suite | No adapter deletion before parity. |
| 1/9 | View contract to report/fixture | A deserialized view is not authority; repository reload required. |
| 2/3 | Ledger writer to pipeline targets/candidates | Snapshot completes after semantic commits. |
| 2/4 | Candidate rows to failures/context | Failure rows do not claim commit. |
| 2/5 | Derived rows to summary/patent | Dependencies must bind committed IDs and cutoff. |
| 2/6 | Schema-v7 rows to loader | No historical backfill. |
| 3/4 | `phase6_pipeline.py` selection to candidate outcome | Same candidate identity, distinct outcome. |
| 3/5 | Pipeline snapshot to derived output | Summary/patent included before final snapshot hash. |
| 3/10 | `Phase6EvidenceResult.snapshot_id` to slice | Locator only. |
| 4/5 | Failure exclusion to derived inputs | Rejected candidate cannot contribute. |
| 4/6 | Context/failure rows to view | Status and limitations preserved. |
| 5/6 | Derived rows to loader | Validate exact dependencies and lineage. |
| 6/7 | Single read transaction to graph checks | Same Session; no nested public reads. |
| 6/10 | Loader to real slice | Reopen repository by assessment+snapshot. |
| 7/8 | Graph authority to parity | Graph relation cannot be inferred from semantic status. |
| 7/9 | Authorized relation to fixture/report | Revalidate current repository state. |
| 7/10 | Loader fail-closed to lifecycle | Integrity failure prevents report completion. |
| 8/11 | Parity suite to adapter removal | Keep diagnostic only until parity passes. |
| 9/10 | `Phase6FixtureAdjudicator` and report to slice | Earlier `AdjudicationEngine` unaffected. |
| 10/11 | Production adapter call to retirement | Remove trusted call first, definition last. |
| 10/12 | New export and lifecycle to docs | Label export derived/nonauthority. |
| 11/12 | Adapter retirement to ADR/README | Historical review remains unchanged. |

Ruling: Task 2 checks migration creates no historical ledger; Task 6 tests the unavailable-loader error — because the loader does not exist in Task 2. Cost if wrong: migration gap might be discovered later, but Task 6 is a mandatory gate.

Ruling: Task 6 tests consistent semantic/ledger reads; Task 7 extends the interleaving probe to membership and projection — because graph validation is Task 7's deliverable. Cost if wrong: a transaction bug could surface one task later.

Ruling: Task 11's guard rejects the production adapter definition as well as trusted calls — because Task 10 must already remove the only production call. Cost if wrong: a diagnostic helper must move into tests before the guard passes.

## Task completion

| Task | Commits | Focused verification | Review |
| --- | --- | --- | --- |
| 1 | `0957f78`, `0af677c` | 6 contract tests, Pyright 0 errors, Ruff clean | PASS after cited-passage completeness fix |
| 2 | `1da0af5`, `74ecbd9`, `e0807f0` | 112 ledger/SQL/authority tests, Pyright 0, Ruff clean | PASS after top-level and nested clock replay fixes |
| 3 | `dbc94abcafdf7537dddb4f665c9cc797e4666630` | `scripts/verify.py`: Ruff/format/Pyright clean, 1631 passed, 5 deselected | PASS; bounded source/version facts retained |
| 4 | `b1ec218`, `11d5beb` | Focused Phase 6 pipeline/R10/R11-R12: 43 passed; `scripts/verify.py`: Ruff/format/Pyright clean, 1634 passed, 5 deselected; `git diff --check` passed | Implemented failure-stage ledger rows, authority-rejection rows, context outcomes, and post-commit trace refs; review P1 fixed by retaining expansions and limitations on assessed rows |
| 5 | `abbb481`, `8da437f` | Focused pipeline/patent: 24 passed; R11/R12: 21 passed; R10–R14/provenance milestone: 109 passed; Pyright/Ruff clean | PASS; derived inputs and persisted lineage bound before post-ledger publication |
| 6 | `9239442`, `04c1b0b`, `83665a9`, `ac5f80d`, `bfe62e6`, `d75b332` | Loader/ledger/pipeline/R10/R13: 88 passed before pair fix; 38 focused + 41 R10/R13 after; Pyright/Ruff clean | PASS after descriptor, derived, row metadata, multi-root and exact manifest-pair fixes; graph-backed read remains fail-closed for Task 7 |
| 7 | `7f3a892354e2c540b9590cec0b9ba7f98c782075`, `f151fa8335b6e332510d1f054f74ba391d8d976b` | R10–R15, provenance, assessment-view/graph repository: 173 passed; relation matrix plus loader integration: 23 passed; Pyright 0; Ruff/format/diff clean | Implemented exact current graph membership authority, semantic-only/nonrelational statuses, corruption failure, v5 no-backfill regression. R11 rejected descriptor persistence was narrowed to explicit untrusted CONTENT_AUTHORITY outcomes. Added every reachable projected relation-kind matrix; superficial is helper-tested as no-edge because the current validated classifier cannot produce that persisted state. Track classifier reachability in Tasks 8/12. R15 remains open for independent review. |

Task 7 review: PASS after the relation-kind matrix. The production legacy adapter still exists for Task 8 parity and Task 10–11 migration; R15 is not independently closed.

Task 8: complete (commits `f151fa8..1b7a6b0`, tests: focused parity/view/benchmark `17 passed`; Phase 6 adversarial `232 passed`; Pyright/Ruff/format/diff clean). Report: `.superpowers/sdd/2026-10-01-phase-6-downstream-authority-consolidation-implementation-plan/task-8-report.md`. `SUPERFICIAL_SIMILARITY` remains uncommittable under the validated classifier; the existing no-edge test is helper-level only, not a fabricated persisted class.

Task 8 review follow-up complete: commit `4fe93a73a2cf173080b78781b9244681416e06a4`. Added repository-loaded scoped-partial and citation-state assertions, exact coverage/patent/lineage/dependency checks, a constrained passage limitation, and persisted/reloaded unassessable candidate proof. Follow-up focused suite 38 passed; parity/view/benchmark suite 20 passed; Phase 6 adversarial suite 232 passed; Pyright/Ruff/format/diff clean. Updated `task-8-report.md`.

Task 9 complete with review fixes: report compilation enforces fixture provenance and UNASSESSABLE overall/MCU verdicts, and requires DIRECT_PRECEDENT finding state for decisive direct evidence. Focused report/full-slice/Phase 1 suite: 40 passed; Pyright 0 errors; Ruff and format checks clean. Report: `.superpowers/sdd/2026-10-01-phase-6-downstream-authority-consolidation-implementation-plan/task-9-report.md`. Scoped follow-up commit created.

Task 10 complete: commit `bfd52f0` migrates the real Phase 6 slice to repository-loaded `Phase6AssessmentView` with an explicit Phase 7 fixture injection, a derived snapshot/commit export, view-backed report and summary, and no trusted real-Phase-6 `evidence_edges.jsonl`. Focused slice/Phase 1/R15/architecture suite: 47 passed. Initial full verifier: 1704 passed, 5 deselected, 2 architecture-test failures; integration-test repair `9872a74` resolved them. Final `uv run python scripts/verify.py`: Ruff/format/Pyright clean, 1706 passed, 5 deselected. Report: `.superpowers/sdd/2026-10-01-phase-6-downstream-authority-consolidation-implementation-plan/task-10-report.md`. Phase 7 remains fixture-only; Task 11 adapter retirement and Task 12 documentation/review remain.

Task 11 complete: commit `5d26c91809d7f79508250082960adf080477f87d` retires the production `project_verified_edges` adapter and moves historical receipt/negative-control comparisons into an explicitly nonauthoritative test-only diagnostic module. Production architecture guard observed RED on the old definition, then passed. R11 positive uses the repository loader; R15 caller-created view/receipt regression added. Focused R10–R15/parity/full-slice suite: 134 passed. Final `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run python scripts/verify.py`: Ruff/format/Pyright clean, 1708 passed, 5 deselected; `git diff --check` clean. Report: `.superpowers/sdd/2026-10-01-phase-6-downstream-authority-consolidation-implementation-plan/task-11-report.md`. No Phase 7 logic; Task 12 documentation, exact-commit verification, and independent review remain.

Task 11 review follow-up complete: commit `5e52ee8e531ce23cb75beae1efbdca8a3dab92d4` converts R13 positive direct/replay, receipt reopen, semantic polarity, and strong-partial assertions to complete repository-loaded assessment snapshots. Historical negative diagnostic attacks remain. Initial new loader assertion RED on missing snapshot; R13 26 passed, R10–R15/parity/full-slice 134 passed, final `UV_CACHE_DIR=/private/tmp/novcheck-uv-cache uv run python scripts/verify.py` Ruff/format/Pyright clean and 1708 passed/5 deselected; `git diff --check` clean. No production or Phase 7 change. Task 12 and independent review remain.
