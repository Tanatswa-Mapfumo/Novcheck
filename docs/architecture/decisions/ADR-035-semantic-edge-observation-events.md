# ADR-035: Semantic edge identity and verification observations

Status: Implemented for Phase 6 consolidation; independent acceptance pending

## Context

An identical assessment observed twice received one stable semantic edge ID
but two different `observed_at` payloads, causing append-only upsert to fail.
Changing the ID to include time would fragment semantically identical edges.

## Decision

Graph schema v4 stores one immutable semantic `verified_edges` row and
append-only `verification_observations` rows keyed by semantic edge ID and
observation timestamp. Exact replay of one observation is idempotent. A later
observation appends an event without rewriting the original semantic row.
Semantic comparisons of persisted chains, classifications, nodes, and edges
ignore only observation timestamps; their semantic fields must still match.

Assessment ID, cutoff, cited disclosure and chronology remain in semantic
edge identity as specified by ADR-032. A different assessment or cutoff
creates a different edge. Observation history survives database reopen.

Metadata-only v1-v3 databases may migrate to v4. A legacy Phase 6 edge or
verified artifact without the v4 authoritative chain/classification contract
blocks migration until reprocessed; it is never silently authoritative.

## Consequences

Re-observation and historical reassessment coexist without overwrite.
Repository transactions roll back an observation if graph projection or
identity validation fails.

## Provenance hardening amendment (30 September 2026)

The legacy verified-artifact guard applies to v2 as well as v3 databases,
including orphan verified rows with no corresponding graph edge. Such rows
lack the current authoritative chain and require reprocessing before migration.
