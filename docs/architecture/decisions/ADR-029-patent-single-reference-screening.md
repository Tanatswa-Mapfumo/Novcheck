# ADR-029: Patent-mode single-reference screening

Status: Accepted for Phase 6 implementation

## Decision

Patent-mode screening (`evidence/precedent/patent.py`) is a specialized view
over the same verified classifications. It is screening, never a legal
patentability or validity determination, and its result carries the fixed
disclaimer `patent-screening-not-legal-advice-v1`.

- `SINGLE_REFERENCE_ANTICIPATION_LIKE` requires exactly one earlier patent
  reference whose classification is a decisive `DIRECT_PRECEDENT` (every
  material element and contribution-bearing relationship/configuration
  verified as supported and pre-cutoff). When several decisive references
  exist, the earliest by priority date (then source id) is chosen
  deterministically.
- `MULTI_REFERENCE_COMBINATION_LIKE` is produced when two or more references
  contribute partial/component/analogous coverage. It explicitly states that
  multiple references are combination/obviousness-like context and are never
  one-reference anticipation.
- A single partial reference, or patent references with no verified
  contribution, yields `LIMITED`; no patent evidence at all yields
  `UNASSESSABLE` when nothing was retrieved and `LIMITED` when only non-patent
  evidence exists. Both record that this is not a finding of absence.
- Patent priority and publication dates stay separate records. Public
  disclosure eligibility still uses publication-type dates (ADR-020), so a
  priority date alone cannot make a reference decisive.
- Claim/specification locators are retained and classified as
  `CLAIMS`/`SPECIFICATION`/`OTHER` from the passage locator.

The normal per-source classifications remain authoritative; patent mode never
upgrades a classification and never merges references into a direct finding.

## Consequences

Stitched multi-reference reasoning cannot be mislabeled as anticipation, and
missing patent evidence cannot become an absence claim. The cost is that a
genuinely anticipatory combination (rare in this screening context) stays
combination-context only; that conservatism is required because the patent
lens is explicitly non-legal and must not overstate.

## Amendment (F08 remediation)

Screening now receives the assessment cutoff and lineage roots. Only
references whose publication date is known and at or before `as_of` can
challenge the historical cutoff; post-cutoff or unknown-date references remain
explicit limitations. Multi-reference combination context requires at least two
distinct eligible lineage roots, so later versions or family publications of
one patent count as one root and can never inflate the combination view.
Priority dates alone still do not establish disclosure, and neither case can
become one-reference anticipation. This closes GPT-6 Sol High finding F08.
