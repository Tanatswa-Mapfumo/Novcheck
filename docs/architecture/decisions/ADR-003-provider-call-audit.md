# ADR-003: Audit every provider call without changing the planned DTOs

Status: Accepted for Phase 0
Date: 2026-09-26

## Context

FR-PROV-003 requires metadata to be recorded for every provider call. Task 6
includes call metadata in result envelopes, but ProviderCapabilities,
ProviderHealth, and Passage have no call field. Task 8's instruction that every
mock call return metadata cannot literally apply to those fixed return contracts.

## Decision

Preserve the approved DTO fields and async signatures. Mocks record constructor-
supplied, deterministic metadata in an append-only call history for every method,
including capabilities, health, and passage resolution. Result envelopes also
return their supplied metadata. Later concrete adapters must record all calls
through tracing, including operations whose DTOs carry no metadata.

## Consequences

No transport contract is expanded implicitly. Runtime-checkable protocols verify
interface shape, not audit side effects; adapters need contract tests and tracing
tests when introduced. Phase 0 has only deterministic test fixtures, no adapters.
If consumers later require metadata directly on every response, that is a versioned
contract change rather than a silent addition.
