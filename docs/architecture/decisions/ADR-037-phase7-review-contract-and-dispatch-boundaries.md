# ADR-037: Phase 7 review contracts and dispatch boundaries

Status: Implemented in the single independent-review fix pass; Phase 7 acceptance OPEN

## Context

The independent review of `4a4b0a7` failed with five Important findings. Neutral
review was skipped for agreement, residual omission could authorize a negative,
model-discovered needs had no typed route, LIMITED input lost all permissions,
and escalation could spend the original budget again. These are corrections to
the approved Phase 7 semantics. The locked public method signatures remain.

## Decision

1. Assessable targets receive repository-required neutral scope review even when
   roles agree. A scope review has no complete bounded alternative pair, so the
   conservative unbounded consequence rule requires both argument orders. The
   same protocol applies to any invoked alternate model. Agreement does not vote
   or confer evidence authority. Input-insufficient targets may abstain.
2. Counterfactual removal must account for every remaining Phase 6 residual.
   Omission cannot eliminate another difference. Structured dependent-removal
   accounting is not implemented; such a case remains unresolved.
3. Prosecution, defense, rebuttal and judge proposals contain typed `input_needs`
   and `research_gaps` alongside their exact ID lists. Packet and committed-role
   joins validate scope and links. Input needs reduce Gate A permission and never
   dispatch. External gaps receive immutable request/disposition dependencies;
   accepted gaps use the reviewed Phases 3–6 path, including after judging.
   Changed state supersedes and restarts both independent roles; a proven true
   no-op can resume judging. Outstanding gaps limit positive permission.
4. Complete LIMITED input can support scoped negatives or bounded potentials.
   Missing claim meaning or unresolved decomposition stays unassessable. A strong
   positive still requires ASSESSABLE input and trusted future qualifications.
5. Before research, intersect sealed and configured cumulative caps, subtract the
   maximum observed usage in every dimension, and bind `dispatch_allowance` to
   the request. The reviewed adapter supplies that allowance to Phase 4's existing
   enforcement. The returned cost must fit it. The original cumulative limits
   remain sealed; optional Phase 4 allowance does not change default behavior.
   Research artifacts can only be added in active first-pass-complete/judging states.

Affected proposal, dispute, research-gap and counterfactual contracts use v2;
role/rebuttal prompt IDs and the judge rubric, gate method and verdict policy
also use v2. Older preacceptance v1 proposals fail current authority validation;
there is no backfill or silent semantic reinterpretation. The SQLite schema
remains v8, storing explicitly versioned canonical documents. Existing Phase 6
rows, classification and validation semantics are unchanged.

## Consequences

Neutral review of agreement now costs a reversed pair. Typed proposals and
recorded dispositions add storage and validation work. Dependent residuals need
explicit future accounting rather than a permissive omission. A new Phase 7 run
is required for outdated proposal/method versions. Providers implementing the
research port must obey its reserved allowance; the reviewed adapter enforces
it before calls, while outcome checks alone cannot undo a dishonest port's spend.
No live-quality guarantee, Phase 8 compiler or production strong-positive issuer
is introduced. The original independent FAIL remains recorded; implementer
regressions are not a replacement independent acceptance PASS.
