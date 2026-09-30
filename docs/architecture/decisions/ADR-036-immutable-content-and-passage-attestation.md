# ADR-036: Immutable content provenance and extractor-owned passage attestation

Status: Implemented for Phase 6 hardening; independent acceptance pending

## Context

The 30 September independent review reproduced a decisive graph edge whose
passage self-hash was valid but whose text differed from the cited immutable
source version. A caller could also mark a short excerpt as a complete document
and hide a following qualifier. Local source/version ID checks do not prove
that cited text came from the cited content.

## Decision

`ResolvedVersionContent` holds normalized resolved text, its digest, content
kind, access state, source/version owner and retrieval time. The resolver checks
the digest against the owned `SourceVersionRecord.content_hash`, or the
`SourceRecord.content_hash` for genuinely unversioned content. A conflict is
an extraction failure. Source/version records remain the authoritative digest
claims supplied by the normalization stage.

Extraction creates a `PassageAttestation` carrying that parent artifact, exact
half-open offsets, passage digest and optional evidence-unit limits. Contract
validation recomputes the parent digest and exact slice. Whole-document and
abstract units must span the parent. Paragraph, Markdown section and numbered
patent-claim limits are recomputed from the same parent text. Caller-supplied
`EvidenceUnitBoundary` flags are never accepted as extraction proof. Context
completeness derives from the attestation and cannot be asserted by labels.

At the semantic-chain and repository boundaries, every Phase 6 cited passage
must have an attestation whose parent digest equals the cited owned version's
hash, or the unversioned source hash. Verifier-cited support cannot be decisive
unless authenticated context is complete. A source with no authoritative
content hash stays nondecisive. Legacy unattested passages may be represented
for Phase 5 compatibility but cannot back a Phase 6 verified chain.

Public semantic gates revalidate serialized Pydantic instances before using
their facts. `SupportVerification` requires one judgment per material
commitment, without missing, extra or duplicate IDs; edge decisiveness comes
from those validated records. Patent screening derives eligibility from an
authenticated `ClassifiedComparison`, not caller-provided chronology. Candidate
results keep classification and optional chain aligned. Multi-source summaries
validate target and assessment context when given authoritative comparisons.
Schema-v4 migration rejects nonempty legacy v2 and v3 verified artifacts that
lack the current provenance chain.

## Consequences

The decisive citation path now retains an exact, auditable slice of an
authoritative content digest. This is a provenance and structural guarantee,
not a live-model entailment guarantee. The numbered patent-claim extractor
supports unambiguous numbered blocks; unrecognized claim layouts need a
separate extractor and remain nondecisive. Passage attestations enlarge stored
chain artifacts because they retain the normalized parent text. Gate 30 remains
open until an independent semantic review verifies these contracts.
