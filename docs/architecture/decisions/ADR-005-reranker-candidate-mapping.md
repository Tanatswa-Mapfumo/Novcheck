# ADR-005: Define reranker candidate mapping and rank validity

Status: Accepted for Phase 0
Date: 2026-09-26

## Context

The Phase 0 review found that the shared reranker contract helper accepted
unknown candidate IDs, duplicate candidates, and invalid ranks. The abstract
port accepts strings without separate IDs, and the existing deterministic
fixture returns those exact input strings as candidate IDs. The completion
record requires an ADR before adding mapping rules.

## Decision

For the existing string-based interface, each returned candidate_id must equal
an input candidate string. Returned candidate IDs must be unique. Ranks are
unique one-based integers within 1..len(input candidates). The shared provider
contract helper checks these rules in addition to model and audit validation.
The protocol documents them without changing its signature or DTO fields.

Reordered, partial, and empty responses remain valid. This decision does not
require complete responses, contiguous ranks, response ordering by rank, or
particular scores. Identical input strings share an identity and cannot appear
more than once in the output; distinguishing them would require a future
explicit interface decision.

## Consequences

These checks reject basic transport errors without introducing a reranking
algorithm, provider implementation, or novelty semantics. Public interfaces and
serialized artifact shapes remain unchanged; no artifact migration or new
dependency is required. Future adapters must pass the shared contract suite.
