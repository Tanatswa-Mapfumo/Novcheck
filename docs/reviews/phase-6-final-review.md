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
precheck). The graph schema was migrated to v2 with a `verified_edges` table. Full and
fresh-checkout verification of the repaired commit passed (1426 deterministic
tests, Ruff/format/Pyright clean, `git diff --check` clean).

**Gate 30 remains OPEN.** The mandatory GPT-6 Sol High re-review must re-run
the F01–F11 reproductions, inspect the changed code, attempt fresh variants,
verify no regression was introduced, run full and fresh-checkout verification,
and explicitly set Gate 30 PASS or FAIL. Phase 6 is **not accepted** and
Phase 7 remains blocked.

---

## Independent semantic re-review at `c41b11f`

**Re-reviewer/model:** GPT-6 Sol High, independent of the Phase 6 implementation and remediation, with separate coordinator reproductions. **Reviewed commit:** `c41b11fec99ef0f67739c13cb5aad31ec150bcd2` on `phase-6-evidence-verification`; comparison base `e4683fd`. The original FAIL review and implementer's remediation record above remain unchanged. This section judges the actual repaired code, not the completion report or number of passing tests. No code or tests were changed by the reviewers.

### F01-F11 closure table

The regression names below refer to `tests/adversarial/test_phase6_sol_review_regressions.py` unless otherwise noted. `OPEN` means a fresh variant still violates the finding's semantic invariant, even where the exact shipped example now passes.

| ID | Original failure | Implemented remediation / regression | Independent attack and actual result | Status |
| --- | --- | --- | --- | --- |
| F01 | Material MCU statement qualifier omitted from proposition. | `statement:material` lexical-token fallback; `test_f01_statement_only_condition_is_material_and_blocks_generic_direct` and six variants. | `Alpha and beta enable relay` with separately structured `alpha enable relay` and `beta enable relay` features yields **no** statement commitment; valid support for the separate features makes an edge decisive and classifies `DIRECT_PRECEDENT`. `Alpha then beta` also loses order; reversed directed relation and combination-member condition variants fail. | **OPEN** |
| F02 | 2027 revision inherited 2020 source date. | Optional cited-version chronology; `test_f02_post_cutoff_revision_of_old_source_is_not_decisive` and three chronology cases. | Original call with supplied version is nondecisive. But omitting the optional version at the public edge gate still makes a versioned 2027 disclosure decisive from the 2020 source date. `ClassificationFacts(decisive=True, chronology_state='POST_CUTOFF')` also returns decisive direct. A 2020 preprint plus 2027 journal source date wrongly disqualifies the cited 2020 version. | **OPEN** |
| F03 | Short supporting excerpt hid nearby negation. | ADR-030 bounded initial context precheck; `test_f03_nearby_negation_cannot_be_hidden_by_a_short_excerpt` and boundary cases. | Original contained qualifier is shown. A qualifier immediately beyond `window_chars=20` remains outside the supplied window and the scripted verifier returns `SUPPORTED`; `max_expansions=0` skips the precheck entirely. A separate adjacent same-version passage and repeated-text occurrence also evade the containing-window algorithm. | **OPEN** |
| F04 | Fourth source/earlier version silently omitted. | Explicit bounded coverage and oldest-first version selection; `test_f04_fourth_source_is_explicitly_unassessed`, `test_f04_older_version_is_assessed_not_silently_dropped`. | Fourth source and excess versions are listed. With one versioned and one unversioned passage for a source, `select_versions` selects the version and returns no exclusion, silently dropping the unversioned exact-configuration passage. | **OPEN** |
| F05 | `SUPPORTED` judgment could cite no passage. | Evidential judgments require nonempty citations and no mapper fallback; `test_f05_supported_without_citations_is_rejected`, `test_f05_mapper_passages_cannot_substitute_for_verifier_citations`. | Empty `SUPPORTED`/`PARTIALLY_SUPPORTED`/`CONTRADICTED` citations are rejected. A Pydantic-valid verification whose judgments cite `pass_1` but `relied_on_passage_ids=('pass_unseen',)` still builds a decisive edge citing `pass_unseen`. | **OPEN** |
| F06 | Foreign source/version/proposition joins. | More identity checks at aggregate, edge, classifier and patent boundaries; `test_f06_foreign_source_version_proposition_joins_are_rejected`, `test_f06_patent_entry_mcu_and_version_joins_are_rejected`. | The shipped mismatches fail. A version record with the expected version ID but `source_id='src_other'` is accepted for `src_1` and becomes decisive. Verification of a different proposition/claim with the same MCU and mapping ID can also be joined. | **OPEN** |
| F07 | Graph trusted a self-declared verification reference. | v2 `verified_edges` table and transactional reference lookup; `test_f07_graph_persistence_rejects_unresolved_or_mismatched_verification`, `test_f07_schema_v1_migrates_to_v2`. | A nonexistent verified-edge ID is rejected. A supplied Pydantic-valid verified artifact citing nonexistent `pass_unseen` can still back a direct graph edge. A v1 direct edge with no verified artifact remains readable after the v1-to-v2 migration. | **OPEN** |
| F08 | Future/duplicate patents counted as eligible independent partials. | `as_of` and lineage roots; four `test_f08_*` regressions. | Future source-level dates and family duplicates are excluded. Patent entries use the parent source's publication date, not the cited classified version's date: two 2027 partial revisions of 2020 parents can still yield `MULTI_REFERENCE_COMBINATION_LIKE` for a 2026 cutoff. | **OPEN** |
| F09 | Unverified mapper purpose match changed class; conflict ignored by direct. | Verified functional dimensions and conflict gate; three `test_f09_*` regressions. | Added mapper-only PURPOSE conflict changes fixed verified direct to `UNRESOLVED`; `mapping.unresolved=('Contribution relationship unresolved',)` is ignored and still returns `DIRECT_PRECEDENT`. | **OPEN** |
| F10 | Narrow special case labeled generic insufficient context. | Scoped within-commitment partial support; `test_f10_narrower_special_case_is_scoped_partial_support`, `test_f10_partial_commitment_requires_a_citation_and_scoped_fields`; benchmark updated. | Verifier now records read-only subset and unsupported universal remainder. Classifier of a single valid scoped-partial commitment returns `SUPERFICIAL_SIMILARITY`, `covered_elements=()`, losing the known supported subset. | **OPEN** |
| F11 | Combination/expanded passage rejected at legacy slice bridge. | Explicit Phase 6 combination and expansion identities; `test_f11_bridge_accepts_combination_and_expanded_passage_identities`, `test_f11_pipeline_projection_passes_the_bridge_with_combination_and_window`; accepted slice test reaches lifecycle with a combination. | Original bridge failures are fixed; direct foreign-source and foreign-target probes fail. The requested simultaneous combination-plus-expanded-passage *full-lifecycle* case and foreign-version bridge case are not covered by a full-slice regression; the legacy edge projection has no version field. This is a residual test/boundary limitation, not a reproduced original failure. | **CLOSED** |

### Fresh attack coverage

- **Statement semantics:** Tested `only after`, `only if`, `unless`, conjunction, order, quantifiers and sparse fields via shipped cases; additionally tested same-token conjunction/order, reversed direction, and combination-member conditions. The lexical set comparison in `build_proposition` misses the latter group (F01).
- **Chronology:** Supplied post-cutoff version and missing version date abstain; optional-version bypass, contradictory classifier facts, and later source metadata disqualifying an earlier cited preprint fail (F02). Version owner mismatch fails identity integrity (F06).
- **Context:** Immediate contained negation is shown; separate adjacent passage, truncated window, repeated occurrence and zero precheck budget fail (F03). Same-source/version filter holds for the containing-passage expansion it does perform.
- **Coverage:** Bounded fourth source and older matched versions are visible; mixed versioned/unversioned passages are not (F04). Local `NO_DIRECT_PRECEDENT_IDENTIFIED` remains explicitly local, never permission for a global absence claim.
- **Evidence joins:** Zero evidential citations, foreign cited passage IDs in verifier proposals and common foreign source/version/MCU/proposition joins are rejected; mismatched aggregate relied-on IDs, version ownership, and another claim's valid-shaped support are not (F05-F07). A forged graph ref to an unknown artifact fails; a fabricated referenced artifact with an unresolved citation survives.
- **Patent:** Two future source-level references, family duplicates, one eligible plus one future, two independent pre-cutoff partials and one direct plus unrelated partials behave as intended in the shipped tests. A post-cutoff classified version of an older parent is still counted as an eligible partial (F08). Multi-reference context is not relabeled one-reference anticipation.
- **Mapper/classifier and partial support:** Added unverified functional *match* no longer establishes analogy; arbitrary mapper conflict still changes fixed verification, unresolved mapping is ignored for direct, and within-commitment subset support disappears from classification (F09-F10).
- **Original Phase 6 invariants:** Reversed causal relation, paraphrased equivalent mechanism, unsupported abstract, A+B+C stitching, components without configuration, analogy inflation, Tier-A unsupported evidence, lower-quality supported evidence, prompt-injection text as inert data, passage/source/version mismatch, unsupported conjunction, conditional and population-limited claims, and local no-direct scope were re-exercised through the shipped adversarial suite and additional probes. These tests use scripted semantic labels; they do **not** establish live-model entailment, calibration or prompt-injection resistance. The specific failures above override any green fixture result.

### Benchmark interpretation

`tests/benchmarks/test_phase6_support_verifier.py` and `tests/fixtures/phase6_support_benchmark.json` now use `citation_presence_and_bundle_integrity`. The benchmark states that this metric checks reference presence and bundle integrity, **not** semantic rationale faithfulness, model calibration, production accuracy, empirical factuality, or live-verifier performance. The eight deterministic fixture cases remain a diagnostic only. M01 is closed.

### Open Critical findings

**F01 — Statement relationships are still lost.** **Invariant:** INV-02/03/14. **Function:** `src/novelty_harness/evidence/mapping/dimensions.py:274`, `build_proposition` and its `_material_tokens` coverage test near line 410; combination member commitments near line 354. **Reproduction/current behavior:** An MCU with statement `Alpha and beta enable relay` and separate feature concepts `alpha enable relay`, `beta enable relay` produces only `feat:0` and `feat:1`, because `and` is a stopword. Valid support for each feature separately yields `edge.decisive=True` and `DIRECT_PRECEDENT` although joint activation is unproved. `Alpha then beta enables relay` likewise drops order; reversed subject/object and member-statement qualifiers also evade the token-set fallback. **Required:** Material conjunction, direction, order and member conditions must constrain direct equivalence without fabricating a relation. **Smallest fix:** Check structural/relational coverage of every MCU and member statement; if material meaning is not represented, carry an unresolved statement commitment and block direct until independently verified. **Regression:** Same-word conjunction, `then` order, reversed relationship, and a qualified combination member against separate-component passages must remain nondecisive; full configuration support should remain direct-eligible.

**F02 — The historical cutoff is still bypassable at public gates.** **Invariant:** FR-EXP-003/INV-14. **Functions:** `src/novelty_harness/evidence/verification/gates.py:310` (`assess_chronology`), `:407` (`build_verified_evidence_edge`), `src/novelty_harness/evidence/precedent/gates.py:162` (`classify_precedent`). **Reproduction/current behavior:** A mapping and verification cite `srcv_1_v1`, whose actual publication is 2027; call the edge builder without its optional `version` and with a 2020 parent source. It returns decisive `PREDATES_CUTOFF` at `as_of=2026`. Separately, valid `ClassificationFacts(decisive=True, chronology_state='POST_CUTOFF')` returns decisive direct. In the opposite direction, a cited 2020 preprint under a source also carrying a 2027 journal publication is wrongly `POST_CUTOFF` because `max` combines unrelated version dates. **Required:** Eligibility follows the cited disclosure, rejects contradictory decisive facts, and does not erase an earlier eligible version. **Smallest fix:** Require and validate the matching version whenever a version ID is cited; anchor chronology to that version's public date, treating conflicting metadata as uncertainty rather than using unrelated later editions; validate the classifier's decisive/chronology invariant. **Regression:** Repeat all three variants through public gates, plus unknown version date and foreign-version passage.

**F03 — Bounded context can still conceal a known qualifier.** **Invariant:** INV-14/FR-EVID-005. **Functions:** `src/novelty_harness/evidence/context/expansion.py:34` (`expand_passage_context`), `src/novelty_harness/evidence/verification/verifier.py:84` (`verify_with_context_retry`). **Reproduction/current behavior:** A stored wider same-version passage contains the mapped sentence, then 100 filler characters, then `However, the operator must switch it manually`. With `window_chars=20`, the precheck creates a window lacking `However`; the normal qualifier-aware fixture returns `SUPPORTED` in one attempt. With `max_expansions=0`, it also returns `SUPPORTED` despite an available contradiction. Adjacent standalone passages are not considered, and repeated text expands around the first occurrence rather than the mapped locator. **Required:** Known nearby material context cannot be silently omitted from a potentially decisive claim. **Smallest fix:** Locate the actual occurrence and same-version neighbors; trace truncation, and withhold decisiveness when configured bounds cannot establish context completeness. A zero precheck budget cannot silently grant decisive support. **Regression:** Before/after neighbor, window boundary, repeated occurrence, blocked context and zero-budget examples, including one benign neighbor that remains supported.

**F05 — Verifier reliance can be detached from its judged passages.** **Invariant:** INV-14/FR-EVID-001. **Functions:** `src/novelty_harness/evidence/verification/models.py` (`SupportVerification`), `src/novelty_harness/evidence/verification/gates.py:407` (`build_verified_evidence_edge`). **Reproduction/current behavior:** Revalidate a `SupportVerification` whose two `SUPPORTED` commitment records cite `pass_1`, but whose top-level `relied_on_passage_ids` is `('pass_unseen',)`. The public edge builder returns `decisive=True` and `passage_ids=('pass_unseen',)`. **Required:** Every support-bearing edge cites exactly the verifier-supported, supplied, same-source/version passages. **Smallest fix:** Validate top-level reliance against the union of per-commitment citations and against the resolved claim bundle before edge construction. **Regression:** Revalidated support object with a nonexistent, foreign, or extra top-level relied-on ID must not create an edge; zero-citation regressions continue to pass.

**F06 — Version ownership and claim/proposition identity are not fully joined.** **Invariant:** INV-14 and passage/source-version integrity. **Functions:** `src/novelty_harness/evidence/verification/gates.py:407` (`build_verified_evidence_edge`), `src/novelty_harness/evidence/precedent/gates.py:162` (`classify_precedent`). **Reproduction/current behavior:** A version record with `version_id='srcv_1_v1'`, `source_id='src_other'`, and a 2020 date is accepted for `src_1` and produces a decisive edge. A verification for a different claim/proposition can be paired when its MCU and mapping IDs match; the edge builder has no actual bundle/claim to check. **Required:** Version owner, claim ID, proposition ID, MCU/combination target, mapping ID, verifier ID and cited passage identity all belong to the same comparison. **Smallest fix:** Join the version's source owner and the exact claim/bundle identities at edge/classification boundaries; reject absent or mismatched identity, not merely matching identifier strings. **Regression:** Foreign version owner and alternate proposition/claim with otherwise identical IDs must fail; valid combination target remains accepted.

**F07 — Persistence can still store a direct edge without resolved decisive citations.** **Invariant:** FR-EVID-004/INV-14. **Functions:** `src/novelty_harness/evidence/graph/sqlalchemy_repository.py:125` (`_persist_verified_edge`), `:152` (`_verify_phase6_edges`); `src/novelty_harness/evidence/graph/migrations.py:22` (`ensure_schema`). **Reproduction/current behavior:** Supply the Pydantic-valid verified artifact from F05, then a graph `DIRECT_PRECEDENT` edge referencing its real ID. Repository validation checks endpoint, support flag and chronology but not that `pass_unseen` exists; it persists. Also simulate a v1 graph with a direct edge referencing `edge_missing`; upgrading to v2 leaves that direct edge readable with no `verified_edges` row. **Required:** The stored decisive edge resolves to genuine same-source/version passages and a matching verified claim; old unverified edges cannot silently gain v2 legitimacy. **Smallest fix:** Resolve cited passages/claim in the same transaction, and validate or quarantine preexisting v1 Phase 6 edges during migration/read. **Regression:** Supplied fake verified artifact and legacy dangling direct edge must be rejected/quarantined; legitimate v2 round-trip and idempotent upsert remain valid.

### Open Important findings

**F04 — Unversioned evidence can disappear without a coverage record.** **Invariant:** FR-SRC-001/INV-12. **Function:** `src/novelty_harness/evidence/phase6_pipeline.py:167` (`select_versions`) and its selected-version passage filter. **Reproduction/current behavior:** One source has versioned passage `p1` and unversioned exact-configuration passage `p0`; one matching version record is supplied. Selection returns only that version and `excluded=()`, so `p0` is neither mapped nor listed unassessed. **Required:** Unknown-version evidence is assessed with explicit uncertain chronology or recorded as unassessed. **Smallest fix:** Include an unversioned slot when unversioned passages exist, or add their IDs to the bounded coverage artifact. **Regression:** Mixed versioned/unversioned source with exact hit in `p0` cannot appear fully assessed.

**F08 — Patent partial screening uses parent date, not cited version eligibility.** **Invariant:** FR-EXP-003/INV-07 and the one-reference patent distinction. **Functions:** `src/novelty_harness/evidence/phase6_pipeline.py:550` (patent entry construction), `src/novelty_harness/evidence/precedent/patent.py:90` (`screen_patent_references`). **Reproduction/current behavior:** Two partial classifications are for 2027 revisions of patent sources whose parent `patent_publication_date` is 2020. The entries carry 2020, so screening emits `MULTI_REFERENCE_COMBINATION_LIKE` for `as_of=2026`. **Required:** Only distinct lineage roots of *eligible cited versions* contribute historical combination context. **Smallest fix:** Carry each edge's assessed version chronology into `PatentEvidenceEntry` and screen it alongside source/family identity. **Regression:** Two future revisions of old parents, one old plus one future version, two independent eligible partial patents, and a direct eligible patent plus partials.

**F09 — Mapper-only assertions still control, or fail to constrain, class.** **Invariant:** INV-02/INV-14 and mapper/verifier separation. **Function:** `src/novelty_harness/evidence/precedent/gates.py:162` (`classify_precedent`), notably `unresolved_conflicts` and the all-supported branch. **Reproduction/current behavior:** Fixed all-supported verification and decisive chronology classify direct; append an unverified PURPOSE conflict to the mapper and class becomes `UNRESOLVED`. Instead add `mapping.unresolved=('Contribution relationship unresolved',)` and class remains `DIRECT_PRECEDENT`. **Required:** Material mapping conflicts/unresolved claims must be independently verified and bound to commitments; irrelevant mapper variation cannot change semantic precedent. **Smallest fix:** Resolve material conflicts in the blinded verifier output and use only that resolution for classification; block direct while a genuinely material relation is unresolved. **Regression:** Perturb mapper-only purpose, mechanism, relationship, control flow, context and outcome assertions while holding verification fixed; distinguish irrelevant conflict from verified material disagreement.

**F10 — Scoped partial support is lost after verification.** **Invariant:** INV-14 and plan Task 14's partial-support preservation. **Function:** `src/novelty_harness/evidence/precedent/gates.py:204` (`supported` set and coverage construction). **Reproduction/current behavior:** A valid one-commitment `PARTIALLY_SUPPORTED` verification for `works for all workloads` records supported subset `read-only workloads` and unsupported remainder `all workloads`. Classifier returns `SUPERFICIAL_SIMILARITY` with `covered_elements=()`. **Required:** A known supported subset remains visible in a nondecisive, appropriately scoped partial relation; the broader remainder is not inferred supported. **Smallest fix:** Consume scoped partial records in the local coverage/classification representation without counting them as fully supported commitments. **Regression:** Single and multiple partial commitments, partial-plus-contradiction, condition-limited and population-limited evidence retain scope and never aggregate to direct.

**N01 — Cutoff-dependent verified edges collide across assessments.** **Invariant:** FR-AUD-002, FR-EXP-003 and append-only artifact identity: a stable ID must distinguish different semantic eligibility. **Functions:** `src/novelty_harness/evidence/verification/gates.py:468` (edge ID hash), `src/novelty_harness/evidence/graph/sqlalchemy_repository.py:125` (`_persist_verified_edge`). **Reproduction/current behavior:** Same source/version, mapping, verification and passages at `as_of=2019` and `as_of=2026` receive the **same** `edge_id`, although one is nondecisive and the other decisive. Persisting the first in one repository, then the second, raises `ValueError: Verified edge ... already exists with different content`; a legitimate historical re-assessment cannot be stored append-only. **Required:** Different cutoff/chronology meaning has a different immutable artifact identity, without allowing replacement of the earlier result. **Smallest fix:** Include `as_of` and other stable chronology inputs in the verified-edge canonical ID; leave observation timestamps outside only if intentionally versioned separately. **Regression:** Persist the same evidence for two cutoff dates in one graph; both IDs and eligibility records remain distinct, while identical re-upsert remains idempotent.

### Verification and gate decision

- **Repaired worktree:** `uv sync --dev` passed; `uv run python scripts/verify.py` passed again after the re-review section was appended: Ruff check, Ruff format (285 files), Pyright 0 errors/warnings, pytest **1426 passed, 5 deselected**. `git diff --check` passed after that append.
- **Fresh exact-commit checkout:** Local clone at `/private/tmp/novcheck-phase6-rereview-c41b11f` was detached at the full `c41b11f` hash. `uv sync --dev` passed; `uv run python scripts/verify.py` passed with Ruff/format/Pyright clean and **1426 passed, 5 deselected**; `git diff --check` passed. No live network suite was run.
- **Regression evidence:** The 37 review-derived tests and existing Phase 6 adversarial/benchmark/integration tests pass. They close the exact shipped examples, but do not cover the independent variants above. No reviewer regression tests or implementation fixes were added.
- **Gate 30:** **FAIL** because F01-F10 have open Critical/Important variants and N01 is Important. The earlier F11 bridge failure and M01 benchmark labeling are closed; the simultaneous full-lifecycle/foreign-version F11 scenario remains unproven and must be exercised before any later PASS decision. Phase 7 remains unstarted.

Acceptance Gate 30: FAIL — Phase 6 remains blocked.

---

## Round-2 implementation record (not an independent re-review)

The preceding independent **FAIL** at `c41b11f`, including every original
counterexample, remains unchanged. The Phase 6 implementation owner has
applied a second remediation against F01-F10 and N01. This section records
implementation and regression evidence only; it does **not** close findings
or grant Gate 30 acceptance. The requested Round-2 plan file was absent from
the checkout, so the attached user instruction was used as the approved
task scope. ADR-030 was amended and ADR-031/032 record the new contracts and
schema/identity decisions.

| Finding | Round-2 repair | Regression evidence |
| --- | --- | --- |
| F01 | Preserve ordered MCU and combination-member statements as material obligations unless one structured commitment carries the same ordered meaning. | `test_split_features_do_not_cover_joint_or_ordered_statement`, `test_f01_*` |
| F02 | Require owned cited version at the edge gate, use cited disclosure date, reject contradictory decisive chronology. | `test_f02_*` in both Sol suites and verification unit tests |
| F03 | Record explicit context completeness, inspect mapped occurrence and same-version neighbors, block decisive support for incomplete context. | `test_f03_*`, context expansion/retry unit tests |
| F04 | Explicitly disclose mixed unversioned passages and bounded version work; never borrow a known version's parent date. | `test_f04_mixed_unversioned_passages_are_selected_or_disclosed`, pipeline coverage tests |
| F05 | Require canonical top-level verifier reliance to equal the commitment citation union. | `test_f05_*` and eligibility unit tests |
| F06 | Join version owner, proposition, mapping, actual claim, verification and cited passage identities at public gates. | `test_f06_another_claim_or_proposition_cannot_share_a_verified_result`, `test_f06_*` |
| F07 | Persist reconstructible verified chains; resolve source/version/cited passage nodes transactionally; block unsafe legacy Phase 6 edge migration. | `test_f07_decisive_chain_requires_the_real_cited_passage_node`, `test_f07_legacy_direct_edge_cannot_be_reinterpreted_as_verified`, graph tests |
| F08 | Screen the classified patent version's chronology and distinct eligible lineage roots. | `test_post_cutoff_revisions_of_old_patents_cannot_form_combination_context` and related patent tests |
| F09 | Classify from verified commitment states, not mapper-only claims or conflicts. | `test_f09_mapper_only_conflict_cannot_change_fixed_verified_semantics` over six dimensions |
| F10 | Preserve scoped subset/remainder in nondecisive classification, including alongside contradiction. | `test_f10_scoped_partial_survives_classification_without_direct_inflation`, `test_f10_partial_subsets_survive_a_separate_contradiction` |
| N01 | Include stable assessment/chronology inputs in edge ID and edge ID in proposition-node ID. | `test_n01_cutoff_changes_immutable_verified_edge_identity`, `test_n01_two_cutoffs_persist_as_immutable_distinct_graph_artifacts` |

The strengthened full-slice test carries **both** a combination target and a
verifier-cited expanded passage through `REPORTED` and `COMPLETED`. Foreign
version ownership remains rejected by the F06 gate. The benchmark's
`citation_presence_and_bundle_integrity` label remains a fixture diagnostic,
not semantic faithfulness or live accuracy. No Phase 7 behavior was added.

Implementation worktree verification after the final code change: `uv sync
--dev` passed; `uv run python scripts/verify.py` passed with Ruff check and
format (287 files) clean, Pyright 0 errors/warnings, and **1471 passed, 5
network tests deselected**; `git diff --check` passed. Exact commit and
fresh-checkout results are recorded in a follow-up verification amendment.
A fresh independent GPT-6 Sol High reviewer must replay the attacks and
decide Gate 30; implementer tests cannot self-certify semantic acceptance.

Gate 30 remains OPEN pending a fresh independent GPT-6 Sol High semantic re-review.

### Round-2 verification amendment

- **Implementation commit:** `54364bac8a58493ccbd87e26867d4f419be94226`.
- **Worktree:** `uv sync --dev` passed. `uv run python scripts/verify.py`
  passed: Ruff check clean, Ruff format clean (287 files), Pyright 0
  errors/0 warnings, pytest **1471 passed, 5 opt-in network tests
  deselected**. `git diff --check` and staged-diff whitespace checks passed.
- **Fresh exact-commit checkout:** local no-network clone at
  `/private/tmp/novcheck-phase6-round2-54364ba`, HEAD exactly
  `54364bac8a58493ccbd87e26867d4f419be94226`. `uv sync --dev`,
  `uv run python scripts/verify.py` (same 1471/5 result and clean
  Ruff/format/Pyright), and `git diff --check` all passed.
- **Decision:** This is implementer verification, not the required independent
  semantic re-review. The `c41b11f` FAIL record remains in force until a
  fresh GPT-6 Sol High reviewer independently closes F01-F10 and N01.

Gate 30 remains OPEN pending a fresh independent GPT-6 Sol High semantic re-review.
