import pytest

from novelty_harness.runtime.budgets.controller import BudgetController, BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits


def test_none_limits_are_unlimited_and_zero_limits_are_not():
    controller = BudgetController()
    assert controller.check(BudgetUsage(provider_calls=1000), BudgetLimits()).allowed
    result = controller.check(BudgetUsage(), BudgetLimits(max_provider_calls=0))
    assert not result.allowed and result.exhausted_dimensions == ("provider_calls",)
    assert result.remaining["provider_calls"] == 0


@pytest.mark.parametrize(
    "usage_field,limit_field",
    [
        ("provider_calls", "max_provider_calls"),
        ("llm_input_tokens", "max_llm_input_tokens"),
        ("llm_output_tokens", "max_llm_output_tokens"),
        ("retrieved_documents", "max_retrieved_documents"),
        ("full_text_fetches", "max_full_text_fetches"),
        ("deep_search_rounds", "max_deep_search_rounds"),
        ("elapsed_seconds", "max_elapsed_seconds"),
    ],
)
def test_each_hard_limit_stops_at_boundary_and_projected_cost_cannot_overshoot(
    usage_field, limit_field
):
    controller = BudgetController()
    limits = BudgetLimits.model_validate({limit_field: 2})
    assert controller.check(BudgetUsage.model_validate({usage_field: 1}), limits).allowed
    assert not controller.check(BudgetUsage.model_validate({usage_field: 2}), limits).allowed
    assert not controller.permit(
        BudgetUsage.model_validate({usage_field: 1}),
        limits,
        BudgetUsage.model_validate({usage_field: 2}),
    ).allowed
    assert controller.permit(
        BudgetUsage.model_validate({usage_field: 1}),
        limits,
        BudgetUsage.model_validate({usage_field: 1}),
    ).allowed


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_usage_is_not_coerced_to_an_unlimited_budget(value):
    with pytest.raises(ValueError):
        BudgetUsage(elapsed_seconds=value)
