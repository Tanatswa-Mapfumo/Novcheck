from dataclasses import dataclass
from datetime import date
from typing import cast

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
from novelty_harness.domain.reporting import Phase7FrozenSummary as Phase7FrozenSummary
from novelty_harness.domain.research import CoverageEntry
from novelty_harness.ports.reporting import ReportPorts
from novelty_harness.reporting.models import ReportOptions


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


@dataclass(frozen=True, slots=True)
class ReportCompilationRequest:
    options: ReportOptions
    ports: ReportPorts | None = None
    attempt_token: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.options), ReportOptions):
            raise ValueError("Phase 8 request requires ReportOptions")
        ReportOptions.model_validate_json(self.options.model_dump_json())
        if self.ports is not None and not isinstance(cast(object, self.ports), ReportPorts):
            raise ValueError("Phase 8 request requires ReportPorts")


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
