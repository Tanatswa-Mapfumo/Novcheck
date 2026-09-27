"""Deterministic evidentiary-quality assessment.

Quality is computed from explicit signals plus access state, lineage position
and source dates. Semantic relevance is not an input and can never raise a
quality tier; source type alone never decides the tier either. Missing signals
stay ``UNKNOWN`` and produce conservative tiers.
"""

from collections.abc import Sequence

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.enums import EvidenceTier
from novelty_harness.domain.ids import MCUId, SourceId
from novelty_harness.evidence.normalization.models import (
    SourceAccessState,
    SourceRecord,
)
from novelty_harness.evidence.quality.models import (
    AssessmentLevel,
    DimensionAssessment,
    EvidenceQualityAssessment,
    EvidenceQualitySignals,
    QualityDimension,
    SourceRelevanceAssessment,
)

_LEVEL_ORDER = {
    AssessmentLevel.UNKNOWN: 0,
    AssessmentLevel.LOW: 1,
    AssessmentLevel.MEDIUM: 2,
    AssessmentLevel.HIGH: 3,
}

_TIER_ORDER = (EvidenceTier.D, EvidenceTier.C, EvidenceTier.B, EvidenceTier.A)


def _worse(left: EvidenceTier, right: EvidenceTier) -> EvidenceTier:
    return left if _TIER_ORDER.index(left) <= _TIER_ORDER.index(right) else right


def _cap(level: AssessmentLevel, ceiling: AssessmentLevel) -> AssessmentLevel:
    return level if _LEVEL_ORDER[level] <= _LEVEL_ORDER[ceiling] else ceiling


def _primaryness(signals: EvidenceQualitySignals) -> tuple[AssessmentLevel, str]:
    if signals.primary_artifact or signals.first_party:
        return AssessmentLevel.HIGH, "First-party or primary-artifact signal"
    if signals.peer_reviewed or signals.official:
        return AssessmentLevel.MEDIUM, "Peer-reviewed or official but not first-party primary"
    if signals.secondary_analysis:
        return AssessmentLevel.LOW, "Reputable secondary analysis"
    return AssessmentLevel.UNKNOWN, "No primaryness signal supplied"


def _specificity(
    signals: EvidenceQualitySignals, source: SourceRecord
) -> tuple[AssessmentLevel, str]:
    level = signals.technical_specificity
    if source.access_state == SourceAccessState.METADATA_ONLY:
        capped = _cap(level, AssessmentLevel.LOW)
        if capped != level:
            return capped, "Metadata-only access prevents specificity assessment"
    return level, f"Caller-supplied technical specificity: {level.value}"


def _authenticity(signals: EvidenceQualitySignals) -> tuple[AssessmentLevel, str]:
    level = signals.provenance_authenticity
    if signals.discovery_snippet or signals.promotional:
        return _cap(level, AssessmentLevel.LOW), "Promotional/snippet provenance caps authenticity"
    return level, f"Caller-supplied provenance authenticity: {level.value}"


def _date_certainty(
    signals: EvidenceQualitySignals, source: SourceRecord
) -> tuple[AssessmentLevel, str]:
    level = signals.date_certainty
    has_dates = any(
        value is not None
        for value in (
            source.dates.publication_date,
            source.dates.first_public_version,
            source.dates.repository_created_at,
            source.dates.first_release_date,
            source.dates.patent_priority_date,
            source.dates.patent_publication_date,
            source.dates.product_launch_date,
            source.dates.archive_capture_date,
        )
    )
    if level == AssessmentLevel.UNKNOWN and not has_dates:
        return AssessmentLevel.LOW, "No usable date metadata"
    return level, f"Caller-supplied date certainty: {level.value}"


def _independence(is_lineage_root: bool | None) -> tuple[AssessmentLevel, str]:
    if is_lineage_root is True:
        return AssessmentLevel.HIGH, "Independent lineage root"
    if is_lineage_root is False:
        return AssessmentLevel.LOW, "Derived from another source in the same lineage"
    return AssessmentLevel.UNKNOWN, "Lineage position not supplied"


def _completeness(source: SourceRecord) -> tuple[AssessmentLevel, str]:
    return {
        SourceAccessState.FULL_TEXT: (AssessmentLevel.HIGH, "Full text resolved"),
        SourceAccessState.ABSTRACT_ONLY: (
            AssessmentLevel.MEDIUM,
            "Abstract-only access; full text unavailable",
        ),
        SourceAccessState.METADATA_ONLY: (
            AssessmentLevel.LOW,
            "Metadata-only; no content resolved",
        ),
        SourceAccessState.BLOCKED: (AssessmentLevel.LOW, "Content access blocked"),
    }[source.access_state]


def _reproducibility(
    signals: EvidenceQualitySignals, source: SourceRecord
) -> tuple[AssessmentLevel, str]:
    if (
        signals.reproducibility == AssessmentLevel.UNKNOWN
        and signals.primary_artifact
        and source.access_state == SourceAccessState.FULL_TEXT
    ):
        return AssessmentLevel.MEDIUM, "Primary artifact is inspectable"
    return (
        signals.reproducibility,
        f"Caller-supplied reproducibility: {signals.reproducibility.value}",
    )


def assess_quality(
    source: SourceRecord,
    *,
    assessed_at: UTCDateTime,
    signals: EvidenceQualitySignals | None = None,
    is_lineage_root: bool | None = None,
) -> EvidenceQualityAssessment:
    """Assess evidentiary quality. Relevance is deliberately not an input."""

    resolved_signals = signals or EvidenceQualitySignals()
    primaryness, primaryness_reason = _primaryness(resolved_signals)
    specificity, specificity_reason = _specificity(resolved_signals, source)
    authenticity, authenticity_reason = _authenticity(resolved_signals)
    date_certainty, date_reason = _date_certainty(resolved_signals, source)
    independence, independence_reason = _independence(is_lineage_root)
    completeness, completeness_reason = _completeness(source)
    reproducibility, reproducibility_reason = _reproducibility(resolved_signals, source)

    base = {
        AssessmentLevel.HIGH: EvidenceTier.A,
        AssessmentLevel.MEDIUM: EvidenceTier.B,
        AssessmentLevel.LOW: EvidenceTier.C,
        AssessmentLevel.UNKNOWN: EvidenceTier.D,
    }[primaryness]
    limitations: list[str] = []

    if specificity in {AssessmentLevel.LOW, AssessmentLevel.UNKNOWN}:
        base = _worse(base, EvidenceTier.B)
        limitations.append("Technical specificity below Tier A")
    if source.access_state != SourceAccessState.FULL_TEXT:
        base = _worse(base, EvidenceTier.B)
        limitations.append("Full text not available")
    if source.access_state == SourceAccessState.BLOCKED:
        base = _worse(base, EvidenceTier.C)
    if source.access_state == SourceAccessState.METADATA_ONLY:
        base = EvidenceTier.D
        limitations.append("Metadata-only source is discovery-only evidence")
    if resolved_signals.discovery_snippet:
        base = EvidenceTier.D
        limitations.append("Search snippet is discovery-only evidence")
    if resolved_signals.promotional or resolved_signals.news_or_aggregator:
        base = _worse(base, EvidenceTier.C)
        if specificity != AssessmentLevel.HIGH:
            base = EvidenceTier.D
        limitations.append("Promotional/news material cannot be decisive evidence")
    if authenticity == AssessmentLevel.LOW:
        base = _worse(base, EvidenceTier.C)
        limitations.append("Provenance authenticity is low")
    if date_certainty in {AssessmentLevel.UNKNOWN, AssessmentLevel.LOW}:
        limitations.append("Chronology remains uncertain; tier is not raised or lowered for it")

    dimensions = (
        DimensionAssessment(
            dimension=QualityDimension.PRIMARYNESS_DIRECTNESS,
            level=primaryness,
            rationale=primaryness_reason,
        ),
        DimensionAssessment(
            dimension=QualityDimension.TECHNICAL_SPECIFICITY,
            level=specificity,
            rationale=specificity_reason,
        ),
        DimensionAssessment(
            dimension=QualityDimension.PROVENANCE_AUTHENTICITY,
            level=authenticity,
            rationale=authenticity_reason,
        ),
        DimensionAssessment(
            dimension=QualityDimension.DATE_CERTAINTY,
            level=date_certainty,
            rationale=date_reason,
        ),
        DimensionAssessment(
            dimension=QualityDimension.INDEPENDENCE,
            level=independence,
            rationale=independence_reason,
        ),
        DimensionAssessment(
            dimension=QualityDimension.COMPLETENESS_ACCESS,
            level=completeness,
            rationale=completeness_reason,
        ),
        DimensionAssessment(
            dimension=QualityDimension.REPRODUCIBILITY_VERIFIABILITY,
            level=reproducibility,
            rationale=reproducibility_reason,
        ),
    )
    return EvidenceQualityAssessment(
        source_id=source.source_id,
        tier=base,
        dimensions=dimensions,
        limitations=tuple(dict.fromkeys(limitations)),
        basis=(
            f"source_type:{source.source_type.value}",
            f"access_state:{source.access_state.value}",
            "quality-only; relevance is a separate assessment",
        ),
        assessed_at=assessed_at,
    )


def unassessed_relevance(
    source_id: SourceId,
    *,
    assessed_at: UTCDateTime,
    mcu_id: MCUId | None = None,
    basis: Sequence[str] = (),
) -> SourceRelevanceAssessment:
    """Explicit relevance placeholder that cannot influence quality."""

    return SourceRelevanceAssessment(
        source_id=source_id,
        mcu_id=mcu_id,
        relevance=AssessmentLevel.UNKNOWN,
        basis=tuple(
            dict.fromkeys(
                (
                    "Phase 5 does not verify semantic relevance; retrieval rank is a "
                    "discovery proxy only",
                    *basis,
                )
            )
        ),
        limitations=("No Phase 5 relevance verdict; Phase 6 performs supported mapping",),
        assessed_at=assessed_at,
    )
