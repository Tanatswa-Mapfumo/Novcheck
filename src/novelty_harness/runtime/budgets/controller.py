from typing import Literal

from pydantic import ConfigDict, Field, FiniteFloat

from novelty_harness.domain.base import ContractModel
from novelty_harness.runtime.config.models import BudgetLimits


class BudgetUsage(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["budget-usage-v1"] = "budget-usage-v1"
    provider_calls: int = Field(default=0, ge=0, strict=True)
    llm_input_tokens: int = Field(default=0, ge=0, strict=True)
    llm_output_tokens: int = Field(default=0, ge=0, strict=True)
    retrieved_documents: int = Field(default=0, ge=0, strict=True)
    full_text_fetches: int = Field(default=0, ge=0, strict=True)
    deep_search_rounds: int = Field(default=0, ge=0, strict=True)
    elapsed_seconds: FiniteFloat = Field(default=0, ge=0)


class BudgetDecision(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["budget-decision-v1"] = "budget-decision-v1"
    allowed: bool
    exhausted_dimensions: tuple[str, ...]
    remaining: dict[str, float | int | None]


DIMENSIONS = (
    "provider_calls",
    "llm_input_tokens",
    "llm_output_tokens",
    "retrieved_documents",
    "full_text_fetches",
    "deep_search_rounds",
    "elapsed_seconds",
)


class BudgetController:
    def check(self, usage: BudgetUsage, limits: BudgetLimits) -> BudgetDecision:
        return self._decision(usage, limits, None)

    def permit(self, usage: BudgetUsage, limits: BudgetLimits, cost: BudgetUsage) -> BudgetDecision:
        return self._decision(usage, limits, cost)

    def _decision(
        self, usage: BudgetUsage, limits: BudgetLimits, cost: BudgetUsage | None
    ) -> BudgetDecision:
        usage = BudgetUsage.model_validate(usage.model_dump())
        limits = BudgetLimits.model_validate(limits.model_dump())
        remaining: dict[str, float | int | None] = {}
        exhausted: list[str] = []
        for dim in DIMENSIONS:
            limit: float | int | None = getattr(limits, "max_" + dim)
            used: float | int = getattr(usage, dim)
            extra: float | int = getattr(cost, dim) if cost is not None else 0
            remaining[dim] = None if limit is None else max(0, limit - used)
            if limit is not None and (used >= limit or used + extra > limit):
                exhausted.append(dim)
        return BudgetDecision(
            allowed=not exhausted, exhausted_dimensions=tuple(exhausted), remaining=remaining
        )
