from collections.abc import Sequence

from novelty_harness.research.adaptive.escalation import FALSIFICATION_STRATEGIES
from novelty_harness.research.adaptive.models import BranchState, ResearchAction
from novelty_harness.research.retrieval.models import mechanism_for


class AdaptiveController:
    def next_action(
        self,
        state: BranchState,
        actions: Sequence[ResearchAction],
        *,
        apparent_novelty: bool = False,
        coverage_floor_met: bool = False,
    ) -> ResearchAction:
        if state.budget_stopped:
            return ResearchAction(
                action_type="BUDGET_STOPPED",
                mcu_id=state.mcu_id,
                evidence_family=state.evidence_family,
                rationale="Budget prevents the next reasonable action",
            )
        eligible = [
            a
            for a in actions
            if a.mcu_id == state.mcu_id
            and a.evidence_family == state.evidence_family
            and a.action_type in {"RETRIEVE", "PAGE", "EXPAND"}
        ]
        if not eligible:
            return ResearchAction(
                action_type="ACCESS_BLOCKED" if state.access_failures else "NO_ACTION",
                mcu_id=state.mcu_id,
                evidence_family=state.evidence_family,
                rationale="Material access gaps remain"
                if state.access_failures
                else "No configured action remains; saturation must be assessed separately",
            )
        mechanisms = {mechanism_for(s) for s in state.strategies_attempted}
        deepen = (
            coverage_floor_met
            and len(mechanisms) > 1
            and len(state.providers_attempted) > 1
            and bool(state.new_candidate_yield)
            and state.new_candidate_yield[-1] > 0
            and not apparent_novelty
        )

        def priority(a: ResearchAction) -> tuple[int, ...]:
            new_provider = a.provider_name not in state.providers_attempted
            new_mechanism = a.strategy is not None and mechanism_for(a.strategy) not in mechanisms
            new_strategy = a.strategy not in state.strategies_attempted
            return (
                int(deepen and a.action_type in {"PAGE", "EXPAND"}),
                int(apparent_novelty and new_provider),
                int(new_mechanism),
                int(new_provider),
                int(new_strategy),
                int(a.strategy in FALSIFICATION_STRATEGIES),
                int(a.action_type == "PAGE"),
            )

        # Input order is the explicit configured tie-break; no probability estimates are invented.
        chosen = max(eligible, key=priority)
        reason = (
            "Additional falsification for apparent-novelty hypothesis"
            if apparent_novelty
            else (
                "Deepen a covered, productive branch"
                if deepen
                else "Broaden unresolved branch with additional retrieval diversity"
            )
        )
        return chosen.model_copy(update={"rationale": reason})
