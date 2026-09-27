import pytest

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.research.coverage import (
    CoverageFloor,
    CoveragePolicy,
    CoverageState,
    QueryScreeningOutcome,
    evaluate_coverage,
)
from novelty_harness.research.critique import bind_review
from tests.unit.research.test_search_critique import critique
from tests.unit.research.test_strategist import build


async def prepared():
    plan, _ = await build()
    review, _ = await critique(plan)
    return bind_review(plan, review)


async def test_missing_patent_provider_is_blocked_not_excluded():
    cells = evaluate_coverage(
        await prepared(),
        CoveragePolicy.standard(),
        {EvidenceFamily.SCHOLARLY: ("openalex", "crossref"), EvidenceFamily.SOFTWARE: ("github",)},
    )
    assert all(
        c.state == CoverageState.BLOCKED_NO_PROVIDER
        for c in cells
        if c.evidence_family == EvidenceFamily.PATENT
    )
    assert all(
        c.state == CoverageState.READY_FOR_SCREENING
        for c in cells
        if c.evidence_family == EvidenceFamily.SCHOLARLY
    )


async def test_zero_results_can_be_screened_but_failure_remains_degraded():
    plan = await prepared()
    outcomes = [
        QueryScreeningOutcome(
            query_id=q.query_id, provider_name="openalex", success=True, inspected_results=0
        )
        for q in plan.intents
        if q.evidence_family == EvidenceFamily.SCHOLARLY
    ]
    cells = evaluate_coverage(
        plan, CoveragePolicy.standard(), {EvidenceFamily.SCHOLARLY: ("openalex",)}, outcomes
    )
    assert all(
        c.state == CoverageState.SCREENED
        for c in cells
        if c.evidence_family == EvidenceFamily.SCHOLARLY
    )
    outcomes[0] = outcomes[0].model_copy(update={"had_failed_attempts": True})
    cells = evaluate_coverage(
        plan, CoveragePolicy.standard(), {EvidenceFamily.SCHOLARLY: ("openalex",)}, outcomes
    )
    assert cells[0].state == CoverageState.DEGRADED


async def test_hit_count_does_not_replace_query_diversity():
    plan = await prepared()
    outcomes = [
        QueryScreeningOutcome(
            query_id=plan.intents[0].query_id,
            provider_name="openalex",
            success=True,
            inspected_results=10000,
        )
    ]
    cells = evaluate_coverage(
        plan, CoveragePolicy.standard(), {EvidenceFamily.SCHOLARLY: ("openalex",)}, outcomes
    )
    assert cells[0].state == CoverageState.DEGRADED


def test_policy_is_complete_configurable_and_never_saturated():
    assert "SATURATED" not in CoverageState.__members__
    with pytest.raises(ValueError):
        CoveragePolicy(by_family={})
    with pytest.raises(ValueError):
        CoverageFloor(min_distinct_query_families=0, min_configured_providers=1)
    policy = CoveragePolicy.standard()
    assert CoveragePolicy.model_validate_json(policy.model_dump_json()) == policy
