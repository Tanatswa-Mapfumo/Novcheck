from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import EvidenceTier
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId, SourceId


class AssessmentLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class QualityDimension(StrEnum):
    PRIMARYNESS_DIRECTNESS = "PRIMARYNESS_DIRECTNESS"
    TECHNICAL_SPECIFICITY = "TECHNICAL_SPECIFICITY"
    PROVENANCE_AUTHENTICITY = "PROVENANCE_AUTHENTICITY"
    DATE_CERTAINTY = "DATE_CERTAINTY"
    INDEPENDENCE = "INDEPENDENCE"
    COMPLETENESS_ACCESS = "COMPLETENESS_ACCESS"
    REPRODUCIBILITY_VERIFIABILITY = "REPRODUCIBILITY_VERIFIABILITY"


class DimensionAssessment(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["quality-dimension-assessment-v1"] = "quality-dimension-assessment-v1"

    dimension: QualityDimension
    level: AssessmentLevel
    rationale: NonBlankText


class EvidenceQualitySignals(ContractModel):
    """Explicit, caller-supplied signals about a source.

    Signals are never inferred from semantic similarity, and the source type
    alone never decides the tier. Missing signals stay ``UNKNOWN``.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-quality-signals-v1"] = "evidence-quality-signals-v1"

    first_party: bool = False
    primary_artifact: bool = False
    peer_reviewed: bool = False
    official: bool = False
    secondary_analysis: bool = False
    promotional: bool = False
    news_or_aggregator: bool = False
    discovery_snippet: bool = False
    technical_specificity: AssessmentLevel = AssessmentLevel.UNKNOWN
    date_certainty: AssessmentLevel = AssessmentLevel.UNKNOWN
    provenance_authenticity: AssessmentLevel = AssessmentLevel.UNKNOWN
    reproducibility: AssessmentLevel = AssessmentLevel.UNKNOWN

    @model_validator(mode="after")
    def mutually_exclusive_roles(self) -> Self:
        roles = (
            self.promotional,
            self.news_or_aggregator,
            self.discovery_snippet,
        )
        if sum(roles) > 1:
            raise ValueError("Promotional, news/aggregator and snippet roles are exclusive")
        return self


class EvidenceQualityAssessment(ContractModel):
    """Evidentiary quality only; relevance lives in a separate contract."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-quality-v1"] = "evidence-quality-v1"

    source_id: SourceId
    tier: EvidenceTier
    dimensions: tuple[DimensionAssessment, ...]
    limitations: tuple[NonBlankText, ...] = ()
    basis: tuple[NonBlankText, ...] = ()
    assessed_at: UTCDateTime

    @model_validator(mode="after")
    def all_dimensions_once(self) -> Self:
        seen = [assessment.dimension for assessment in self.dimensions]
        if sorted(seen, key=lambda d: d.value) != sorted(QualityDimension, key=lambda d: d.value):
            raise ValueError("Quality assessment must rate every dimension exactly once")
        if len(set(seen)) != len(seen):
            raise ValueError("Quality dimensions must be unique")
        return self


class SourceRelevanceAssessment(ContractModel):
    """Relevance, deliberately unable to carry a quality tier."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["source-relevance-v1"] = "source-relevance-v1"

    source_id: SourceId
    mcu_id: MCUId | None = None
    relevance: AssessmentLevel
    basis: tuple[NonBlankText, ...] = ()
    limitations: tuple[NonBlankText, ...] = ()
    assessed_at: UTCDateTime
