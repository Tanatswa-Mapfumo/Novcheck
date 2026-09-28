# ADR-031: Persist the verified semantic chain

Status: Implemented for Phase 6 Round-2 remediation; independent acceptance pending

## Context

A schema-valid verified edge could previously be paired with another claim or
nonexistent passage, then referenced by a graph edge. F05-F07 require the
source, cited version, proposition, mapping, claim, passages, verification,
eligibility, and graph edge to remain one traceable comparison.

## Decision

`validate_semantic_chain` checks those identities and canonical
commitment-level citations before edge construction. Classification facts now
carry the actual support claim, not only an optional claim ID. Decisive
classification requires a complete verification context and eligible
chronology. `VerifiedEvidenceChain` retains the inputs required to
reconstruct an edge. Graph persistence resolves that chain, its source and
version nodes, and every cited passage node with matching ownership and
content hash in one transaction. Repeated identical artifacts are idempotent;
different content under one ID is rejected.

The graph schema moves to v3 with an append-only `verified_chains` table.
An existing v1/v2 database with Phase 6 graph edges is migration-blocked,
because those edges cannot be proven against a complete chain. Databases
without such edges migrate deterministically. The changed facts and edge
contracts are explicitly versioned; no old artifact is silently reinterpreted.

## Consequences

Callers must supply the cited version and support bundle/claim when building
or classifying verified evidence. Additional persisted input enables reopening
and revalidating the semantic chain. This gate does not infer entailment from
schema validity: the independent verifier remains responsible for semantic
judgments, and a live verifier's accuracy remains uncalibrated.
