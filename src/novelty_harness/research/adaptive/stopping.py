from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.research.adaptive.models import BranchState
from novelty_harness.research.retrieval.models import RetrievalStrategy, mechanism_for


class StopReason(StrEnum):
    CONTINUE = "CONTINUE"
    SATURATED = "SATURATED"
    BUDGET_STOPPED = "BUDGET_STOPPED"
    ACCESS_BLOCKED = "ACCESS_BLOCKED"


class StopAssessment(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["stop-assessment-v1"] = "stop-assessment-v1"
    reason: StopReason
    signals: dict[str, JsonValue]
    unresolved_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_false_saturation(self) -> Self:
        if self.reason == StopReason.SATURATED and (
            self.unresolved_gaps or self.signals.get("budget_blocked") is not False
        ):
            raise ValueError("Saturation cannot contain budget stops or unresolved material gaps")
        return self


class StoppingPolicy(ContractModel):
    model_config = ConfigDict(frozen=True)
    min_providers: int = Field(ge=1)
    min_mechanisms: int = Field(ge=1)
    convergence_rounds: int = Field(ge=2)
    max_new_candidates: int = Field(ge=0)
    require_citation_convergence: bool = True


class ConvergenceSignals(ContractModel):
    model_config = ConfigDict(frozen=True)
    successful_providers: frozenset[str] = frozenset()
    successful_strategies: frozenset[RetrievalStrategy] = frozenset()
    coverage_floor_met: bool = False
    top_cluster_history: tuple[tuple[str, ...], ...] = ()
    overlap_observed: bool = False
    major_candidates_explored: bool = False
    citation_yield: tuple[int, ...] = ()


def assess_stop(
    state: BranchState, convergence: ConvergenceSignals, policy: StoppingPolicy
) -> StopAssessment:
    window = policy.convergence_rounds
    yields = state.new_candidate_yield[-window:]
    tops = convergence.top_cluster_history[-window:]
    citation = convergence.citation_yield[-window:]
    checks: dict[str, JsonValue] = {
        "budget_blocked": state.budget_stopped,
        "provider_diversity": len(convergence.successful_providers) >= policy.min_providers,
        "mechanism_diversity": len({mechanism_for(s) for s in convergence.successful_strategies})
        >= policy.min_mechanisms,
        "diminishing_yield": len(yields) == window
        and all(n <= policy.max_new_candidates for n in yields),
        "stable_top_clusters": len(tops) == window
        and bool(tops[0])
        and all(t == tops[0] for t in tops),
        "overlap": convergence.overlap_observed,
        "major_candidates_explored": convergence.major_candidates_explored,
        "coverage_floor": convergence.coverage_floor_met,
        "citation_convergence": not policy.require_citation_convergence
        or (len(citation) == window and all(n <= policy.max_new_candidates for n in citation)),
    }
    reason = StopReason.CONTINUE
    if state.budget_stopped:
        reason = StopReason.BUDGET_STOPPED
    elif state.access_failures:
        reason = StopReason.ACCESS_BLOCKED
    elif all(value is True for key, value in checks.items() if key != "budget_blocked"):
        reason = StopReason.SATURATED
    gaps = list(state.access_failures)
    if reason == StopReason.CONTINUE:
        gaps.extend(
            key for key, value in checks.items() if key != "budget_blocked" and value is False
        )
    return StopAssessment(reason=reason, signals=checks, unresolved_gaps=tuple(gaps))
