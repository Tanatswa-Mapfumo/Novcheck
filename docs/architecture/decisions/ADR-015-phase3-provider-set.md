# ADR-015: Phase 3 provider set and explicit screening boundary

Status: Accepted for Phase 3 implementation

Initial implemented adapters are OpenAlex and Crossref (SCHOLARLY) and GitHub
repository search (SOFTWARE). Their independent compilation limitations remain
visible; they are not universal interchangeable search engines. Semantic Scholar,
EPO OPS, general web/Brave, standards, regulatory and archive providers are planned
only. Missing ecosystems stay blocked in coverage; registry lookup cannot exclude
families. No vendor model provider is added. httpx is the only new direct dependency.

Phase 3 performs real planning, independent criticism and bounded first-page
screening. The application accepts an optional Phase3ResearchComponents bundle
alongside an explicit DeferredFixtureContinuation. Existing Phase 1/2 callers and
persisted legacy artifacts are unchanged. Rich Phase 3 artifacts live under phase3/
when running the accepted slice, or at the standalone screening run root.

The continuation consumes screening hits, but is not a real selection, provenance
or evidence engine. Supplied source/passage artifacts must be visibly fixture-backed.
Trace records the precise boundary. Synthetic test mappings may bind screened
identities to synthetic passages; this proves data flow, not citation support.
Later mapping, verification and adjudication remain injected fixtures. Report
generation still consumes frozen findings and cannot re-decide novelty.

Phase 3 never emits SATURATED and implements no fusion, adaptive allocation,
citation chasing, entity expansion, multilingual deepening, prior-art equivalence,
adversarial reasoning or novelty scores/probabilities. Repository dates and
scholarly metadata are screening candidates only, not proven priority/provenance.
