import pytest

from novelty_harness.research.adaptive.stopping import (
    ConvergenceSignals,
    StopAssessment,
    StoppingPolicy,
    assess_stop,
)
from tests.unit.research.adaptive.test_controller import branch


def policy():
    return StoppingPolicy(
        min_providers=2, min_mechanisms=2, convergence_rounds=2, max_new_candidates=0
    )


def signals(**updates):
    return ConvergenceSignals.model_validate(
        {
            "successful_providers": ["openalex", "crossref"],
            "successful_strategies": ["LEXICAL", "SEMANTIC", "CITATION_BACKWARD"],
            "coverage_floor_met": True,
            "top_cluster_history": [["known"], ["known"]],
            "overlap_observed": True,
            "major_candidates_explored": True,
            "citation_yield": [0, 0],
            **updates,
        }
    )


def stable(**updates):
    return type(branch()).model_validate(
        {**branch().model_dump(), "new_candidate_yield": [0, 0], **updates}
    )


def test_true_diminishing_yield_requires_all_convergence_signals():
    assert assess_stop(stable(), signals(), policy()).reason.value == "SATURATED"


@pytest.mark.parametrize(
    "updates",
    [
        {"successful_providers": ["openalex"]},
        {"successful_strategies": ["LEXICAL", "HISTORICAL_TERM", "ADJACENT_DOMAIN"]},
        {"overlap_observed": False},
        {"coverage_floor_met": False},
        {"major_candidates_explored": False},
        {"citation_yield": [0, 1]},
        {"top_cluster_history": [["a"], ["b"]]},
    ],
)
def test_false_monoculture_unexplored_and_yielding_neighborhoods_continue(updates):
    assert assess_stop(stable(), signals(**updates), policy()).reason.value == "CONTINUE"


def test_material_access_gap_blocks_saturation_and_budget_takes_distinct_precedence():
    blocked = stable(access_failures=["patent provider unavailable"])
    assert assess_stop(blocked, signals(), policy()).reason.value == "ACCESS_BLOCKED"
    budget = stable(budget_stopped=True, access_failures=["blocked"])
    assert assess_stop(budget, signals(), policy()).reason.value == "BUDGET_STOPPED"


def test_false_saturation_cannot_roundtrip_with_budget_or_material_gaps():
    with pytest.raises(ValueError):
        StopAssessment(reason="SATURATED", signals={"budget_blocked": True}, unresolved_gaps=[])
    with pytest.raises(ValueError):
        StopAssessment(
            reason="SATURATED", signals={"budget_blocked": False}, unresolved_gaps=["blocked"]
        )
