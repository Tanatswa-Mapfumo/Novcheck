from dataclasses import dataclass
from datetime import date

from pydantic import ConfigDict

from novelty_harness.application.ports import (
    AdjudicationEngine,
    EvidenceMapper,
    EvidenceVerifier,
    IdeaNormalizer,
    MCUDecomposer,
    MCUReconciler,
    SearchPlanner,
    SearchPlanReviewer,
    SufficiencyAnalyzer,
)
from novelty_harness.domain.adjudication import MCUFinding
from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import (
    AssessmentStage,
    AssessmentStatus,
    SufficiencyState,
    VerdictState,
)
from novelty_harness.domain.idea import ArtifactProvenance, ClaimedAdvantage, NonBlankText
from novelty_harness.domain.ids import AssessmentId, SourceId
from novelty_harness.domain.research import CoverageEntry


@dataclass(frozen=True, slots=True)
class VerticalSliceComponents:
    normalizer: IdeaNormalizer
    sufficiency_analyzer: SufficiencyAnalyzer
    decomposer: MCUDecomposer
    reconciler: MCUReconciler
    planner: SearchPlanner
    plan_reviewer: SearchPlanReviewer
    mapper: EvidenceMapper
    verifier: EvidenceVerifier
    adjudicator: AdjudicationEngine


class AssessmentSummary(ContractModel):
    model_config = ConfigDict(frozen=True)
    id: AssessmentId
    as_of: date
    stage: AssessmentStage
    status: AssessmentStatus
    input_sufficiency: SufficiencyState
    overall_verdict: VerdictState
    mcu_findings: tuple[MCUFinding, ...]
    closest_precedents: tuple[SourceId, ...]
    value_findings: tuple[ClaimedAdvantage, ...]
    evidence_limitations: tuple[str, ...]
    coverage_matrix: tuple[CoverageEntry, ...]
    trace_ref: NonBlankText
    provenance: ArtifactProvenance
