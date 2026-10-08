"""Actual strict report calls with isolated audit capture and bounded recovery."""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pydantic import JsonValue

from novelty_harness.domain.base import ContractModel
from novelty_harness.ports.models import ContextBlock, LLMCallConfig
from novelty_harness.reporting.artifacts import (
    ReportArtifact,
    ReportArtifactKind,
    report_artifact_id,
)
from novelty_harness.reporting.claims import ClaimExtractionContext, ClaimExtractionProposal
from novelty_harness.reporting.drafts import SectionContext, SectionDraft, SectionDraftFragment
from novelty_harness.reporting.execution import (
    ReportExecutionObservations,
    ReportExecutionRecord,
    ReportPortConfiguration,
    ReportSamplingSettings,
    approved_role_configuration,
)
from novelty_harness.reporting.models import ReportOptions, ReportScoped, ReportSemanticRole
from novelty_harness.reporting.plan import PlannerContext, ReportPlanProposal
from novelty_harness.reporting.prompts import (
    SEMANTIC_METHODS,
    UNTRUSTED_CONTEXT_SUFFIX,
    approved_instruction,
)
from novelty_harness.reporting.repair import LocalRepairContext
from novelty_harness.reporting.verification import (
    ClaimVerificationBatch,
    ClaimVerificationContext,
    CompositionCheck,
    CompositionContext,
)
from novelty_harness.runtime.semantic.structured import (
    SemanticCallAudit,
    SemanticOutputValidationError,
    SemanticRunner,
    SemanticTaskSpec,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def execution_artifact_reference(record: ReportExecutionRecord) -> str:
    artifact = ReportArtifact(
        scope=record.scope,
        compilation_id=record.compilation_id,
        artifact_id="pending",
        kind=ReportArtifactKind.EXECUTION,
        method_version=record.method_version,
        document=record,
    )
    return report_artifact_id(artifact)


class ReportModelOutputError(ValueError):
    """Redacted operational failure retains every completed attempt in this invocation."""

    def __init__(self, message: str, executions: tuple[ReportExecutionRecord, ...]) -> None:
        super().__init__(message)
        self.executions = executions


class ReportModelAdapter:
    def __init__(self, runner: SemanticRunner) -> None:
        self._template = runner
        self._audits: list[SemanticCallAudit] = []
        self._executions: list[ReportExecutionRecord] = []
        self._by_proposal: dict[str, list[ReportExecutionRecord]] = {}
        self._context_digests: dict[str, str] = {}

    @property
    def configuration(self) -> ReportPortConfiguration:
        if self._template.config.model is None:
            raise ValueError("report semantic runner requires an explicit actual model")
        return ReportPortConfiguration(
            mode="SEMANTIC_RUNNER",
            implementation=type(self).__module__ + "." + type(self).__qualname__,
            provider=self._template.provider.name,
            model=self._template.config.model,
            runtime_configuration_digest=canonical_hash(self._template.config),
            sampling=ReportSamplingSettings(temperature=self._template.config.temperature),
        )

    @property
    def audits(self) -> tuple[SemanticCallAudit, ...]:
        return tuple(a.model_copy(deep=True) for a in self._audits)

    @property
    def executions(self) -> tuple[ReportExecutionRecord, ...]:
        return tuple(e.model_copy(deep=True) for e in self._executions)

    def execution_for(self, proposal: ContractModel) -> ReportExecutionRecord:
        matching = self._by_proposal.get(canonical_hash(proposal), ())
        if len(matching) != 1:
            raise ValueError(
                "proposal has no unique actual invocation; never select the last audit"
            )
        return matching[0].model_copy(deep=True)

    def invocation_context_digest(self, invocation_id: str) -> str:
        """Trusted digest of the context actually delivered in this invocation."""
        return self._context_digests[invocation_id]

    async def _invoke[T: ReportScoped](
        self, context: ReportScoped, role: ReportSemanticRole, output: type[T]
    ) -> T:
        context = type(context).model_validate_json(canonical_json(context), strict=True)
        initial_config = self.configuration
        configuration = approved_role_configuration(
            context.scope, context.compilation_id, role, initial_config
        )
        # A shared runner supplies only the provider/config template. Audit state is
        # private to this invocation, including its single possible recovery.
        runner = SemanticRunner(self._template.provider, self._template.config)
        identifier = uuid4().hex
        task = f"phase8-{role.value.lower()}-{identifier}"
        spec = SemanticTaskSpec(task, SEMANTIC_METHODS[role][0], output)
        blocks = (ContextBlock(label="report_context", text=canonical_json(context)),)
        attempts: list[ReportExecutionRecord] = []
        for index in range(1 if role == ReportSemanticRole.REPAIR else 2):
            recovery = bool(index)
            instruction = approved_instruction(role, recovery=recovery)
            call_config = LLMCallConfig.model_validate(
                {
                    **runner.config.model_dump(mode="json"),
                    "metadata": {
                        **runner.config.metadata,
                        "task_name": task,
                        "prompt_version": spec.prompt_version,
                    },
                }
            )
            schema = cast(dict[str, JsonValue], output.model_json_schema())
            request_hash = canonical_hash(
                {
                    "task": task,
                    "schema": schema,
                    "context": [
                        ContextBlock(
                            label="system_instruction", text=instruction, trusted_instruction=True
                        ).model_dump(mode="json"),
                        *(b.model_dump(mode="json") for b in blocks),
                    ],
                    "config": call_config.model_dump(mode="json"),
                }
            )
            started = datetime.now(UTC)
            proposal: T | None = None
            audit: SemanticCallAudit | None = None
            before = len(runner.audits)
            try:
                # SemanticRunner appends the same isolation suffix exactly once.
                proposal = await runner.run(
                    spec, instruction.removesuffix(UNTRUSTED_CONTEXT_SUFFIX), blocks
                )
                audit_slice = runner.audits[before:]
                if len(audit_slice) != 1 or audit_slice[0].request_hash != request_hash:
                    raise ValueError("actual invocation audit does not match its delivered request")
                audit = audit_slice[0]
                outcome = "VALIDATED"
            except SemanticOutputValidationError as error:
                audit = error.audit
                outcome = audit.validation_state
            except Exception:
                # No schema retry for an ambiguous/missing audit or transport failure.
                outcome = "PROVIDER_FAILURE"
            finished = datetime.now(UTC)
            if audit is not None:
                if (
                    audit.request_hash != request_hash
                    or audit.task_name != task
                    or audit.prompt_version != spec.prompt_version
                ):
                    raise ReportModelOutputError("report runtime audit mismatch", tuple(attempts))
                self._audits.append(audit)
            record = ReportExecutionRecord(
                scope=context.scope,
                compilation_id=context.compilation_id,
                invocation_id="p8invoke_" + identifier + ("_recovery" if recovery else ""),
                role=role,
                task_name=task,
                method_version=spec.prompt_version,
                actual_instruction_hash=canonical_hash(instruction),
                configuration_id=configuration.configuration_id,
                request_hash=request_hash,
                raw_response_hash=audit.response_hash if audit is not None else None,
                validated_proposal_hash=canonical_hash(proposal)
                if outcome == "VALIDATED" and proposal is not None
                else None,
                outcome=outcome,
                recovery=recovery,
                predecessor_ref=execution_artifact_reference(attempts[0]) if recovery else None,
                observations=ReportExecutionObservations(
                    observed_at=finished,
                    latency_ms=max(0.0, (finished - started).total_seconds() * 1000),
                ),
            )
            self._executions.append(record)
            self._context_digests[record.invocation_id] = canonical_hash(context)
            attempts.append(record)
            if self.configuration != initial_config:
                raise ReportModelOutputError(
                    "actual report runtime configuration changed", tuple(attempts)
                )
            if proposal is not None and outcome == "VALIDATED":
                self._by_proposal.setdefault(canonical_hash(proposal), []).append(record)
                return proposal
            if outcome != "INVALID":
                break
        raise ReportModelOutputError(
            "report provider output unavailable or invalid", tuple(attempts)
        )

    async def plan(self, context: PlannerContext, options: ReportOptions) -> ReportPlanProposal:
        if context.options != options:
            raise ValueError("planner options differ from invocation context")
        return await self._invoke(context, ReportSemanticRole.PLANNER, ReportPlanProposal)

    async def write(self, context: SectionContext) -> SectionDraft:
        return await self._invoke(context, ReportSemanticRole.WRITER, SectionDraft)

    async def repair(self, context: LocalRepairContext) -> SectionDraftFragment:
        return await self._invoke(context, ReportSemanticRole.REPAIR, SectionDraftFragment)

    async def extract(self, context: ClaimExtractionContext) -> ClaimExtractionProposal:
        return await self._invoke(context, ReportSemanticRole.EXTRACTOR, ClaimExtractionProposal)

    async def verify(self, context: ClaimVerificationContext) -> ClaimVerificationBatch:
        return await self._invoke(context, ReportSemanticRole.VERIFIER, ClaimVerificationBatch)

    async def check_composition(self, context: CompositionContext) -> CompositionCheck:
        return await self._invoke(context, ReportSemanticRole.COMPOSITION, CompositionCheck)
