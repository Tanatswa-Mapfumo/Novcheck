# ADR-004: Validate serialized lifecycle artifacts and finite JSON values

Status: Accepted for Phase 0
Date: 2026-09-26

## Context

The Phase 0 review found that direct model construction or JSON loading could
accept COMPLETED at RECEIVED, invalid lifecycle event values, and blank audit
fields despite the transition functions rejecting those conditions. It also
found that non-finite values inside JsonValue fields serialized to null, losing
meaning. Credential keys such as GITHUB_TOKEN escaped the enumerated redaction list.

## Decision

Apply the existing lifecycle policy to validated persisted artifacts as well as
transition functions. COMPLETED records require REPORTED. Lifecycle events keep
their specified string fields, but values must belong to the event's canonical
stage/status vocabulary and describe an allowed transition. Audit fields must
contain non-whitespace text. A shared domain policy module prevents the two
validation paths from diverging and avoids circular imports; public signatures
remain unchanged.

A standalone completion status event cannot prove its processing stage because
the planned event has no stage field. Its source status must be reportable; the
linked assessment record and complete_assessment enforce REPORTED.

All ContractModel descendants reject non-finite floats, including nested JSON
values. Trace sinks revalidate snapshots, so mutated nested data is also rejected.
Redaction recognizes normalized singular token suffixes (including GITHUB_TOKEN),
while preserving plural input_tokens/output_tokens counters and unrelated words.

## Consequences

This tightens structural validation of the initial, unreleased 0.1 contracts;
there are no previously released artifact versions to migrate. It clarifies the
plan's intentionally string-valued lifecycle events without adding novelty
semantics, new status policy, or later-phase services. Valid Phase 0 payloads and
provider signatures retain their existing serialization shape.
