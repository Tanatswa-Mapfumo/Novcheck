# ADR-007: Phase 1 transport wrapping and trace boundaries

Status: Accepted for Phase 1 architecture only
Date: 2026-09-26

## Context

The Phase 1 plan connects search/content DTOs to domain source/passage artifacts
without specifying a source-normalization component. True normalization,
chronology, deduplication and passage extraction belong to later phases.

## Decision

The slice mechanically wraps returned content, preserving title/URL/provider
identity and hashing exact content. Source IDs hash the supplied canonical URL
when available, otherwise provider identity; passage IDs hash source ID, locator
and exact text. No URL canonicalization, fuzzy matching or independence reasoning
occurs. The whole supplied text is a passage at resolved_content, not a claim
that full text is available. Unknown source type and access completeness remain
explicitly unknown. The initial 0.1 source contract gains this unknown access
state before Phase 1 release; no Phase 0 artifact shape changes.

Repeated exact identities retain query discovery references. Conflicting content
for one identity within a run is rejected, not silently reinterpreted as a
version or independent evidence. Query pagination follows explicit provider
cursors and rejects cycles; no budget, saturation or adaptive search logic exists.

Every canonical transition records lifecycle data plus implementation/fixture/
deferred origin. Adaptive research, adversarial roles and robustness are explicitly
skipped/deferred. Injected semantic artifacts supply their origin; transport
wrapping does not claim semantic normalization. Each event is sent to the supplied
sink and a run-local append-only JSONL sink, making trace_ref resolvable regardless
of the injected sink. An assessment_record snapshot retains actual lifecycle state.

Structural binding checks reject changed original input, cross-run findings,
unknown MCU/source/passage/edge references, and unsupported decisive edges. They
do not judge sufficiency, equivalence or verdict permission. Unexpected component
or provider failures record FAILED plus an explicit failure event and propagate;
there is no silent fallback or invented partial judgment.

The retained request and persisted search plan are authoritative snapshots;
normalization and plan review receive independent deep copies. Approval binds to
the pre-review persisted plan hash, and that same plan is executed. Before freeze,
MCU findings must be unique and coverage MCU/query references must exist in the
run graph/plan. These are structural integrity rules, not semantic coverage gates.

## Consequences

This is deterministic transport plumbing, not Phase 2-7 intelligence. Later
normalization, source versions, selective passage extraction, failure recovery,
resume and partial-branch orchestration remain deferred. File writes are atomic
individually, not a multi-file transaction; assessment_record is the lifecycle
snapshot and trace explains any failed run. No new dependency is required.
