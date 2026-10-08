"""Provider-neutral application ports for Phase 7 semantic proposals."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from novelty_harness.adjudication.context import SealedAssessmentContext
from novelty_harness.adjudication.judge import JudgeFinding
from novelty_harness.adjudication.needs import (
    ResearchEscalationBudget,
    ResearchEscalationOutcome,
    ResearchGapRequest,
)
from novelty_harness.adjudication.packet import AdjudicationCasePacket
from novelty_harness.adjudication.roles import (
    DefenseCase,
    ProsecutionCase,
    RebuttalCase,
    RoleArgument,
)
from novelty_harness.runtime.tracing.sinks import TraceSink


class ProsecutionPort(Protocol):
    async def propose(self, packet: AdjudicationCasePacket) -> ProsecutionCase: ...


class DefensePort(Protocol):
    async def propose(self, packet: AdjudicationCasePacket) -> DefenseCase: ...


class RebuttalPort(Protocol):
    async def propose(
        self,
        packet: AdjudicationCasePacket,
        disputed_ids: tuple[str, ...],
        other_case: ProsecutionCase | DefenseCase,
    ) -> RebuttalCase: ...


class EvidenceJudgePort(Protocol):
    @property
    def model_config_id(self) -> str: ...

    async def judge(
        self,
        packet: AdjudicationCasePacket,
        arguments: tuple[RoleArgument, ...],
        *,
        order: tuple[str, str],
        rubric_version: str,
    ) -> JudgeFinding: ...


class ResearchEscalationPort(Protocol):
    async def execute(
        self, request: ResearchGapRequest, context: SealedAssessmentContext
    ) -> ResearchEscalationOutcome: ...


@dataclass(frozen=True, slots=True)
class Phase7TargetRoles:
    prosecutor: ProsecutionPort
    defender: DefensePort


def _empty_target_roles() -> Mapping[str, Phase7TargetRoles]:
    return {}


@dataclass(frozen=True, slots=True)
class Phase7Ports:
    prosecutor: ProsecutionPort
    defender: DefensePort
    prosecutor_rebuttal: RebuttalPort
    defender_rebuttal: RebuttalPort
    judge: EvidenceJudgePort
    research_escalation: ResearchEscalationPort | None = None
    research_budget: ResearchEscalationBudget | None = None
    trace_sink: TraceSink | None = None
    alternate_judge: EvidenceJudgePort | None = None
    target_roles: Mapping[str, Phase7TargetRoles] = field(default_factory=_empty_target_roles)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_roles", MappingProxyType(dict(self.target_roles)))
