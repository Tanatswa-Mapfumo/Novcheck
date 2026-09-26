# ADR-002: Separate lifecycle stage and run status

Status: Accepted for Phase 0
Date: 2026-09-26

## Context

Master-spec Section 8 defines ordered processing stages and additional partial,
abstained, blocked, and failed states. An abstained assessment still needs frozen
findings and a report. The approved plan supplies a distinct status transition policy.

## Decision

Represent processing progress as AssessmentStage and execution condition as
AssessmentStatus. Only adjacent forward stage transitions are allowed. ACTIVE,
PARTIAL, and ABSTAINED may advance; BLOCKED must resume to ACTIVE first. FAILED
and COMPLETED are terminal. Only complete_assessment at REPORTED may enter COMPLETED,
from ACTIVE, PARTIAL, or ABSTAINED; blocked/failed runs cannot be completed as successes.

Use the plan's explicit status transition table. Each successful transition returns
a new record and a lifecycle event with timestamp, actor, and reason. Callers must
persist these events through a trace sink; there is no persistence service in Phase 0.
Invalid transitions raise a dedicated error and emit an error log.

Persisted timestamp contracts reject naive datetimes and normalize aware timestamps
to UTC. Assessment records and lifecycle events are frozen at the model field level;
transition copies are deep copies. This is not a guarantee of recursive immutability
for all nested user metadata.

## Consequences

Partial/abstained runs remain reportable and resumable while stage progress is retained.
COMPLETED indicates processing completion, not a novelty verdict. This is a
representation of Section 8, not a change to evidence or verdict semantics.
The master spec's suggested persistence ADR will receive a later available number;
this plan explicitly assigns ADR-002 to lifecycle representation.
