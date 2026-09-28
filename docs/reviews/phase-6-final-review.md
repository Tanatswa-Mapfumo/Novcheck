# Phase 6 independent semantic review

**Reviewer/model:** Independent GPT-6 Sol High reviewer, with coordinator reproduction and verification. The reviewer did not implement Phase 6.
**Reviewed branch/commit:** `phase-6-evidence-verification` at `e4683fdd6e050904bab6a5ffe85703992d8de964`.
**Decision:** **FAIL**. This is a final record of the review of that commit, not semantic acceptance. Findings F01-F11 remain open; no implementation fixes or regression tests were added by the reviewer. Re-review the changed areas after fixes. Do not start Phase 7 on the basis of this review.

## Method

Read `AGENTS.md`, the master spec, Phase 5 completion, the approved Phase 6 plan, Phase 6 completion, the review request, ADR-026 through ADR-029, then the Phase 6 code, tests, benchmark and fixtures. Inspected the actual passage-to-claim-to-verification-to-edge-to-classification flow rather than treating schema validity or test count as semantic proof. Used read-only offline counterexamples with valid Pydantic artifacts and the deterministic gates; no live providers or network calls. The GPT-6 Sol High reviewer ran the shipped adversarial and benchmark tests (23 passed). The coordinator reproduced the missing-citation, version-chronology, foreign-identity, and omitted-qualifier failures independently. The full suite passes but does not cover these counterexamples.

## Critical findings

### F01. Statement-only material qualifier disappears

- **Invariant:** INV-02, INV-03, INV-14: direct precedent must cover the claimed relationship/configuration, not just a component or nearby mechanism.
- **Affected:** `src/novelty_harness/evidence/mapping/dimensions.py:234` (`build_proposition`); downstream `src/novelty_harness/evidence/precedent/gates.py:282` (`classify_precedent`).
- **Minimal reproduction:** Valid MCU with `statement="A relay activates only after two independent sensors agree"`, `mechanism="threshold switches relay"`, and other structured fields empty. `build_proposition(build_mcu_comparison_profile(mcu))` yields only `('mech', 'threshold switches relay')`; the two-sensor condition is absent. A passage saying only "A threshold switches a relay" can then be verified against every generated commitment and classified decisive `DIRECT_PRECEDENT`.
- **Current / required:** Current direct classification ignores the material condition in the MCU statement. Required: every material expressed claim constrains equivalence; if reconciliation cannot reliably preserve it, direct classification must abstain rather than infer support.
- **Smallest fix:** Reconcile material statement qualifiers with structured commitments before verification, or deterministically block decisive support when the statement contains unresolved material content. Do not fabricate a relationship.
- **Regression:** An end-to-end conditional/conjunction MCU whose source supports only its generic mechanism must not produce `DIRECT_PRECEDENT`; a source supporting the complete configuration may do so.

### F02. Old source chronology launders a post-cutoff version

- **Invariant:** FR-EXP-003 and the cutoff rule: the *cited disclosure* must predate `as_of`.
- **Affected:** `src/novelty_harness/evidence/verification/gates.py:274` (`assess_chronology`), `:325` (`build_verified_evidence_edge`), `src/novelty_harness/evidence/phase6_pipeline.py:148` (`_best_version`).
- **Minimal reproduction:** `SourceRecord.dates.publication_date=2020-01-01`, cited `SourceVersionRecord.published_date=2027-01-01`, `as_of=2026-09-28`, all commitments marked supported. The edge reports `PREDATES_CUTOFF`, `decisive=True`, and the classifier returns `DIRECT_PRECEDENT`. The edge gate never receives the version publication date.
- **Current / required:** Current chronology uses the earliest source-level date even for content introduced later. Required: post-cutoff version content cannot negate historical novelty; unknown version timing must remain uncertain.
- **Smallest fix:** Pass the cited version's public date into chronology eligibility and conservatively combine it with source-level dates; ensure selected passages belong to that version.
- **Regression:** Old preprint with a new post-cutoff claim in a revised version must not be decisive; older eligible version remains independently assessable.

### F03. A selected excerpt can hide a nearby negation

- **Invariant:** INV-14, FR-EVID-005: the exact cited evidence, including material same-source context, must support the claim.
- **Affected:** `src/novelty_harness/evidence/verification/verifier.py:91` (`verify_with_context_retry`); `src/novelty_harness/evidence/context/selection.py:69` (`select_support_passages`).
- **Minimal reproduction:** Mapped passage: "The method is effective." Available wider passage from the same source/version: "The method is effective. However, in all tested cases it failed after a week." A verifier reasonably returns `SUPPORTED` for the isolated sentence. Retry exits immediately with zero expansions, leaving a potentially decisive edge.
- **Current / required:** Current context expansion happens only after an `INSUFFICIENT_CONTEXT` response; a qualifier that the verifier never sees cannot trigger it. Required: decisive support must not be established from a known incomplete excerpt that omits nearby material qualification.
- **Smallest fix:** Add a bounded same-source context-completeness check before decisive support, or present the bounded surrounding context with the initial verification. This changes the approved plan's insufficient-only expansion policy and needs an explicit ADR or user decision.
- **Regression:** With the nearby negation, the claim is contradicted or unresolved, never decisive; same-source and same-version boundaries remain enforced.

## Important findings

### F04. Candidate and version truncation omit relevant precedent

- **Invariant:** INV-11 and FR-SRC-001: a bounded local search must expose its coverage limits, and source versions cannot be silently collapsed.
- **Affected:** `src/novelty_harness/evidence/phase6_pipeline.py:121` (`select_candidate_sources`), `:148` (`_best_version`).
- **Minimal reproduction:** Five eligible sources sorted by source ID, with the only direct source fourth; the default `max_sources_per_mcu=3` never maps it. Separately, an older version contains the exact pre-cutoff mechanism while a later observed version differs; `_best_version` maps only the latter.
- **Current / required:** Current local output can appear exhaustive for processed candidates, with omitted sources/versions not represented as unassessed. Required: skipped work is explicit and an earlier relevant version is not lost.
- **Smallest fix:** Record candidate/version exclusions and bounded coverage; compare relevant versions under a documented selection policy. Do not infer global absence from the local remainder.
- **Regression:** Fourth-source decisive hit and older-version-only hit are surfaced or explicitly marked unassessed, never reported as exhaustive local coverage.

### F05. Supported commitments can cite zero passages

- **Invariant:** INV-14: a decisive citation must support its proposition.
- **Affected:** `src/novelty_harness/evidence/verification/gates.py:95` (`validate_judgments`), `:373` (`build_verified_evidence_edge`), `src/novelty_harness/evidence/verification/prompts.py` (`CommitmentJudgmentProposal`).
- **Minimal reproduction:** Bundle passage "Unrelated: the operator manually opens a valve." Valid verifier proposal marks both material commitments `SUPPORTED` with `passage_ids=[]`. Aggregation returns `SUPPORTED` and `relied_on_passage_ids=()`. The edge falls back to mapper passage `pass_1`, becomes decisive, and the classifier returns `DIRECT_PRECEDENT`.
- **Current / required:** Current schema checks only invented IDs, not absent citations; mapper IDs substitute for verifier reliance. Required: each supported or contradicted commitment identifies at least one supplied passage; a decisive edge must use verifier-cited passages.
- **Smallest fix:** Reject empty citations for evidential judgments and remove mapper-citation fallback for support-bearing/decisive edges.
- **Regression:** All-supported response with empty passage lists must fail validation or stay nondecisive; no direct graph edge may be emitted.

### F06. Cross-stage identity joins are incomplete

- **Invariant:** INV-14 and source/version integrity: evidence for one proposition or version cannot establish another.
- **Affected:** `src/novelty_harness/evidence/precedent/gates.py:161` (`classify_precedent`), `src/novelty_harness/evidence/verification/gates.py:325` (`build_verified_evidence_edge`), `src/novelty_harness/evidence/precedent/patent.py:56` (`PatentEvidenceEntry`).
- **Minimal reproduction:** `ClassificationFacts(source_id='src_other', source_version_id='srcv_other', mapping=src_1/srcv_1 mapping, verification=src_1/srcv_1 SUPPORTED, decisive=True, chronology_state='PREDATES_CUTOFF')` returns `DIRECT_PRECEDENT` for `src_other`. An edge accepts a different proposition ID when MCU ID matches; patent entry validation checks source ID but not version/MCU ID.
- **Current / required:** Current validation permits semantically unrelated artifacts to be joined. Required: source, version, MCU, proposition, mapping, claim and verification identities agree at each boundary.
- **Smallest fix:** Add explicit cross-object identity checks to each public gate/contract, without changing their substantive classification rules.
- **Regression:** One negative case for each foreign source, version, proposition, mapping/verification, and patent MCU join; no direct classification is emitted.

### F07. Graph persistence trusts a self-declared verification reference

- **Invariant:** FR-EVID-004 and INV-14: decisive graph relationships require an eligible, traceable verified edge.
- **Affected:** `src/novelty_harness/evidence/graph/models.py:170` (`GraphEdge.phase_boundaries_and_eligibility`), `src/novelty_harness/evidence/graph/sqlalchemy_repository.py:118` (`_persist_edge`).
- **Minimal reproduction:** Persist a `DIRECT_PRECEDENT` graph edge with `EdgeVerificationRef(verified_edge_id='edge_does_not_exist', support_state=SUPPORTED, decisive=True, precedent_relation=DIRECT_PRECEDENT)`. It is accepted with valid graph endpoints despite no corresponding verified artifact.
- **Current / required:** Current reference is only a self-assertion. Required: the referenced verified edge exists and matches the graph relation, source/MCU, support state and chronology eligibility.
- **Smallest fix:** Resolve and validate the referenced verified artifact transactionally at graph persistence (or through a verifiable repository port).
- **Regression:** Fake or mismatched verified-edge IDs cannot be persisted as decisive; legitimate projected edges still persist.

### F08. Patent multi-reference context counts future and duplicate lineage

- **Invariant:** FR-EXP-003, INV-07, and one-reference anticipation-style screening.
- **Affected:** `src/novelty_harness/evidence/precedent/patent.py:88` (`screen_patent_references`), `:143` (contributing-entry count).
- **Minimal reproduction:** Two partial patent entries published in 2027 produce `MULTI_REFERENCE_COMBINATION_LIKE` for a 2026 assessment. Two versions/publications of one patent family also count as two entries. The function receives neither cutoff nor lineage roots.
- **Current / required:** Current combination context can be post-cutoff or non-independent. Required: post-cutoff references cannot challenge the historical cutoff, and one family/root is not two independent references. Neither case may become single-reference anticipation.
- **Smallest fix:** Supply cutoff and lineage identity to screening, retain ineligible references as limitations, and count distinct eligible roots.
- **Regression:** Two future partial patents and two versions of one patent family do not produce eligible multi-reference context; two independent pre-cutoff partial patents do, without anticipation.

### F09. Unverified mapping claims influence precedent class

- **Invariant:** INV-02 and INV-14: mapper relevance is not verified support or equivalence.
- **Affected:** `src/novelty_harness/evidence/precedent/gates.py:224` (`functional_matched`), `:282` (all-supported direct branch).
- **Minimal reproduction:** Keep commitment-level verification fixed while adding an unverified `PURPOSE` match to mapper dimensions; `COMPONENT_PRECEDENT_ONLY` changes to `ANALOGOUS_PRECEDENT`. Conversely, all commitments marked supported with a mapper-conflicting directed relationship still becomes `DIRECT_PRECEDENT`.
- **Current / required:** Current analogy can rest on mapping alone, while a material mapper conflict is ignored in the direct branch. Required: functional analogy has verified support; a material conflict must be resolved before direct precedent.
- **Smallest fix:** Tie functional dimensions to verified commitment/passage IDs and gate direct on unresolved material conflicts.
- **Regression:** Unverified purpose match does not change precedent class; conflicting relationship prevents direct until independently resolved.

### F10. Narrow special-case evidence is not represented as partial support

- **Invariant:** INV-14 and plan Task 14: a supported subset cannot support an unqualified universal claim, and supported/unsupported portions should be preserved.
- **Affected:** `tests/benchmarks/test_phase6_support_verifier.py:105` (`special-case-only`), `src/novelty_harness/evidence/verification/gates.py:124` (`aggregate_verification`).
- **Minimal reproduction:** Proposition "works for all workloads"; exact passage "works only for read-only workloads". Benchmark expects `INSUFFICIENT_CONTEXT`; the known subset and failed generalization are not recorded as partial support.
- **Current / required:** Current single-commitment state cannot express the supported special case plus unsupported remainder; asking for more context obscures a known limitation. Required: record the narrower support and unsupported universal extrapolation without making the whole proposition supported.
- **Smallest fix:** Split quantified/conditional material into assessable commitments or add a strictly scoped within-commitment partial-support representation, preserving existing public semantics where possible.
- **Regression:** The read-only-workload passage yields nondecisive partial support with its subset and remainder; an unqualified universal passage may be fully supported.

### F11. Existing full-slice edge validation rejects valid Phase 6 output

- **Invariant:** Phase 6 Task 12 requires the accepted end-to-end slice to carry real combination and context-expansion evidence through the lifecycle.
- **Affected:** `src/novelty_harness/application/vertical_slice.py:327` (`_check_edges`).
- **Minimal reproduction:** A valid Phase 6 combination target has `mcu_comb_*` ID, absent from the plain MCU-ID set; `_check_edges` rejects it as unknown. A verifier-cited same-source expanded context passage is absent from the original Phase 5 passage set; `_check_edges` rejects it as wrong-source.
- **Current / required:** Current bridge rejects valid Phase 6 edge identities in these paths. Required: the slice accepts combination target IDs and verified expansion passage IDs while still rejecting foreign source/version IDs.
- **Smallest fix:** Extend the bridge's identity index from the persisted Phase 6 combination and context-expansion artifacts.
- **Regression:** Full slice reaches `REPORTED`/`COMPLETED` with one combination edge and one expanded-passage edge; foreign IDs remain rejected.

## Minor observation

**M01.** `tests/benchmarks/test_phase6_support_verifier.py:322` calls a rationale "faithful" if it is nonblank and cites a supplied passage. It does not test entailment or rationale grounding. The eight-case lexical baseline is useful as a deterministic diagnostic, but its reported 1.0 metrics are not model-quality or passage-faithfulness evidence. Rename/qualify that metric before citing it as such; this does not independently block gate 30.

## Attack ledger

`Held` below means the deterministic gate held with the supplied semantic labels; it does not prove an actual LLM will infer those labels correctly.

| # | Required attack | Result at reviewed commit |
|---|---|---|
| 1 | Same nouns, different causal relation | Held with correctly labeled verifier result; F01/F09 expose omissions/conflicts. |
| 2 | Different words, equivalent mechanism/relation | Held with supplied equivalent label; live semantic inference unmeasured. |
| 3 | Relevant abstract, unsupported proposition | Held with supplied unsupported label. |
| 4 | Narrower special case | F10: recorded as insufficient instead of scoped partial. |
| 5 | Adjacent negation/qualifier | F03: no context retry after initially supported excerpt. |
| 6 | Equivalent evidence after cutoff | Source-date gate holds; F02 fails for later version of older source. |
| 7 | A/B/C each supplies one part | Held: no multi-source direct stitching. |
| 8 | One source has components, not configuration | Held when configuration is a commitment; F01 can omit it. |
| 9 | Superficially similar analogy | Held with correct label; F09 admits unverified mapper analogy. |
| 10 | Tier-A unsupported | Held: quality excluded from entailment. |
| 11 | Lower-quality genuinely supported | Held: quality does not veto support. |
| 12 | Revision retracts older claim | F02/F04: version chronology and single-version choice fail. |
| 13 | Two patents jointly cover claim | Held for one-reference anticipation; F08 miscounts future/duplicate partial context. |
| 14 | Prompt injection in passage | Scripted tests preserve data boundary; live model resistance unmeasured. |
| 15 | Passage/source/version mismatch | Basic passage checks hold; F06/F07 fail cross-artifact joins. |
| 16 | Mapper proposes unsupported relationship | Held with correct verifier label; F05/F09 permit structural bypass. |
| 17 | Separate statements, unsupported conjunction | F01 can omit the conjunction; F09 can ignore conflict. |
| 18 | Conditional made unconditional | Existing conditional benchmark abstains; F01 loses statement-only condition. |
| 19 | Context/population generalization | Held with correct label; F10 mishandles known narrower subset. |
| 20 | Local no-direct becomes global absence | Local-only flag and global-absence prohibition hold; F04 still hides unassessed coverage. |

## Fix/re-review status and verification

- **Fixes:** None. This is an independent review; implementing or redesigning Phase 6 was outside the review role.
- **Regression tests added:** None. F01-F11 each specify a required regression. No Critical/Important finding is closed.
- **Baseline verification at `e4683fd`:** `uv run python scripts/verify.py` passed (Ruff check, Ruff format check of 284 files, Pyright 0 errors, pytest **1389 passed, 5 network tests deselected**). `git diff --check` passed on the clean baseline. Reviewer subset: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/adversarial/test_phase6_equivalence_attacks.py tests/benchmarks/test_phase6_support_verifier.py` passed **23/23**. These green results do not close the reproduced semantic findings.
- **After-review artifact checks:** `uv run python scripts/verify.py` passed after this review document was added: Ruff check passed, Ruff format check passed (284 files), Pyright reported 0 errors/0 warnings, and pytest reported **1389 passed, 5 deselected** in 23.38 s. `git diff --check` passed. The review file is untracked, so `git diff --no-index --check /dev/null docs/reviews/phase-6-final-review.md` was also run; it produced no whitespace diagnostics (exit 1 denotes the expected content difference).
- **Fresh checkout:** Not run. It is an acceptance prerequisite after findings are fixed, not evidence that can cure open findings.
- **Acceptance gate 30:** **FAIL**. The mandatory independent GPT-6 Sol High review is complete, but open Critical and Important findings remain. Phase 6 is **not semantically accepted**. Phase 7 was neither started nor designed by this review.

---

## Remediation record (post-FAIL)

The **FAIL decision, findings F01–F11, the Minor observation M01 and all
verification evidence above remain the authoritative record of reviewed commit
`e4683fd` and have not been overwritten.** This section records the implementer
fixes made under
`docs/superpowers/plans/2026-09-28-phase-6-semantic-review-remediation-plan.md`.
Every Critical/Important finding has a stable regression in
`tests/adversarial/test_phase6_sol_review_regressions.py` (37 tests) plus
focused module tests. The mapper -> verifier -> eligibility -> classifier
separation, conservative abstention and the no-novelty-score rules are
preserved.

| Finding | Fix commit | Regression test(s) | Focused verification | Status |
| --- | --- | --- | --- | --- |
| F05 empty evidential citations | `6e416a4` | `test_f05_supported_without_citations_is_rejected`, `test_f05_mapper_passages_cannot_substitute_for_verifier_citations` | regression suite; `tests/unit/evidence/verification` | Awaiting re-review |
| F06 incomplete identity joins | `6e416a4` | `test_f06_foreign_source_version_proposition_joins_are_rejected`, `test_f06_patent_entry_mcu_and_version_joins_are_rejected` | regression suite; `tests/unit/evidence/precedent`, `tests/unit/evidence/verification` | Awaiting re-review |
| F07 self-declared verification refs | `6e416a4` | `test_f07_graph_persistence_rejects_unresolved_or_mismatched_verification`, `test_f07_schema_v1_migrates_to_v2` | regression suite; `tests/unit/evidence/graph` | Awaiting re-review |
| F02 post-cutoff version laundering | `f54917c` | `test_f02_post_cutoff_revision_of_old_source_is_not_decisive`, `test_f02_unknown_version_timing_stays_uncertain`, `test_f02_older_eligible_version_remains_independently_assessable`, `test_f02_later_source_level_date_is_combined_conservatively` | regression suite; `tests/unit/evidence/verification` | Awaiting re-review |
| F04 candidate/version truncation | `f54917c` | `test_f04_fourth_source_is_explicitly_unassessed`, `test_f04_older_version_is_assessed_not_silently_dropped`, `test_f04_selection_helpers_report_bounds` | regression suite; `tests/integration/test_phase6_evidence_pipeline.py` | Awaiting re-review |
| F01 statement-only material qualifier | `bdcd688` | `test_f01_statement_only_condition_is_material_and_blocks_generic_direct`, `test_f01_conditional_conjunction_quantified_sequence_and_only_if_conditions` (6 variants), `test_f01_structured_statement_coverage_does_not_add_material_noise` | regression suite; `tests/unit/evidence/mapping` | Awaiting re-review |
| F10 narrower special case | `266aa00` | `test_f10_narrower_special_case_is_scoped_partial_support`, `test_f10_partial_commitment_requires_a_citation_and_scoped_fields` | regression suite; benchmark `special-case-only` now expects scoped partial support | Awaiting re-review |
| F03 hidden nearby negation | `07d892d` | `test_f03_nearby_negation_cannot_be_hidden_by_a_short_excerpt`, `test_f03_benign_nearby_context_preserves_support`, `test_f03_no_expandable_context_is_explicit_and_bounded`, `test_f03_expansion_never_crosses_source_or_version` | regression suite; `tests/unit/evidence/verification/test_context_retry.py` | Awaiting re-review |
| F09 unverified mapper influence | `9f39ccc` | `test_f09_unverified_purpose_match_cannot_upgrade_to_analogy`, `test_f09_verified_functional_commitment_supports_analogy`, `test_f09_mapper_conflict_blocks_direct_until_resolved` | regression suite; `tests/unit/evidence/precedent` | Awaiting re-review |
| F08 patent future/duplicate references | `e2722d9` | `test_f08_future_patent_references_cannot_challenge_the_cutoff`, `test_f08_family_publications_count_as_one_lineage_root`, `test_f08_independent_pre_cutoff_partials_remain_combination_context`, `test_f08_future_decisive_reference_is_not_selected_over_eligible_one` | regression suite; `tests/unit/evidence/precedent/test_patent.py` | Awaiting re-review |
| F11 slice identity bridge | `e952ad1` | `test_f11_bridge_accepts_combination_and_expanded_passage_identities`, `test_f11_pipeline_projection_passes_the_bridge_with_combination_and_window`; accepted slice now carries a real combination contribution through `REPORTED/COMPLETED` | regression suite; `tests/integration/test_phase5_slice_with_phase6_evidence.py` | Awaiting re-review |
| M01 benchmark metric labeling | `f4a6f93` | metric renamed to `citation_presence_and_bundle_integrity`; benchmark docstring states citation/bundle integrity only | `tests/benchmarks/test_phase6_support_verifier.py` | Closed, pending re-review |

Policy/contract changes made for the fixes are recorded in ADR-026 (statement
material commitments), ADR-027 scope (citation requirements), ADR-029
(patent eligibility/lineage) and the new ADR-030 (context-completeness
precheck). The graph schema was migrated to v2 with a `verified_edges` table.

**Gate 30 remains OPEN.** The mandatory GPT-6 Sol High re-review must re-run
the F01–F11 reproductions, inspect the changed code, attempt fresh variants,
verify no regression was introduced, run full and fresh-checkout verification,
and explicitly set Gate 30 PASS or FAIL. Phase 6 is **not accepted** and
Phase 7 remains blocked.
