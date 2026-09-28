"""Phase 6 mapping contracts.

A mapping is a *proposal*: it states which exact source passages appear to
address which comparison dimensions of an MCU proposition. It never asserts
support, precedent, or novelty.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import (
    MappingId,
    MCUId,
    PassageId,
    PropositionId,
    SourceId,
    SourceVersionId,
)


class ComparisonDimension(StrEnum):
    PURPOSE = "PURPOSE"
    PROBLEM = "PROBLEM"
    TARGET = "TARGET"
    MECHANISM = "MECHANISM"
    ARCHITECTURE = "ARCHITECTURE"
    FEATURES = "FEATURES"
    RELATIONSHIPS = "RELATIONSHIPS"
    CONTROL_FLOW = "CONTROL_FLOW"
    CONTEXT = "CONTEXT"
    INTENDED_OUTCOME = "INTENDED_OUTCOME"
    CONSTRAINTS = "CONSTRAINTS"
    EVALUATION_TARGET = "EVALUATION_TARGET"


#: Dimensions that must carry a directed relationship when mapped.
RELATIONSHIP_DIMENSIONS = frozenset(
    {ComparisonDimension.RELATIONSHIPS, ComparisonDimension.CONTROL_FLOW}
)


class DirectedRelationship(ContractModel):
    """First-class directed relationship or control-flow statement."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["directed-relationship-v1"] = "directed-relationship-v1"

    subject: NonBlankText
    relation: NonBlankText
    object: NonBlankText

    def describe(self) -> str:
        return f"{self.subject} {self.relation} {self.object}"


class MappedStatement(ContractModel):
    """One grounded statement about a dimension, tied to exact passages."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["mapped-statement-v1"] = "mapped-statement-v1"

    dimension: ComparisonDimension
    statement: NonBlankText
    passage_ids: tuple[PassageId, ...] = Field(min_length=1)
    relationship: DirectedRelationship | None = None

    @model_validator(mode="after")
    def relationship_dimensions_require_structure(self) -> Self:
        if self.dimension in RELATIONSHIP_DIMENSIONS and self.relationship is None:
            raise ValueError(f"{self.dimension.value} mappings require a directed relationship")
        return self

    def label(self) -> str:
        return self.relationship.describe() if self.relationship else self.statement


class DimensionMapping(ContractModel):
    """What a source appears to match, miss or conflict with for one dimension."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["dimension-mapping-v1"] = "dimension-mapping-v1"

    dimension: ComparisonDimension
    matching: tuple[MappedStatement, ...] = ()
    missing: tuple[NonBlankText, ...] = ()
    conflicting: tuple[MappedStatement, ...] = ()

    @model_validator(mode="after")
    def nonempty_and_consistent(self) -> Self:
        if not (self.matching or self.missing or self.conflicting):
            raise ValueError("A dimension mapping must state a match, a gap or a conflict")
        if any(item.dimension != self.dimension for item in (*self.matching, *self.conflicting)):
            raise ValueError("Mapped statements must carry their dimension")
        return self


class MappingComparison(ContractModel):
    """Aggregated comparison for one source/MCU mapping (spec section 27)."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["mapping-comparison-v1"] = "mapping-comparison-v1"

    matching_elements: tuple[NonBlankText, ...] = ()
    matching_relationships: tuple[NonBlankText, ...] = ()
    missing_elements: tuple[NonBlankText, ...] = ()
    conflicting_elements: tuple[NonBlankText, ...] = ()


class PropositionCommitment(ContractModel):
    """One material commitment of an MCU proposition.

    Commitments come only from explicitly stated MCU fields; nothing is
    invented for absent dimensions.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["proposition-commitment-v1"] = "proposition-commitment-v1"

    commitment_id: NonBlankText
    dimension: ComparisonDimension
    text: NonBlankText
    relationship: DirectedRelationship | None = None

    @model_validator(mode="after")
    def relationship_dimensions_require_structure(self) -> Self:
        if self.dimension in RELATIONSHIP_DIMENSIONS and self.relationship is None:
            raise ValueError(f"{self.dimension.value} commitment requires a directed relationship")
        return self


class EvidenceProposition(ContractModel):
    """The MCU claim as verifiable material commitments."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-proposition-v1"] = "evidence-proposition-v1"

    proposition_id: PropositionId
    mcu_id: MCUId
    statement: NonBlankText
    commitments: tuple[PropositionCommitment, ...] = Field(min_length=1)
    unknown_dimensions: tuple[ComparisonDimension, ...] = ()
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def unique_commitments(self) -> Self:
        identities = [commitment.commitment_id for commitment in self.commitments]
        if len(set(identities)) != len(identities):
            raise ValueError("Proposition commitments must be unique")
        return self


class SourceMCUMapping(ContractModel):
    """A proposed, unverified source-to-MCU mapping."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["source-mcu-mapping-v1"] = "source-mcu-mapping-v1"

    mapping_id: MappingId
    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    mcu_id: MCUId
    proposition_id: PropositionId
    dimensions: tuple[DimensionMapping, ...] = Field(min_length=1)
    unresolved: tuple[NonBlankText, ...] = ()
    mapper_prompt_version: NonBlankText
    mapper_rubric_version: NonBlankText
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def unique_dimensions(self) -> Self:
        dimensions = [item.dimension for item in self.dimensions]
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("A mapping may state each dimension at most once")
        return self

    def mapped_passage_ids(self) -> tuple[PassageId, ...]:
        return tuple(
            dict.fromkeys(
                passage_id
                for dimension in self.dimensions
                for statement in (*dimension.matching, *dimension.conflicting)
                for passage_id in statement.passage_ids
            )
        )

    def aggregate_comparison(self) -> MappingComparison:
        matching_elements: list[str] = []
        matching_relationships: list[str] = []
        missing_elements: list[str] = []
        conflicting_elements: list[str] = []
        for dimension in self.dimensions:
            for statement in dimension.matching:
                if statement.relationship is not None:
                    matching_relationships.append(statement.relationship.describe())
                else:
                    matching_elements.append(statement.statement)
            for missing in dimension.missing:
                missing_elements.append(f"{dimension.dimension.value}: {missing}")
            for statement in dimension.conflicting:
                conflicting_elements.append(f"{dimension.dimension.value}: {statement.label()}")
        return MappingComparison(
            matching_elements=tuple(dict.fromkeys(matching_elements)),
            matching_relationships=tuple(dict.fromkeys(matching_relationships)),
            missing_elements=tuple(dict.fromkeys(missing_elements)),
            conflicting_elements=tuple(dict.fromkeys(conflicting_elements)),
        )
