# ADR-009: Immutable MCU versions and override audit

Status: Accepted for Phase 2 implementation.

Every user operation returns a new MCUVersion with a canonical content-hash ID,
parent ID, UTC timestamp, actor and reconciliation hash. Graph and nested features,
relationships, combinations and history use frozen models/tuples. Rollback selects
a retained parent; no in-place edit API exists.

MCUOverrideOperation keeps the plan's dictionary payload at the request boundary.
Persisted MCUOverrideRecord instead stores canonical payload_json and exposes a
defensive payload dictionary accessor. This distinct versioned audit contract avoids
Pydantic frozen models' shallow dictionary immutability. Audit includes the complete
previous graph and before/after graph hashes, preserving merge/split provenance.

Each operation uses its own strict typed payload. Add/edit/remove, merge/split,
relationship edits and combination upserts are explicit. Merge/split can atomically
include combination_updates; dangling members/endpoints and duplicate identifiers
are rejected. No implicit cascade deletion/remapping. EDIT_COMBINATION also allows
creation because the approved operation set has no ADD_COMBINATION.

Duplicate operation IDs and operations predating the parent are rejected. Hashes
cover graph and audit semantics; changing an actor/reason creates a different version.
Overrides express user intent, not model-verified truth or novelty permission. They
do not erase original reconciliation/ceiling history; downstream reassessment must
explicitly address structural changes before relaxing a prior limitation.

Cost: audit history retains full snapshots and grows with edits; dictionaries are
request DTOs, not immutable stored history. Parent retention/storage selection is
the caller's responsibility; no database, UI, auto-research or resume is added.
