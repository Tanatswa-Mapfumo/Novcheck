# ADR-034: VerifiedComparison and repository-derived Phase 6 projection

Status: Implemented for Phase 6 consolidation; independent acceptance pending

## Context

Individually valid verification, classification, and graph objects could be
cross-wired after chain validation. A direct graph edge could advertise a
nonexistent passage or a foreign classification basis.

## Decision

`VerifiedComparison` is created from a reconstructible, validated semantic
chain. It binds assessment, source and owned version, target, proposition,
mapping, claim, verifier result, canonical cited passages, chronology, and
context status. The public verified classifier consumes this artifact.
Loose `ClassificationFacts` remain usable only for unassessable selection
failures at the public gate; the private facts classifier supports deterministic
classifier-unit tests.

`ClassifiedComparison` re-derives and validates classification identity and
basis from the verified comparison. Its classification ID includes the final
verified-edge ID, so distinct assessments and cutoffs cannot collide.

The repository resolves and stores the chain and classified comparison in one
transaction. It generates Phase 6 graph attributes from those records and
requires supplied graph nodes and edges to match exactly before insertion.
Source, version, and every cited passage node must resolve to the chain.
Unsafe legacy Phase 6 graph edges are refused during schema migration.

## Consequences

A foreign mapping, version, claim, proposition, citation, relation, or
classification basis cannot establish a persisted direct graph relation.
Valid combination targets and multi-passage evidence retain their exact IDs.
The graph remains local evidence, not a Phase 7 novelty verdict.
