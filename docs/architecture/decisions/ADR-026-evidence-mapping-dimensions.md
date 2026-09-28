# ADR-026: Evidence mapping dimensions and proposition commitments

Status: Accepted for Phase 6 implementation

## Decision

Source-to-MCU comparison uses twelve structured dimensions: PURPOSE, PROBLEM,
TARGET, MECHANISM, ARCHITECTURE, FEATURES, RELATIONSHIPS, CONTROL_FLOW, CONTEXT,
INTENDED_OUTCOME, CONSTRAINTS and EVALUATION_TARGET. Relationships and control
flow are first-class: they are stored as directed `subject relation object`
structures, never flattened into bag-of-words similarity.

`build_mcu_comparison_profile` constructs a profile from explicitly stated MCU
fields only. Absent dimensions are listed in `unknown_dimensions`; nothing is
inferred, and an absent mechanism stays unknown rather than being replaced by a
plausible guess. A relationship is additionally classified as control flow only
when its verb appears in the documented conservative lexicon
(`evidence/mapping/dimensions.py`); unusual terminology remains a material
RELATIONSHIPS commitment instead of being dropped or force-classified.

`build_proposition` derives verifiable material commitments from the profile:
mechanism, purpose, target, context, intended outcome, each feature, and each
directed relationship (control-flow relationships keep the CONTROL_FLOW
dimension). A bare MCU with no structured fields yields one commitment equal to
its own statement; no mechanism detail is invented. Combination profiles retain
member ids, member mechanisms/features/relationships and the combination's own
configuration relationships, and the proposition adds explicit `cfg`, `member:*`
and `crel:*` commitments so an alleged configuration can never be satisfied by
member components alone.

Mapping remains a *proposal*: profiles and commitments are deterministic, but
which exact passages map to which dimension is proposed by the mapper stage and
verified independently afterwards.

## Consequences

The same feature set with a reversed relationship produces different
commitments, so relationship loss cannot be silently averaged away. Control
flow coverage depends on the lexicon; unmatched verbs still produce material
relationship commitments, so the cost is a coarser dimension label, never a
lost relationship. Combination claims require configuration evidence, which
makes later anti-stitching enforcement structural rather than heuristic.

## Amendment (F01 remediation)

Structured MCU fields remain preferred, but they are no longer assumed to be
complete. A token union across separate commitments is insufficient evidence
that the whole statement is represented: it loses conjunction, order and
direction. `build_proposition` treats a statement as structurally covered only
when one existing commitment preserves its complete ordered wording, ignoring
articles and punctuation but retaining semantic operators such as `and`,
`then`, `only if` and `unless`. Otherwise it adds a `statement:material`
CONSTRAINTS commitment carrying the exact statement. Combination member
statements receive the same check; the combination's own statement is already
carried by `cfg`.

This is a conservative *coverage* check, not an equivalence or entailment
judgment. It may add a redundant commitment for a paraphrase; the independent
verifier must assess that commitment against the cited passages. It never
fabricates a directed relationship. A source supporting only isolated parts
cannot become direct until the joint statement is supported, while evidence
supporting the complete configuration remains direct-eligible.
