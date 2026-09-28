# ADR-027: Independent blinded support verification

Status: Accepted for Phase 6 implementation

## Decision

Support verification is a separate stage from mapping and from precedent
classification, executed by `IndependentSupportVerifier`. Its only input is a
`BlindedVerificationInput` built from a support bundle:

- the proposition statement;
- the material commitments (with their dimensions and directed relationships);
- the claimed dimensions/relationships;
- the exact passage text and locator;
- source id / version id strictly for passage integrity.

The input contract uses `extra="forbid"` and carries no field for a novelty
verdict, a proposed precedent class, a prosecutor/defender role, a source
quality tier, a retrieval rank, a provider score, a user novelty claim or
report wording. The mapper stage and the verifier stage use different contracts
and prompts, and the verifier sees only the blinded input (plus its trusted
system instruction).

The LLM proposal is untrusted. Deterministic gates require:

- every material commitment judged exactly once; missing, duplicate or unknown
  commitments invalidate the response;
- cited passage ids exist in the supplied set; invented ids invalidate the
  response;
- `SUPPORTED` only when every commitment is `SUPPORTED`;
- `PARTIALLY_SUPPORTED` always records the unsupported remainder;
- any `CONTRADICTED` commitment makes the overall state `CONTRADICTED`;
- `INSUFFICIENT_CONTEXT` abstains and names the missing context;
- passage content is re-hashed against its recorded hash before any judgment is
  trusted; a `PassageIntegrityError` is an explicit failure, never coerced.

Contradictions are final for the stage unless passage integrity itself failed.
Quality, chronology and precedent metadata are attached after verification and
cannot alter the verification state.

## Consequences

A high-quality or highly ranked source cannot turn unsupported text into
support, and a low-quality source with exact supporting text keeps its support.
Commitment-level aggregation makes "all material commitments" structural
rather than a prompt request. The cost is one LLM call per claim (plus bounded
context retries) and less fluent free-form reasoning; the separation is the
property Phase 7 depends on.
