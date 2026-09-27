from collections.abc import Sequence
from datetime import date
from typing import Literal

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.ports.models import ContextBlock
from novelty_harness.research.models import (
    EvidenceFamilyAssessment,
    FamilyApplicability,
    QueryOmission,
    ResearchPlan,
    SearchIntent,
)
from novelty_harness.research.prompts import STRATEGIST, STRATEGIST_VERSION
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.research.query_validation import distinct_query_texts, terms_add_perspective
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec
from novelty_harness.runtime.tracing.hashing import canonical_json


class PlanProposal(ContractModel):
    prompt_version: Literal["search-strategist-v1"]
    intents: tuple[SearchIntent, ...]
    omissions: tuple[QueryOmission, ...]


def validate_strategy(plan: ResearchPlan, idea: CanonicalIdeaRepresentation) -> None:
    for branch in plan.family_assessments:
        if branch.applicability == FamilyApplicability.NOT_APPLICABLE:
            continue
        queries = [
            q
            for q in plan.intents
            if (q.mcu_id, q.evidence_family) == (branch.mcu_id, branch.evidence_family)
        ]
        omissions = [
            o
            for o in plan.omissions
            if (o.mcu_id, o.evidence_family) == (branch.mcu_id, branch.evidence_family)
        ]
        queried = {q.query_family for q in queries}
        omitted = {o.query_family for o in omissions}
        if (
            len(queried) < 2
            or len(distinct_query_texts(queries)) < 2
            or queried & omitted
            or queried | omitted != set(QueryFamily)
        ):
            raise ValueError("every plausible branch needs diverse queries and explicit omissions")
        if len(omitted) != len(omissions):
            raise ValueError("duplicate query-family omission")
    for q in plan.intents:
        canonical = [
            c
            for c in plan.intents
            if c.query_family == QueryFamily.DIRECT_CANONICAL
            and (c.mcu_id, c.evidence_family) == (q.mcu_id, q.evidence_family)
        ]
        if q.query_family == QueryFamily.RELATIONSHIP and not terms_add_perspective(q, canonical):
            raise ValueError("relationship search must include the relation, not only nouns")
        if q.query_family == QueryFamily.HISTORICAL_TERMINOLOGY and not terms_add_perspective(
            q, canonical
        ):
            raise ValueError("historical queries require changed terminology")
        if q.query_family == QueryFamily.COMBINATION and q.combination_id is None:
            raise ValueError("combination queries require a separate combination reference")
        if q.filters and not all(str(v) in idea.constraints for v in q.filters.values()):
            raise ValueError("filters need explicit CIR constraints; cutoff belongs to compilation")


class SearchStrategist:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def build_plan(
        self,
        *,
        assessment_id: AssessmentId,
        as_of: date,
        idea: CanonicalIdeaRepresentation,
        mcus: Sequence[MCU],
        combinations: Sequence[MCUCombination],
        applicability: Sequence[EvidenceFamilyAssessment],
    ) -> ResearchPlan:
        context = planning_context(idea, mcus, combinations, applicability)
        proposal = await self.runner.run(
            SemanticTaskSpec("plan_research", STRATEGIST_VERSION, PlanProposal), STRATEGIST, context
        )
        plan = ResearchPlan(
            assessment_id=assessment_id,
            as_of=as_of,
            mcu_ids=tuple(m.mcu_id for m in mcus),
            combination_ids=tuple(c.combination_id for c in combinations),
            family_assessments=tuple(applicability),
            intents=proposal.intents,
            omissions=proposal.omissions,
        )
        validate_strategy(plan, idea)
        return plan


def planning_context(
    idea: CanonicalIdeaRepresentation,
    mcus: Sequence[MCU],
    combinations: Sequence[MCUCombination],
    applicability: Sequence[EvidenceFamilyAssessment],
) -> list[ContextBlock]:
    return [
        ContextBlock(label="idea", text=idea.model_dump_json()),
        ContextBlock(label="mcus", text=canonical_json([m.model_dump(mode="json") for m in mcus])),
        ContextBlock(
            label="combinations",
            text=canonical_json([c.model_dump(mode="json") for c in combinations]),
        ),
        ContextBlock(
            label="applicability",
            text=canonical_json([a.model_dump(mode="json") for a in applicability]),
        ),
    ]
