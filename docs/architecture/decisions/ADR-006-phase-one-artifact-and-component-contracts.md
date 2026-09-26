# ADR-006: Phase 1 artifact and semantic-component contracts

Status: Accepted for Phase 1 architecture only
Date: 2026-09-26

## Context

The approved Phase 1 plan specifies final-shape contracts and replaceable async
semantic components, but leaves exact field representation and component method
signatures open. No semantic judgment is authorized in this phase.

## Decision

New artifacts inherit the existing versioned, extra-forbid ContractModel. Frozen
findings and their nested records use frozen models and tuples rather than
mutable lists/dictionaries. Optional unknown descriptive fields remain None.
Each analytical artifact records provenance as implemented, fixture, or deferred,
with a component name and explanation. These labels describe origin, not evidence
quality or verdict permission.

CIR preserves exact original input plus an original-input reference independently
of the request artifact. MCU graphs retain features, relationships and separate
combinations. Queries retain family, target, text, rationale and generator.
Sources/passages have normalized transport records with separate date fields,
access state, content hashes and discovery references. Evidence edges retain
comparison, passage IDs, cutoff information, quality and support verification.
No normalization, chronology, equivalence or support reasoning is implemented.

Frozen adjudication contains per-MCU findings, decisive-edge references, distinct
value findings, language permissions, unresolved questions and structured answer
material. The report compiler renders only these findings and provided artifact
references; missing information is explicitly unknown. It hashes adjudication
before rendering and returns that hash, without making a new verdict.

Async components operate on these typed artifacts. The adjudication component
receives the run assessment ID/cutoff so injected findings bind to the current
run without fixture identities leaking into production. A frozen dataclass holds
the component instances; they are never persisted as protocol objects.

## Consequences

This defines version 0.1 transport shape, not novelty intelligence. No persisted
Phase 0 shape changes, migration, new provider or dependency is required. Later
implementations replace injected fixtures while preserving orchestration and
must version incompatible artifact changes. Semantic gates, confidence, adaptive
research, and real source interpretation remain deferred.
