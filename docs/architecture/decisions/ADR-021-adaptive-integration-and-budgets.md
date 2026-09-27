# ADR-021: Native screening batches and auditable wire budgets

Status: Accepted for Phase 4 implementation

## Decision

Consume the accepted rich ResearchPlan, not its deliberately lossy domain SearchPlan
projection. Native first-page text batches implement screening within the same
controller budget as adaptive retrieval. Do not run the old screening executor
outside that budget and then repeat its requests. Preserve all older Phase 1-3
entry points. A new optional Phase 4 application component has a distinct explicit
Phase 5 fixture continuation.

Use a versioned ResearchResult contract for persistence. Phase 3 coverage states
remain unchanged; Phase 4 adds depth and stopping as a versioned sidecar cell.
Chronology is keyed by complete discovery-observation hash, not a single cluster
date, so conflicting observations remain available for later resolution.

An optional neutral audit/budget port exposes compiled requests and safe physical
attempt records. All concrete Phase 4 adapters implement it. Guards run after
pacing but before every wire attempt, including retries and hydration requests;
they are removed in finally blocks. Bounded call/elapsed/document budgets refuse
providers without this hook. Remaining document budgets clamp declared page sizes;
an untrusted provider ignoring that size is recorded truthfully and prevents
further work rather than silently discarding discovery records.

Logical deep rounds are admitted and charged once, separately from physical
attempts within that round. The last admitted round can execute without being
charged twice. Remaining elapsed budgets bound pacing/cooldown waits and in-flight
requests; cancelled attempts remain safely audited as budget-stopped. Continuation
uses consumed provider rank spans, not surviving candidate counts, so missing graph
targets do not inflate subsequent ranks. These are pre-release Phase 4 v1 contract
corrections; optional rank_span preserves older mock/native batch compatibility.

Routing counts retrieval candidates as provisional relevance proxies, never as
verified relevant evidence. No novelty inference or calibrated information-value
probability is introduced. Successful complete requests, actual cross-mechanism
cluster overlap, yield history and explored strongest neighborhoods provide the
operational stopping signals. Remaining unsupported or unexplored work remains
explicit and inconclusive. Multilingual capability is not invented; caller-
supplied translated intents can pass through the reviewed planning contract.

## Consequences

Wire budgets are exact for compliant adapters even during partial expansion.
Trace/audit records survive failed attempts. The compatibility slice still works;
the new slice proves Phase 2-4 architecture while evidence and findings stay
fixture-backed. Candidate-proxy stopping is intentionally not authority for a
future absence-based positive novelty verdict; later evidence stages must assess
actual relevance and intended conclusion strength.
