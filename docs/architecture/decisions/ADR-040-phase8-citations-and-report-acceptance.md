# ADR-040: Phase 8 citations and immutable report acceptance

- Date: 2026-10-06
- Status: Accepted design; implementation follows the Phase 8 task gates
- Governing design: [Phase 8 full report compiler](../../superpowers/specs/2026-10-05-phase-8-full-report-compiler-design.md)

## Context

Phase 6 supplies verified prior-art authority. Frozen Phase 7 findings supply
verdicts, Gates, scope and language permissions. Report prose and bibliographic
metadata cannot create either authority. ADR-010 remains the Phase 2 grounding
and assessment-ceiling decision.

## Decision

One verified ReportIR supplies all report formats. The deterministic
`p8-citations-v1` registry joins actual claim bases to admitted passages and their
exact comparison, commit, commitment, source and version ancestry. It retains
committed metadata observations separately, including missing or conflicting
metadata. A source title, related version or canonical URL cannot replace a
supported passage or certify the assertion's meaning.

Citation identity hashes source/version/passage/locator and supporting
comparison/commitment identity. Display numbers follow stable native identities,
independent of paragraph order. Repeated citations and related versions do not
establish independent evidence. Internal input, Gate, uncertainty and prospective
recommendation bases retain internal references without invented bibliography.

Only a stored canonical HTTP(S) URL or stored DOI resolved by the pinned v1 rule
may link externally. DOI path characters are encoded; unsupported identifiers
remain plain recorded data. Unsafe schemes, credentials and control characters
cannot become links. No retrieval, link check, guessed URL or citation expansion
occurs. Canonical source pages are labeled versionless rather than presented as
archived links to the exact cited version. Publication, retrieval and assessment
cutoff remain separately labeled; an absent date is not invented.

Report authority is established only by transactional acceptance and read
validation over repository locators. Schema v9 adds exactly four report tables
on the existing engine. Acceptance reloads the exact upstream and report
artifact dependency closure in one explicit write transaction and atomically
commits the immutable report, dependencies and ACCEPTED status. Reads revalidate
that same closure in one explicit read transaction. Caller ReportIR, exports,
receipts, citation registries and traces confer no authority. Missing or corrupt
authority is a hard error, without an accepted or exported downgrade.

## Consequences

Renderers escape attributed text and emit stable local reference anchors.
Canonical metadata, actual source dates, access limitations and exact locators
remain inspectable in the structured report. Citation membership is mechanical;
independent semantic support and completeness checks still govern generative
assertions. Deterministic fallback is accepted only through exact recomputation
and the same repository closure. No Phase 6/7 semantic rows are changed.

Task 16 implements citation resolution. Tasks 17–20 implement ReportIR, rendering
and transactional acceptance/read; this ADR does not claim those gates have
already passed or grant Phase 8 independent acceptance.
