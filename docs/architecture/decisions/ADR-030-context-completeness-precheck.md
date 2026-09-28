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
again, and exhausted context still yields `INSUFFICIENT_CONTEXT`. A source with
no stored wider context cannot be expanded, so the excerpt stands as the best
available evidence and remains subject to all other gates.

## Consequences

A near negation can no longer be hidden by choosing a short mapped excerpt, and
the verifier sees material same-source context from the start. The costs are
one extra expansion pass per claim and a slightly larger verifier input; both
are bounded and traced. Decisive support still requires verifier-cited
passages, and the precheck does not upgrade or downgrade any state by itself.
