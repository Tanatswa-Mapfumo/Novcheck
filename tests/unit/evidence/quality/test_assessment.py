import inspect
from datetime import UTC, datetime

from novelty_harness.domain.enums import EvidenceTier
from novelty_harness.evidence.normalization.models import SourceAccessState, SourceType
from novelty_harness.evidence.quality.assessment import assess_quality, unassessed_relevance
from novelty_harness.evidence.quality.models import (
    AssessmentLevel,
    EvidenceQualitySignals,
    QualityDimension,
    SourceRelevanceAssessment,
)
from tests.fixtures.phase5 import make_source

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def dimensions(assessment):
    return {item.dimension: item.level for item in assessment.dimensions}


def test_full_text_primary_paper_reaches_tier_a() -> None:
    source = make_source("src_paper")
    assessment = assess_quality(
        source,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            first_party=True,
            primary_artifact=True,
            peer_reviewed=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
            date_certainty=AssessmentLevel.HIGH,
            reproducibility=AssessmentLevel.HIGH,
        ),
    )
    assert assessment.tier == EvidenceTier.A
    assert dimensions(assessment)[QualityDimension.COMPLETENESS_ACCESS] == AssessmentLevel.HIGH


def test_abstract_only_paper_lowers_completeness_without_touching_relevance() -> None:
    source = make_source("src_abstract", access_state=SourceAccessState.ABSTRACT_ONLY)
    assessment = assess_quality(
        source,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            first_party=True,
            primary_artifact=True,
            peer_reviewed=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
        ),
    )
    assert assessment.tier == EvidenceTier.B
    assert dimensions(assessment)[QualityDimension.COMPLETENESS_ACCESS] == AssessmentLevel.MEDIUM
    assert any("Full text not available" in item for item in assessment.limitations)


def test_patent_specification_and_official_documentation() -> None:
    patent = make_source("src_patent", source_type=SourceType.PATENT)
    patent_assessment = assess_quality(
        patent,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            primary_artifact=True,
            official=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
        ),
    )
    assert patent_assessment.tier == EvidenceTier.A
    official = make_source("src_docs", source_type=SourceType.STANDARD)
    official_assessment = assess_quality(
        official,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            official=True,
            technical_specificity=AssessmentLevel.MEDIUM,
            provenance_authenticity=AssessmentLevel.HIGH,
        ),
    )
    assert official_assessment.tier == EvidenceTier.B


def test_marketing_and_snippets_cannot_reach_decisive_tiers() -> None:
    marketing = make_source("src_marketing", source_type=SourceType.PRODUCT)
    marketing_assessment = assess_quality(
        marketing,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            promotional=True,
            technical_specificity=AssessmentLevel.LOW,
            provenance_authenticity=AssessmentLevel.LOW,
        ),
    )
    assert marketing_assessment.tier == EvidenceTier.D
    snippet = make_source("src_snippet", access_state=SourceAccessState.METADATA_ONLY)
    snippet_assessment = assess_quality(
        snippet,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            discovery_snippet=True, technical_specificity=AssessmentLevel.HIGH
        ),
    )
    assert snippet_assessment.tier == EvidenceTier.D
    assert any("discovery-only" in item for item in snippet_assessment.limitations)


def test_reputable_secondary_analysis_is_tier_c() -> None:
    review = make_source("src_review", source_type=SourceType.REPORT)
    assessment = assess_quality(
        review,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            secondary_analysis=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.MEDIUM,
        ),
    )
    assert assessment.tier == EvidenceTier.C


def test_source_type_alone_never_decides_the_tier() -> None:
    paper = make_source("src_full", source_type=SourceType.PAPER)
    same_type_only_metadata = make_source(
        "src_metadata", source_type=SourceType.PAPER, access_state=SourceAccessState.METADATA_ONLY
    )
    strong = assess_quality(
        paper,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            primary_artifact=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
        ),
    )
    weak = assess_quality(same_type_only_metadata, assessed_at=NOW)
    assert strong.tier == EvidenceTier.A and weak.tier == EvidenceTier.D
    assert strong.basis[0] == weak.basis[0] == "source_type:PAPER"


def test_high_relevance_cannot_raise_quality() -> None:
    parameters = set(inspect.signature(assess_quality).parameters)
    assert not parameters & {"relevance", "relevance_strength", "semantic_similarity"}
    marketing = make_source("src_marketing", source_type=SourceType.WEB)
    quality = assess_quality(
        marketing,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(promotional=True, technical_specificity=AssessmentLevel.LOW),
    )
    relevance = SourceRelevanceAssessment(
        source_id=marketing.source_id,
        mcu_id="mcu_1",
        relevance=AssessmentLevel.HIGH,
        basis=("Extremely similar wording to the MCU",),
        assessed_at=NOW,
    )
    assert relevance.relevance == AssessmentLevel.HIGH
    assert quality.tier == EvidenceTier.D


def test_uncertain_chronology_does_not_falsely_raise_or_lower_quality() -> None:
    source = make_source("src_undated", dates={})
    assessment = assess_quality(
        source,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            primary_artifact=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
            date_certainty=AssessmentLevel.LOW,
        ),
    )
    assert assessment.tier == EvidenceTier.A
    assert dimensions(assessment)[QualityDimension.DATE_CERTAINTY] == AssessmentLevel.LOW
    assert any("Chronology remains uncertain" in item for item in assessment.limitations)


def test_blocked_primary_source_cannot_be_tier_a() -> None:
    source = make_source("src_blocked", access_state=SourceAccessState.BLOCKED)
    assessment = assess_quality(
        source,
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            primary_artifact=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
        ),
    )
    assert assessment.tier == EvidenceTier.C
    assert dimensions(assessment)[QualityDimension.COMPLETENESS_ACCESS] == AssessmentLevel.LOW


def test_independence_dimension_comes_from_lineage_position() -> None:
    source = make_source("src_derivative")
    root = assess_quality(source, assessed_at=NOW, is_lineage_root=True)
    derived = assess_quality(source, assessed_at=NOW, is_lineage_root=False)
    unknown = assess_quality(source, assessed_at=NOW)
    assert dimensions(root)[QualityDimension.INDEPENDENCE] == AssessmentLevel.HIGH
    assert dimensions(derived)[QualityDimension.INDEPENDENCE] == AssessmentLevel.LOW
    assert dimensions(unknown)[QualityDimension.INDEPENDENCE] == AssessmentLevel.UNKNOWN


def test_unassessed_relevance_is_explicitly_not_a_quality_or_mapping_verdict() -> None:
    relevance = unassessed_relevance("src_paper", assessed_at=NOW, mcu_id="mcu_1")
    assert relevance.relevance == AssessmentLevel.UNKNOWN
    assert any("Phase 5 does not verify semantic relevance" in item for item in relevance.basis)
    assert isinstance(relevance, SourceRelevanceAssessment)
    assert not hasattr(relevance, "tier")


def test_quality_assessment_records_all_dimensions_and_source_identity() -> None:
    assessment = assess_quality(make_source("src_paper"), assessed_at=NOW)
    assert assessment.source_id == "src_paper"
    assert {item.dimension for item in assessment.dimensions} == set(QualityDimension)
