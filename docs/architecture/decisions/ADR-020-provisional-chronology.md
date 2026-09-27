# ADR-020: Provisional public-disclosure chronology

Status: Accepted for Phase 4 implementation

## Decision

Retain all eight temporal fields separately. Only complete dates explicitly
describing publication, public version, release, launch or archive capture can
establish provisional cutoff eligibility. Repository creation and patent priority
alone do not establish public disclosure. Partial years/months are not guessed.
The earliest supplied public-disclosure date is recorded with its field name;
unknown eligibility remains unknown. Cutoff dates are inclusive.

## Consequences

Post-cutoff candidates remain available as context and expansion seeds, but cannot
negate historical novelty. Eligibility is not evidence support or equivalence.
Raw metadata and uncertainty remain available for Phase 5 normalization and
chronology verification. Conservative handling may leave publicly old repositories
undated until a verified disclosure date is obtained; no private creation or
priority date silently becomes a public-art date.

## Native semantic API cutoff

The opt-in live OpenAlex smoke exposed that `to_publication_date` is rejected by
deployed semantic search. A bounded diagnostic confirmed `publication_year:<Y+1`
works. Native semantic compilation uses that coarse year bound and explicitly
records its limitation. Complete returned publication dates still undergo the
exact inclusive local cutoff; later dates in the same year remain context only.
No cutoff is relaxed and no post-cutoff result becomes historical negation.
