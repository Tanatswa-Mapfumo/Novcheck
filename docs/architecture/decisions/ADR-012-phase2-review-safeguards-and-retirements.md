# ADR-012: Phase 2 review safeguards and explicit combination retirement

Status: accepted for the authorized Phase 2 scope.
Date: 2026-09-27.

## Context

The final review reproduced six understanding safeguards that existing recordings
did not exercise. Features/endpoints alone did not ground predicates; reconciliation
could drop operating restrictions; later sufficiency assertions could override a
normalized missing mechanism; combination disagreement was omitted from stability;
shared citations created false competing pairs; and no override could retire a
combination after merging all its members.

## Decision

- Require each MCU/combination predicate and endpoint concepts to occur together
  in an original-input supporting excerpt. Predicate matching is case-insensitive
  and admits regular surface inflections (including active/passive wording), not
  inferred synonyms. This is a conservative lexical grounding gate, not a semantic
  entailment parser. Direction/negation interpretation remains model-assisted;
  incompatible interpreted directions remain explicit disagreement.
- Preserve every input candidate's material statement/mechanism/purpose/target/
  effect/context across its explicitly mapped outputs. Split/merge resolutions
  may distribute intact text across outputs. Unsupported loss rejects the proposal
  rather than silently broadening its scope.
- The understanding pipeline supplies its immutable NormalizationResult to the
  deterministic sufficiency gate. A null normalized mechanism remains unassessable
  even if a later response claims otherwise; retained explicit unknowns accompany
  that blocker. Optional parameters preserve existing ports and artifact schemas.
  Standalone CIR-only use has no normalization artifact to enforce this cross-stage
  guarantee; callers should supply normalization for that use.
- Compare directed combination graphs after explicit member-to-output mapping,
  independent of arbitrary combination IDs. Incompatible predicates/directions
  lower the ceiling to EXPLORATORY and retain both interpretations.
- Do not count a disjoint-feature cross-pair as unresolved correspondence merely
  because it shares paragraph support when both endpoints have unique equivalent
  counterparts. Ambiguous or structurally overlapping pairs remain unresolved.
- REMOVE_MCU, MERGE_MCUS and SPLIT_MCU payloads may explicitly list
  `combination_retirements` only with `payload_version: "0.2"`. Old unversioned
  payloads retain version 0.1 behavior; no existing persisted payload is reinterpreted.
  Retirement IDs must be existing, unique, and not also updated. The final graph
  must still validate. The immutable audit already captures the exact payload,
  previous combinations, parent ID, actor/reason and before/after hashes.

No new override kind, domain/provider SDK, dependency or novelty policy is added.
No automatic cascade deletes, model retry/repair or later-phase reasoning is added.

## Consequences

Lexical/extractive gates can reject valid synonym-heavy interpretations; schema,
surface support and span conservation do not prove universal entailment. Explicit
retirement requires additional user payload detail and a new payload revision,
but does not mutate parent snapshots or conceal removed relationships. The retained
source reconciliation still requires downstream reassessment before lifting ceilings.

Regression tests reproduce all six review failures through real understanding;
additional invalid-retirement cases verify rejection without parent mutation.
