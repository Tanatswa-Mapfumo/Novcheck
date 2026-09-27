import pytest

from novelty_harness.research.critique import SearchPlanCritic, bind_review
from novelty_harness.research.revision import SearchPlanReviser, review_and_revise
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM
from tests.fixtures.phase3 import planning_response
from tests.unit.research.test_strategist import build


def critic_response():
    from novelty_harness.research.models import SearchPlanIssueCategory

    return {
        "prompt_version": "search-critic-v1",
        "status": "PASS",
        "issues": [],
        "checked_categories": [c.value for c in SearchPlanIssueCategory],
    }


async def critique(plan, data=None):
    provider = RecordedLLM({"criticize_search": data or critic_response()})
    critic = SearchPlanCritic(SemanticRunner(provider))
    fixture = make_fixture()
    return await critic.review(
        idea=fixture.idea, mcus=fixture.graph.mcus, applicability=plan.family_assessments, plan=plan
    ), provider


async def test_pass_review_is_bound_and_critic_context_is_independent():
    plan, _ = await build()
    review, provider = await critique(plan)
    assert review.status == "PASS"
    assert bind_review(plan, review).reviewed
    assert {c.label for c in provider.requests[0][2]} == {
        "system_instruction",
        "idea",
        "mcus",
        "applicability",
        "plan",
    }
    assert provider.requests[0][0] == "criticize_search"


@pytest.mark.parametrize("defect", ["canonical", "family", "relationship", "filter"])
async def test_deterministic_critic_overrides_false_model_pass(defect):
    plan, _ = await build()
    if defect == "canonical":
        plan = plan.model_copy(
            update={
                "intents": tuple(
                    q for q in plan.intents if q.query_family.value == "DIRECT_CANONICAL"
                )
            }
        )
    elif defect == "family":
        plan = plan.model_copy(
            update={
                "intents": tuple(q for q in plan.intents if q.evidence_family.value != "PATENT")
            }
        )
    elif defect == "relationship":
        plan = plan.model_copy(
            update={
                "intents": tuple(q for q in plan.intents if q.query_family.value != "RELATIONSHIP")
            }
        )
    else:
        first = plan.intents[0].model_copy(update={"filters": {"language": "en"}})
        plan = plan.model_copy(update={"intents": (first, *plan.intents[1:])})
    review, _ = await critique(plan)
    assert review.status == "REVISE"
    assert any(i.severity == "MATERIAL" for i in review.issues)
    with pytest.raises(ValueError):
        bind_review(plan, review)


async def test_exhausted_revision_is_blocked_not_implicitly_passed():
    plan, _ = await build()
    data = critic_response()
    data["status"] = "REVISE"
    critic = SearchPlanCritic(SemanticRunner(RecordedLLM({"criticize_search": data})))
    revised = planning_response()
    revised["prompt_version"] = "search-reviser-v1"
    reviser = SearchPlanReviser(SemanticRunner(RecordedLLM({"revise_search": revised})))
    final, reviews = await review_and_revise(
        plan=plan,
        idea=make_fixture().idea,
        mcus=make_fixture().graph.mcus,
        critic=critic,
        reviser=reviser,
        max_revisions=1,
    )
    assert not final.reviewed
    assert len(reviews) == 2 and reviews[-1].status == "BLOCKED"


async def test_unknown_issue_references_and_incomplete_checklist_reject():
    plan, _ = await build()
    data = critic_response()
    data["checked_categories"].pop()
    with pytest.raises(ValueError):
        await critique(plan, data)
