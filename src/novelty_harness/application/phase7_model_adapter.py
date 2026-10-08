"""Bounded structured model adapters; proposals remain untrusted until validation."""

from collections.abc import Callable, Sequence
from typing import cast

from pydantic import BaseModel, ConfigDict, JsonValue

from novelty_harness.adjudication.judge import JudgeFinding, validate_judge_finding
from novelty_harness.adjudication.models import SemanticExecutionRecord
from novelty_harness.adjudication.needs import clarify_unproved_gate_d, gate_d_external_fact_bases
from novelty_harness.adjudication.packet import AdjudicationCasePacket
from novelty_harness.adjudication.prompts import (
    DEFENDER_INSTRUCTION,
    DEFENDER_PROMPT_VERSION,
    JUDGE_INSTRUCTION,
    JUDGE_RUBRIC_VERSION,
    PROSECUTOR_INSTRUCTION,
    PROSECUTOR_PROMPT_VERSION,
    REBUTTAL_INSTRUCTION,
    REBUTTAL_PROMPT_VERSION,
    RECOVERY_INSTRUCTION,
    UNTRUSTED_CONTEXT_SUFFIX,
)
from novelty_harness.adjudication.roles import (
    DefenseCase,
    ProsecutionCase,
    RebuttalCase,
    RoleArgument,
    validate_defense_case,
    validate_prosecution_case,
    validate_rebuttal_case,
)
from novelty_harness.domain.base import ContractModel
from novelty_harness.ports.models import ContextBlock, LLMCallConfig
from novelty_harness.runtime.semantic.structured import (
    SemanticCallAudit,
    SemanticOutputValidationError,
    SemanticRunner,
    SemanticTaskSpec,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


class Phase7ModelOutputError(ValueError):
    """Operational model failure; it is never a semantic UNASSESSABLE finding."""

    def __init__(self, message: str, audits: tuple[SemanticCallAudit, ...]) -> None:
        super().__init__(message)
        self.audits = audits


class Phase7ModelCallRecord(ContractModel):
    """Operational provenance; unavailable provider usage stays unknown."""

    model_config = ConfigDict(frozen=True)
    prompt_version: str
    model_name: str | None
    provider_name: str
    provider_version: str | None
    request_hash: str
    response_hash: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    validation_state: str


class Phase7ModelAdapter:
    def __init__(self, runner: SemanticRunner, *, target_id: str | None = None) -> None:
        self._runner = runner
        self._target_id = target_id
        self._executions: dict[str, SemanticExecutionRecord] = {}

    @property
    def execution_configuration(self) -> dict[str, JsonValue]:
        return {
            "provider": self._runner.provider.name,
            "config": self._runner.config.model_dump(mode="json"),
        }

    @property
    def model_config_id(self) -> str:
        return "p7model_" + canonical_hash(self.execution_configuration)

    def execution_for(self, proposal: BaseModel) -> SemanticExecutionRecord:
        return self._executions[canonical_hash(proposal)]

    def _role_blocks(self, packet: AdjudicationCasePacket) -> tuple[ContextBlock, ...]:
        if self._target_id is None:
            return (_packet_block(packet),)
        profile = next((p for p in packet.target_profiles if p.target_id == self._target_id), None)
        if profile is None:
            raise ValueError("Selected role target is absent from the complete packet")
        return (
            _packet_block(packet),
            ContextBlock(label="selected_target", text=canonical_json(profile)),
        )

    def _validate_role_target[T: ProsecutionCase | DefenseCase](self, case: T) -> T:
        if self._target_id is not None and case.target_id != self._target_id:
            raise ValueError("Role response differs from the explicitly selected target")
        return case

    @property
    def audits(self) -> tuple[SemanticCallAudit, ...]:
        return self._runner.audits

    @property
    def call_records(self) -> tuple[Phase7ModelCallRecord, ...]:
        return tuple(
            Phase7ModelCallRecord(
                prompt_version=audit.prompt_version,
                model_name=self._runner.config.model,
                provider_name=audit.call.provider_name,
                provider_version=audit.call.provider_version,
                request_hash=audit.request_hash,
                response_hash=audit.response_hash,
                latency_ms=max(
                    0.0,
                    (audit.call.finished_at - audit.call.started_at).total_seconds() * 1000,
                ),
                validation_state=audit.validation_state,
            )
            for audit in self.audits
        )

    async def _run[T: BaseModel](
        self,
        spec: SemanticTaskSpec[T],
        instruction: str,
        blocks: Sequence[ContextBlock],
        validate: Callable[[T], T],
    ) -> T:
        for attempt in range(2):
            current_instruction = instruction
            if attempt:
                current_instruction += RECOVERY_INSTRUCTION
            try:
                config_id = self.model_config_id
                call_config = LLMCallConfig.model_validate(
                    {
                        **self._runner.config.model_dump(),
                        "metadata": {
                            **self._runner.config.metadata,
                            "task_name": spec.task_name,
                            "prompt_version": spec.prompt_version,
                        },
                    }
                )
                actual_blocks = [
                    ContextBlock(
                        label="system_instruction",
                        trusted_instruction=True,
                        text=current_instruction + UNTRUSTED_CONTEXT_SUFFIX,
                    ),
                    *(ContextBlock(label=b.label, text=b.text) for b in blocks),
                ]
                request_hash = canonical_hash(
                    {
                        "task": spec.task_name,
                        "schema": spec.output_model.model_json_schema(),
                        "context": [b.model_dump(mode="json") for b in actual_blocks],
                        "config": call_config.model_dump(mode="json"),
                    }
                )
                result = await self._runner.run(spec, current_instruction, blocks)
                proposal = validate(result)
                if self.model_config_id != config_id:
                    raise ValueError("Semantic model configuration changed during execution")
                matching = [
                    a
                    for a in self.audits
                    if a.task_name == spec.task_name
                    and a.request_hash == request_hash
                    and a.validation_state == "VALIDATED"
                ]
                if not matching:
                    raise ValueError("Semantic invocation audit is missing")
                audit = matching[-1]
                self._executions[canonical_hash(proposal)] = SemanticExecutionRecord(
                    invocation_prompt_hash=canonical_hash(actual_blocks[0].text),
                    prompt_version=audit.prompt_version,
                    prompt_hash=canonical_hash(instruction),
                    model_config_id=config_id,
                    provider_name=audit.call.provider_name,
                    execution_mode="SEMANTIC_RUNNER",
                    request_hash=audit.request_hash,
                    response_hash=audit.response_hash,
                    proposal_hash=canonical_hash(proposal),
                    model_name=self._runner.config.model,
                    provider_version=audit.call.provider_version,
                    latency_ms=max(
                        0.0, (audit.call.finished_at - audit.call.started_at).total_seconds() * 1000
                    ),
                )
                return proposal
            except SemanticOutputValidationError as error:
                if error.audit.validation_state != "INVALID" or attempt:
                    raise Phase7ModelOutputError(str(error), self.audits) from error
            except ValueError as error:
                if attempt:
                    raise Phase7ModelOutputError(
                        "Phase 7 proposal failed packet membership validation", self.audits
                    ) from error
        raise Phase7ModelOutputError("Phase 7 model recovery exhausted", self.audits)


def _packet_block(packet: AdjudicationCasePacket) -> ContextBlock:
    display = packet.model_dump(mode="json")
    display["gate_d_external_fact_bases"] = [
        b.model_dump(mode="json") for b in gate_d_external_fact_bases(packet)
    ]
    return ContextBlock(label="case_packet", text=canonical_json(display))


class ProsecutionModelAdapter(Phase7ModelAdapter):
    async def propose(self, packet: AdjudicationCasePacket) -> ProsecutionCase:
        return await self._run(
            SemanticTaskSpec("phase7_prosecutor", PROSECUTOR_PROMPT_VERSION, ProsecutionCase),
            PROSECUTOR_INSTRUCTION
            + " When selected_target data is present, assess only that target.",
            self._role_blocks(packet),
            lambda case: self._validate_role_target(
                validate_prosecution_case(clarify_unproved_gate_d(case, packet), packet)
            ),
        )


class DefenseModelAdapter(Phase7ModelAdapter):
    async def propose(self, packet: AdjudicationCasePacket) -> DefenseCase:
        return await self._run(
            SemanticTaskSpec("phase7_defender", DEFENDER_PROMPT_VERSION, DefenseCase),
            DEFENDER_INSTRUCTION
            + " When selected_target data is present, assess only that target.",
            self._role_blocks(packet),
            lambda case: self._validate_role_target(
                validate_defense_case(clarify_unproved_gate_d(case, packet), packet)
            ),
        )


class RebuttalModelAdapter(Phase7ModelAdapter):
    async def propose(
        self,
        packet: AdjudicationCasePacket,
        disputed_ids: tuple[str, ...],
        other_case: ProsecutionCase | DefenseCase,
    ) -> RebuttalCase:
        return await self._run(
            SemanticTaskSpec("phase7_rebuttal", REBUTTAL_PROMPT_VERSION, RebuttalCase),
            REBUTTAL_INSTRUCTION,
            (
                _packet_block(packet),
                ContextBlock(
                    label="selected_disputes",
                    text=canonical_json(cast(JsonValue, list(disputed_ids))),
                ),
                ContextBlock(label="other_case", text=canonical_json(other_case)),
            ),
            lambda case: validate_rebuttal_case(clarify_unproved_gate_d(case, packet), packet),
        )


class EvidenceJudgeModelAdapter(Phase7ModelAdapter):
    @property
    def model_config_id(self) -> str:
        return "p7model_" + canonical_hash(
            {
                "provider": self._runner.provider.name,
                "config": self._runner.config.model_dump(mode="json"),
            }
        )

    async def judge(
        self,
        packet: AdjudicationCasePacket,
        arguments: tuple[RoleArgument, ...],
        *,
        order: tuple[str, str],
        rubric_version: str,
    ) -> JudgeFinding:
        if set(order) != {"A", "B"} or rubric_version != JUDGE_RUBRIC_VERSION:
            raise ValueError("Judge order or rubric differs from configured Phase 7 protocol")
        if len(arguments) != 2 or len({item.argument_id for item in arguments}) != 2:
            raise ValueError("Judge needs two distinct argument records")
        by_label = {"A": arguments[0], "B": arguments[1]}
        neutral_arguments = tuple(
            {"label": label, "argument": by_label[label].model_dump(mode="json")} for label in order
        )
        return await self._run(
            SemanticTaskSpec("phase7_judge", JUDGE_RUBRIC_VERSION, JudgeFinding),
            JUDGE_INSTRUCTION,
            (
                _packet_block(packet),
                ContextBlock(
                    label="blinded_arguments",
                    text=canonical_json(cast(JsonValue, list(neutral_arguments))),
                ),
            ),
            lambda finding: validate_judge_finding(
                clarify_unproved_gate_d(finding, packet), packet, arguments
            ),
        )
