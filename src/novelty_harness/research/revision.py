from collections.abc import Sequence
from typing import Literal

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.domain.mcu import MCU
from novelty_harness.ports.models import ContextBlock
from novelty_harness.research.critique import SearchPlanCritic, bind_review
from novelty_harness.research.models import (
    QueryOmission,
    ResearchPlan,
    SearchIntent,
    SearchPlanReview,
)
from novelty_harness.research.planning import validate_strategy
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec


class RevisionProposal(ContractModel):
    prompt_version: Literal["search-reviser-v1"]
    intents: tuple[SearchIntent, ...]
    omissions: tuple[QueryOmission, ...]


class SearchPlanReviser:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def revise(
        self, *, idea: CanonicalIdeaRepresentation, plan: ResearchPlan, review: SearchPlanReview
    ) -> ResearchPlan:
        if review.plan_hash != plan.content_hash() or review.status != "REVISE":
            raise ValueError("revision requires this plan's REVISE review")
        proposal = await self.runner.run(
            SemanticTaskSpec("revise_search", "search-reviser-v1", RevisionProposal),
            "Apply the structured corrections. Preserve neutral intent and applicability. "
            "Return corrected intents and explicit omissions, not an approval.",
            [
                ContextBlock(label="idea", text=idea.model_dump_json()),
                ContextBlock(label="plan", text=plan.model_dump_json()),
                ContextBlock(label="review", text=review.model_dump_json()),
            ],
        )
        revised = ResearchPlan.model_validate(
            {
                **plan.model_dump(),
                "intents": proposal.intents,
                "omissions": proposal.omissions,
                "reviewed": False,
                "review_id": None,
                "review": None,
            }
        )
        validate_strategy(revised, idea)
        return revised


async def review_and_revise(
    *,
    plan: ResearchPlan,
    idea: CanonicalIdeaRepresentation,
    mcus: Sequence[MCU],
    critic: SearchPlanCritic,
    reviser: SearchPlanReviser,
    max_revisions: int = 2,
) -> tuple[ResearchPlan, tuple[SearchPlanReview, ...]]:
    if max_revisions < 0:
        raise ValueError("revision limit must be nonnegative")
    reviews: list[SearchPlanReview] = []
    for attempt in range(max_revisions + 1):
        review = await critic.review(
            idea=idea, mcus=mcus, applicability=plan.family_assessments, plan=plan
        )
        reviews.append(review)
        if review.status == "PASS":
            return bind_review(plan, review), tuple(reviews)
        if review.status == "BLOCKED" or attempt == max_revisions:
            reviews[-1] = SearchPlanReview.model_validate(
                {**review.model_dump(), "status": "BLOCKED"}
            )
            return plan, tuple(reviews)
        plan = await reviser.revise(idea=idea, plan=plan, review=review)
    raise AssertionError("bounded review loop must return")
