# Phase 5 — Source Normalization, Provenance, and Evidence Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` task-by-task. Track progress with checkboxes.

**Goal:** Convert Phase 4 retrieval candidates into canonical, version-aware, provenance-aware source and passage records; persist an auditable evidence graph; distinguish independent evidence from duplicate/version/derivative records; and expose source quality separately from source relevance without performing Phase 6 equivalence/support adjudication.

**Architecture:** Phase 5 introduces the canonical evidence substrate between retrieval and evidence reasoning. Phase 4 candidate clusters become `SourceRecord`, `SourceVersionRecord`, `PassageRecord`, provenance relations, lineage clusters and evidence-quality records. Stable global identifiers are preferred over fuzzy matching. Uncertain identity stays uncertain rather than being force-merged. Graph persistence uses a repository protocol with SQLAlchemy 2.x + SQLite as the first implementation; domain models remain storage-independent. Phase 6 will consume this layer to create source-to-MCU evidence edges and verify passage support.

**Tech Stack:** Existing Python 3.12+ / `uv` / Pydantic v2 / pytest / Pyright / Ruff stack. Add SQLAlchemy 2.x and SQLite persistence in this phase. Preserve PostgreSQL-compatible schema choices where practical. No graph database is required.

**Spec:** `docs/specs/master-design-spec.md`, especially Sections 23–26, 27 as a downstream boundary, 44–46, 49, 54, Phase 5 in Section 60, 61–62 and Appendix E.

## Global Constraints

- Base Phase 5 on accepted Phase 4 commit `ba92895` or an accepted descendant.
- Implement **Phase 5 only**.
- Retrieval candidate identity is not canonical source identity.
- Source count MUST NOT be used as independent evidence count.
- Relevance and evidentiary quality MUST remain separate dimensions.
- Versions of one underlying work SHOULD be linked, not counted independently.
- Patent-family members MUST preserve family lineage and must not inflate independent-evidence count by default.
- Reposts, mirrors, press-release repetitions and derivative summaries MUST preserve lineage.
- Circular derivation/dependency chains SHOULD be detectable where data permits.
- Source content and passages SHOULD be content-hashed deterministically.
- Titles, search snippets and discovery-only metadata MUST NOT become decisive evidence.
- Access state MUST distinguish full text, abstract-only, metadata-only and blocked.
- Phase 5 MAY extract passages but MUST NOT decide whether they support MCU equivalence.
- Do not create Phase 6 precedent/support findings (`DIRECT_PRECEDENT`, `STRONG_PARTIAL_PRECEDENT`, etc.) as adjudicated conclusions.
- Do not implement prosecutor/defender or novelty verdict logic.
- Do not silently guess source identity or chronology when metadata conflicts.
- All external content remains untrusted data.
- Default tests remain network-isolated.
- Production code MUST NOT import test fixtures.
- All Phase 4 discovery paths must survive canonical normalization.

## Review Focus

1. **Evidence-count inflation:** one underlying work appears via several providers/versions and is counted repeatedly.
2. **Over-aggressive dedup:** similar titles/authors are merged despite representing different works.
3. **Provenance collapse:** secondary/derivative pages obscure the original primary source.
4. **Quality/relevance conflation:** a highly similar low-quality source is treated as strong evidence automatically.
5. **Passage overreach:** title/snippet/abstract-only content is treated as equivalent to full primary evidence.

---

## Prerequisite Gate — Accept Phase 4 Baseline

Before Phase 5 coding:

- create an isolated worktree based on accepted Phase 4 commit `ba92895`;
- suggested branch: `phase-5-evidence-graph`;
- run:
  ```bash
  uv sync --dev
  uv run python scripts/verify.py
  git diff --check
  ```
- confirm `docs/phase-4-completion.md` remains accurate;
- do not begin Phase 5 if the baseline fails.

---

### Task 1: Define canonical source, version, passage, provenance and quality contracts

**Files:**
- Create `src/novelty_harness/evidence/normalization/models.py`
- Create `src/novelty_harness/evidence/passages/models.py`
- Create `src/novelty_harness/evidence/provenance/models.py`
- Create `src/novelty_harness/evidence/quality/models.py`
- Create `tests/unit/evidence/test_phase5_contracts.py`

Required contracts include:

```python
class SourceAccessState(str, Enum):
    FULL_TEXT = "FULL_TEXT"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    BLOCKED = "BLOCKED"

class SourceType(str, Enum):
    PAPER = "PAPER"
    PREPRINT = "PREPRINT"
    PATENT = "PATENT"
    REPOSITORY = "REPOSITORY"
    PRODUCT = "PRODUCT"
    STANDARD = "STANDARD"
    GOVERNMENT = "GOVERNMENT"
    REPORT = "REPORT"
    WEB = "WEB"
    DATASET = "DATASET"
    OTHER = "OTHER"
```

Add versioned Pydantic contracts for:
- `CanonicalIdentifiers`
- `SourceRecord`
- `SourceVersionRecord`
- `PassageRecord`
- `ProvenanceEdge`
- `EvidenceQualityAssessment`
- `SourceRelevanceAssessment`

`CanonicalIdentifiers` should support DOI, OpenAlex, Semantic Scholar, arXiv, patent numbers, GitHub repository identity and extensible other identifiers.

`SourceRecord` must preserve canonical title/type/url, identifiers, authors/owners, date fields, languages, access state, evidence families, content hash, discovery queries and discovery paths.

`PassageRecord` must retain source ID, optional source-version ID, exact text, locator, hash and access state.

Provenance relation values must include at least:
`CITES`, `DERIVES_FROM`, `REPOSTS`, `VERSION_OF`, `PATENT_FAMILY_OF`, `IMPLEMENTS`, `DOCUMENTS`, `FOUND_BY`.

Tests:
- strict unknown-field rejection;
- round-trip serialization;
- blank source title/passages rejected;
- quality and relevance cannot collapse into one scalar field.

- [ ] Write failing tests.
- [ ] Implement contracts only, no fuzzy identity logic.
- [ ] Commit.

---

### Task 2: Implement canonical identifier normalization

**Files:**
- Create `src/novelty_harness/evidence/normalization/identifiers.py`
- Create `tests/unit/evidence/normalization/test_identifiers.py`
- Create `docs/architecture/decisions/ADR-023-canonical-source-identity.md`

Normalize deterministically:
- DOI URL/prefix/case forms;
- OpenAlex IDs;
- Semantic Scholar IDs;
- arXiv IDs and version suffixes;
- GitHub `owner/repository` identity;
- patent publication/application identifiers conservatively;
- canonical URLs where deterministic.

Hard rules:
- global stable identifiers outrank fuzzy title matching;
- DOI identity outranks title similarity for scholarly works;
- arXiv versions are version relations, not independent evidence by default;
- GitHub forks are not automatically the same source as upstream;
- patent family is a lineage relation, not source collapse;
- title similarity alone cannot establish identity.

Tests:
- DOI URL vs bare DOI;
- case normalization;
- arXiv v1/v3;
- GitHub URL variants;
- conflicting stable identifiers;
- same title / different DOI stays distinct.

- [ ] Implement.
- [ ] Document ADR.
- [ ] Commit.

---

### Task 3: Normalize Phase 4 candidate clusters into canonical source records

**Files:**
- Create `src/novelty_harness/evidence/normalization/source_normalizer.py`
- Create `tests/unit/evidence/normalization/test_source_normalizer.py`

**Interface:**

```python
class SourceNormalizationResult(ContractModel):
    source: SourceRecord
    version: SourceVersionRecord | None
    conflicts: list[str]
    unresolved_fields: list[str]
    merged_candidate_keys: list[str]

async def normalize_candidate_cluster(... ) -> SourceNormalizationResult: ...
```

Policy:
- consume Phase 4 conservative candidate clusters;
- prefer stable identifiers/primary metadata;
- retain conflicts rather than silently choosing;
- retain all Phase 4 discovery paths;
- access state reflects actual resolved content;
- metadata-only remains metadata-only if content cannot be resolved;
- no source-to-MCU equivalence reasoning.

Required cases:
- same DOI from OpenAlex/Crossref/S2 -> one canonical source;
- conflicting titles/authors retained as conflicts;
- metadata-only source;
- blocked full text;
- GitHub repository source;
- same title/different DOI -> separate sources.

- [ ] Implement.
- [ ] Commit.

---

### Task 4: Implement source-version linking and deterministic content hashing

**Files:**
- Create `src/novelty_harness/evidence/normalization/versions.py`
- Create `src/novelty_harness/evidence/passages/hashing.py`
- Create `tests/unit/evidence/normalization/test_versions.py`
- Create `docs/architecture/decisions/ADR-025-passage-storage-and-hashing.md`

Requirements:
- canonical source may have multiple versions;
- preprint/journal/repository releases remain version-aware;
- use stable Unicode/newline normalization before hashing text;
- identical normalized text yields identical hash;
- content change creates new version/hash, never silent overwrite;
- hash equality does not itself imply conceptual equivalence;
- version chronology preserves uncertainty.

Tests:
- newline/Unicode normalization;
- changed content;
- arXiv versions;
- preprint -> journal;
- repository releases.

- [ ] Implement.
- [ ] Commit.

---

### Task 5: Implement passage extraction with locator preservation

**Files:**
- Create `src/novelty_harness/evidence/passages/extraction.py`
- Create `tests/unit/evidence/passages/test_extraction.py`

Support deterministic extraction from:
- abstracts;
- full-text section/block locators;
- paragraph windows;
- repository README/docs;
- provider/user-supplied locators.

Rules:
- preserve exact resolved content after deterministic normalization;
- do not rewrite/summarize passages;
- retain locator and source-version identity;
- abstract-only remains explicitly abstract-only;
- metadata/search snippets cannot become full passage evidence;
- prompt-injection text remains inert content.

Tests:
- abstract-only;
- full-text section;
- repeated same text at distinct locators;
- invalid locator;
- malicious instruction text;
- stable hashes.

- [ ] Implement.
- [ ] Commit.

---

### Task 6: Construct provenance lineage relations

**Files:**
- Create `src/novelty_harness/evidence/provenance/lineage.py`
- Create `tests/unit/evidence/provenance/test_lineage.py`
- Create `docs/architecture/decisions/ADR-024-provenance-independence.md`

Construct traceable relations from:
- citation metadata;
- version metadata;
- patent-family metadata;
- repository/project documentation;
- structured “extends/based on” links;
- repost/mirror metadata;
- primary announcement -> derivative coverage.

Rules:
- every relation has metadata/evidence;
- no model speculation creates `CONFIRMED` lineage;
- uncertain lineage remains `POSSIBLE`;
- one source may have several relation types.

Tests:
- paper cites predecessor;
- blog derives from press release;
- repo implements paper;
- patent family;
- uncertain lineage.

- [ ] Implement.
- [ ] Commit.

---

### Task 7: Build conservative provenance clusters and independence groups

**Files:**
- Create `src/novelty_harness/evidence/provenance/clustering.py`
- Create `tests/unit/evidence/provenance/test_clustering.py`

**Contract:**

```python
class EvidenceLineageCluster(ContractModel):
    cluster_id: str
    source_ids: list[SourceId]
    root_source_ids: list[SourceId]
    independent_roots: int
    rationale: list[str]
    unresolved_ambiguities: list[str]
```

Rules:
- versions of one work -> one underlying lineage;
- patent family -> one family lineage for independence counting by default;
- repeated reporting of one announcement -> one underlying root;
- independent replications/implementations may remain separate even when citing the same predecessor;
- citation alone does not make two works non-independent;
- uncertainty blocks forced collapse.

Tests:
- 50 articles from one press release -> one root;
- preprint+journal -> one lineage;
- independent replications -> multiple roots;
- patent family;
- ambiguous blog source.

- [ ] Implement.
- [ ] Commit.

---

### Task 8: Detect circular provenance/dependency chains

**Files:**
- Create `src/novelty_harness/evidence/provenance/circularity.py`
- Create `tests/unit/evidence/provenance/test_circularity.py`

Detect suspicious cycles for dependency relations such as `DERIVES_FROM` and `REPOSTS` while distinguishing ordinary mutual citation.

Output:

```python
class ProvenanceCycle(ContractModel):
    source_ids: list[SourceId]
    relation_types: list[ProvenanceRelation]
    severity: Literal["INFO", "WARNING", "MATERIAL"]
    explanation: str
```

Tests:
- A derives B derives C derives A;
- circular reposts;
- mutual paper citation -> informational/non-dependency;
- acyclic lineage.

- [ ] Implement.
- [ ] Commit.

---

### Task 9: Implement evidence-quality assessment separately from relevance

**Files:**
- Create `src/novelty_harness/evidence/quality/assessment.py`
- Create `tests/unit/evidence/quality/test_assessment.py`

Assess separately:
- primaryness/directness;
- technical specificity;
- provenance/authenticity;
- date certainty;
- independence;
- completeness/access;
- reproducibility/verifiability where applicable.

Tier mapping:
- A direct primary;
- B strong primary/official;
- C secondary;
- D discovery-only.

Hard rules:
- source type alone does not decide tier;
- snippet/news/marketing cannot normally become Tier A;
- abstract-only lowers completeness without changing relevance automatically;
- primary source may still have uncertain chronology;
- high relevance cannot increase evidence quality by itself.

Tests cover paper, abstract-only paper, patent, official docs, marketing page, reputable secondary analysis, snippet and high-relevance/low-quality cases.

- [ ] Implement.
- [ ] Commit.

---

### Task 10: Define storage-independent evidence graph domain and repository protocol

**Files:**
- Create `src/novelty_harness/evidence/graph/models.py`
- Create `src/novelty_harness/evidence/graph/repository.py`
- Create `tests/unit/evidence/graph/test_models.py`
- Create `docs/architecture/decisions/ADR-022-evidence-graph-storage.md`

Node kinds:
- Idea, MCU, Feature, Relationship, Source, SourceVersion, Passage, EvidenceProposition, Entity, Query, SearchRun.

Phase 5 edge kinds:
- `CITES`, `PREDATES`, `DISCOVERED_BY`, `DERIVES_FROM`, `VERSION_OF`, `PATENT_FAMILY_OF`, `IMPLEMENTS`, `DOCUMENTS`, `FOUND_BY`.

Reserve but do **not** create as adjudicated Phase 5 findings:
- `SUPPORTS`, `CHALLENGES`, `DIRECT_PRECEDENT`, `STRONG_PARTIAL_PRECEDENT`, `COMPONENT_PRECEDENT`, `ANALOGOUS`, `NO_MATCH`, `CONTRADICTS`.

Repository protocol must support add/get nodes/edges, neighbors, edge lookup and lineage cluster lookup.

Tests:
- strict node/edge types;
- dangling endpoints rejected;
- storage-independent Pydantic models.

- [ ] Implement.
- [ ] Document ADR.
- [ ] Commit.

---

### Task 11: Implement SQLAlchemy 2.x + SQLite graph persistence

**Files:**
- Add SQLAlchemy 2.x dependency.
- Create `src/novelty_harness/evidence/graph/sqlalchemy_models.py`
- Create `src/novelty_harness/evidence/graph/sqlalchemy_repository.py`
- Create `src/novelty_harness/evidence/graph/migrations.py`
- Create `tests/unit/evidence/graph/test_sqlalchemy_repository.py`

Requirements:
- SQLite first implementation;
- foreign keys enforced;
- unique canonical identities;
- repository returns domain models, not ORM objects;
- batch graph writes are transactional;
- deterministic upsert/idempotence where safe;
- schema version/migration table exists;
- avoid SQLite-only domain semantics where practical.

Tests:
- create/read/reopen;
- edge persistence;
- FK rejection;
- rollback on batch failure;
- idempotent repeated persistence;
- migration/version metadata.

- [ ] Implement.
- [ ] Commit.

---

### Task 12: Preserve query/retrieval/search-run discovery provenance

**Files:**
- Add graph mapping utilities.
- Create `tests/unit/evidence/graph/test_retrieval_mapping.py`

Preserve for every normalized source:
- Phase 4 candidate keys;
- providers;
- query IDs;
- retrieval strategies;
- search run IDs;
- expansion seed/source.

Graph relations must preserve `Source -> DISCOVERED_BY -> Query/SearchRun` and citation/entity expansion origin.

Tests:
- same source from OpenAlex/Crossref/S2 keeps all paths;
- citation discovery retains seed;
- dedup does not delete provenance;
- identical repeated path not multiplied accidentally.

- [ ] Implement.
- [ ] Commit.

---

### Task 13: Build the Phase 5 evidence-normalization pipeline

**Files:**
- Create `src/novelty_harness/evidence/pipeline.py`
- Create `tests/integration/test_phase5_evidence_pipeline.py`
- Create `tests/integration/test_phase4_slice_with_phase5_evidence.py`
- Create `tests/fixtures/phase5.py`

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class EvidenceNormalizationResult:
    sources: tuple[SourceRecord, ...]
    versions: tuple[SourceVersionRecord, ...]
    passages: tuple[PassageRecord, ...]
    provenance_edges: tuple[ProvenanceEdge, ...]
    lineage_clusters: tuple[EvidenceLineageCluster, ...]
    quality_assessments: tuple[EvidenceQualityAssessment, ...]
    graph_ref: str
```

Flow:
1. consume Phase 4 candidate clusters;
2. normalize identifiers;
3. resolve content where available;
4. create canonical sources/versions;
5. extract passages;
6. construct provenance;
7. compute lineage/independence groups;
8. assess quality separately from relevance;
9. persist graph;
10. write Phase 5 artifacts;
11. advance to `EVIDENCE_NORMALIZED`.

Persist:
- `sources.jsonl`
- `source_versions.jsonl`
- `passages.jsonl`
- `provenance_edges.jsonl`
- `lineage_clusters.jsonl`
- `source_quality.jsonl`
- SQLite evidence graph database
- trace events

Full vertical slice must use real Phases 2–5 while Phase 6+ remains fixture-backed.

- [ ] Write integration tests first.
- [ ] Implement.
- [ ] Commit.

---

### Task 14: Add Phase 5 adversarial provenance/evidence suite

**Files:**
- Create `tests/adversarial/test_phase5_provenance_attacks.py`

Mandatory cases:
1. same DOI via three providers -> one source, all discovery paths;
2. preprint+journal -> version-aware single lineage;
3. 50 pages repeating one press release -> one independent root;
4. similar-title distinct papers -> no merge;
5. patent family -> no independence inflation;
6. deleted/archived project -> retained with access limitation;
7. abstract-only closest source -> explicit completeness limitation;
8. metadata-only candidate -> not promoted to passage evidence;
9. search snippet -> discovery-only;
10. circular derivation -> flagged;
11. mutual citation -> not falsely collapsed;
12. highly relevant marketing page -> relevance can be high while quality remains low;
13. conflicting dates -> uncertainty preserved;
14. changed content -> new version/hash;
15. prompt injection in source text -> inert data;
16. one source found through many queries -> one source/many paths;
17. duplicated version -> independence unchanged;
18. two independent implementations -> separate roots.

- [ ] Implement.
- [ ] Commit.

---

### Task 15: Traceability, architecture guards, and final acceptance

**Files:**
- Create `docs/traceability/phase-5.yaml`
- Create `docs/phase-5-completion.md`
- Modify `README.md`
- Extend architecture/import guards.

Traceability must cover:
- Sections 23–26;
- `FR-SRC-001`, `FR-SRC-002`;
- `FR-PROV-001`, `FR-PROV-002`;
- INV-07, INV-08 and INV-14 where architecturally relevant;
- Phase 5 / Section 60;
- explicit deferral of Phase 6 evidence-mapping/support semantics.

Architecture guards:
- domain evidence models do not import SQLAlchemy;
- ORM objects do not leak through repository interfaces;
- Phase 5 creates no Phase 6 precedent/support adjudication edges;
- raw source count is never treated as independent evidence count;
- relevance and quality remain distinct types;
- metadata/snippets cannot become full-text passages;
- default tests remain network-blocked;
- no production imports from tests.

Run final verification:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

Perform fresh-checkout verification if practical.

- [ ] Write completion report.
- [ ] Commit.

---

## Phase 5 Acceptance Gate

Phase 5 is accepted only when all are true:

1. Accepted Phase 4 baseline passes before changes.
2. Final full verification passes.
3. Canonical source records round-trip through persisted artifacts.
4. Stable identifiers normalize deterministically.
5. Same DOI across providers resolves to one source while preserving all discovery paths.
6. Similar title alone cannot merge distinct works.
7. Versions are linked instead of counted independently.
8. Changed content produces a new version/hash rather than silent overwrite.
9. Access state distinguishes full text, abstract-only, metadata-only and blocked.
10. Passage extraction preserves source text/locator/hash.
11. Snippets/metadata cannot become full passage evidence.
12. Provenance relations preserve citation, derivation, repost, version, patent-family, implementation and documentation lineage where known.
13. Raw source count is never used as independent evidence count.
14. Press-release/repost flooding collapses to the correct lineage.
15. Patent-family records do not inflate independence.
16. Independent works remain separate despite shared citations.
17. Circular dependency/derivation is detectable.
18. Relevance and evidentiary quality remain separate.
19. Evidence tier respects access/primaryness without source-type shortcuts.
20. SQLAlchemy/SQLite persistence passes reopen/rollback/idempotence tests.
21. Domain graph models remain storage-independent.
22. Retrieval/query/search-run discovery provenance survives normalization.
23. All Phase 5 adversarial cases pass.
24. Full slice reaches `REPORTED/COMPLETED` with Phases 2–5 real and Phase 6+ fixture-backed.
25. No Phase 6 source-to-MCU equivalence/support adjudication was implemented.
26. No Phase 5 component creates a `DIRECT_PRECEDENT`-style adjudicated finding.
27. No prosecutor/defender/adjudication logic was implemented.
28. README/traceability accurately distinguish implemented/deferred behavior.
29. Phase 6 has not started.

If any gate fails, do not begin Phase 6.

---

## Self-Review Against Master Spec

### Phase 5 coverage
- canonical source records -> Tasks 1–3;
- versions/family relationships -> Tasks 4, 6–7;
- content hashes -> Tasks 4–5;
- provenance clustering -> Tasks 6–8;
- passage extraction -> Task 5;
- evidence graph persistence -> Tasks 10–13;
- quality/relevance separation -> Task 9;
- lineage/circularity diagnostics -> Tasks 6–8;
- citation flooding/version duplication exit criteria -> Tasks 7 and 14.

### Explicitly deferred
- source-to-MCU evidence mapping -> Phase 6;
- equivalence dimensions -> Phase 6;
- evidence support verifier -> Phase 6;
- direct/partial/component/analogy precedent adjudication -> Phase 6;
- prosecutor/defender/verdict gates -> Phase 7;
- full narrative report -> Phase 8.

## Execution Handoff

Recommended execution: **isolated worktree + task-gated/subagent-driven implementation**. Incorrect identity/provenance decisions can create false corroboration or erase real precedent, so conservative normalization and independent review are especially important.

Do not start Phase 6 until this phase has been reviewed and explicitly accepted.
