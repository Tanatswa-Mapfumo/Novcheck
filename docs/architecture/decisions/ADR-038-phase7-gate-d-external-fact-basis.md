# ADR-038: Gate D research requires a bound external fact

Status: Targeted remediation of final independent review F1; acceptance OPEN

## Context

The final review at `ef60111` reproduced a schema-valid D/ACCESS request that
asked research to infer the user's mechanism. An existing source-version string
was sufficient for dispatch, and a no-op response could leave a frozen negative.
The user explicitly authorized this targeted correction and its regression tests.

## Decision

Research-gap v3 contains an optional untrusted `GateDExternalEvidenceBasis`.
Gate D authority requires that basis; its absence is not proof of externality.
The basis binds exact assessment/context/snapshot/target, the complete target
profile digest, a stated contribution, source/version, exact comparison IDs,
an external fact type, and a fixed contribution-significance question/effect.

The deterministic validator first requires a comparable Gate A target. It then
joins the basis to an authoritative Phase 6 coverage exclusion (unassessed
implementation), uncertain source chronology, or a specific verified source
contradiction. An arbitrary source ID, text rationale, or D enum cannot grant
permission. The basis is a dispatch justification, never additional evidence.
The model display includes copyable validated bases projected from the packet;
models do not need to compute target digests. These display annotations remain
untrusted and every proposed copy undergoes the full authority joins again.

Unproved D gaps in untrusted role/rebuttal/judge proposals become typed input
clarification before persistence. Stored malformed gaps are rejected rather
than repaired. Dispatch, dispositions, continuation and frozen ancestor/dependency
validation repeat the proof. Accepted research cannot rewrite CIR, sufficiency
or the target graph. B/C research and cumulative budget enforcement retain their
existing contracts. Complete LIMITED input remains comparable under ADR-037.

The SQLite schema remains v8; explicitly versioned canonical documents retain
all dependencies. Old gap v2 records remain audit history and cannot gain v3
semantic authority through deserialization. No historical record is backfilled.

## Consequences

A D request must identify a demonstrably missing external fact. Missing proof
conservatively asks for contribution/external-question clarification; it cannot
freeze a stronger conclusion. Legitimate unassessed-source, chronology and
contradiction requests remain available. No natural-language keyword rule or
new evidence classifier is introduced. Phase 6 semantics and Phase 8 are untouched.
The historical FAIL review remains unchanged. Implementer green tests do not
establish independent acceptance.
