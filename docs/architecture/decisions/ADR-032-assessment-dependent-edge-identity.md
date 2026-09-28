# ADR-032: Assessment-dependent verified-edge identity

Status: Implemented for Phase 6 Round-2 remediation; independent acceptance pending

## Context

N01 showed that the same verification can be post-cutoff in one assessment and
eligible in another. Reusing one edge ID for both violates append-only graph
persistence and can make an old eligibility assertion appear current.

## Decision

The canonical verified-edge ID includes stable assessment context, `as_of`,
the cited source/version, mapping, claim digest, verification, canonical
verifier-cited passages, context completeness, and assessed chronology state
and public date. Observation timestamps do not determine semantic identity.
The graph evidence-proposition node is keyed by the verified-edge ID as well,
so two cutoff-specific assessments cannot overwrite each other's projection.

An exact repeat remains idempotent. A changed cutoff or other semantic input
creates a new immutable edge, not an update to the old one. Patent screening
uses the chronology of that cited classified version, not a parent source's
earlier publication metadata.

## Consequences

Historical reassessments can coexist in one repository and retain their
original eligibility. No assessment can turn post-cutoff disclosure into
historical prior art by reusing a source-level or sibling-version date. This
does not implement Phase 7 adjudication or a global novelty conclusion.
