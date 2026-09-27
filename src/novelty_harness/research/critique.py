from collections.abc import Sequence
from datetime import date
from typing import Literal

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.domain.mcu import MCU
from novelty_harness.ports.models import ContextBlock
from novelty_harness.research.models import (
    EvidenceFamilyAssessment,
    FamilyApplicability,
    ResearchPlan,
    SearchPlanIssue,
    SearchPlanReview,
)
from novelty_harness.research.models import (
    SearchPlanIssueCategory as Category,
)
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

CRITIC_VERSION = "search-critic-v1"
CRITIC = """Independently critique this persisted plan using every checklist category.
Examine translation, concepts, synonyms/acronyms/spelling, functional/mechanistic coverage,
relationships, historical terminology, adjacent disciplines, overly broad/narrow terms,
Boolean/proximity assumptions and syntax, date/language/filter overrestriction, family omissions,
and overreliance on user terminology (including renamed established concepts).
Record structured issues and actionable corrections. Do not reason about novelty.
You receive no strategist private context or call history."""


class CriticProposal(ContractModel):
    prompt_version: Literal["search-critic-v1"]
    status: Literal["PASS", "REVISE", "BLOCKED"]
    issues: tuple[SearchPlanIssue, ...]
    checked_categories: tuple[Category, ...]


def deterministic_issues(
    plan: ResearchPlan,
    idea: CanonicalIdeaRepresentation,
    mcus: Sequence[MCU],
    applicability: Sequence[EvidenceFamilyAssessment],
) -> list[SearchPlanIssue]:
    issues: list[SearchPlanIssue] = []

    def add(
        category: Category,
        explanation: str,
        mcu: MCU | None = None,
        family: EvidenceFamily | None = None,
    ) -> None:
        issues.append(
            SearchPlanIssue(
                issue_id=f"guard_{len(issues)}",
                category=category,
                severity="MATERIAL",
                mcu_id=mcu.mcu_id if mcu else None,
                evidence_family=family,
                explanation=explanation,
                required_correction=explanation,
            )
        )

    expected = {(m.mcu_id, f) for m in mcus for f in EvidenceFamily}
    actual = {(a.mcu_id, a.evidence_family) for a in applicability}
    if actual != expected or len(actual) != len(applicability):
        add(Category.FAMILY_OMISSION, "Assess every evidence family per MCU")
    if tuple(applicability) != plan.family_assessments:
        add(Category.FAMILY_OMISSION, "Plan applicability must match the assessed matrix")
    for mcu in mcus:
        for a in applicability:
            if a.mcu_id != mcu.mcu_id or a.applicability == FamilyApplicability.NOT_APPLICABLE:
                continue
            queries = [
                q
                for q in plan.intents
                if (q.mcu_id, q.evidence_family) == (a.mcu_id, a.evidence_family)
            ]
            families = {q.query_family for q in queries}
            omitted = {
                o.query_family
                for o in plan.omissions
                if (o.mcu_id, o.evidence_family) == (a.mcu_id, a.evidence_family)
            }
            if not queries:
                add(
                    Category.FAMILY_OMISSION,
                    "Search this plausible evidence branch",
                    mcu,
                    a.evidence_family,
                )
            if len(families) < 2 or families | omitted != set(QueryFamily):
                add(
                    Category.QUERY_FAMILY_GAP,
                    "Diversify queries and explain omissions",
                    mcu,
                    a.evidence_family,
                )
            if mcu.relationships and not any(
                q.query_family == QueryFamily.RELATIONSHIP
                and q.relationship_terms
                and all(t.casefold() in q.text.casefold() for t in q.relationship_terms)
                for q in queries
            ):
                add(
                    Category.RELATIONSHIP_GAP,
                    "Search contribution-bearing relationships",
                    mcu,
                    a.evidence_family,
                )
    for q in plan.intents:
        for key, value in q.filters.items():
            invalid = str(value) not in idea.constraints
            if key in {"to_date", "from_date"}:
                try:
                    invalid |= date.fromisoformat(str(value)) > plan.as_of
                except ValueError:
                    invalid = True
            if invalid:
                add(Category.LIMIT_OR_FILTER, "Remove or justify restrictive filters")
    return issues


class SearchPlanCritic:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def review(
        self,
        *,
        idea: CanonicalIdeaRepresentation,
        mcus: Sequence[MCU],
        applicability: Sequence[EvidenceFamilyAssessment],
        plan: ResearchPlan,
    ) -> SearchPlanReview:
        proposal = await self.runner.run(
            SemanticTaskSpec("criticize_search", CRITIC_VERSION, CriticProposal),
            CRITIC,
            [
                ContextBlock(label="idea", text=idea.model_dump_json()),
                ContextBlock(
                    label="mcus", text=canonical_json([m.model_dump(mode="json") for m in mcus])
                ),
                ContextBlock(
                    label="applicability",
                    text=canonical_json([a.model_dump(mode="json") for a in applicability]),
                ),
                ContextBlock(label="plan", text=plan.model_dump_json()),
            ],
        )
        if set(proposal.checked_categories) != set(Category) or len(
            proposal.checked_categories
        ) != len(Category):
            raise ValueError("critic must examine the complete checklist")
        known_queries = {q.query_id for q in plan.intents}
        for issue in proposal.issues:
            if (
                issue.mcu_id is not None
                and issue.mcu_id not in plan.mcu_ids
                or issue.evidence_family is not None
                and issue.evidence_family not in EvidenceFamily
                or not set(issue.query_ids) <= known_queries
            ):
                raise ValueError("critic issue has unknown references")
        issues = (*proposal.issues, *deterministic_issues(plan, idea, mcus, applicability))
        status = proposal.status
        if status == "PASS" and any(i.severity == "MATERIAL" for i in issues):
            status = "REVISE"
        return SearchPlanReview(
            review_id="review_"
            + canonical_hash(
                [plan.content_hash(), [i.model_dump(mode="json") for i in issues], status]
            ),
            plan_hash=plan.content_hash(),
            status=status,
            issues=issues,
            critic_prompt_version=CRITIC_VERSION,
        )


def bind_review(plan: ResearchPlan, review: SearchPlanReview) -> ResearchPlan:
    if review.status != "PASS":
        raise ValueError("only PASS can authorize screening")
    return ResearchPlan.model_validate(
        {**plan.model_dump(), "reviewed": True, "review_id": review.review_id, "review": review}
    )
