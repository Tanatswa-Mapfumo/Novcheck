from typing import Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import IdeaId, MCUId


class MCUFeature(ContractModel):
    model_config = ConfigDict(frozen=True)
    feature_id: NonBlankText
    concept: NonBlankText


class MCURelationship(ContractModel):
    model_config = ConfigDict(frozen=True)
    subject: NonBlankText
    relation: NonBlankText
    object: NonBlankText


class MCU(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    label: NonBlankText
    statement: NonBlankText
    types: tuple[str, ...] = ()
    importance: str | None = None
    purpose: str | None = None
    object_or_target: str | None = None
    mechanism: str | None = None
    intended_effect: str | None = None
    context: str | None = None
    features: tuple[MCUFeature, ...] = ()
    relationships: tuple[MCURelationship, ...] = ()
    provenance: ArtifactProvenance


class MCUCombination(ContractModel):
    model_config = ConfigDict(frozen=True)
    combination_id: NonBlankText
    label: NonBlankText
    statement: NonBlankText
    member_ids: tuple[MCUId, ...] = Field(min_length=2)
    relationships: tuple[MCURelationship, ...] = ()
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def distinct_members(self) -> Self:
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("combination members must be distinct")
        return self


class MCUGraph(ContractModel):
    model_config = ConfigDict(frozen=True)
    idea_id: IdeaId
    mcus: tuple[MCU, ...]
    combinations: tuple[MCUCombination, ...] = ()
    unresolved_disagreements: tuple[str, ...] = ()
    provenance: ArtifactProvenance
