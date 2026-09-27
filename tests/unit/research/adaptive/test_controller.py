from novelty_harness.research.adaptive.controller import AdaptiveController
from novelty_harness.research.adaptive.escalation import multilingual_hook
from novelty_harness.research.adaptive.models import BranchState, ResearchAction


def branch(**updates):
    return BranchState.model_validate(
        dict(
            mcu_id="mcu_control",
            evidence_family="SCHOLARLY",
            depth="SCREENING",
            strategies_attempted=["LEXICAL"],
            providers_attempted=["openalex"],
            rounds=1,
            relevant_candidate_count=0,
            new_candidate_yield=[0],
            unresolved=True,
            access_failures=[],
            **updates,
        )
    )


def action(strategy="SEMANTIC", provider="openalex", kind="RETRIEVE"):
    return ResearchAction(
        action_type=kind,
        mcu_id="mcu_control",
        evidence_family="SCHOLARLY",
        strategy=strategy,
        provider_name=provider,
        rationale="Configured available action",
    )


def test_empty_branch_broadens_mechanism_before_repeating_paraphrases():
    result = AdaptiveController().next_action(branch(), [action("LEXICAL", kind="PAGE"), action()])
    assert result.strategy.value == "SEMANTIC" and result.action_type == "RETRIEVE"


def test_high_apparent_novelty_escalates_without_assigning_any_verdict():
    result = AdaptiveController().next_action(
        branch(),
        [action("HISTORICAL_TERM"), action("LEXICAL", "semantic_scholar")],
        apparent_novelty=True,
    )
    assert result.provider_name == "semantic_scholar" and "falsification" in result.rationale
    assert "novelty_score" not in result.model_dump()


def test_budget_and_access_are_explicit_not_loss_of_branch_priority():
    assert (
        AdaptiveController().next_action(branch(budget_stopped=True), [action()]).action_type
        == "BUDGET_STOPPED"
    )
    blocked = BranchState.model_validate(
        {**branch().model_dump(), "access_failures": ["crossref:unavailable"]}
    )
    assert AdaptiveController().next_action(blocked, []).action_type == "ACCESS_BLOCKED"
    assert AdaptiveController().next_action(blocked, [action()]).strategy.value == "SEMANTIC"


def test_covered_diverse_high_yield_branch_deepens():
    state = BranchState.model_validate(
        {
            **branch().model_dump(),
            "strategies_attempted": ["LEXICAL", "SEMANTIC"],
            "providers_attempted": ["openalex", "crossref"],
            "relevant_candidate_count": 5,
            "new_candidate_yield": [5],
        }
    )
    result = AdaptiveController().next_action(
        state, [action("ADJACENT_DOMAIN"), action("LEXICAL", kind="PAGE")], coverage_floor_met=True
    )
    assert result.action_type == "PAGE"


def test_multilingual_unavailability_is_explicit_not_claimed_coverage():
    hook = multilingual_hook(branch(), supported=False)
    assert hook.action_type == "MULTILINGUAL_UNAVAILABLE" and hook.strategy is None
