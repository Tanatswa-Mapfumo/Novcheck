from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from novelty_harness.domain.enums import EvidenceFamily, EvidenceTier
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    DiscoveryPath,
    ResolvedContent,
    SourceAccessState,
    SourceNormalizationResult,
    SourceRecord,
    SourceType,
    SourceVersionRecord,
    VersionKind,
)
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import (
    PassageLocator,
    PassageLocatorKind,
    PassageRecord,
)
from novelty_harness.evidence.provenance.models import (
    DEPENDENCY_RELATIONS,
    EvidenceLineageCluster,
    LineageConfidence,
    ProvenanceCycle,
    ProvenanceEdge,
    ProvenanceRelation,
)
from novelty_harness.evidence.quality.models import (
    AssessmentLevel,
    DimensionAssessment,
    EvidenceQualityAssessment,
    EvidenceQualitySignals,
    QualityDimension,
    SourceRelevanceAssessment,
)
from novelty_harness.research.retrieval.models import RetrievalMechanism, RetrievalStrategy

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = ArtifactProvenance(kind="implemented", component="phase5-test", detail="deterministic")
TEXT = "Exact source text about a thermal feedback controller.\n"


def make_identifiers(**overrides: object) -> CanonicalIdentifiers:
    values: dict[str, object] = {"doi": "10.1234/example"}
    values.update(overrides)
    return CanonicalIdentifiers.model_validate(values)


def make_source(**overrides: object) -> SourceRecord:
    values: dict[str, object] = {
        "source_id": "src_abc",
        "canonical_title": "Thermal feedback controller",
        "source_type": SourceType.PAPER,
        "canonical_url": "https://example.org/paper",
        "identifiers": make_identifiers(),
        "authors_or_owners": ("Ada Example",),
        "languages": ("en",),
        "access_state": SourceAccessState.FULL_TEXT,
        "evidence_families": (EvidenceFamily.SCHOLARLY,),
        "content_hash": text_hash(TEXT),
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return SourceRecord.model_validate(values)


def make_discovery(**overrides: object) -> DiscoveryPath:
    values: dict[str, object] = {
        "provider_name": "openalex",
        "provider_source_id": "W123",
        "strategy": RetrievalStrategy.LEXICAL,
        "mechanism": RetrievalMechanism.TEXT_SEARCH,
        "evidence_family": EvidenceFamily.SCHOLARLY,
        "query_id": "qry_1",
        "local_rank": 3,
        "discovered_at": NOW,
    }
    values.update(overrides)
    return DiscoveryPath.model_validate(values)


def make_version(**overrides: object) -> SourceVersionRecord:
    values: dict[str, object] = {
        "version_id": "srcv_v1",
        "source_id": "src_abc",
        "version_label": "v1",
        "version_kind": VersionKind.PREPRINT,
        "content_hash": text_hash(TEXT),
        "access_state": SourceAccessState.FULL_TEXT,
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return SourceVersionRecord.model_validate(values)


def make_passage(**overrides: object) -> PassageRecord:
    values: dict[str, object] = {
        "passage_id": "pass_1",
        "source_id": "src_abc",
        "text": TEXT,
        "content_hash": text_hash(TEXT),
        "access_state": SourceAccessState.FULL_TEXT,
        "locator": PassageLocator(kind=PassageLocatorKind.RESOLVED_CONTENT),
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return PassageRecord.model_validate(values)


def make_quality(**overrides: object) -> EvidenceQualityAssessment:
    values: dict[str, object] = {
        "source_id": "src_abc",
        "tier": EvidenceTier.B,
        "dimensions": tuple(
            DimensionAssessment(dimension=dimension, level=level, rationale="test")
            for dimension, level in (
                (QualityDimension.PRIMARYNESS_DIRECTNESS, AssessmentLevel.MEDIUM),
                (QualityDimension.TECHNICAL_SPECIFICITY, AssessmentLevel.MEDIUM),
                (QualityDimension.PROVENANCE_AUTHENTICITY, AssessmentLevel.MEDIUM),
                (QualityDimension.DATE_CERTAINTY, AssessmentLevel.UNKNOWN),
                (QualityDimension.INDEPENDENCE, AssessmentLevel.HIGH),
                (QualityDimension.COMPLETENESS_ACCESS, AssessmentLevel.HIGH),
                (QualityDimension.REPRODUCIBILITY_VERIFIABILITY, AssessmentLevel.UNKNOWN),
            )
        ),
        "assessed_at": NOW,
    }
    values.update(overrides)
    return EvidenceQualityAssessment.model_validate(values)


def test_source_record_round_trips_with_discovery_paths() -> None:
    source = make_source(
        discovery_queries=("qry_1", "qry_2"),
        discovery_paths=(
            make_discovery(),
            make_discovery(
                provider_name="crossref",
                provider_source_id="10.1234/example",
                strategy=RetrievalStrategy.SEMANTIC,
                mechanism=RetrievalMechanism.SEMANTIC_SEARCH,
                query_id=None,
                seed_source=None,
                local_rank=1,
            ),
        ),
        limitations=("Only one provider returned a full text",),
    )
    assert SourceRecord.model_validate(source.model_dump(mode="json")) == source
    assert len(source.discovery_paths) == 2
    assert source.has_stable_identity()


def test_source_rejects_unknown_and_blank_fields() -> None:
    with pytest.raises(ValidationError):
        make_source(unexpected_field=True)
    with pytest.raises(ValidationError):
        make_source(canonical_title="   ")


def test_resolved_access_requires_a_content_hash() -> None:
    with pytest.raises(ValidationError):
        make_source(content_hash=None)
    metadata_only = make_source(access_state=SourceAccessState.METADATA_ONLY, content_hash=None)
    assert metadata_only.content_hash is None


def test_passage_round_trips_and_requires_exact_hashed_text() -> None:
    passage = make_passage(
        locator=PassageLocator(
            kind=PassageLocatorKind.SECTION,
            section="4.2",
            char_start=0,
            char_end=8,
        )
    )
    assert PassageRecord.model_validate(passage.model_dump(mode="json")) == passage
    with pytest.raises(ValidationError):
        make_passage(content_hash=text_hash("different text"))
    with pytest.raises(ValidationError):
        make_passage(text="   ")


def test_discovery_only_text_cannot_become_a_passage() -> None:
    for access_state in (SourceAccessState.METADATA_ONLY, SourceAccessState.BLOCKED):
        with pytest.raises(ValidationError):
            make_passage(access_state=access_state)
    with pytest.raises(ValidationError):
        make_passage(
            access_state=SourceAccessState.ABSTRACT_ONLY,
            locator=PassageLocator(kind=PassageLocatorKind.SECTION, section="4.2"),
        )
    abstract = make_passage(
        access_state=SourceAccessState.ABSTRACT_ONLY,
        locator=PassageLocator(kind=PassageLocatorKind.ABSTRACT, label="Abstract"),
    )
    assert abstract.access_state == SourceAccessState.ABSTRACT_ONLY


def test_locator_rejects_inconsistent_spans() -> None:
    with pytest.raises(ValidationError):
        PassageLocator(kind=PassageLocatorKind.RESOLVED_CONTENT, char_start=4)
    with pytest.raises(ValidationError):
        PassageLocator(kind=PassageLocatorKind.SECTION)
    with pytest.raises(ValidationError):
        PassageLocator(kind=PassageLocatorKind.PARAGRAPH_WINDOW, start_paragraph=3)


def test_provenance_edge_round_trips_with_evidence() -> None:
    edge = ProvenanceEdge(
        edge_id="prov_1",
        source_id="src_a",
        related_source_id="src_b",
        relation=ProvenanceRelation.CITES,
        lineage_confidence=LineageConfidence.CONFIRMED,
        evidence=("crossref:reference-list",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert ProvenanceEdge.model_validate(edge.model_dump(mode="json")) == edge
    with pytest.raises(ValidationError):
        ProvenanceEdge.model_validate({**edge.model_dump(), "evidence": ()})
    with pytest.raises(ValidationError):
        ProvenanceEdge.model_validate({**edge.model_dump(), "related_source_id": "src_a"})
    with pytest.raises(ValidationError):
        ProvenanceEdge.model_validate({**edge.model_dump(), "unexpected": 1})


def test_required_provenance_relations_and_dependency_split() -> None:
    assert {
        "CITES",
        "DERIVES_FROM",
        "REPOSTS",
        "VERSION_OF",
        "PATENT_FAMILY_OF",
        "IMPLEMENTS",
        "DOCUMENTS",
        "FOUND_BY",
    } <= {relation.value for relation in ProvenanceRelation}
    assert ProvenanceRelation.CITES not in DEPENDENCY_RELATIONS
    assert ProvenanceRelation.FOUND_BY not in DEPENDENCY_RELATIONS
    assert ProvenanceRelation.PATENT_FAMILY_OF in DEPENDENCY_RELATIONS


def test_lineage_cluster_enforces_root_count_consistency() -> None:
    cluster = EvidenceLineageCluster(
        cluster_id="lin_1",
        source_ids=("src_a", "src_b"),
        root_source_ids=("src_b",),
        independent_roots=1,
        rationale=("src_a derives from src_b",),
        unresolved_ambiguities=("One mirror relation is unverified",),
    )
    assert EvidenceLineageCluster.model_validate(cluster.model_dump(mode="json")) == cluster
    with pytest.raises(ValidationError):
        EvidenceLineageCluster.model_validate({**cluster.model_dump(), "independent_roots": 2})
    with pytest.raises(ValidationError):
        EvidenceLineageCluster.model_validate(
            {**cluster.model_dump(), "root_source_ids": ("src_z",)}
        )
    with pytest.raises(ValidationError):
        EvidenceLineageCluster.model_validate(
            {**cluster.model_dump(), "source_ids": ("src_a", "src_a")}
        )


def test_provenance_cycle_round_trips() -> None:
    cycle = ProvenanceCycle(
        source_ids=("src_a", "src_b", "src_c"),
        relation_types=(ProvenanceRelation.DERIVES_FROM,),
        severity="MATERIAL",
        explanation="A derives B derives C derives A",
    )
    assert ProvenanceCycle.model_validate(cycle.model_dump(mode="json")) == cycle
    with pytest.raises(ValidationError):
        ProvenanceCycle.model_validate({**cycle.model_dump(), "severity": "CRITICAL"})


def test_quality_and_relevance_cannot_collapse_into_one_scalar() -> None:
    quality_fields = set(EvidenceQualityAssessment.model_fields)
    relevance_fields = set(SourceRelevanceAssessment.model_fields)
    assert "tier" in quality_fields and "tier" not in relevance_fields
    assert "relevance" in relevance_fields and "relevance" not in quality_fields
    assert not quality_fields & {"relevance_strength", "similarity", "score"}
    assert not relevance_fields & {"evidence_quality", "tier", "score"}
    relevance = SourceRelevanceAssessment(
        source_id="src_abc",
        mcu_id="mcu_1",
        relevance=AssessmentLevel.HIGH,
        basis=("Ranked first by two independent mechanisms",),
        assessed_at=NOW,
    )
    assert SourceRelevanceAssessment.model_validate(relevance.model_dump(mode="json")) == relevance


def test_quality_assessment_requires_every_dimension_once() -> None:
    quality = make_quality()
    assert {item.dimension for item in quality.dimensions} == set(QualityDimension)
    with pytest.raises(ValidationError):
        make_quality(dimensions=quality.dimensions[:-1])
    with pytest.raises(ValidationError):
        make_quality(dimensions=(*quality.dimensions, quality.dimensions[0]))


def test_quality_signals_reject_conflicting_discovery_roles() -> None:
    with pytest.raises(ValidationError):
        EvidenceQualitySignals(promotional=True, news_or_aggregator=True)
    with pytest.raises(ValidationError):
        EvidenceQualitySignals(unexpected=True)


def test_resolved_content_state_matches_payload() -> None:
    full = ResolvedContent(access_state=SourceAccessState.FULL_TEXT, text=TEXT)
    assert full.text == TEXT
    abstract = ResolvedContent(access_state=SourceAccessState.ABSTRACT_ONLY, abstract="Short")
    assert abstract.abstract == "Short"
    with pytest.raises(ValidationError):
        ResolvedContent(access_state=SourceAccessState.FULL_TEXT)
    with pytest.raises(ValidationError):
        ResolvedContent(access_state=SourceAccessState.METADATA_ONLY, text=TEXT)
    with pytest.raises(ValidationError):
        ResolvedContent(access_state=SourceAccessState.BLOCKED, abstract="Short")


def test_source_version_and_normalization_result_round_trip() -> None:
    version = make_version(
        published_date=date(2020, 1, 1),
        identifiers=make_identifiers(arxiv_id="2001.00001"),
        limitations=("Preprint; journal version unknown",),
    )
    result = SourceNormalizationResult(
        source=make_source(),
        version=version,
        conflicts=("OpenAlex and Crossref disagree on the publication year",),
        unresolved_fields=("authors",),
        merged_candidate_keys=("cluster:abc",),
    )
    assert SourceNormalizationResult.model_validate(result.model_dump(mode="json")) == result


def test_discovery_path_key_ignores_rank_and_time() -> None:
    first = make_discovery(local_rank=1)
    later = make_discovery(local_rank=9, discovered_at=datetime(2026, 9, 27, tzinfo=UTC))
    assert first.path_key() == later.path_key()
    other_query = make_discovery(query_id="qry_2")
    assert first.path_key() != other_query.path_key()
    expanded = make_discovery(
        strategy=RetrievalStrategy.CITATION_BACKWARD,
        mechanism=RetrievalMechanism.GRAPH_EXPANSION,
        query_id=None,
        seed_source={"provider_name": "openalex", "provider_source_id": "W1"},
    )
    assert expanded.path_key() != first.path_key()
    assert expanded.seed_source is not None
