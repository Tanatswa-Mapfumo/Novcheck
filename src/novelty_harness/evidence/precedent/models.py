"""Phase 6 precedent-classification contracts.

Every classification is a *local* source/MCU comparison result. The Phase 6
`NO_DIRECT_PRECEDENT_IDENTIFIED` state is not permission for any global absence
claim, and quality is attached metadata that cannot alter the local relation.
"""

from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import EvidenceTier, PrecedentState
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import (
    ClassificationId,
    MappingId,
    MCUId,
    PassageId,
    PatentScreeningId,
    SourceId,
    SourceVersionId,
    VerificationId,
)
from novelty_harness.evidence.mapping.models import ComparisonDimension


class CounterfactualDiagnostic(ContractModel):
    """Diagnostic-only record of removing a differentiating element."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["counterfactual-diagnostic-v1"] = "counterfactual-diagnostic-v1"

    removed_element: NonBlankText
    remaining_distinction: NonBlankText | None = None
    becomes_substantially_equivalent: bool | None = None
    basis: tuple[NonBlankText, ...] = ()
    diagnostic_only: Literal[True] = True


class PrecedentClassification(ContractModel):
    """Local precedent relation for one source/version against one MCU."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["precedent-classification-v1"] = "precedent-classification-v1"

    classification_id: ClassificationId
    source_id: SourceId
    source_version_id: SourceVersionId | None
    mcu_id: MCUId
    mapping_id: MappingId
    verification_id: VerificationId | None
    relation: PrecedentState
    scope: Literal["LOCAL_SOURCE_MCU"] = "LOCAL_SOURCE_MCU"
    global_absence_claim_permitted: Literal[False] = False
    single_source: Literal[True] = True
    decisive: bool = False
    basis: tuple[NonBlankText, ...] = Field(min_length=1)
    covered_elements: tuple[NonBlankText, ...] = ()
    covered_relationships: tuple[NonBlankText, ...] = ()
    missing_elements: tuple[NonBlankText, ...] = ()
    missing_relationships: tuple[NonBlankText, ...] = ()
    configuration_gap: NonBlankText | None = None
    functional_similarity: tuple[ComparisonDimension, ...] = ()
    contradictions: tuple[NonBlankText, ...] = ()
    unresolved: tuple[NonBlankText, ...] = ()
    unassessable_reason: NonBlankText | None = None
    counterfactual: CounterfactualDiagnostic | None = None
    quality_tier: EvidenceTier | None = None
    classifier_version: NonBlankText
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def relation_matches_payload(self) -> Self:
        if self.relation == PrecedentState.DIRECT_PRECEDENT:
            if not self.single_source or not self.decisive:
                raise ValueError("Direct precedent must be decisive and single-source")
            if self.missing_elements or self.missing_relationships or self.configuration_gap:
                raise ValueError("Direct precedent cannot have missing material elements")
        elif self.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT:
            if not (self.missing_elements or self.missing_relationships or self.configuration_gap):
                raise ValueError("Strong partial precedent must identify its material gap")
        elif self.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY:
            if not (self.configuration_gap or self.missing_relationships):
                raise ValueError("Component precedent must identify the missing configuration")
        elif self.relation == PrecedentState.ANALOGOUS_PRECEDENT:
            if not self.functional_similarity:
                raise ValueError("Analogy must record the functional principle it shares")
            if not (self.missing_elements or self.missing_relationships or self.configuration_gap):
                raise ValueError("Analogy must record a material mechanism/relationship gap")
        elif self.relation == PrecedentState.CONTRADICTORY_EVIDENCE:
            if not self.contradictions:
                raise ValueError("Contradictory evidence must record the contradiction")
        elif self.relation == PrecedentState.UNRESOLVED:
            if not self.unresolved:
                raise ValueError("Unresolved classification must state the ambiguity")
        elif self.relation == PrecedentState.UNASSESSABLE:
            if self.unassessable_reason is None:
                raise ValueError("Unassessable classification must state why")
        if self.unassessable_reason is not None and self.relation != PrecedentState.UNASSESSABLE:
            raise ValueError("Only UNASSESSABLE classifications carry an unassessable reason")
        return self


class PatentScreeningDateRecord(ContractModel):
    """Priority and publication chronology kept separate for one reference."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["patent-screening-date-v1"] = "patent-screening-date-v1"

    source_id: SourceId
    priority_date: date | None = None
    publication_date: date | None = None


class PatentScreeningLocator(ContractModel):
    """Claim/specification locator retained for a patent reference."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["patent-screening-locator-v1"] = "patent-screening-locator-v1"

    source_id: SourceId
    passage_id: PassageId
    locator: NonBlankText
    section: Literal["CLAIMS", "SPECIFICATION", "OTHER"]


class PatentScreeningResult(ContractModel):
    """One-reference anticipation-like screening versus multi-reference context.

    Screening only; never a legal patentability determination.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["patent-screening-result-v1"] = "patent-screening-result-v1"

    screening_id: PatentScreeningId
    mcu_id: MCUId
    mode: Literal[
        "SINGLE_REFERENCE_ANTICIPATION_LIKE",
        "MULTI_REFERENCE_COMBINATION_LIKE",
        "LIMITED",
        "UNASSESSABLE",
    ]
    single_reference_id: SourceId | None = None
    reference_source_ids: tuple[SourceId, ...] = ()
    covered_elements: tuple[NonBlankText, ...] = ()
    covered_relationships: tuple[NonBlankText, ...] = ()
    missing_elements: tuple[NonBlankText, ...] = ()
    missing_relationships: tuple[NonBlankText, ...] = ()
    dates: tuple[PatentScreeningDateRecord, ...] = ()
    locators: tuple[PatentScreeningLocator, ...] = ()
    limitations: tuple[NonBlankText, ...] = ()
    disclaimer: Literal["patent-screening-not-legal-advice-v1"] = (
        "patent-screening-not-legal-advice-v1"
    )
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def mode_matches_references(self) -> Self:
        references = set(self.reference_source_ids)
        if self.single_reference_id is not None:
            if references != {self.single_reference_id}:
                raise ValueError("Single-reference mode requires exactly that one reference")
        if self.mode == "SINGLE_REFERENCE_ANTICIPATION_LIKE":
            if self.single_reference_id is None or len(self.reference_source_ids) != 1:
                raise ValueError("Anticipation-like screening requires exactly one reference")
            if self.missing_elements or self.missing_relationships:
                raise ValueError("Anticipation-like screening cannot have material gaps")
        elif self.mode == "MULTI_REFERENCE_COMBINATION_LIKE":
            if self.single_reference_id is not None or len(self.reference_source_ids) < 2:
                raise ValueError(
                    "Multi-reference combination context requires at least two references "
                    "and no single-reference claim"
                )
        return self
