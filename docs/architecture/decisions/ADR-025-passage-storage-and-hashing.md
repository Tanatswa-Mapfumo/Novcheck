# ADR-025: Passage storage, exact text and content hashing

Status: Accepted for Phase 5 implementation

## Decision

Passages are exact, source-derived slices of resolved content or of a supplied
abstract. They are never summaries, paraphrases or LLM rewrites, and they never
originate from titles, search snippets or discovery metadata.

Normalization before hashing is deliberately small and documented in
`evidence/passages/hashing.py`:

1. drop a leading BOM;
2. `\r\n`/`\r` become `\n`;
3. trailing spaces/tabs are removed per line;
4. Unicode NFC normalization;
5. surrounding whitespace is stripped.

Interior whitespace, case, punctuation and wording are preserved. The content
hash is `sha256` over the UTF-8 bytes of the normalized text (hex digest).
Identical normalized text always yields the identical hash; changed content
always yields a different hash.

`PassageRecord` requires `content_hash == text_hash(text)`, keeps its
`source_id`, an optional `source_version_id`, a structured `PassageLocator`
(kind, section/label, paragraph window, character span), the access state that
made it available, observed time and provenance. Access state must be FULL_TEXT
or ABSTRACT_ONLY; a metadata-only or blocked source has no passages at all.
Abstract-only access requires an abstract locator, so partial access can never
masquerade as full text.

Passage identity is deterministic: `pass_` + SHA-256 over
`{source_id, source_version_id, locator, content_hash}`. Re-extracting the same
exact passage at the same locator is idempotent; the same text at different
locators produces distinct passages, and changed text produces a distinct
passage instead of overwriting history.

Version records (`srcv_` + SHA-256 over source/label/content-hash) are
append-only in the same way: a content change creates a new version linked by
`predecessor_version_id` and by a `VERSION_OF` provenance edge. Hash equality
is evidence only that the exact normalized content is unchanged; it is never
treated as conceptual equivalence.

## Consequences

Passages are auditable and reproducible, and reruns can detect changed source
material by comparing content hashes. Storage is larger than summary storage
and passage extraction depends on the caller supplying real locators or exact
spans; the alternative (inferred or rewritten passages) would violate the
passage-grounding invariant that Phase 6 depends on.
