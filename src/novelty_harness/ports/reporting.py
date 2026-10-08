"""Stateless report proposal capabilities, without repository or research access."""

from dataclasses import dataclass
from typing import Protocol

from novelty_harness.reporting.claims import ClaimExtractionContext, ClaimExtractionProposal
from novelty_harness.reporting.drafts import SectionContext, SectionDraft, SectionDraftFragment
from novelty_harness.reporting.execution import ReportPortConfiguration
from novelty_harness.reporting.models import ReportOptions
from novelty_harness.reporting.plan import PlannerContext, ReportPlanProposal
from novelty_harness.reporting.repair import LocalRepairContext
from novelty_harness.reporting.verification import (
    ClaimVerificationBatch,
    ClaimVerificationContext,
    CompositionCheck,
    CompositionContext,
)
from novelty_harness.runtime.tracing.sinks import TraceSink


class ReportPlannerPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def plan(self, context: PlannerContext, options: ReportOptions) -> ReportPlanProposal: ...


class SectionWriterPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def write(self, context: SectionContext) -> SectionDraft: ...
    async def repair(self, context: LocalRepairContext) -> SectionDraftFragment: ...


class ReportClaimExtractorPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def extract(self, context: ClaimExtractionContext) -> ClaimExtractionProposal: ...


class ReportClaimVerifierPort(Protocol):
    @property
    def configuration(self) -> ReportPortConfiguration: ...
    async def verify(self, context: ClaimVerificationContext) -> ClaimVerificationBatch: ...
    async def check_composition(self, context: CompositionContext) -> CompositionCheck: ...


@dataclass(frozen=True, slots=True)
class ReportPorts:
    planner: ReportPlannerPort | None = None
    writer: SectionWriterPort | None = None
    extractor: ReportClaimExtractorPort | None = None
    verifier: ReportClaimVerifierPort | None = None
    trace_sink: TraceSink | None = None
