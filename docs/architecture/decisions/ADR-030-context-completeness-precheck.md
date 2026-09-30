# ADR-030: Context-completeness precheck before decisive support

Status: Accepted for Phase 6 remediation (F03)

## Decision

The approved Phase 6 plan expanded context only after an
`INSUFFICIENT_CONTEXT` verifier result. GPT-6 Sol High finding F03 showed that
this lets a short, apparently supporting excerpt hide a nearby negation or
qualifier: a verifier reasonably returns `SUPPORTED` for "The method is
effective." and never sees "However, in all tested cases it failed after a
week.".

`verify_with_context_retry` therefore performs a bounded
**context-completeness precheck** before the first judgment: for every passage
in the support bundle it attempts the same-source, same-version bounded window
expansion and, when a window is available, presents the original passages plus
the windows to the initial verification. The precheck consumes the first
expansion round; retries remain bounded by `max_expansions` rounds and the
INSUFFICIENT_CONTEXT-only retry policy is unchanged.

Boundaries are unchanged: expansion never crosses source or version, blocked
expansions are recorded explicitly, expansion-created windows are not expanded
again, and exhausted context still yields `INSUFFICIENT_CONTEXT`.

Round-2 remediation records context completeness as `COMPLETE`, `TRUNCATED`,
`UNAVAILABLE`, or `UNKNOWN`; unavailable or unknown excerpts are not decisive.
A full resolved source passage may establish completeness when its locator
spans the content. Otherwise the precheck uses the mapped occurrence and
bounded same-version neighbors. A truncated window, ambiguous repeated
occurrence, or zero precheck budget cannot silently become complete.

## Consequences

A near negation can no longer be hidden by choosing a short mapped excerpt, and
the verifier sees material same-source context from the start. The costs are
one extra expansion pass per claim and a slightly larger verifier input; both
are bounded and traced. Decisive support still requires verifier-cited
passages. The completeness gate can conservatively downgrade apparently
supported evidence to insufficient context, but cannot manufacture support or
a contradiction. This is deliberately stricter than the initial precheck
policy; the original decision remains documented above for audit history.

## Provenance hardening amendment (30 September 2026)

ADR-036 makes completeness depend on extractor-owned `PassageAttestation`
limits over the immutable resolved parent. Caller-created unit flags and
unattested neighboring blocks cannot establish a complete unit. A complete
abstract is complete only within its explicitly abstract-only access scope.
