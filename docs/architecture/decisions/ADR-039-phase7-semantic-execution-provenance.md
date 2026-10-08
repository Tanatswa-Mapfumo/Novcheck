# ADR-039: Bind Phase 7 semantic artifacts to actual execution provenance

- Status: Accepted for the explicitly authorized targeted Phase 7 remediation
- Date: 2026-10-05
- Scope: Final independent review Finding B; no Phase 6 semantic change

## Problem

A schema-valid role could advertise a v1 prompt while the runtime invoked v2.
The role acquired frozen authority and trace publication displayed current
constants. Neither self-description nor trace delivery proves execution.

## Decision

The application records a scoped `SemanticConfiguration` in the existing
schema-v8 Phase 7 artifact table before invoking a semantic port. It binds the
current approved method version and instruction hash, provider/configuration
identity, execution mode and exact target/context/snapshot. Completed calls
attach a frozen `SemanticExecutionRecord` to the versioned v2 artifact wrapper.
Its configuration reference, method and actual invocation hashes, actual model
configuration, request/response hashes and validated proposal hash are distinct
from the model's semantic payload. No second truth store or schema backfill is
introduced. Old preacceptance wrappers cannot establish current authority.

`SemanticRunner` adapters obtain provenance from the matching actual invocation
audit, including the exact schema/context/config request hash. They retain the
raw structured response hash separately from the validated proposal hash; input
clarification normalization does not relabel the raw response. A bounded retry
retains the successful recovery instruction hash. Only the current instruction
and its one approved recovery suffix are permitted. Model name, provider version
and observed latency are retained; latency does not enter semantic artifact IDs.

Other configured protocol ports use explicit `PORT_PROTOCOL` execution records.
These identify the actual application port implementation and declared config,
not an invented LLM/provider call or usage record. The application observes the
invocation and checks configuration before/after it. A scripted port is not
represented as having executed an LLM prompt. Its output must still satisfy the
current method contract and all semantic/evidence validators.

Persistence joins the envelope to the previously committed configuration and
exact proposal. Freeze repeats those joins for every prosecutor, defender,
rebuttal and primary/alternate judge dependency. Authoritative frozen load
repeats the same checks in its read transaction. Current role prompt fields are
untrusted assertions: stale values are rejected, and matching values alone grant
no authority. Judge rubric/config fields must match the invocation envelope.

Committed-artifact trace events derive provenance from repository execution
records, not current constants or model self-description. A supplied operational
call audit that claims a committed request must match its execution provenance.
Unmatched operational audits have no artifact dependency binding and are labeled
`UNBOUND_OPERATIONAL_AUDIT`; they cannot confer frozen authority. Failed trace
delivery leaves repository authority intact and remains retryable.

## Consequences

Additional immutable configuration dependencies precede semantic calls. They
remain audit history after failed calls. First-pass completeness counts semantic
role artifacts, not these configuration records. Per-target role orchestration
registers only unfinished role/target pairs and never changes a committed role
configuration. Historical v1 semantic records require fresh current execution;
there is no silent provenance upgrade. Future prompt/config changes require an
explicit method/version policy change. Phase 8 and future qualification issuers
remain deferred; implementer verification does not establish acceptance.
