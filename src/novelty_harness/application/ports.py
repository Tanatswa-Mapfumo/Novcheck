from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable

from novelty_harness.domain.adjudication import FrozenAdjudication
from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.domain.evidence import EvidenceEdge, SourcePassage, SourceRecord
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, SufficiencyAssessment
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCU, MCUGraph
from novelty_harness.domain.research import SearchPlan, SearchPlanReview


@runtime_checkable
class IdeaNormalizer(Protocol):
    async def normalize(self, request: AssessmentRequest) -> CanonicalIdeaRepresentation: ...


@runtime_checkable
class SufficiencyAnalyzer(Protocol):
    async def analyze(self, idea: CanonicalIdeaRepresentation) -> SufficiencyAssessment: ...


@runtime_checkable
class MCUDecomposer(Protocol):
    async def decompose(self, idea: CanonicalIdeaRepresentation) -> tuple[MCU, ...]: ...


@runtime_checkable
class MCUReconciler(Protocol):
    async def reconcile(
        self, idea: CanonicalIdeaRepresentation, candidates: Sequence[MCU]
    ) -> MCUGraph: ...


@runtime_checkable
class SearchPlanner(Protocol):
    async def plan(self, idea: CanonicalIdeaRepresentation, graph: MCUGraph) -> SearchPlan: ...


@runtime_checkable
class SearchPlanReviewer(Protocol):
    async def review(self, plan: SearchPlan) -> SearchPlanReview: ...


@runtime_checkable
class EvidenceMapper(Protocol):
    async def map(
        self,
        mcus: Sequence[MCU],
        sources: Sequence[SourceRecord],
        passages: Sequence[SourcePassage],
    ) -> tuple[EvidenceEdge, ...]: ...


@runtime_checkable
class EvidenceVerifier(Protocol):
    async def verify(
        self,
        edge: EvidenceEdge,
        mcus: Sequence[MCU],
        sources: Sequence[SourceRecord],
        passages: Sequence[SourcePassage],
    ) -> EvidenceEdge: ...


@runtime_checkable
class AdjudicationEngine(Protocol):
    async def adjudicate(
        self,
        *,
        assessment_id: AssessmentId,
        as_of: date,
        idea: CanonicalIdeaRepresentation,
        sufficiency: SufficiencyAssessment,
        mcus: Sequence[MCU],
        edges: Sequence[EvidenceEdge],
    ) -> FrozenAdjudication: ...
