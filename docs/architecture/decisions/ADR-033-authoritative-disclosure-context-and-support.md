# ADR-033: Authoritative disclosure, context, and support contracts

Status: Implemented for Phase 6 consolidation; independent acceptance pending

## Context

The final independent review found that a cited version could contradict
source-wide first-public metadata, an adjacent passage could be mistaken for
the end of a context unit, and a caller could assert an aggregate support state
that disagreed with its commitment records.

## Decision

`CitedDisclosure` binds chronology to the owned cited version. Its public date
governs cutoff eligibility; a source-wide `first_public_version` later than
the cited date makes chronology uncertain. Later sibling publication dates do
not change a separately cited earlier version.

Passage extractors attest evidence-unit start and end boundaries. Context is
complete only when both boundaries of the relevant unit are proven. A complete
abstract is complete within its abstract scope and retains its abstract-only
access limitation. Unmarked adjacent passages and truncated windows cannot
establish complete context.

`SupportVerification.state` remains serialized for compatibility but must
equal the deterministic state derived from all commitment records. A direct
precedent requires aggregate `SUPPORTED` and complete context.

## Consequences

Uncertain chronology and incomplete context abstain from decisive support.
Known scoped partial support remains visible without upgrading to direct.
Old passage records lack unit-boundary proof and therefore cannot acquire
decisive completeness solely from their locator shape.
