# Phase 6 Semantic Review Remediation Plan

**Base branch:** `phase-6-evidence-verification`
**Reviewed commit:** `e4683fd`
**Review decision:** FAIL
**Reviewer:** GPT-6 Sol High
**Scope:** Close F01–F11 and M01 without starting Phase 7.

## Repair principles

- Do not redesign Phase 6 architecture.
- Preserve mapper -> verifier -> eligibility -> classifier separation.
- Add a regression test for every Critical and Important finding.
- Do not weaken existing tests to accommodate fixes.
- Treat the review document as authoritative for the reproduced counterexamples.
- Use DeepSeek V4.1 Flash Max for implementation/fixes.
- After all fixes pass, require a fresh GPT-6 Sol High re-review.
- Phase 7 remains blocked until Gate 30 passes.

## Recommended fix order

### Task 1 — Close cross-artifact integrity holes (F05, F06, F07)

These are foundational because later semantic logic is unsafe if support can be detached from the cited artifact.

#### F05 — Supported judgments must cite evidence
Fix:
- Reject `SUPPORTED`, `PARTIALLY_SUPPORTED`, and `CONTRADICTED` commitment judgments with zero relied-on passages.
- Remove mapper-passage fallback when constructing a support-bearing or decisive edge.
- A decisive edge must use verifier-cited passage IDs only.

Required regressions:
- `SUPPORTED` with `passage_ids=[]` is rejected or remains nondecisive.
- Mapper-cited passages cannot substitute for verifier citations.
- No direct-precedent graph edge is emitted without verifier-cited support.

#### F06 — Enforce complete identity joins
At every public semantic boundary validate agreement of:
- source ID;
- source-version ID;
- MCU/combination target ID;
- proposition ID;
- mapping ID;
- claim/bundle ID;
- verification ID.

Required regressions:
- foreign source;
- foreign version;
- foreign proposition;
- mismatched mapping/verification;
- patent entry with wrong MCU/version.

#### F07 — Verified graph edges must reference real verified artifacts
Fix:
- graph persistence must resolve `verified_edge_id`;
- referenced artifact must exist;
- relation, source, target MCU, support state, decisiveness, and chronology eligibility must match;
- validation occurs transactionally before persistence.

Required regressions:
- nonexistent verified-edge ID rejected;
- mismatched verified-edge ID rejected;
- valid projected edge persists.

Commit this integrity repair separately.

### Task 2 — Fix version-aware chronology and candidate/version coverage (F02, F04)

#### F02 — Cited version controls disclosure eligibility
Fix:
- `assess_chronology` must receive the cited source-version publication/disclosure date;
- eligibility must be conservative across source-level and version-level dates;
- a post-cutoff revision cannot inherit an older source date;
- unknown version timing remains uncertain/nondecisive;
- passage version must match the assessed version.

Regression:
- 2020 source + 2027 revised version + 2026 cutoff => not decisive;
- an older eligible version can still be assessed independently.

#### F04 — Do not silently truncate relevant sources/versions
Fix:
- record source candidates excluded by `max_sources_per_mcu`;
- record versions not selected for comparison;
- expose bounded coverage in Phase 6 artifacts;
- use a documented multi-version selection policy rather than one `_best_version` that can hide earlier relevant content;
- local classification must never imply exhaustiveness over unassessed sources/versions.

Regressions:
- decisive fourth candidate is either assessed or explicitly listed unassessed;
- older-version-only hit is assessed or explicitly unassessed;
- local `NO_DIRECT_PRECEDENT_IDENTIFIED` cannot imply exhaustive coverage.

Commit separately.

### Task 3 — Preserve every material MCU commitment (F01)

Fix proposition construction so a material condition expressed in the MCU statement cannot disappear merely because structured fields are sparse.

Required policy:
- structured MCU fields remain preferred;
- statement-level material qualifiers/conditions must be reconciled into the proposition;
- do not fabricate a relationship;
- if statement content cannot be safely structured, mark an unresolved material commitment and block decisive direct classification.

Regression:
- MCU: “relay activates only after two independent sensors agree” + generic mechanism;
- source only says “threshold switches relay” => never direct;
- source supporting full two-sensor agreement configuration may become direct-eligible.

Also add:
- conditional;
- conjunction;
- quantified;
- sequence/order;
- “only if” / “unless” material qualifiers.

Commit separately.

### Task 4 — Represent scoped partial support correctly (F10)

The verifier must distinguish:
- a supported narrower subset;
- the unsupported broader remainder.

Fix either by:
1. splitting quantified/conditional material into separate commitments before verification, or
2. adding a scoped within-commitment partial-support structure.

Prefer the smallest change that preserves current contracts.

Regression:
- claim: “works for all workloads”;
- passage: “works only for read-only workloads”;
- expected: nondecisive `PARTIALLY_SUPPORTED`;
- supported subset and unsupported universal remainder are both explicit.

Do not convert this case to `INSUFFICIENT_CONTEXT` when the limitation is already known.

Commit separately.

### Task 5 — Add context-completeness protection before decisive support (F03)

This finding changes the approved “expand only after INSUFFICIENT_CONTEXT” policy.

Create an ADR documenting the change.

Required behavior:
- before a support result can become decisive, determine whether the selected passage is a bounded excerpt from a source with available nearby context;
- either include bounded same-source/same-version surrounding context in the initial verification bundle, or run a context-completeness precheck before decisiveness;
- preserve same-source/same-version boundaries;
- keep expansion bounded and traceable.

Regression:
- selected sentence says “method is effective”;
- adjacent same-version context says it failed after a week;
- result must be `CONTRADICTED`, `PARTIALLY_SUPPORTED`, or `UNRESOLVED`, never decisive `SUPPORTED`.

Also test:
- nearby qualifier that does not alter meaning;
- blocked source with no expandable context;
- excessive context does not cross source/version boundaries.

Commit with ADR.

### Task 6 — Ensure classification depends only on verified semantic facts (F09)

Fix classifier inputs so unverified mapper assertions cannot change precedent class.

Required behavior:
- functional analogy requires verified evidence for the relevant functional dimension;
- material mapper conflicts must be independently resolved before direct precedent;
- direct branch cannot ignore verified or unresolved relationship conflicts;
- mapper proposals are not semantic facts until verification binds them to passages.

Regressions:
- adding an unverified PURPOSE match cannot change component-only -> analogous;
- mapper-conflicting directed relationship blocks direct;
- verified relationship support can restore direct eligibility.

Commit separately.

### Task 7 — Fix patent combination context (F08)

Patent multi-reference context must be chronology- and lineage-aware.

Fix:
- provide `as_of` cutoff;
- provide lineage/family root identity;
- count distinct eligible roots, not raw entries;
- post-cutoff references remain limitations/context but not historical challenge evidence;
- multiple versions/publications of one family count as one root;
- never turn multi-reference combination context into single-reference anticipation.

Regressions:
- two 2027 partial patents for 2026 cutoff => no eligible multi-reference challenge;
- two versions of one patent family => one root;
- two independent pre-cutoff partial patents => eligible combination-like context, not anticipation.

Commit separately.

### Task 8 — Repair full-slice identity bridge (F11)

Update `vertical_slice._check_edges` to understand legitimate Phase 6 identities.

Fix:
- include Phase 6 combination target IDs;
- include same-source/same-version context-expansion passage IDs;
- preserve foreign source/version rejection;
- build the identity index from persisted Phase 6 artifacts, not inferred string patterns.

Regression:
- full slice with a combination edge reaches `REPORTED/COMPLETED`;
- full slice with an expanded-context passage edge reaches `REPORTED/COMPLETED`;
- foreign target/source/version/passages still fail.

Commit separately.

### Task 9 — Correct benchmark labeling (M01)

Rename the current “passage/rationale faithfulness” metric so it does not imply entailment-quality validation.

Recommended name:
- `citation_presence_and_bundle_integrity`

Document:
- deterministic fixture benchmark;
- checks citation/reference integrity only;
- does not establish model rationale faithfulness or semantic calibration.

This is Minor and not independently Gate-30 blocking, but close it before final review.

## Cross-cutting regression suite

Add a review-derived suite, for example:

`tests/adversarial/test_phase6_sol_review_regressions.py`

It should contain one stable reproduction for every F01–F11.

Required cases:
1. omitted statement-only material condition;
2. post-cutoff revision of pre-cutoff source;
3. adjacent negation;
4. fourth-source/older-version omission;
5. supported-with-zero-citations;
6. foreign source/version/proposition joins;
7. nonexistent verified artifact;
8. future/duplicate patent references;
9. unverified mapper claim changes class;
10. narrower special case;
11. valid combination/expanded passage rejected by vertical slice.

Do not replace the original tests; these are additional regression evidence.

## Verification after fixes

Run:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

Then run a fresh checkout at the final repair commit.

Update:
- `docs/phase-6-completion.md`
- `docs/reviews/phase-6-final-review.md`

The review document must retain the original FAIL record and add a remediation/re-review section rather than erasing history.

## Mandatory re-review

Use GPT-6 Sol High on the repaired final commit.

The re-review must:
- re-run F01–F11 reproductions;
- inspect changed code, not just new tests;
- attempt fresh variants of the same attack classes;
- verify no regression introduced by the fixes;
- confirm all Critical and Important findings are CLOSED;
- run full verification and fresh-checkout verification;
- explicitly set Gate 30 PASS or FAIL.

## Acceptance

Phase 6 can be accepted only if:
- F01–F11 are closed;
- no new Critical/Important findings remain;
- all regression tests pass;
- full verification passes;
- fresh-checkout verification passes;
- Gate 30 is explicitly PASS;
- Phase 7 remains unstarted.
