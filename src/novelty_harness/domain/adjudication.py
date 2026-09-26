from datetime import date

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import PrecedentState, VerdictState
from novelty_harness.domain.idea import ArtifactProvenance, ClaimedAdvantage
from novelty_harness.domain.ids import AssessmentId, EvidenceEdgeId, MCUId
from novelty_harness.domain.research import CoverageEntry


class MCUFinding(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    precedent_state: PrecedentState
    verdict: VerdictState
    decisive_edges: tuple[EvidenceEdgeId, ...] = ()
    limiting_factors: tuple[str, ...] = ()


class FrozenAdjudication(ContractModel):
    model_config = ConfigDict(frozen=True)
    assessment_id: AssessmentId
    as_of: date
    frozen_at: UTCDateTime
    overall_state: VerdictState
    mcus: tuple[MCUFinding, ...] = ()
    established_findings: tuple[str, ...] = ()
    novelty_candidates: tuple[str, ...] = ()
    strongest_challenges: tuple[str, ...] = ()
    value_findings: tuple[ClaimedAdvantage, ...] = ()
    validation_requirements: tuple[str, ...] = ()
    permitted_language: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    evidence_limitations: tuple[str, ...] = ()
    coverage_matrix: tuple[CoverageEntry, ...] = ()
    provenance: ArtifactProvenance
