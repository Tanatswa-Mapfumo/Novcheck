# Phase 6 — Evidence Mapping, Support Verification, and Precedent Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Convert the Phase 5 evidence graph into passage-grounded, source-to-MCU mappings whose factual support is independently verified and whose precedent relationship is classified without performing Phase 7 adjudication.

**Architecture:** Phase 6 is split into four semantic stages: candidate mapping, context/passage selection, independent support verification, and constrained precedent classification. LLM-assisted stages sit behind strict provider-independent schemas; deterministic gates enforce chronology, one-source direct-precedent rules, relationship preservation, passage grounding, and support eligibility.

**Tech Stack:** Existing Python 3.12+, `uv`, Pydantic v2, pytest, Pyright, Ruff, SQLAlchemy/SQLite evidence graph, abstract `LLMProvider`.

**Spec:** `docs/specs/master-design-spec.md`, especially the evidence mapping, evidence support verification, equivalence, precedent, chronology, patent-screening, lifecycle, and Phase 6 sections.

## Model Execution Policy

- **DeepSeek V4.1 Flash Max:** approved for implementation, TDD, deterministic validators, fixtures, graph persistence, and concrete review fixes.
- **GPT-6 Sol High:** REQUIRED for the final independent semantic review before Phase 6 is accepted.

Do not accept Phase 6 from DeepSeek self-review alone.

## Global Constraints

- Base work on accepted Phase 5 commit `3974b4c`.
- Implement Phase 6 only.
- Retrieved relevance != evidentiary support.
- Similarity != equivalence.
- Mapping and support verification are separate.
- The support verifier must not see the final novelty verdict, prosecutor/defender role, report wording, retrieval rank/score, or overall source-quality tier.
- Exact passages must support the proposition for which they are cited.
- `NOT_SUPPORTED` evidence cannot justify a precedent edge.
- `INSUFFICIENT_CONTEXT` triggers same-source context expansion where possible.
- `PARTIALLY_SUPPORTED` must identify the unsupported remainder.
- Direct precedent generally requires one source/version containing the material elements and relationships.
- Sources A+B+C cannot be stitched into one-source direct precedent for A+B+C.
- Components-known != configuration-known.
- Relationships/control flow are first-class.
- Terminology differences do not protect equivalent mechanisms.
- Shared terminology does not establish equivalence.
- Post-`as_of` evidence cannot negate historical novelty.
- Patent mode distinguishes one-reference anticipation-like evidence from multi-reference combination reasoning.
- Source quality may be attached after verification but cannot alter entailment state.
- No prosecutor/defender, final novelty gate, final novelty verdict, or novelty probability in Phase 6.
- Default tests remain network-isolated.
- External text is inert/untrusted content.
- Prompt/rubric versions are traceable.

## Review Focus

1. Entailment inflation: same concepts but no actual support.
2. Multi-source stitching into direct precedent.
3. Relationship/control-flow loss.
4. Qualifiers/negation hidden outside a short passage.
5. Chronology leakage.

---

## Suggested File Map

```text
src/novelty_harness/evidence/
  mapping/
    models.py
    dimensions.py
    mapper.py
    prompts.py
  context/
    selection.py
    expansion.py
  verification/
    models.py
    verifier.py
    prompts.py
    gates.py
  precedent/
    models.py
    classifier.py
    gates.py
    counterfactuals.py
    patent.py
  graph/
    phase6_mapping.py
  phase6_pipeline.py

tests/
  unit/evidence/{mapping,context,verification,precedent}/
  integration/
    test_phase6_evidence_pipeline.py
    test_phase5_slice_with_phase6_evidence.py
  adversarial/
    test_phase6_equivalence_attacks.py
  benchmarks/
    test_phase6_support_verifier.py
  fixtures/
    phase6.py

docs/
  traceability/phase-6.yaml
  architecture/decisions/
    ADR-026-evidence-mapping-dimensions.md
    ADR-027-independent-support-verification.md
    ADR-028-precedent-classification-gates.md
    ADR-029-patent-single-reference-screening.md
```

---

## Prerequisite Gate

- Create an isolated worktree from `3974b4c`.
- Suggested branch: `phase-6-evidence-verification`.
- Run:
  ```bash
  uv sync --dev
  uv run python scripts/verify.py
  git diff --check
  ```
- Confirm Phase 5 reserved Phase 6 edges remain guarded before the controlled Phase 6 construction path exists.

---

### Task 1: Define mapping, verification, and precedent contracts

Create strict contracts for:

- `ComparisonDimension`
- `EvidenceProposition`
- `DimensionMapping`
- `SourceMCUMapping`
- `PassageSupportClaim`
- `SupportVerification`
- `VerifiedEvidenceEdge`
- `PrecedentClassification`

Comparison dimensions:

```text
PURPOSE
PROBLEM
TARGET
MECHANISM
ARCHITECTURE
FEATURES
RELATIONSHIPS
CONTROL_FLOW
CONTEXT
INTENDED_OUTCOME
CONSTRAINTS
EVALUATION_TARGET
```

Verification states remain exactly:

```text
SUPPORTED
PARTIALLY_SUPPORTED
NOT_SUPPORTED
INSUFFICIENT_CONTEXT
CONTRADICTED
```

Tests must enforce:
- nonblank propositions;
- passage grounding;
- matching/missing/conflicting elements kept separately;
- strict schemas;
- unsupported evidence cannot be marked decisive;
- JSON round trips.

Commit after focused tests pass.

---

### Task 2: Build MCU comparison profiles

Create `build_mcu_comparison_profile(...)`.

Requirements:
- preserve mechanism, relationships, and control flow separately;
- never invent absent dimensions;
- unknown mechanism remains unknown;
- combination MCUs retain member and relationship structure.

Tests:
- same features/different relationship;
- different terminology/same relationship;
- missing mechanism;
- combination contribution;
- workflow/process MCU;
- engineering/product MCU.

Create ADR-026.

---

### Task 3: Implement source-to-MCU candidate mapper

Create `EvidenceMapperV2.map_source_to_mcu(...)`.

Rules:
- mapping is a proposal, not verified support;
- every mapped dimension cites exact passage IDs;
- passages belong to the source/version;
- matching/missing/conflicting elements explicit;
- relationship/control-flow differences preserved;
- unresolved mapping allowed;
- source prestige/quality cannot decide mapping;
- strict versioned prompt/schema.

Tests include:
- same terms but missing mechanism;
- mechanism match but purpose mismatch;
- reversed control flow;
- one conflicting element;
- abstract-only mapping;
- prompt injection in evidence.

---

### Task 4: Implement passage selection and context expansion

Create:
- `select_support_passages(...)`
- `expand_passage_context(...)`

Rules:
- verification begins with exact mapped passages;
- only `INSUFFICIENT_CONTEXT` should normally trigger expansion;
- expansion remains inside same source/version;
- locators/provenance retained;
- cross-source evidence cannot rescue a one-source direct-precedent claim;
- blocked context remains explicit.

Tests:
- following qualifier reverses apparent claim;
- preceding negation;
- version mismatch;
- blocked expansion;
- short passage insufficient until expanded.

---

### Task 5: Implement blinded independent support verifier

Create `IndependentSupportVerifier.verify(...)`.

Verifier input may contain only:
- proposition;
- claimed dimension mapping;
- exact passage text/locator;
- minimal source/version identity needed for passage integrity.

It must NOT receive:
- novelty verdict;
- proposed precedent class;
- prosecutor/defender role;
- source quality tier;
- search rank;
- provider relevance score;
- user novelty claim;
- report wording.

Outputs:
- verification state;
- supported portions;
- unsupported portions;
- contradictions;
- context needed;
- relied-on passage IDs;
- prompt/rubric version.

Deterministic guards:
- no invented passage IDs/text;
- `SUPPORTED` requires all material commitments;
- partial support records remainder;
- insufficient evidence abstains;
- contradiction remains contradiction.

Create ADR-027.

---

### Task 6: Implement context-retry loop

Create `verify_with_context_retry(...)`.

Rules:
- retry only for `INSUFFICIENT_CONTEXT`;
- expansion is bounded and traced;
- do not retry `NOT_SUPPORTED` merely to obtain a preferred answer;
- contradiction is final unless passage-integrity failure is detected;
- exhausted expansion stays insufficient.

Tests cover:
- insufficient -> supported;
- insufficient -> contradicted;
- no available context;
- no retry for unsupported;
- retry cap.

---

### Task 7: Implement verified-edge eligibility gates

Create `build_verified_evidence_edge(...)`.

Rules:
- `NOT_SUPPORTED`/`INSUFFICIENT_CONTEXT` cannot create decisive supportive edges;
- post-cutoff sources cannot become novelty-defeating precedent;
- uncertain chronology remains uncertain;
- quality attached without changing verification state;
- source/version/passage identities must agree;
- contradictions remain contradictions.

---

### Task 8: Implement precedent classification

Allowed local comparison states:

```text
DIRECT_PRECEDENT
STRONG_PARTIAL_PRECEDENT
COMPONENT_PRECEDENT_ONLY
ANALOGOUS_PRECEDENT
SUPERFICIAL_SIMILARITY
NO_DIRECT_PRECEDENT_IDENTIFIED
CONTRADICTORY_EVIDENCE
UNRESOLVED
UNASSESSABLE
```

Important Phase 6 restriction:
`NO_DIRECT_PRECEDENT_IDENTIFIED` is only a local source/MCU comparison result. It is NOT yet permission for a global absence claim.

Classification rules:
- direct = one eligible source/version covers all material elements plus contribution-bearing relationships/control flow;
- strong partial = substantial overlap but material gap;
- component-only = components without claimed configuration;
- analogous = relevant functional principle but not direct structural equivalence;
- superficial = vocabulary/domain overlap without material functional match;
- contradiction = verified contradiction;
- unresolved = material ambiguity;
- unassessable = required information unavailable.

Create ADR-028.

---

### Task 9: Enforce single-source direct precedent and anti-stitching

Mandatory tests:
- A supplies component 1, B component 2, C relationship 3 -> never direct for A+B+C;
- one source has all components but not relationship -> not direct;
- one source has all material elements + relationship -> direct-eligible;
- source-family/version duplicates do not count as independent combination evidence;
- multiple sources may establish component precedent without becoming direct combination precedent.

Implement counterfactual-removal diagnostic:
remove the differentiating element/relationship and report what distinction remains. This is diagnostic only.

---

### Task 10: Implement patent-mode single-reference screening

Rules:
- screening, not legal advice;
- direct anticipation-like result requires one earlier patent/reference covering relevant elements/relationships;
- multiple references remain combination/obviousness-like context, never one-reference anticipation;
- priority and publication chronology separate;
- claims/specification locators retained;
- unavailable patent evidence -> limited/unassessable, not absence.

Create ADR-029.

---

### Task 11: Persist Phase 6 propositions and verified graph edges

Permit controlled graph construction of:

```text
SUPPORTS
CHALLENGES
CONTRADICTS
DIRECT_PRECEDENT
STRONG_PARTIAL_PRECEDENT
COMPONENT_PRECEDENT
ANALOGOUS
NO_MATCH
```

Each decisive edge carries:
- source/version;
- MCU;
- proposition;
- passage IDs;
- dimension mapping;
- relationship mapping;
- missing/conflicting elements;
- chronology;
- quality;
- support-verification state;
- prompt/rubric versions;
- trace refs.

Repository must reject decisive edges lacking eligible verification.

No Phase 7 final verdict stored here.

---

### Task 12: Build Phase 6 pipeline

Create `verify_evidence_against_mcus(...)`.

Flow:
1. build MCU profiles;
2. choose candidate source/MCU pairs without assigning precedent;
3. map passages/dimensions;
4. select exact passages;
5. independently verify;
6. expand context only when insufficient;
7. apply chronology/quality eligibility;
8. classify local precedent relation;
9. persist propositions/verified edges;
10. advance lifecycle through `EVIDENCE_MAPPED` and `EVIDENCE_VERIFIED`.

Full slice:
- Phase 2 real;
- Phase 3 real;
- Phase 4 real;
- Phase 5 real;
- Phase 6 real;
- Phase 7+ fixture-backed.

---

### Task 13: Add deterministic support-verifier benchmark

Create an offline benchmark inspired by FEVER/SciFact claim/evidence structure.

Include:
- support;
- contradiction;
- insufficient evidence;
- special-case-only evidence;
- negative qualifier;
- conditional claim;
- context/population mismatch;
- dispersed multi-sentence evidence.

Record:
- support-state accuracy;
- `SUPPORTED` precision;
- contradiction recall;
- insufficient-context abstention;
- passage/rationale faithfulness.

This is a diagnostic baseline, not calibration.

---

### Task 14: Add Phase 6 adversarial suite

Mandatory cases:

1. same nouns, different causal relation -> not direct;
2. different terminology, equivalent mechanism -> strong mapping possible;
3. relevant abstract but passage lacks proposition -> unsupported;
4. special case only -> partial;
5. hidden negation in context -> caught;
6. post-cutoff exact match -> temporally ineligible;
7. three-source stitched combination -> never direct;
8. components without configuration -> component only;
9. configuration missing material constraint -> partial/unresolved;
10. analogy inflation -> cannot become direct;
11. source says "novel" -> irrelevant to support classification;
12. high-quality unsupported passage -> no supportive edge;
13. lower-quality but supported passage -> support preserved, quality separate;
14. contradictory passages -> explicit unresolved/contradictory handling;
15. source version changes/retracts -> version-specific result;
16. patent A+B stitched -> not direct anticipation;
17. prompt injection -> inert;
18. source quality/order presentation does not change blinded verifier;
19. mapper invents relationship -> verifier rejects;
20. passage locator mismatch -> edge rejected.

---

### Task 15: Add Phase 6 guards and traceability

Architecture guards must ensure:
- verifier API has no verdict/prosecutor/defender/source-tier/search-rank input;
- no Phase 7 imports;
- direct-precedent builder has exactly one source/version identity;
- decisive support requires verified passage support;
- post-cutoff direct precedent forbidden;
- provider retrieval scores absent from mapper/verifier semantic contracts;
- no numeric novelty/confidence output;
- no test-fixture imports in production;
- default tests network-blocked.

Create `docs/traceability/phase-6.yaml` and update README accurately.

---

### Task 16: Mandatory GPT-6 Sol High independent semantic review

**Required reviewer: GPT-6 Sol High.**

The reviewer must examine:
- mapper/verifier separation;
- verifier blindness;
- relationship/control-flow preservation;
- single-source direct-precedent rule;
- multi-source anti-stitching;
- chronology gates;
- context expansion;
- patent single-reference semantics;
- graph-edge eligibility;
- benchmark behavior;
- adversarial cases;
- Phase 7 leakage.

For every Important/Critical finding:
1. reproduce with regression test where possible;
2. fix;
3. run focused tests;
4. run full verification;
5. document in `docs/reviews/phase-6-final-review.md`.

Final verification:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

Repeat in a fresh checkout.

Create:
- `docs/reviews/phase-6-final-review.md`
- `docs/phase-6-completion.md`

Do not accept Phase 6 before this review is closed.

---

## Phase 6 Acceptance Gate

Phase 6 passes only if:

1. Phase 5 baseline is clean.
2. Final full verification passes.
3. MCU profiles preserve relationship/control-flow structure.
4. Mappings are exact-passage grounded.
5. Mapping does not itself verify support.
6. Support verifier is blinded from verdict/prestige.
7. `SUPPORTED` requires all material proposition commitments.
8. Partial support states the unsupported remainder.
9. Insufficient context expands same-source context where possible.
10. Unsupported evidence cannot create decisive supportive edges.
11. Contradictions remain contradictions.
12. Passage/source/version integrity is enforced.
13. Post-cutoff evidence cannot negate historical novelty.
14. Direct precedent requires one eligible source/version.
15. Multi-source stitching cannot create direct combination precedent.
16. Component precedent remains separate from combination precedent.
17. Relationship mismatch can defeat direct equivalence despite feature overlap.
18. Terminology mismatch alone cannot defeat equivalence.
19. Analogy cannot become direct without relationship-level support.
20. Patent mode preserves the one-reference distinction.
21. Quality/relevance cannot alter blinded support state.
22. Verified graph edges retain exact passages and mappings.
23. Benchmark runs deterministically.
24. All adversarial cases pass.
25. Full slice reaches `REPORTED/COMPLETED` with Phases 2–6 real.
26. No prosecutor/defender implemented.
27. No final novelty verdict/gates implemented.
28. No novelty probability/scalar confidence added.
29. README/traceability correctly defer Phase 7+.
30. GPT-6 Sol High independent semantic review is completed and all Important/Critical findings are closed.
31. Phase 7 has not started.

## Explicitly Deferred

- prosecutor/defender -> Phase 7;
- counterbalanced neutral adjudication -> Phase 7;
- final input/research/equivalence/contribution permission gates -> Phase 7;
- final novelty verdict -> Phase 7;
- full narrative report -> Phase 8.

## Execution Handoff

Recommended execution: **OpenCode + DeepSeek V4.1 Flash Max for implementation, followed by mandatory GPT-6 Sol High independent semantic review.**

Do not start Phase 7 until the Sol High review is closed and Phase 6 is explicitly accepted.
