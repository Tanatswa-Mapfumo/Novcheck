# ADR-014: Explicit operational screening floors

Status: Accepted for Phase 3 implementation

The standard-screening-v1 profile requires two distinct query families and one
configured provider per plausible MCU/family. Required families and per-query
inspection minima default to none. Every value is configurable through a complete
CoveragePolicy JSON document. Two families is the architectural minimum for a
multi-query strategy, not a novelty/confidence threshold. These engineering floors
are subject to later calibration; they do not represent research saturation.

Screening executes a bounded first page for each planned query/provider pair.
Coverage requires all those pairs to succeed; counts cannot replace diversity.
Transient failures remain visible as degradation even after retry success.
Missing providers block coverage and cannot change family applicability. Zero
results can complete screening but are never evidence of universal absence.

Applicability exclusions require semantic-incompatibility classification and
support quoted from preserved input. Unsupported, provider-based or user-asserted
exclusions remain UNRESOLVED. This is a conservative validation safeguard, not a
claim that textual grounding alone proves a semantic exclusion. Independent plan
criticism must still examine exclusions and family omissions.
