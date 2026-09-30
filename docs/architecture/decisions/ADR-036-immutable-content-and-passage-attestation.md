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

## R10 amendment: persisted content authority (30 September 2026)

Source/version identity has one immutable persisted content authority;
caller-supplied internally consistent provenance cannot override it. A
versioned chain must agree with the stored or concurrently supplied
`SOURCE_VERSION` node on owner, content hash and access state. Its attested
parent digest and passage access state must agree with that cited version.
The `SOURCE` node's content hash and access state must also agree with the
chain's source record when present; a source hash need not equal every version
hash. An unversioned chain requires a `SOURCE` node with matching content hash
and access state.

The graph repository checks these authorities in the same transaction as
verified edges, observations, chains, classifications and Phase 6 graph
projections. It compares all same-ID nodes supplied in one batch, using an
existing persisted node as authority if one is present. A conflict rejects
the whole batch. A chain-only `VerifiedComparison` or precedent classification
is provisional until this repository validation succeeds; the classifier has
no independent authority to replace persisted content.

## R11 amendment: authoritative publication after commit (30 September 2026)

Semantic results computed before repository content-authority reconciliation
are provisional. Only artifacts covered by a successful authoritative
repository commit may produce authoritative Phase 6 success publication.
The repository returns an immutable `Phase6CommitReceipt` after the transaction
commits. The pipeline persists each assessed source/target comparison before
publishing its mapping, verification or classification success events. It
calculates multi-source and patent findings from committed comparisons only;
a rejected comparison becomes an explicit unassessable failure and cannot
contribute to published summary or patent success.
The Phase 6 result carries the receipts, and its legacy Phase 7 projection
rejects any verified edge whose classification lacks a matching receipt.

The SQL commit and JSONL trace append are separate operations. If trace
delivery fails after commit, the repository remains authoritative and the run
fails visibly. A retry reuses the immutable semantic edge/classification IDs
and stable success-event IDs; the JSONL sink skips event IDs already present.
The specification calls for append-only audit and a traceable *completed*
assessment, but does not require crash-safe guaranteed delivery between SQL
commit and trace append. An outbox is therefore deferred. A partially written
trace file may require recovery before replay, and no run is reported complete
while trace delivery fails.
