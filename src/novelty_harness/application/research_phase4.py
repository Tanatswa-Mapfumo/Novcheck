from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.domain.base import utc_now
from novelty_harness.domain.evidence import SourcePassage, SourceRecord
from novelty_harness.domain.mcu import MCU, MCUGraph
from novelty_harness.providers.registry import ProviderRegistry
from novelty_harness.research.adaptive.pipeline import ResearchResult, run_adaptive_research
from novelty_harness.research.adaptive.stopping import StoppingPolicy
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.research.models import ResearchPlan
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.budgets.controller import BudgetController
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.sinks import TraceSink


class Phase5FixtureContinuation(Protocol):
    async def materialize(
        self, research: ResearchResult, graph: MCUGraph
    ) -> tuple[tuple[SourceRecord, ...], tuple[SourcePassage, ...]]: ...


class Phase4ResearchComponents:
    def __init__(
        self,
        registry: ProviderRegistry,
        coverage_policy: CoveragePolicy,
        budget_limits: BudgetLimits,
        stopping_policy: StoppingPolicy,
    ) -> None:
        self.registry, self.coverage_policy = registry, coverage_policy
        self.budget_limits, self.stopping_policy = budget_limits, stopping_policy

    async def execute(
        self,
        *,
        assessment: AssessmentRecord,
        mcus: Sequence[MCU],
        plan: ResearchPlan,
        trace_sink: TraceSink,
        writer: RunArtifactWriter,
        clock: Callable[[], datetime] = utc_now,
    ) -> ResearchResult:
        return await run_adaptive_research(
            assessment=assessment,
            mcus=mcus,
            reviewed_plan=plan,
            provider_registry=self.registry,
            coverage_policy=self.coverage_policy,
            budget_controller=BudgetController(),
            budget_limits=self.budget_limits,
            stopping_policy=self.stopping_policy,
            trace_sink=trace_sink,
            artifact_writer=writer,
            clock=clock,
        )
