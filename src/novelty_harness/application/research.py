from dataclasses import dataclass
from typing import Protocol

from novelty_harness.domain.evidence import SourcePassage, SourceRecord
from novelty_harness.domain.idea import ArtifactProvenance, CanonicalIdeaRepresentation
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.domain.research import (
    EvidenceFamilyDecision,
    PlannedQuery,
    SearchPlan,
    SearchPlanReview,
)
from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.research.coverage import evaluate_coverage
from novelty_harness.research.critique import SearchPlanCritic
from novelty_harness.research.models import ResearchPlan
from novelty_harness.research.planning import SearchStrategist
from novelty_harness.research.revision import SearchPlanReviser, review_and_revise
from novelty_harness.research.screening import ScreeningExecutor, ScreeningRunResult
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticCallAudit
from novelty_harness.runtime.tracing.hashing import canonical_hash


class DeferredFixtureContinuation(Protocol):
    async def materialize(
        self, screening: ScreeningRunResult, graph: MCUGraph
    ) -> tuple[tuple[SourceRecord, ...], tuple[SourcePassage, ...]]: ...


@dataclass(frozen=True)
class ResearchPreparation:
    plan: ResearchPlan
    legacy_plan: SearchPlan
    legacy_review: SearchPlanReview


class Phase3ResearchComponents:
    def __init__(
        self,
        assessor: EvidenceFamilyApplicabilityAssessor,
        strategist: SearchStrategist,
        critic: SearchPlanCritic,
        reviser: SearchPlanReviser,
        executor: ScreeningExecutor,
        *,
        max_revisions: int = 2,
    ) -> None:
        self.assessor, self.strategist, self.critic, self.reviser = (
            assessor,
            strategist,
            critic,
            reviser,
        )
        self.executor, self.max_revisions = executor, max_revisions
        self._offsets: dict[int, int] = {}

    def drain_research_audits(self) -> tuple[SemanticCallAudit, ...]:
        calls: list[SemanticCallAudit] = []
        for component in (self.assessor, self.strategist, self.critic, self.reviser):
            runner = component.runner
            identity = id(runner)
            calls.extend(runner.audits[self._offsets.get(identity, 0) :])
            self._offsets[identity] = len(runner.audits)
        return tuple(calls)

    async def prepare(
        self,
        *,
        assessment_id: AssessmentId,
        idea: CanonicalIdeaRepresentation,
        graph: MCUGraph,
        writer: RunArtifactWriter,
    ) -> ResearchPreparation:
        applicability = await self.assessor.assess(idea=idea, mcus=graph.mcus)
        writer.write_json(
            assessment_id,
            "phase3/family_applicability.json",
            [a.model_dump(mode="json") for a in applicability],
        )
        plan = await self.strategist.build_plan(
            assessment_id=assessment_id,
            as_of=idea.context.temporal_cutoff,
            idea=idea,
            mcus=graph.mcus,
            combinations=graph.combinations,
            applicability=applicability,
        )
        plan, reviews = await review_and_revise(
            plan=plan,
            idea=idea,
            mcus=graph.mcus,
            critic=self.critic,
            reviser=self.reviser,
            max_revisions=self.max_revisions,
        )
        writer.write_json(assessment_id, "phase3/search_plan.json", plan)
        writer.write_jsonl(assessment_id, "phase3/search_plan_reviews.jsonl", reviews)
        writer.write_json(assessment_id, "phase3/search_plan_review.json", reviews[-1])
        preflight = evaluate_coverage(
            plan,
            self.executor.policy,
            {
                a.evidence_family: tuple(
                    p.descriptor.name
                    for p in self.executor.registry.providers_for(a.evidence_family)
                )
                for a in applicability
            },
        )
        writer.write_json(
            assessment_id,
            "phase3/preflight_coverage.json",
            [c.model_dump(mode="json") for c in preflight],
        )
        if not plan.reviewed:
            raise ValueError("Phase 3 search-plan review blocked; see persisted reviews")
        origin = ArtifactProvenance(
            kind="implemented",
            component="phase3_research",
            detail="Real neutral planning and independent PASS criticism; later semantics deferred",
        )
        legacy = SearchPlan(
            idea_id=idea.idea_id,
            queries=tuple(
                PlannedQuery(
                    query_id=q.query_id,
                    mcu_id=q.mcu_id,
                    family=q.query_family.value,
                    evidence_family=q.evidence_family,
                    text=q.text,
                    rationale=q.rationale,
                    generated_by="search-strategist-v1",
                    filters=q.filters,
                    provenance=origin,
                )
                for q in plan.intents
            ),
            family_decisions=tuple(
                EvidenceFamilyDecision(
                    mcu_id=a.mcu_id,
                    family=a.evidence_family,
                    applicability=a.applicability.value,
                    exclusion_reason=a.exclusion_reason,
                )
                for a in applicability
            ),
            provenance=origin,
        )
        review = SearchPlanReview(
            plan_hash=canonical_hash(legacy), approved=True, provenance=origin
        )
        return ResearchPreparation(plan, legacy, review)
