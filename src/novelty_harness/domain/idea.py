from datetime import date
from typing import Annotated, Literal

from pydantic import ConfigDict, StringConstraints

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import SufficiencyState, ValueMaturity
from novelty_harness.domain.ids import IdeaId, MCUId

NonBlankText = Annotated[str, StringConstraints(pattern=r"\S")]


class ArtifactProvenance(ContractModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["implemented", "fixture", "deferred"]
    component: NonBlankText
    detail: NonBlankText


class ProblemDescription(ContractModel):
    model_config = ConfigDict(frozen=True)
    statement: NonBlankText
    target_users_or_context: str | None = None
    significance_claims: tuple[str, ...] = ()


class IdeaContext(ContractModel):
    model_config = ConfigDict(frozen=True)
    temporal_cutoff: date
    domains: tuple[str, ...] = ()
    application_setting: str | None = None


class ClaimedAdvantage(ContractModel):
    model_config = ConfigDict(frozen=True)
    dimension: NonBlankText
    statement: NonBlankText
    maturity: ValueMaturity = ValueMaturity.CLAIMED


class CanonicalIdeaRepresentation(ContractModel):
    model_config = ConfigDict(frozen=True)
    idea_id: IdeaId
    original_input: NonBlankText
    original_input_ref: NonBlankText
    title: str | None = None
    problem: ProblemDescription
    context: IdeaContext
    mcu_ids: tuple[MCUId, ...] = ()
    combination_ids: tuple[NonBlankText, ...] = ()
    claimed_advantages: tuple[ClaimedAdvantage, ...] = ()
    user_supplied_evidence: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    provenance: ArtifactProvenance


class SufficiencyAssessment(ContractModel):
    model_config = ConfigDict(frozen=True)
    idea_id: IdeaId
    state: SufficiencyState
    assessable_dimensions: tuple[str, ...] = ()
    unassessable_dimensions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    consequences: tuple[str, ...] = ()
    provenance: ArtifactProvenance
