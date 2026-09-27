# ADR-023: Canonical source identity

Status: Accepted for Phase 5 implementation

## Decision

A retrieved candidate is a discovery observation, never a canonical source. Phase 5
derives canonical source identity from normalized stable identifiers, using a fixed
ranking, and only then links versions and provenance. Titles never participate in
identity determination. Search snippets, ranks and provider-local scores never
participate either.

Identity ranking (highest first):

1. `doi` — globally shared scholarly identity, case-insensitive, URL/`doi:` forms folded;
2. `patent_numbers` — normalized publication/application numbers, sorted;
3. `repository` — GitHub `owner/repository`, case-folded; forks and mirrors keep
   distinct owner/repository identities and are linked, if at all, by provenance;
4. `arxiv_id` — the arXiv base identifier; an explicit `vN` suffix is a version
   attribute, not a new work and not independent evidence;
5. `openalex_id`, then `semantic_scholar_id` — corpus-local stable identifiers;
6. sorted `other` identifiers (for example PubMed);
7. the normalized canonical URL, only when no stable identifier exists;
8. otherwise a conservative fallback over the discovery identities
   (`provider:provider_source_id`) present in the candidate cluster.

The source identifier is the first available level's canonical value hashed with
SHA-256 (`src_<hex>`), so the same stable identifier always produces the same
source ID across providers and runs. Lower-level identifiers remain on the
record; they are additional identity, not alternative identities.

## Rules

- Same DOI from any number of providers resolves to one canonical source while
  every discovery path (provider, strategy, query, search run, expansion seed)
  is retained separately.
- Disagreeing stable identifiers are a conflict. The conflicted field is left
  unresolved (never guessed), the conflict and unresolved field are recorded,
  and identity falls back to a lower ranking level rather than merging.
- Similar titles alone can never establish identity; same title with different
  DOIs remains two sources.
- Uncertainty stays visible: when only the conservative discovery fallback is
  available, the source records `limitations` explaining that identity may be
  incomplete, rather than silently merging with a later observation.
- Version identity (arXiv `vN`, preprint/journal, repository releases) links
  versions of one work; it never creates additional independence.
- Patent family membership is a lineage relation (`PATENT_FAMILY_OF`), not a
  source collapse: each publication number keeps its own identity while family
  lineage prevents independence inflation.

## Consequences

Canonical identity is deterministic and rerunnable, and provenance is preserved
through deduplication. The price is more conservative behavior: works without
stable identifiers may remain split when a human would merge them, and identity
fallback level 8 is discovery-set dependent. Both are accepted because false
merges create false corroboration, which is worse than visible duplication.
