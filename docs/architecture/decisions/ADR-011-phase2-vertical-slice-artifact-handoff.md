# ADR-011: Understanding artifacts through the accepted vertical slice

Status: Accepted for Phase 2 implementation.

UnderstandingComponents is a request-scoped adapter implementing the four existing
normalization/sufficiency/decomposition/reconciliation ports. It runs real Phase 2
components in lifecycle order. A/B share only defensive CIR copies; reconciliation
requires both independently obtained snapshots. No Phase 1 required signature or
persisted schema changes.

An optional UnderstandingArtifactSource protocol drains named sidecar artifacts,
semantic audits, finalized CIR contribution references and a conservative ceiling.
The application writes sidecars and emits audit events at the corresponding stage.
The finalized CIR binds MCU/combination IDs only after reconciliation. Initial CIR
and sufficiency snapshots are retained separately; ceiling corrections append an
explicit instability event before research and update the final sufficiency artifact.
The nine-question report still consumes frozen adjudication and cannot re-decide.

Standalone understand_idea exposes the same frozen result and optional local files;
semantic_calls.jsonl is retained even on schema failure. No research provider is
created. Later stages remain explicitly injected/fixture-backed in integration tests.

Cost: the four-port adapter is request-scoped, not reusable or resumable. Individual
file writes retain the Phase 1 atomicity boundary. Semantic output validation and
grounding rejection are distinct; a schema-valid response can still fail grounding,
which is a failed run rather than repaired output. No assessment/verdict permission
engine is added: later adjudication must honor the recorded structural ceiling.
