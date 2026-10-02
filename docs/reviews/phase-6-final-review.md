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

---

## Final independent Round-2 semantic re-review at `75cee5e`

**Reviewed commit:** `75cee5e926b27a2ae695c7ad37db2eedc6404a6f` on
`phase-6-evidence-verification`. This review did not implement the remediation.
The two earlier independent FAIL records and the implementation records above
remain intact. The checks below used new, schema-valid variants at public
boundaries, inspected the actual production code changed since `c41b11f`, and
ran the existing adversarial, benchmark, integration, and full-slice suites.
Passing fixture tests were not treated as semantic proof.

### Finding-by-finding attacks

| Finding | Invariant and implemented repair | Independent attack and actual behavior | Status |
| --- | --- | --- | --- |
| F01 | MCU structure must survive proposition construction. `build_proposition` adds ordered `statement:material` and member obligations unless an existing commitment contains the complete statement. | Fresh statements for `and`, `or`, both `then` orders, `only after`, `unless`, `requires both`, two-step activation, reversed subject/object, and a member-only condition each retained a material statement alongside split features. An exact duplicate mechanism statement produced only `mech`, avoiding a fabricated extra obligation. Generic components still lack full configuration support. | **CLOSED** |
| F02 | Eligibility must follow the cited public version. The edge gate now requires an owned version, and `assess_chronology` uses its date. | Old parent/later revision, missing/foreign version, unknown version date, later journal/earlier preprint, and decisive/post-cutoff facts are guarded. A fresh conflict remains: source `first_public_version=2027-01-01` plus cited version `published_date=2020-01-01`, cutoff 2026, returns `PREDATES_CUTOFF` and a decisive edge. Those two claims cannot both describe the first public disclosure. | **OPEN** |
| F03 | Decisive support needs complete same-version context. The precheck now expands the located occurrence and records completeness. | A qualifier beyond the window is `TRUNCATED`; an ambiguous repeat, zero budget, and unavailable context do not become decisive. Yet a mapped block at `[100,113)` with only an adjacent benign block at `[85,100)` is marked `COMPLETE`, despite no evidence that content after 113 was obtained. A standalone complete abstract is `UNAVAILABLE`. Thus an omitted next-block qualifier can still be treated as absent, while a complete limited unit can be permanently downgraded. | **OPEN** |
| F04 | Every unversioned passage must be assessed or disclosed. `select_versions` adds an unversioned slot when no versions exist and otherwise records passage IDs as unassessed. | Mixed versioned/unversioned passages at version limits 1 and 2 disclosed `unversioned:pass_no_version`; only-unversioned and multiple-unversioned inputs selected the unversioned slot. No tested passage silently vanished. | **CLOSED** |
| F05 | Verifier reliance must equal its commitment citation union. Schema and chain checks now enforce canonical reliance and actual supplied passages. | Reordered, added, missing, and foreign top-level citation IDs fail validation or edge construction; a partial-support citation must likewise be in the bundle. Duplicate commitment-level IDs collapse to one canonical relied-on ID, without creating a second source. The graph attribute failure below is a later projection defect. | **CLOSED** |
| F06 | Classification and verification must belong to the same proposition, claim, mapping, source, version, and MCU. The edge gate and `validate_semantic_chain` join these objects. | Foreign source/version owners and a claim or proposition from another comparison are rejected at the edge gate. But a schema-valid `PrecedentClassification` with `mapping_id=map_foreign` and `classification_id=cls_foreign`, while retaining the verified edge's `verification_id`, was paired with that edge by `verified_edge_graph_fragment` and persisted as direct. Classification identity is still cross-wirable after chain validation. | **OPEN** |
| F07 | A persisted decisive graph relation must resolve to exactly its authoritative verified citation chain. Schema v3 stores and revalidates a chain and refuses v1/v2 Phase 6 edges. | Missing passage nodes, a foreign version node, and unsafe legacy direct edges are refused. But changing only a valid direct `GraphEdge.attributes['passage_ids']` to `['pass_nonexistent']` passed `repository.upsert`; the stored direct edge advertises that nonexistent citation. A foreign classification's ID and basis also persist as graph attributes. | **OPEN** |
| F08 | Patent screening may use only eligible cited versions and distinct lineage roots; separate references never become one-reference anticipation. Screening now consumes version chronology and lineage roots. | Two future revisions from old parents yielded `LIMITED`; two eligible versions sharing one root yielded `LIMITED`; two independent eligible partial patents yielded `MULTI_REFERENCE_COMBINATION_LIKE`. Existing cases also cover missing chronology, mixed eligible/future, and one eligible direct patent. No tested partial set became anticipation-like. | **CLOSED** |
| F09 | Mapper-only assertions must not decide a verified precedent class. The classifier now reads commitment states. | Holding a supported mechanism fixed, independently changing each of all twelve mapper dimensions, including purpose, problem, target, architecture, features, relationships, control flow, context, outcome, and constraints, left the class `DIRECT_PRECEDENT`. Existing verified relationship-gap cases demote direct. | **CLOSED** |
| F10 | Scoped partial support must remain partial and retain its subset/remainder. The classifier now emits `ScopedCoverage`. | Ordinary one- and two-commitment partials, partial plus contradiction, and subgroup/condition records retain scope without aggregating to direct. However a schema-valid `SupportVerification(state=PARTIALLY_SUPPORTED)` with all commitment records `SUPPORTED` and an invented `unsupported_portions` entry yields `DIRECT_PRECEDENT` and `decisive=True` when passed as `ClassificationFacts(decisive=True)`. Aggregate/record inconsistency still permits public direct classification. | **OPEN** |
| N01 | Immutable edge IDs must distinguish assessment context and chronology. The canonical edge ID now includes assessment ID, cutoff, chronology state/date, and context completeness. | Same evidence with cutoffs before/after disclosure had different IDs; two assessment IDs at one cutoff had different IDs; exact same object re-upsert was idempotent. Chronology and eligibility inputs tested did not collide. A separate volatile-observation replay failure is N02 below. | **CLOSED** |
| F11 | The real lifecycle must admit a combination target and verifier-cited expanded passage while rejecting foreign identities. The projection bridge now accepts the genuine extra target and expansion IDs. | The full-slice integration reached `REPORTED`/`COMPLETED` with both identities. Foreign target/source/expanded-passage source fail the bridge; foreign version and expansion version fail the upstream semantic-chain and expansion ownership checks. The legacy bridge itself carries source-level passage identity, so upstream version validation remains essential. | **CLOSED** |
| M01 | A lexical fixture citation metric must not be presented as semantic faithfulness. The benchmark now names `citation_presence_and_bundle_integrity` and states its limits. | Inspected the metric and benchmark fixtures: they measure bundle citation presence and deterministic state agreement, without claiming rationale faithfulness, calibration, or live accuracy. | **CLOSED** |

### Open Critical and Important defects

**F02 — Important: contradictory first-public-version chronology.**
Invariant: an internally conflicting chronology cannot establish decisive earlier
disclosure. Function: `evidence/verification/gates.py::assess_chronology`
(around line 317), then `build_verified_evidence_edge`. Minimal reproduction:
construct a source with `dates.first_public_version=date(2027,1,1)`, an owned
cited version with `published_date=date(2020,1,1)`, and `as_of=date(2026,9,28)`;
use otherwise valid fully supported claim artifacts. Current: chronology is
`PREDATES_CUTOFF`, edge `decisive=True`. Required: flag the contradictory
first-public-disclosure claims as uncertain/nondecisive, while permitting a
clearly identified earlier preprint when a later source-level *journal*
publication refers to a separate edition. Smallest fix: distinguish
source-wide first-public-date assertions from edition-specific publication
dates, and validate an owned cited version against the former. Regression:
conflicting first-public-version versus version date is nondecisive; earlier
preprint versus later journal publication stays eligible.

**F03 — Critical: incomplete neighbor coverage is declared complete.**
Invariant: inability to establish context completeness cannot be interpreted
as absence of a qualifier. Function:
`evidence/context/expansion.py::inspect_passage_context` (around lines 220-265).
Minimal reproduction: one mapped block with locator `[100,113)` and one stored
previous block `[85,100)`, with no whole-content boundary or following block.
Current: `ContextCompleteness.COMPLETE`; a supporting verifier can therefore
become decisive although following content is unknown. A complete standalone
abstract currently returns `UNAVAILABLE`, showing the opposite failure.
Required: completeness only when the relevant content unit's boundaries are
proved, including both ends; a known complete abstract/claim unit can be
complete within its explicitly limited scope. Smallest fix: carry an explicit
unit/boundary marker from extraction or resolved content and require it before
setting `COMPLETE`; otherwise use `UNKNOWN`/`TRUNCATED`. Regression: previous-
only and next-only blocks remain nondecisive when the other boundary is
unknown; a fully delimited abstract/claim is classified as complete but retains
its access limitation.

**F06/F07 — Critical: graph projection and persistence accept cross-wired
classification metadata and false decisive citations.** Invariant: every
persisted direct graph relation, including the citations and classification it
advertises, must match the resolved semantic chain. Functions:
`evidence/graph/phase6_mapping.py::verified_edge_graph_fragment` (around line
86) and `evidence/graph/sqlalchemy_repository.py::_verify_phase6_edges`
(around line 213). Minimal reproductions: (1) pair a valid direct edge with a
schema-valid direct classification carrying the same `verification_id` but
`mapping_id='map_foreign'`; (2) take a valid projected direct graph edge and
change only `attributes['passage_ids']` to `['pass_nonexistent']`. Current:
both persist, with the foreign classification basis or nonexistent graph
citation visible on the stored relation. Required: projection and persistence
must join classification source/version/MCU/mapping/verification/relation to
the exact edge, and graph citation/classification attributes must be derived
from or checked against the resolved chain. Smallest fix: key classification
joins by the full edge comparison identity; validate the graph edge's
Phase 6 attribute schema against the chain before insertion, or generate those
attributes only inside the repository. Regression: both reproductions fail
transactionally; a valid multi-passage and combination edge still persist.

**F10 — Important: aggregate partial state can be upgraded to direct.**
Invariant: partial verifier support cannot become decisive/direct. Functions:
`evidence/verification/models.py::SupportVerification.state_matches_payload`
(around line 160) and `evidence/precedent/gates.py::classify_precedent` (around
line 366). Minimal reproduction: a valid claim with one `SUPPORTED` commitment
record, `state=PARTIALLY_SUPPORTED`, `supported_portions` populated and
`unsupported_portions=('all patients',)`; pass it to classification with
`decisive=True` and eligible chronology. Current: schema accepts the internally
inconsistent verification, and classifier returns decisive
`DIRECT_PRECEDENT`. Required: reject inconsistent aggregate/record states and
never classify direct unless the aggregate verifier state itself is
`SUPPORTED`. Smallest fix: recompute/validate the aggregate state from the
commitment records in the model or a shared deterministic gate, then guard
the all-supported classifier branch by aggregate `SUPPORTED`. Regression:
schema-valid-looking forged partial aggregate is rejected or non-direct;
genuine scoped partial plus full/contradictory records retain their coverage.

**N02 — Important, newly identified: repeat observation collides with an
immutable edge.** Invariant: an identical semantic assessment replay must
either be idempotent or append a distinct observation without overwriting
history. Functions: `evidence/verification/gates.py::build_verified_evidence_edge`
(edge ID construction around line 500) and
`evidence/graph/sqlalchemy_repository.py::_persist_verified_edge` (around line
131). Minimal reproduction: build the same valid edge twice for one
`assessment_id` and cutoff, changing only `observed_at` by one second; upsert
the first then the second. Current: IDs are equal but the second upsert raises
`ValueError ... already exists with different content`. Required: repeated
semantic results must coexist or re-upsert without discarding the observation
history. Smallest fix: persist immutable semantic edge content separately
from append-only observation events, or version the observation in an explicit
artifact identity while retaining a stable semantic key. Regression: same
assessment/evidence with two clocks can be persisted and traced; exact repeat
stays idempotent; different cutoff and assessment IDs remain distinct.

No additional Critical/Important defect was found in F01 statement obligation
construction, F04 unversioned disclosure, F08 patent lineage counting, or F09
mapper separation. Schema v3 refuses unsafe legacy Phase 6 edges rather than
silently reinterpreting them. The very conservative context policy can also
keep large source excerpts nondecisive; that is disclosed as a limitation,
but the false `COMPLETE` result above is the blocking defect.

### Verification and gate

- Exact reviewed worktree, HEAD `75cee5e926b27a2ae695c7ad37db2eedc6404a6f`
  before this review-only append: `uv sync --dev` passed; `uv run python
  scripts/verify.py` passed Ruff, Ruff format (287 files), Pyright (0 errors,
  0 warnings), and pytest **1471 passed, 5 deselected**; `git diff --check`
  passed.
- Fresh no-network local clone at
  `/private/tmp/novcheck-phase6-final-review-75cee5e`, detached at the exact
  same commit: `uv sync --dev`, `uv run python scripts/verify.py` (same checks
  and **1471 passed, 5 deselected**), and `git diff --check` all passed.
- Independent `python` probes, run with the reviewed worktree virtual
  environment, reproduced the open variants above; the existing Phase 6
  adversarial, benchmark, pipeline integration, and full-slice suites were
  included in both full verifier runs. No production code, test fixture, or
  Phase 7 implementation was changed by this review.

Gate 30 **FAILS**: F02, F03, F06, F07, and F10 remain open, and N02 is a new
Important finding. F01, F04, F05, F08, F09, N01, F11, and M01 are closed for
the attacks stated above. Phase 7 remains unstarted.

Acceptance Gate 30: FAIL — Phase 6 remains blocked.

---

## Final contract-consolidation implementation record (not an independent re-review)

The preceding independent **FAIL** at `75cee5e` is preserved. This section
records implementation only; it does not close findings or change Gate 30.
The approved consolidation plan is
`docs/superpowers/plans/2026-09-28-phase-6-contract-consolidation-plan.md`.

| Open finding | Consolidated contract | New adversarial evidence |
| --- | --- | --- |
| F02 | `CitedDisclosure` binds the owned exact version, cutoff and source-wide first-public assertion; conflicts abstain. | Contradictory first-public date, early preprint/later sibling, future revision, missing/foreign/unknown version, decisive/post-cutoff. |
| F03 | Extractor-attested unit start and end govern completeness. | Previous-only, next-only, complete abstract, truncated qualifier, exact repeated locator, zero budget, blocked context. |
| F10 | Commitment records derive aggregate verifier state; direct requires aggregate `SUPPORTED`. | Both forged aggregate directions, genuine multiple partials, partial plus contradiction, all-supported baseline. |
| F06 | `VerifiedComparison` validates the full chain; public verified classification consumes it; `ClassifiedComparison` checks identity and basis. | Foreign mapping and basis, raw public classifier rejection, valid combination comparison. |
| F07 | Repository resolves source/version/claim/passages/chain/classification and derives graph semantic attributes. | False graph citation, nonexistent passage, bare edge, rollback, valid multi-passage and combination edges, unsafe legacy migration block. |
| N02 | Schema v4 stores immutable semantic edges plus append-only observation events. | Two timestamps, exact replay, different cutoff and assessment, reopen, safe metadata-only migration. |

The real full-slice test reaches `REPORTED` and `COMPLETED` with a versioned
disclosure, a verifier-cited expanded passage, scoped partial support and a
combination target. The public graph path uses authoritative comparisons;
Phase 7 adjudication remains a fixture. The previously closed F01, F04,
F05, F08, F09, N01, F11 and M01 contracts were retained. ADR-033 through
ADR-035 document the new decisions and schema migration. No independent
semantic acceptance is claimed from the implementation tests.

Consolidation worktree verification: `uv sync --dev` passed;
`uv run python scripts/verify.py` passed Ruff check, Ruff format (288 files),
Pyright 0 errors/0 warnings, and **1498 passed, 5 network tests
deselected**. `git diff --check` passed. The exact final commit will receive
separate fresh-checkout verification in the implementation handoff.

Gate 30 remains OPEN pending fresh independent GPT-6 Sol High/Max semantic re-review.

---

## Independent review of the final consolidation at `47021af` (30 September 2026)

**Reviewed state:** `phase-6-evidence-verification` at
`47021af9826c431b8900589e57099bd2749d4872`, before this review-only
append. The worktree was clean at that commit. The reviewer did not implement
the consolidation or change production code, tests, fixtures, or Phase 7.
The active Codex session identifies itself as GPT-6; it did not expose a way
to select or attest the requested GPT-6 Sol Max preset. This record therefore
does not claim that model-specific requirement was met.

**Decision: FAIL.** The consolidation tests are green, but new direct probes
found a persistable false direct precedent and several other contract bypasses.
The prior FAIL records above remain historical and unchanged.

### Method and verification

I checked the master-spec evidence, chronology, equivalence, audit, and
abstention requirements; the Phase 6 completion record and prior reviews;
ADR-026 through ADR-035; the Phase 6 mapping, context, verification,
precedent, pipeline, graph, migration, and application paths; and the
consolidation, Sol-derived, unit, integration, full-slice, and benchmark
tests/fixtures. I then used read-only, offline Python probes against the
reviewed code. These probes were not added to the repository.

On the exact worktree, `uv sync --dev` (with a writable temporary uv cache),
`uv run python scripts/verify.py`, and `git diff --check` passed: Ruff check,
Ruff format on 288 files, Pyright with 0 errors and 0 warnings, and **1498
passed, 5 opt-in network tests deselected**. A fresh local clone at
`/private/tmp/novcheck-phase6-review-fresh`, detached at the exact commit,
passed the literal `uv sync --dev`, `uv run python scripts/verify.py`, and
`git diff --check` with the same results. Initial sandboxed fresh-checkout
sync could not reach its package cache; the requested sync subsequently
succeeded with access to the existing uv cache. Green checks establish the
baseline, not semantic correctness.

### Critical finding

**R01 (F03/F06/F07) — A passage from different content can become a persisted
direct precedent.** Violated invariant: FR-EVID-001/004, FR-SRC-002 and
INV-14 require the decisive cited text to belong to the exact cited
source/version. `passages/extraction.py::extract_resolved_content` attests a
whole document from caller-supplied text; `verification/integrity.py::
validate_semantic_chain` checks the passage's self-hash and owner IDs but not
its relationship to `SourceVersionRecord.content_hash` or
`SourceRecord.content_hash`; `graph/sqlalchemy_repository.py::
_persist_verified_chain` checks the passage node against that same passage
self-hash. Minimal reproduction: make a pre-cutoff version and source whose
content hash is for `"Actually the relay requires an operator."`; construct
a complete resolved-content passage for the same IDs containing `"A threshold
drives a relay coil and switches a load without an operator."`; make otherwise
valid, fully supported mapping/verification/claim models. All contracts
validate, `build_verified_evidence_edge` is decisive, classification is
`DIRECT_PRECEDENT`, and `upsert` persists a `DIRECT_PRECEDENT` graph edge while
the passage hash differs from the cited version's hash. Required: source
content provenance must prove that each passage was extracted from the cited
immutable version, and complete-document/abstract attestations must be checked
against that version's content hash. Smallest architectural fix: carry the
resolved parent-content digest and extraction span/unit proof in the passage
contract, validate it against the owned version (or source for genuinely
unversioned evidence) at chain and repository boundaries, and require exact
digest equality for a complete document. Regression: the conflicting-content
case must fail before classification and roll back graph persistence; genuine
subspans, abstracts, and complete documents must still work.

### Important findings

**R02 (F03) — Callers can assert a complete evidence unit.** Violated
invariant: unknown surrounding content cannot make support decisive.
`passages/extraction.py::extract_span` accepts any `unit_boundary`, and
`context/expansion.py::inspect_passage_context` returns `COMPLETE` immediately
when its two Boolean flags are true, without checking who established the
boundary or whether it encloses the cited unit. Minimal reproduction:
`extract_span` of the first `"Support."` from `"Support. However not in
production."`, with a caller-created `EvidenceUnitBoundary(scope=DOCUMENT,
starts_unit=True, ends_unit=True)`, returns `COMPLETE` even though the qualifier
lies outside the passage. Required: both boundaries must be tied to verified
extraction from the same immutable resolved content and exact unit span.
Smallest fix: make boundary attestations extractor-owned, record their parent
digest and offsets, and recheck them in context inspection and the semantic
chain; unknown provenance abstains. Regression: a caller-declared boundary,
including one with a matching-looking locator, cannot rescue a short excerpt.

**R03 (F10) — The verification contract admits duplicate commitments, and an
unchecked copy can create a decisive direct edge.** Violated invariant:
every material commitment is judged exactly once and aggregate support is
derived from those judgments. `verification/models.py::SupportVerification.
state_matches_payload` derives a state from a set of record states but does
not require unique commitment IDs. A JSON payload with records `mech,
outcome, mech`, all `SUPPORTED`, validates as aggregate `SUPPORTED`.
Separately, `model_copy(update={"state": SUPPORTED})` on a genuine partial
verification leaves one `NOT_SUPPORTED` record; `verification/gates.py::
build_verified_evidence_edge` accepts it and emits a decisive
`DIRECT_PRECEDENT` edge. The later semantic-chain/repository checks reject
these particular invalid aggregates, but the public verification and edge
construction boundaries do not. Required: no schema-valid duplicate-record
verification, and every public edge/classification gate must revalidate
untrusted model instances before relying on aggregate state. Smallest fix:
enforce unique IDs in `SupportVerification`, revalidate through serialized
data at the edge boundary, and derive decisiveness from validated commitment
records. Regression: duplicate JSON records and partial-to-supported copies
must fail at the first authoritative boundary; real scoped partials stay
nondecisive.

**R04 (F04) — Source routing silently omits eligible discovered evidence.**
Violated invariant: bounded local coverage must expose unassessed candidates;
no absence claim may rest on an invisible omission. `phase6_pipeline.py::
select_candidate_sources` uses `routed or all sources`, then computes
`unassessed_sources` only inside that chosen pool. Minimal reproduction: one
source routed to target `mcu_A`, another full-text source with passages routed
to `mcu_B`, and target `mcu_A`. The latter is neither selected nor listed as
unassessed, even with room under `max_sources`. A source may be relevant to
more than its discovery route. Required: disclose all eligible skipped
sources for this target, or assess them under an explicit policy. Smallest
fix: separate routing priority from coverage accounting and include every
eligible nonselected source in `unassessed_sources`. Regression: a relevant
unrouted later source is assessed or visibly unassessed when a routed source
exists.

**R05 (F04/F11 failure path) — A handled mapping failure aborts Phase 6
instead of returning unassessable evidence.** Violated invariant: failed
untrusted model output must become an explicit failure state, not erase the
assessment. `phase6_pipeline.py::_assess_candidate` appends an `UNASSESSABLE`
classification for an invalid mapper response but no chain; `run` later
constructs `classified_comparisons` with `zip(chains, classifications,
strict=True)` (lines 715-721). Minimal reproduction: run the real Phase 5
evidence and Phase 6 pipeline with a mapper response having no dimensions.
Current result is `ValueError: zip() argument 2 is longer than argument 1`;
the unassessable result and coverage record never return. Required: preserve
the selection/mapping failure and finish the Phase 6 local assessment.
Smallest fix: pair classifications with their chain at creation, or retain a
separate list of only chain-backed classifications for persistence. Regression:
one failed and one successful source, and all failed sources, both return
explicit unassessable classifications without a graph crash.

**R06 (F08/F02 patent boundary) — Patent screening accepts a caller-asserted
eligible date for a cited version.** Violated invariant: one-reference
anticipation-like screening must use the exact cited version's verified
disclosure. `precedent/patent.py::PatentEvidenceEntry` accepts a free
`ChronologyAssessment`; for a versioned entry it checks only the date-field
name. `screen_patent_references` treats its `PREDATES_CUTOFF` state as
eligibility. Minimal reproduction: a versioned direct/decisive classification
with parent publication in 2027 and a caller-provided
`version_published_date=2020` chronology produces
`SINGLE_REFERENCE_ANTICIPATION_LIKE`; no version record or
`CitedDisclosure` is supplied or checked. Required: the patent view must
consume the validated `ClassifiedComparison`/cited disclosure, not an
independent date assertion. Smallest fix: derive the patent entry from that
authoritative comparison, or validate the entry against it at screening.
Regression: a post-cutoff version paired with an earlier asserted chronology
cannot yield anticipation; a genuine earlier preprint remains eligible.

**R07 (cross-target anti-stitching) — A foreign MCU classification influences
another target's multi-source result.** Violated invariant: local source/MCU
reasoning cannot transfer support or direct eligibility between MCUs.
`precedent/gates.py::summarize_multi_source` never checks the input
classifications' `mcu_id` against its `mcu_id` argument. Minimal reproduction:
pass a direct classification for `mcu_1` while requesting a summary for
`mcu_other`; the result reports `single_source_direct_eligible=True` for
`mcu_other`. The normal pipeline currently passes a target-local list, but
the public summary contract accepts this cross-wire. Required: reject or
filter foreign classifications before counting roots/direct hits. Smallest
fix: require every input classification to match the requested target.
Regression: a direct hit or two partials for another MCU cannot change this
MCU's summary, including a combination target.

### Additional bypass and migration observations

- **R08 (Important, F06 public API):** `classify_verified_comparison` does
  not revalidate an incoming `VerifiedComparison` instance. A valid 2027
  comparison whose chain is copied with a 2020 decisive edge returns a
  decisive `DIRECT_PRECEDENT`. `ClassifiedComparison` construction and the
  repository reject that forged copy, so persistence is protected, but the
  public classifier has already emitted a valid-looking classification.
  Required: revalidate the comparison at the public classifier boundary.
  Regression: a `model_copy(update=...)` chronology/chain substitution cannot
  return direct. See `precedent/gates.py::classify_verified_comparison` and
  `verification/integrity.py::VerifiedComparison.authoritative_chain`.
- **R09 (Minor, F07 migration):** `graph/migrations.py::ensure_schema` blocks
  nonempty legacy `verified_edges` only when `current == 3`. An offline v2
  database with an orphan `verified_edges` row and no Phase 6 graph edge
  migrated to v4 in a direct probe. That row cannot establish a current graph
  edge without a chain, but the migration contradicts ADR-035's stated rule
  that legacy verified artifacts lacking the v4 chain/classification contract
  require reprocessing. Reject nonempty legacy verified tables for every
  version that can have them; add a v2 orphan-row migration regression.

### New cross-contract interaction probes

These are fresh variants exercised against this commit, not acceptance inferred
from existing tests. `ACCEPTED` means the unsafe input reached the stated
public boundary; it does not imply every later boundary accepted it.

| # | Interaction | Observed |
| --- | --- | --- |
| 1 | Cited version hash × complete resolved passage with different text | **ACCEPTED:** decisive direct classification and graph persistence (R01). |
| 2 | Truncated span × caller-supplied `DOCUMENT` start/end flags | **ACCEPTED:** context `COMPLETE` (R02). |
| 3 | Hidden qualifier outside that span × all-supported verifier | **ACCEPTED:** completeness gate can permit decisiveness (R02). |
| 4 | Future version identity × independently asserted old patent chronology | **ACCEPTED:** anticipation-like mode (R06). |
| 5 | Future validated comparison × copied old edge × public classifier | **ACCEPTED:** direct classification; `ClassifiedComparison` rejects it (R08). |
| 6 | Duplicate material ID × derived aggregate state × JSON validation | **ACCEPTED:** three records validate as `SUPPORTED` (R03). |
| 7 | Partial commitment records × copied aggregate `SUPPORTED` × edge gate | **ACCEPTED:** decisive direct edge; later chain validation rejects (R03). |
| 8 | Direct classification for MCU A × summary requested for MCU B | **ACCEPTED:** B reports direct eligible (R07). |
| 9 | Routed candidate × eligible source routed elsewhere × coverage | **ACCEPTED:** second source absent from selected and unassessed (R04). |
| 10 | Mapper validation failure × chain/classification persistence pairing | **FAILED CLOSED:** pipeline raises `zip` error instead of reporting `UNASSESSABLE` (R05). |
| 11 | Legacy v2 verified artifact × v4 migration without a chain | **ACCEPTED:** schema advances to v4 (R09). |

### Finding status and gate

F02's normal edge/chain chronology authority resisted the old-parent,
post-cutoff-revision, earlier-preprint, unknown-date and foreign-owner cases;
the patent-view assertion in R06 remains open. F03 is open (R01/R02). F06 is
open (R01/R08). F07 is open for passage/version content provenance (R01),
with the additional migration issue R09. F10 is open at the verification and
edge construction boundaries (R03). N02's semantic edge/observation split
passed the repeated-time, exact-replay, assessment/cutoff separation, reopen,
and transaction tests in the full suite; no new N02 failure was reproduced.

Of the previously closed findings, F01's ordered statement commitments,
F05's canonical verifier citations, F09's verified-fact classifier rule,
N01's cutoff-dependent edge IDs, F11's valid combination/expanded-passage
full slice, and M01's explicit diagnostic benchmark description resisted the
reviewed attacks. F04 is reopened by R04/R05. F08 is reopened by R06. The
deterministic benchmark remains a fixture diagnostic, not measured live
entailment or calibration. No Phase 7 implementation was found or started.

Gate 30 cannot pass with R01 and the Important findings open. Remediation
requires new regressions and another independent review of the repaired
commit. This review made no implementation changes.

Acceptance Gate 30: FAIL — Phase 6 remains blocked.

---

## Implementer provenance-hardening record after the `47021af` review

The preceding independent **FAIL** at `47021af` and all earlier FAIL records
remain unchanged. This section records R01-R09 implementation only; it is not
an independent re-review or a Gate 30 PASS. The approved task scope is the
30 September user instruction, recorded in
`docs/superpowers/plans/2026-09-30-phase-6-provenance-hardening-plan.md`.

| Finding | Implemented boundary | Regression evidence |
| --- | --- | --- |
| R01 | Resolved immutable source/version digest and exact passage attestation; chain and repository resolve the parent digest. | Conflicting content rejected; genuine subspan, document, abstract and authenticated direct persistence pass. |
| R02 | Unit limits come from extractor-checked parent spans; caller boundary flags cannot assert completeness. | Truncated `Support.` excerpt, paragraph and numbered claim boundaries. |
| R03 | Exactly one judgment per material commitment; public edge revalidates copied verifier records and derives decisive state. | Duplicate/missing/extra judgments and copied partial-to-supported rejection. |
| R04 | All eligible sources enter bounded selection; routing only changes order, with every skipped source disclosed. | Foreign-route eligible source appears selected or unassessed. |
| R05 | Aligned candidate result carries classification, optional chain and explicit failure; failed mapper continues. | All-failed pipeline and mixed full lifecycle. |
| R06 | Patent entry projection consumes authenticated `ClassifiedComparison` and cited chronology. | Caller-asserted older date cannot produce anticipation-like mode. |
| R07 | Multi-source summary checks MCU target; authenticated path also checks assessment, target kind and combination identity. | Foreign direct/partial MCU and foreign assessment/target-kind attacks. |
| R08 | Public verified classifier revalidates the entire copied comparison chain. | Copied chronology cannot return direct. |
| R09 | v2 and v3 verified rows without current chain block migration. | v2 orphan verified-row migration rejected. |

ADR-036 and amendments to ADR-030, ADR-034 and ADR-035 record the provenance,
context and migration decisions. The new adversarial suite and mixed full
lifecycle test use deterministic providers. They do not establish live LLM
entailment, calibration, or prompt-injection resistance. The exact final code
commit requires an independent semantic re-review before any acceptance claim.

**Gate 30 remains OPEN pending fresh independent semantic re-review. Phase 7
has not started.**

---

## Independent semantic re-review of `bcd4b830262ecde2dc7d4b651f721639ac0f3d6c`

Review date: 30 September 2026. Branch: `phase-6-evidence-verification`.
The reviewed worktree was clean at the exact commit before this review record
was appended. This review followed the requested Stage 1 provenance kill-test.
Stage 1 failed, so the substantive Stage 2 review and its full/fresh-checkout
verification were not performed. Earlier FAIL records above are preserved.

### Stage 1 result: provenance root is broken

**R10 — Critical — A classified passage can be persisted against a different
immutable source/version digest.**

- **Violated invariant:** Every authoritative passage must prove exact ancestry
  from the immutable content of the source/version represented in the graph.
  A decisive graph edge may not cite a passage whose attested parent digest
  differs from the stored source/version content hash (ADR-036; FR-SRC-002,
  FR-EVID-001, FR-EVID-004).
- **Exact location:** `verification/integrity.py::validate_semantic_chain`
  checks the passage parent against the *chain-supplied*
  `SourceVersionRecord.content_hash` (lines 228–242).
  `graph/sqlalchemy_repository.py::_persist_verified_chain` checks that the
  stored source node has the right kind and the version node has the right
  owner, but never compares either node's `content_hash` to the chain record
  or attested parent (lines 238–259). `resolve_version_content` likewise
  accepts the digest in the supplied version record as authority without a
  repository/content-store lookup.
- **Minimal reproduction:** Start with the valid `DIRECT_PRECEDENT` chain from
  `tests.unit.evidence.verification.test_eligibility.build` and `_valid_chain`.
  Before persisting it, seed `SOURCE` and `SOURCE_VERSION` graph nodes for
  those same IDs with `content_hash = text_hash("This version requires an
  operator to switch the load.")`. Seed the cited passage node with its
  original self-hash. Build `VerifiedComparison`, classify it, and call
  `SqlAlchemyEvidenceGraphRepository.upsert` with the verified edge, chain,
  classified comparison, and derived graph edges. Both public classification
  and graph persistence accept it. An independent second probe also changed
  the chain-supplied source/version hash and resolved parent together while
  retaining the original stored version node; this also persisted a decisive
  direct edge.
- **Observed behavior:** The first probe returned a stored version hash of
  `1a292cbe812c42e5f0c686a0cf4d7d0881224aa16cd1dc3d1d95642a83ca9fae`,
  a cited passage parent hash of
  `72ee56daa3b5bc6fe2eda7d9d8e5be8f5859a4b405af05f73b826c087609a98f`,
  and **one persisted `DIRECT_PRECEDENT` graph edge**. The second probe's
  chain/parent hash was
  `bf0c2ab07f9d2b43f42bd5058c19cb27adbaaa46dcd1e17313efd4b8839292fb`
  while the persisted version hash stayed
  `72ee56daa3b5bc6fe2eda7d9d8e5be8f5859a4b405af05f73b826c087609a98f`;
  it also persisted a decisive direct edge. The passage is self-consistent
  inside each chain but lacks ancestry from the stored version authority.
- **Required behavior:** Reject the mismatch before decisive classification
  when an authoritative version is available, and reject it transactionally
  at graph persistence in all cases. No verified artifact, classification,
  observation, or graph edge should persist from the mismatched batch.
- **Smallest architectural fix:** Establish one immutable content authority
  per source/version ID. At the repository boundary, compare the attested
  parent digest and chain source/version hashes with the already persisted or
  concurrently supplied authoritative source/version nodes, including access
  state and owner. Reject conflicting batch nodes instead of treating a
  caller-supplied, internally consistent chain as authority. Public gates that
  promise authoritative classification need to resolve that same authority
  or explicitly remain nonauthoritative until repository validation.
- **Required regression:** Seed an existing source/version with content A;
  submit a fully self-consistent, `SUPPORTED` and `COMPLETE` chain for the
  same IDs with content B and a valid extractor attestation. Assert rejection
  and transaction rollback, with no direct graph edge or observation. Repeat
  for an unversioned source and for conflicting source/version nodes supplied
  in the same `upsert` batch. Retain a positive test for an exact matching
  digest and passage slice.

The two reproductions ran against the exact commit with
`PYTHONPATH=.:src UV_CACHE_DIR=/private/tmp/uv-cache uv run python` and exited
successfully as probes. They made no production or test changes. The first
attempt to use the default `uv` cache was denied by the filesystem sandbox;
the writable temporary cache resolved that environment issue. `git diff
--check` passed after this review record was appended. The requested
`uv sync --dev`, full `scripts/verify.py`, and detached-checkout repetition
belong to Stage 2 and were not run after this Stage 1 failure. Passing
implementation-suite results cited above do not close R10.
No Phase 7 work was started.

Acceptance Gate 30: FAIL — Phase 6 remains blocked.

---

## R10 implementation record after the Stage-1 FAIL (not an independent review)

The `bcd4b83` Stage-1 **FAIL** and every earlier FAIL record remain intact.
This section records the implementer's bounded R10 repair, not semantic
acceptance. `SqlAlchemyEvidenceGraphRepository` now treats the persisted
`SOURCE_VERSION` content hash, owner and access state as authority for a cited
version. It compares the chain's version record and every passage parent
attestation to that authority. For unversioned evidence, it uses the
persisted `SOURCE` content hash and access state. A new version may establish
authority only when concurrently supplied nodes, the chain and attestations
agree. Same-ID conflicts, including multiple nodes in one batch, abort the
transaction before any semantic write commits.

The same authority check covers verified-edge replay, chain writes,
classification-only writes, proposition nodes and Phase 6 graph edges.
Chain-only classification is provisional until repository validation.
ADR-036 records the persisted-authority rule. The new R10 adversarial suite
has 15 deterministic cases, including all seven requested conflict and
positive paths, transaction rollback, owner/access disagreement and replay
through alternate persistence inputs. The pre-existing R01–R09 suite is
retained. No Phase 7 work was started.

Implementation tests and verification do not replace the fresh independent
Stage-1 provenance re-review. This record does not close R10 or Gate 30.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance re-review.

---

## Independent Stage-1 provenance kill-test of `f355b433a4f4dc3a4958c7be7c0669f94b63fda7`

**Reviewed state:** exact commit `f355b433a4f4dc3a4958c7be7c0669f94b63fda7` on `phase-6-evidence-verification`. This review changed no production code or tests. It stopped at Stage 1 after the following Important bypass; the full Gate-30 review and full verification suite were not run. Phase 7 was not started.

**Stage 1: FAIL — R11 (Important), provisional classifications escape before content-authority reconciliation.** The repository's R10 check rejects a conflicting stored version digest and rolls back its semantic tables. However, `phase6_pipeline.py::_assess_candidate` emits `PRECEDENT_CLASSIFICATION` with `TraceStatus.SUCCESS` before `run` calls `repository.upsert`. The same `run` computes and emits successful `MULTI_SOURCE_ASSESSMENT` and `PATENT_SCREENING` events before that call. `classify_verified_comparison` calls its output provisional in a docstring, but no provisional type or flag prevents these downstream uses. The application's `JsonlTraceSink` writes the events immediately to `trace.jsonl`; a later repository rollback cannot retract them. This violates the Stage-1 requirement that a comparison derived from content conflicting with immutable authority cannot be presented as authoritative, including through an output written outside the authoritative transaction.

**Independent reproduction:** Using the existing deterministic Phase 5/6 fixture, obtain internally consistent evidence for source `src_8a0415e078bc6a9fb6e9a72081c68a6bedd0de5c050d734abf49addd31c71d08`, version `srcv_2e95a77bc2dd7d915dac4c1ac70513f49979fb47c3858ea2b19019bd9eee0e2c`, with incoming content digest `7a7b5759734ec46553e926f8ccc1dc273513d60dc6c09dc6e93203f5b572cac2`. In a separate repository, seed a normal `SOURCE` node and a same-ID `SOURCE_VERSION` node with digest `a8e6a985acc0141fe341238f86931786d2c261e840552198a214e1932a613bc5`. Run `verify_evidence_against_mcus` with the original evidence, that repository, the scripted provider, and a real `JsonlTraceSink`. The repository raises `ValueError: Version content authority conflicts with semantic chain`. Its `verified_edges`, `verification_observations`, `verified_chains`, and `verified_classifications` tables each have zero rows afterward. Yet the durable trace contains **three** `PRECEDENT_CLASSIFICATION` events for the conflicting source, each with `status=SUCCESS` and `relation=DIRECT_PRECEDENT`; it also contains three successful multi-source summary events and three successful patent-screening events. No result object was returned, but these append-only trace assertions survived the rejection. The probe used a temporary database and trace, with no repository code or fixture edits.

**Required correction:** Reconcile source/version content authority before emitting or consuming a classification as an assessed finding. Ensure summary, patent screening, and success trace publication occur only after the authoritative repository transaction succeeds, or make provisional output structurally distinct and prevent it from reaching these sinks and downstream APIs. A regression should seed a conflicting stored version, run the pipeline with a durable trace sink, and assert that no successful direct-classification, summary, or patent-screening assertion survives; retain the positive exact-match path. Repository rejection and rollback already work for the tested mismatch, but that does not close this output boundary.

**Verification scope:** Two focused offline pipeline probes reproduced the issue, first with a stored-node change and then with a clean separate repository seeded through `upsert`. The second used the production `JsonlTraceSink`. The dedicated R10 tests and full `scripts/verify.py` were not run after this Stage-1 failure, as the requested kill-test instructs. Gate 30 remains blocked pending repair and another independent Stage-1 review.

Acceptance Gate 30: FAIL — Phase 6 remains blocked.

---

## R11 authoritative-publication implementation record (not an independent review)

The independent Stage-1 **FAIL** for R11 at `f355b433` remains unchanged.
This section records implementation evidence only; it does not close R11 or
grant Gate 30 acceptance. Phase 7 was not started.

The repository now returns an immutable `Phase6CommitReceipt` only after its
semantic transaction commits. Phase 6 commits each assessed comparison before
publishing mapping, verification or classification success. A content-authority
rejection becomes an explicit unassessable failure. Published multi-source and
patent results use only committed comparisons, with actual receipt edge and
classification IDs carried in stable success events. Exact replay keeps the
same semantic identities and the JSONL sink skips an already delivered event
ID. If trace delivery fails after commit, the repository remains authoritative;
the run raises and can be retried. The returned Phase 6 result carries the
receipts; the legacy Phase 7 projection refuses an edge without a matching
receipt. ADR-036 records this publication boundary and the absence of a
crash-safe transactional outbox requirement.

`tests/adversarial/test_phase6_r11_authoritative_publication.py` was added
before the production change. Its first conflict test failed against the
reviewed behavior because a rejected chain left a successful
`PRECEDENT_CLASSIFICATION` event, then passed after the repair. The suite
covers version and unversioned conflicts, coordinated provenance fields,
post-commit receipt/trace timing, receipt-gated legacy projection, exact-match
paths, mixed committed/rejected summaries and patent results, two legitimate
partial patents, trace failure
after commit, and idempotent replay. The R10 and R01-R09 adversarial suites
remain in place.

Implementation worktree checks after the code and tests: `uv sync --dev`
passed with the writable uv cache; `uv run python scripts/verify.py` passed
Ruff check, Ruff format (291 files), Pyright with 0 errors/0 warnings, and
**1549 passed, 5 opt-in network tests deselected**. `git diff --check` passed.
These implementation checks do not replace a fresh independent Stage-1
provenance/publication re-review.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance/publication re-review.

---

## Independent Stage-1 provenance/publication kill-test of `49504d7cfa0ff33275c1e15d828b1ffe047849e0`

**Reviewed state:** clean `phase-6-evidence-verification` worktree at the exact
commit above, before this review-only append. The reviewer did not implement
R10/R11 or change production code, tests, fixtures, or Phase 7. Stage 1 stopped
at the reproduced publication bypass below; Stage 2 and its full verification
were not performed.

**Stage 1: FAIL — R12 (Important), an uncommitted verifier conclusion survives
content-authority rejection.** `phase6_pipeline.py::_assess_candidate` emits a
`SUPPORT_VERIFICATION` trace event immediately when the verifier state is
`CONTRADICTED` or `NOT_SUPPORTED`. Its `failure=True` path calls `publish`
directly, bypassing `pending_success` and the `Phase6CommitReceipt` gate. The
event contains the verification ID, source ID, MCU ID, `state=CONTRADICTED`,
and `semantics_implemented=true`. `JsonlTraceSink` appends it durably before
`_commit_candidate` reconciles the cited version with stored content authority.
`TraceStatus.FAILURE` here labels a negative semantic judgment, not a failed
verification operation; it does not make the judgment provisional or retract
it after authority rejection. This violates the Stage-1 requirement that no
uncommitted semantic result escape through durable output.

**Independent reproduction:** Using the deterministic Phase 5 fixture, retain
one source and its cited version. Seed the repository with a `SOURCE_VERSION`
node for that same ID whose `content_hash` is digest A, while the incoming
version and extractor-attested passage use digest B. Supply a valid scripted
verifier response that marks each material commitment `CONTRADICTED`, citing
the supplied passage. Run `verify_evidence_against_mcus` with the production
`JsonlTraceSink`. The repository rejects the comparison with `Version content
authority conflicts with semantic chain`; the returned result has zero edges
and zero commit receipts. `verified_edges`, `verified_chains`,
`verified_classifications`, and `verification_observations` each have zero
rows. Yet `trace.jsonl` contains a durable `SUPPORT_VERIFICATION` event with
`status=FAILURE`, `state=CONTRADICTED`, and a verification ID for the rejected
source, followed by `CONTENT_AUTHORITY_REJECTED`. A second probe using
`NOT_SUPPORTED` likewise left an uncommitted verifier-state event, although
that run subsequently failed chain validation before reaching persistence.
Both probes were read-only with temporary databases/traces outside the repo.

**Required correction:** Defer publication of all verifier conclusions,
including `CONTRADICTED` and `NOT_SUPPORTED`, until the comparison has a
matching post-commit receipt. Processing failures such as invalid mapping or
content-authority rejection may be traced immediately, but must not carry an
uncommitted semantic finding. Add a regression with conflicting stored
version content and a contradicted verifier result; assert no verifier-state
event survives, no semantic rows or receipt exist, and an exact-match
contradiction is published only after commit.

The R10 repository authority check held in this probe; the publication
boundary did not. No full `scripts/verify.py`, fresh checkout, or Stage-2
review was run after this Stage-1 failure. No Phase 7 work was started.

Acceptance Gate 30: FAIL — Phase 6 remains blocked.

---

## R12 verifier-publication implementation record (not an independent review)

The independent **R12 FAIL** at `49504d7` above remains unchanged. This
section records the implementer's bounded repair and does not close R12 or
grant Gate 30 acceptance. No Phase 7 work was started.

Every `SUPPORT_VERIFICATION` outcome now enters the existing pending event
queue, regardless of its semantic state. The event is published with
`TraceStatus.SUCCESS` and the committed edge/classification identities only
after `_commit_candidate` returns a matching `Phase6CommitReceipt`. A guard
rejects use of the immediate operational-failure path for a verifier
conclusion. Mapper and content-authority processing failures remain immediate
diagnostics without semantic verifier-state assertions. ADR-036 records the
status and publication distinction.

The R12 tests in `test_phase6_r11_authoritative_publication.py` were added
first. Both contradictory and not-supported provenance-conflict cases failed
against the reviewed behavior because a verifier-state event survived; after
the change they assert zero semantic rows, edges and receipts, and no durable
verifier conclusion across retries. Positive controls exercise all five
verifier states, verify the matching semantic rows exist when the event is
delivered, and check exact replay does not add an independent trace finding.
An invalid mapper response still produces an immediate operational diagnostic
with no semantic state. The focused R10/R11/provenance suites passed with
**58 tests**. Implementation-worktree verification passed: `uv sync --dev`,
`uv run python scripts/verify.py` (Ruff check, Ruff format on 291 files,
Pyright 0 errors/0 warnings, **1557 passed, 5 opt-in network tests
deselected**) and `git diff --check`. Exact-commit fresh-checkout verification
is recorded in the implementation handoff; these checks are not independent
semantic acceptance.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance/publication re-review.

---

## Stage-1 provenance/publication kill-test of `6abaefc7ea12b9d20ebc397739c8bdc0ac8984ee`

**Scope and reviewer limitation:** This was a read-only Stage-1 attack on the exact
commit, before this review-only append. The reviewer in this Codex session also
implemented the R12 remediation, so this record cannot satisfy the request for
an *independent* reviewer. It records a reproduced failure, not semantic
acceptance. No production code, tests, fixtures or Phase 7 work were changed.

**Stage 1: FAIL — R13 (Important), a caller-created receipt authorizes an
uncommitted direct precedent in the legacy projection.** The
`Phase6CommitReceipt` contract in `evidence/graph/repository.py` is a public,
constructible Pydantic model containing only an assessment ID and edge and
classification ID tuples. `application/evidence_phase6.py::project_verified_edges`
checks those supplied IDs against the supplied result, but does not resolve the
receipt or the semantic artifacts from the authoritative repository. Possession
of a matching caller-created receipt is therefore sufficient to project an
unpersisted `DIRECT_PRECEDENT` edge for the later-phase compatibility boundary.
The normal pipeline's post-commit receipt path does not cure this public
projection bypass.

**Minimal reproduction:** Build the valid supported chain from
`tests.adversarial.test_phase6_sol_review_regressions._valid_chain` and
`tests.unit.evidence.verification.test_eligibility.build`, and classify its
`VerifiedComparison`. Do **not** create or write any repository. Construct
`Phase6CommitReceipt(assessment_id=chain.assessment_id,
committed_edge_ids=(chain.edge.edge_id,),
committed_classification_ids=(classification.classification_id,))`, then place
the chain's edge and classification and this receipt into a
`Phase6EvidenceResult` with `graph_ref='nonexistent.sqlite'`. Calling
`project_verified_edges(result)` returns one legacy edge with
`relation_type=DIRECT_PRECEDENT`. The offline probe printed
`repository_used=False`, `receipt_constructed_by_caller=True`,
`projected_count=1`, and `relation=DIRECT_PRECEDENT`.

**Violated boundary and required behavior:** Stage 1 requires fabricated or
cross-wired receipts to be unable to authorize later-phase projection. This
receipt has never been issued by a repository transaction, yet the projected
edge is presented as implemented Phase 6 evidence. Projection must validate
the exact assessment, edge, classification and provenance against committed
repository artifacts, or consume an authority-controlled projection rather
than a freely constructible result/receipt pair. A regression should construct
this fully matching but unpersisted receipt and require rejection, then retain
the positive exact-commit projection path. Test a receipt from another
repository and an older successful run against a rejected new comparison.

The requested kill-test stops at this reproduced Important bypass. The
focused verification command, full Gate-30 Stage 2 review and fresh checkout
were not run for this review. Earlier implementation test results do not close
R13. Gate 30 remains blocked, and an independent reviewer is still required.

Stage 1 provenance/publication re-review: FAIL — Phase 6 remains blocked.

---

## R13 commit-receipt authority implementation record (not an independent review)

The preceding R13 Stage-1 **FAIL** at `6abaefc7` remains unchanged. This
section records the implementer's bounded repair only; it does not close R13
or grant Gate 30 acceptance. Phase 7 was not started.

Schema v5 stores an immutable Phase 6 commit manifest in the same repository
transaction as its verified edge, chain and classification. The returned
`Phase6CommitReceipt` references that manifest. Repository resolution checks
the receipt against persisted IDs, exact classified comparisons, cited passage
nodes and source/version content authority. The public legacy projection now
requires a repository, rejects caller-result disagreement and projects the
repository-loaded edge and classification. The Phase 6 pipeline resolves its
receipt before publishing queued semantic events. Existing v4 semantic rows
have no manifest and require exact validated replay before projection.

`tests/adversarial/test_phase6_r13_commit_receipt_authority.py` first
reproduced a fabricated receipt projecting an unpersisted direct edge, then
covered empty and foreign repositories; receipt copy, construct and JSON
forgery; missing manifests; an old receipt paired with rejected new content;
caller-mutated identity, citations, classification, chronology and provenance;
content-authority revalidation; v4 replay; exact commit/replay; and positive
projection for direct, partial, component, contradiction, no-direct and
unresolved states. The focused R10–R13/provenance suites passed **84 tests**.
ADR-036 records that a receipt is a repository reference rather than proof.

Implementation verification and a fresh exact-commit checkout are recorded
with the implementation handoff. These checks cannot replace a fresh
independent Stage-1 provenance/publication re-review.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance/publication re-review.

---

## Stage-1 commit-authority probe of `2b8605a948b4992e357f0e94ffc0577802b65f4c`

**Scope and independence limitation:** This read-only probe used the exact
commit above on `phase-6-evidence-verification`; the worktree was clean before
this review-only append. The reviewer in this Codex session also implemented
R12 and R13, so this record cannot satisfy the requested *independent*
review. No production code, tests, fixtures, or Phase 7 work were changed.
The reproduced Important bypass below is sufficient for a Stage-1 FAIL;
the full A–V attack matrix, focused suites, and Gate-30 Stage 2 review were
not run.

**R14 — Important — A Phase 6 direct graph edge is readable and writable
without a v5 commit manifest.** The v5 receipt resolver correctly rejects a
missing manifest, and `project_verified_edges` uses that resolver. The public
graph interface does not enforce the same authority boundary.
`graph/migrations.py::ensure_schema` permits v4 Phase 6 graph edges to migrate
without a manifest. `graph/sqlalchemy_repository.py::edges` and `get_edge`
return those edges without commit resolution. Its `upsert` path also accepts
Phase 6 graph edges backed by migrated verified rows when no
`classified_comparisons` are supplied; `_verify_phase6_edges` resolves the
old chain and classification but does not require a manifest, and `upsert`
returns no receipt. The resulting `GraphEdge` has
`kind=DIRECT_PRECEDENT` and no provisional marker.

Three offline probes against temporary SQLite databases reproduced the gap:

1. Persist a valid direct graph edge and semantic chain, remove only the v5
   manifest, mark the database v4, then reopen it. Migration advances the
   schema to v5 with **zero** manifests, while `edges(kinds={DIRECT_PRECEDENT})`
   returns one edge and `get_edge` returns that direct edge.
2. Persist valid semantic rows without a graph edge, remove the manifest,
   mark the database v4, and reopen it. A graph-only `upsert(nodes=...,
   edges=...)` then returns `None` yet stores one readable
   `DIRECT_PRECEDENT` edge with **zero** manifests.
3. In a v5 database, remove the manifest after a valid commit.
   `resolve_phase6_commit(receipt)` raises `ValueError`, but
   `edges(kinds={DIRECT_PRECEDENT})` still returns the direct edge.

**Violated boundary:** A v4 semantic row must not become a v5 committed
finding merely through migration or a graph-only write. A later missing
manifest must also revoke authoritative retrieval. The graph is the central
analytical structure under master-spec section 26, and its public repository
methods return ordinary domain `GraphEdge` objects; callers have no way to
distinguish these uncommitted edges from committed ones. This is a graph
read/write bypass, not a bypass of `project_verified_edges`, which rejected
the tested missing-manifest state.

**Required correction:** Phase 6 graph-edge writes and authority-sensitive
reads must resolve a matching v5 commit manifest and its exact classified
chain. Quarantine or hide migrated v4 Phase 6 graph edges until validated
replay creates that manifest, while retaining Phase 5 graph behavior.
Regression tests should cover all three probes and a positive exact-replay
direct edge. The probes changed only temporary databases; no repository
production or test files were modified. `git diff --check` passed after
this review-only append.

Stage 1 provenance/publication/commit-authority re-review: FAIL — Phase 6 remains blocked.

---

## R14 graph-authority implementation record (not an independent review)

The R14 **FAIL** at `2b8605a` above and every earlier FAIL record remain
unchanged. This section records the implementer's repair only; it does not
close R14 or grant Gate 30 acceptance. Phase 7 was not started.

Schema v6 adds foreign-key-backed commit membership for Phase 6 graph edges
and evidence-proposition nodes. The repository writes those derived graph
projections, semantic artifacts, manifest and membership in one transaction.
A graph-only `upsert` cannot create or replay a Phase 6 semantic relation.
Public `get_edge`, `edges`, `get_node`, `nodes` and `neighbors` resolve the
membership, manifest, exact classified comparison, passage/content authority
and derived graph fields before returning Phase 6 semantics. Orphan rows from
v4/v5 migration or later corruption are excluded; validated semantic replay
can establish membership. Ordinary Phase 5 graph relations retain generic
write and read behavior. ADR-036 records the sole-authority rule and the
schema migration.

`tests/adversarial/test_phase6_r14_graph_authority.py` was added before the
production repair. Its initial three tests failed against the reviewed code:
migrated v4 direct graph read, graph-only write over legacy semantic rows and
missing-manifest read. The final 24-case suite also covers proposition nodes,
missing membership, cross-manifest association, caller copies, graph citation
corruption, relation-family orphan reads and committed positive controls,
validated replay, exact replay and ordinary nonsemantic graph edges. The
focused R10–R14/provenance suites passed **108 tests**. The R10 replay test
now checks that a content-authority-corrupted direct graph edge disappears
from authoritative reads before testing write rejection. Historical schema
version assertions were updated from v5 to v6 because the persisted schema
changed.

Implementation worktree verification after the production, test and ADR
changes: `uv sync --dev` passed; `uv run python scripts/verify.py` passed
Ruff check, Ruff format (293 files), Pyright with 0 errors/0 warnings, and
**1607 passed, 5 opt-in network tests deselected**; `git diff --check`
passed. The exact implementation commit and detached-checkout verification
are reported in the implementation handoff. These implementation checks
cannot substitute for an independent Stage-1 attack.

Gate 30 remains OPEN pending fresh independent Stage-1 provenance/publication/commit-authority re-review.

---

## Independent Stage-1 authority review of `750917734fbed622f785f96e3d1d443dea166fe7`

**Scope:** Read-only review of the exact clean `phase-6-evidence-verification`
commit above. This reviewer did not implement R10–R14. The earlier FAIL and
implementation records remain unchanged. The attached Stage-1 request requires
the review to stop before focused or full verification when an Important
authority defect is reproduced. No production code, tests, fixtures, or Phase 7
work were changed.

**Stage 1: FAIL — R15 (Important), legacy projection ignores schema-v6 graph
membership.** A Phase 6 commit receipt resolves the stored semantic chain and
classification through `graph/sqlalchemy_repository.py::_resolve_phase6_commit_in_session`
(lines 304–348), but that resolver never checks the schema-v6 graph-edge or
proposition-node membership. `application/evidence_phase6.py::project_verified_edges`
(lines 82–143) accepts this receipt resolution and projects the classified
edge. The graph readers do check membership and hide revoked or orphaned graph
state. Thus the same repository can deny that a direct precedent is an
authoritative graph relation while exporting it as a `DIRECT_PRECEDENT`
`EvidenceEdge` for the later-stage compatibility boundary.

**Minimal reproduction:** Persist a valid, fully supported direct comparison
with its source/version/passage nodes, Phase 6 graph edges, proposition node,
manifest and memberships. Before mutation, the repository returns one direct
graph edge and `project_verified_edges` returns one direct legacy edge. In a
temporary SQLite database, delete only the rows in
`phase6_graph_edge_memberships` and `phase6_graph_node_memberships`. Afterward,
`get_edge(direct_id)` and `get_node(proposition_id)` both return `None`, while
`resolve_phase6_commit(receipt)` still returns the comparison and
`project_verified_edges(result, repository)` still returns one
`DIRECT_PRECEDENT` edge. All caller artifacts and receipt IDs are unchanged;
the removal affects only membership. This is a read-side bypass of the
request's requirement that missing membership revoke authoritative later-stage
projection.

**Fresh variants:** Eleven independent temporary-database probes exercised
edge-only, node-only, both, and direct-edge-only membership deletion; graph
edge deletion; proposition-node deletion; removal of all Phase 6 graph
projections; corrupted graph citation; corrupted proposition identity; a
semantic commit that never wrote graph projections; and v5-to-v6 migration
with a manifest but no graph membership. In each case the relevant graph read
was absent or rejected, but receipt resolution and legacy direct projection
still succeeded. These include migration-plus-projection,
membership-removal-plus-projection, and corruption-plus-projection interaction
attacks. The existing R14 tests cover graph readers but do not check this
cross-boundary export.

**Required behavior:** A later-stage compatibility projection must resolve the
exact authoritative graph projection and its current v6 membership, including
the manifest and derived fields, before exporting a Phase 6 relation. A
semantic-only manifest or a migrated v5 manifest must not silently satisfy
the asserted graph-authority contract. A regression should repeat the minimal
reproduction and the v5 migration and graph-corruption variants, assert that
projection rejects them, and retain a positive exact-commit/replay case.
Revisit the existing semantic-only upsert path, which currently produces a
receipt accepted by projection without any Phase 6 graph relation.
ADR-036 currently describes direct semantic-artifact resolution for the
compatibility projection; reconcile that documented rule with the requested
schema-v6 membership authority before treating the boundary as closed.

**Verification scope:** The probes ran with `PYTHONPATH=.:src .venv/bin/python`
against the exact reviewed commit and used only temporary SQLite databases.
They changed no repository files. The Stage-1 failure is sufficient to block
acceptance, so the focused R10–R14/provenance suites, full Stage-2 review and
fresh checkout were not run. No conclusion is asserted here about the untested
parts of the A–V matrix or live-model entailment. Gate 30 remains open.

Stage 1 provenance/publication/commit/graph-authority re-review: FAIL — Phase 6 remains blocked.

---

## R15 downstream authority consolidation implementation record (not an independent review)

The independent R15 **FAIL** above and all prior FAIL decisions remain intact.
This section records implementation evidence only. It does not close R15 or
grant Gate 30 acceptance.

Schema v7 stores an immutable, versioned assessment ledger for target
profiles, bounded candidate outcomes, failures, context attempts, coverage,
and derived multi-source and patent inputs. The repository assembles
`Phase6AssessmentView` in one SQLite read transaction from that ledger,
committed semantic chains, immutable passage/content ancestry and current
schema-v6 graph membership. A semantic commit remains distinguishable from
an authorized graph relation. Graph-backed membership loss or corruption
fails the trusted read; a deliberately semantic-only or nonrelational status
does not claim a graph edge. Historical coverage is unavailable absent a
validated ledger replay.

The real Phase 6 vertical slice and its fixture adjudicator and minimal
report use a repository-loaded view. The production legacy projection surface
was retired. `phase6/assessment_view.json` is a labeled derived export, not
an authority source. Earlier phase fixture `EvidenceEdge` use remains. The
new R15 adversarial and parity tests and the architecture guard exercise this
boundary. Phase 7 adjudication has not started.

Implementation verification and the exact commit are recorded in the Task 12
handoff. An independent Stage-1 provenance/publication/commit/graph/downstream
authority attack on that commit is still required. A separate full Gate-30
review follows any Stage-1 PASS. R15 and Gate 30 remain OPEN.

---

## Final independent Stage-1 authority review of `7cd20fa80dd73da2d14bc70bd74c6469bbb19678`

**Scope and independence:** This review used the clean
`phase-6-evidence-verification` worktree pinned to the exact commit above.
The reviewer did not implement the downstream consolidation or R10–R15
repairs. The probe changed only a temporary SQLite database. Historical FAIL
and implementation sections above remain unchanged. This is a bounded Stage-1
authority decision, not Gate-30 Stage 2.

**Stage 1: FAIL — R14/R15 graph authority (Important).** A public graph reader
still returns a Phase 6 `DIRECT_PRECEDENT` relation after the matching
evidence-proposition node loses its schema-v6 commit membership. ADR-036's
R15 amendment and the approved consolidation design §7 require both the
relation and proposition membership for graph projection authority. The
governing Stage-1 attack D specifically requires authoritative graph readers
to hide invalid Phase 6 graph state when proposition-node membership is
missing. `load_phase6_assessment` correctly rejects the same database state,
so the repository currently gives conflicting graph-authority answers.

**Reproduction:** In a temporary database, use
`tests.adversarial.test_phase6_r15_assessment_authority._load_committed_matrix_case`
with `DIRECT_PRECEDENT` to create a valid graph-backed semantic commit and v7
snapshot. Select the direct authorized relation. Confirm `get_edge` and
`get_node` both return their respective projection. Delete only the row in
`phase6_graph_node_memberships` for that relation's proposition node, then
read through the public repository APIs and assessment loader:

```text
baseline: get_edge=True, get_node=True, authorized_graph_relations=2
after node-membership deletion:
  get_edge(direct_edge_id)=GraphEdge(kind=DIRECT_PRECEDENT)
  get_node(proposition_node_id)=None
  edges(kinds={DIRECT_PRECEDENT})=[GraphEdge(kind=DIRECT_PRECEDENT)]
  load_phase6_assessment(...)=Phase6AssessmentAuthorityError(
      "Proposition memberships do not exactly match the derived projection")
```

The edge still has its own valid membership, manifest and semantic chain;
only the required companion proposition membership is absent. In
`sqlalchemy_repository.py`, `_authoritative_graph_edge` validates the edge's
membership and derived fields but does not validate the corresponding
proposition-node membership. `get_edge` and `edges` expose that result.
The trusted loader separately checks the exact proposition membership and
fails closed. The R14 regression suite deletes relation membership when
checking `get_edge`; it does not exercise this cross-projection condition.

**Impact and disposition:** A graph specialist consuming public authoritative
graph reads can treat this direct precedent as established while the trusted
assessment view denies graph authority. This violates the approved single
repository authority model. Public Phase 6 graph relation reads must honor
the required proposition membership and current projection validation, or
explicitly signal unavailable authority. This finding does not assert that
the real vertical slice uses the retired legacy adapter; the reproduction is
at the public graph reader boundary.

The reproduced Important defect triggers the requested stop rule. The
remaining A–K attack matrix, including the other four fresh variants, focused
and full verification, clean detached-checkout verification, and Gate-30
Stage 2 were not run. No production code or tests were changed, and no Phase 7
work was started. Gate 30 remains open.

Stage 1 provenance/publication/commit/graph/downstream-authority review: FAIL — Phase 6 remains blocked by a reproduced existing-invariant violation.

---

## R15 public graph-reader consistency implementation record (not an independent review)

The preceding independent Stage-1 **FAIL** at
`7cd20fa80dd73da2d14bc70bd74c6469bbb19678` and all earlier review
decisions remain unchanged. This is implementation evidence for the bounded
R14/R15 authority invariant, not a Stage-1 PASS or Gate-30 acceptance.
The code and regression commit is
`37f29cb43e200c423672bbba7a9b755de66f65e2`.

The exact independent proposition-membership reproduction was added before
the repository change. It failed because `get_edge` returned a
`DIRECT_PRECEDENT` relation after only the required proposition membership
was deleted; `get_node` and `load_phase6_assessment` already rejected that
state. The root cause was that `_authoritative_graph_edge` checked its own
membership and semantic chain but not the complete companion projection.

The repository now uses `_authoritative_phase6_projection` to validate the
exact edge and proposition memberships, their shared commit identity, every
required projection row, derived fields, and committed semantic chain.
`get_edge`, `edges`, `get_node`, `nodes`, and `neighbors` reach this rule;
the assessment loader also calls it within its single read transaction.
Ordinary Phase 5 graph edges retain their existing read behavior. The
semantic receipt still resolves after graph membership revocation, while
the graph readers hide the relation and the assessment loader fails closed.
No schema change or legacy downstream adapter was introduced.

The new table-driven public-reader matrix covers valid state, both membership
deletions, missing graph rows, foreign and split manifests, corrupted edge
source/target/kind/identity/citations, corrupted proposition identity, and
missing sibling relation membership. It exercises direct, contradictory,
strong partial, component, analogous and no-match graph-backed relations,
including their support/contradiction edges. Thirteen further mutation
variants probed membership identity columns, row metadata, proposition
mapping/citations, verification reference and sibling citation, plus a
semantic-receipt-after-revocation probe. No additional authority bypass was
reproduced after the shared resolver was installed. An older F07 positive
fixture was corrected to persist the complete graph projection it claimed
to represent; its negative forged-reference assertions remain.

Progressive verification after the final code path: exact regression and
matrix **36 passed**; R14/R15 plus graph repository **149 passed**;
R10–R15/provenance/publication **166 passed**; Phase 6 integration, parity,
pipeline and full slice **32 passed**. `uv sync --dev` passed. The full
`uv run python scripts/verify.py` passed Ruff check, Ruff format (306 files),
Pyright (0 errors, 0 warnings), and **1745 passed, 5 opt-in network tests
deselected**. `git diff --check` and staged whitespace checks passed. The
final documentation commit and clean detached-checkout verification are
reported in the implementation handoff. This record does not close R15 or
Gate 30. Phase 7 remains unstarted.
