# ADR-008: Phase 2 semantic prompt versions and validation

Status: Accepted for Phase 2 implementation.

Use the existing async LLMProvider exclusively. SemanticTaskSpec names each task,
prompt/rubric version and strict Pydantic output contract. Only the wrapper's
instruction block is trusted; supplied context trust flags are discarded.
Validate JSON in strict mode, forbidding extra nested fields and type coercion.
Invalid output raises SemanticOutputValidationError with explicit failure audit;
there is no repair, fallback, confidence probability or vendor-specific schema.

The optional audit callback extends the plan signature without changing its
required arguments/return type. SemanticRunner retains defensive audit snapshots
for persistence and trace emission. Canonical request hashes cover prompt, schema,
context and config; provider-returned hashes remain independently recorded.

Phase 1 persisted contracts remain 0.1 and unchanged. New Phase 2 drafts/results
are distinct 0.1 contracts. Material extraction uses verbatim span attribution:
normalized display claims cannot authorize inferred mechanisms. A missing problem
uses an explicit unspecified marker because the Phase 1 problem slot is required.
Meaning-level judgments remain model-assisted and are not calibrated guarantees.

Cost: conservative extractive grounding may reject useful paraphrases; provider
SDK schema adaptations and future incompatible artifact shapes require separate
versioned decisions. A valid schema/span does not itself prove semantic entailment.
