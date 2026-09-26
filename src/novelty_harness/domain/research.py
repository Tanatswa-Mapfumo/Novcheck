from pydantic import ConfigDict, Field, JsonValue

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily, ResearchDepth
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import IdeaId, MCUId, QueryId


class PlannedQuery(ContractModel):
    model_config = ConfigDict(frozen=True)
    query_id: QueryId
    mcu_id: MCUId
    family: NonBlankText
    evidence_family: EvidenceFamily
    text: NonBlankText
    rationale: NonBlankText
    generated_by: NonBlankText
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    provenance: ArtifactProvenance


class EvidenceFamilyDecision(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    family: EvidenceFamily
    applicability: NonBlankText
    exclusion_reason: str | None = None


class SearchPlan(ContractModel):
    model_config = ConfigDict(frozen=True)
    idea_id: IdeaId
    queries: tuple[PlannedQuery, ...] = Field(min_length=1)
    family_decisions: tuple[EvidenceFamilyDecision, ...] = ()
    provenance: ArtifactProvenance


class SearchPlanReview(ContractModel):
    model_config = ConfigDict(frozen=True)
    plan_hash: NonBlankText
    approved: bool
    corrections: tuple[str, ...] = ()
    provenance: ArtifactProvenance


class CoverageEntry(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    family: EvidenceFamily
    applicability: NonBlankText
    depth: ResearchDepth
    provider_names: tuple[str, ...] = ()
    query_ids: tuple[QueryId, ...] = ()
    relevant_hits: int | None = Field(default=None, ge=0)
    limitations: tuple[str, ...] = ()
    provenance: ArtifactProvenance
