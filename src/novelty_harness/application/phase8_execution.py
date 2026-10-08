"""Trusted application joins for actual model and explicitly declared protocol calls."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import JsonValue

from novelty_harness.application.phase8_model_adapter import ReportModelAdapter
from novelty_harness.domain.base import ContractModel
from novelty_harness.reporting.artifacts import ReportCompilationRecord
from novelty_harness.reporting.execution import (
    ReportExecutionObservations,
    ReportExecutionRecord,
    ReportPortConfiguration,
    ReportRoleConfiguration,
    approved_role_configuration,
)
from novelty_harness.reporting.models import ReportScoped, ReportSemanticRole
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def actual_port_configuration(port: object | None) -> ReportPortConfiguration:
    if port is None:
        return ReportPortConfiguration(mode="NOT_CONFIGURED", implementation="not-configured")
    if isinstance(port, ReportModelAdapter):
        return port.configuration
    declared = getattr(port, "configuration", None)
    if not isinstance(declared, ReportPortConfiguration):
        raise ValueError("report port lacks a strict read-only configuration")
    configuration = ReportPortConfiguration.model_validate(declared.model_dump(mode="json"))
    implementation = type(port).__module__ + "." + type(port).__qualname__
    if configuration.mode != "PORT_PROTOCOL" or configuration.implementation != implementation:
        raise ValueError(
            "protocol port cannot impersonate a model runtime or another implementation"
        )
    return configuration


def invocation_configuration(
    port: object, role: ReportSemanticRole, compilation: ReportCompilationRecord
) -> ReportRoleConfiguration:
    actual = actual_port_configuration(port)
    expected = approved_role_configuration(
        compilation.scope, compilation.compilation_id, role, actual
    )
    selected = next((c for c in compilation.configuration.roles if c.role == role), None)
    if selected != expected and not (selected is None and actual.mode == "NOT_CONFIGURED"):
        raise ValueError(
            "actual invocation configuration differs from selected attempt configuration"
        )
    return expected


def completed_invocation(
    port: object,
    proposal: ContractModel,
    configuration: ReportRoleConfiguration,
    request: JsonValue,
) -> ReportExecutionRecord:
    if not isinstance(proposal, ReportScoped):
        raise ValueError("report invocation requires a scoped report proposal")
    actual = actual_port_configuration(port)
    expected = approved_role_configuration(
        proposal.scope, proposal.compilation_id, configuration.role, actual
    )
    if configuration != expected or actual.mode == "NOT_CONFIGURED":
        raise ValueError("completed invocation configuration or scope differs")
    proposal = type(proposal).model_validate_json(canonical_json(proposal), strict=True)
    if isinstance(port, ReportModelAdapter):
        execution = port.execution_for(proposal)
        if port.invocation_context_digest(execution.invocation_id) != canonical_hash(request):
            raise ValueError("completed model invocation input differs from actual context")
        if (
            execution.scope,
            execution.compilation_id,
            execution.configuration_id,
            execution.role,
            execution.method_version,
            execution.validated_proposal_hash,
        ) != (
            proposal.scope,
            proposal.compilation_id,
            configuration.configuration_id,
            configuration.role,
            configuration.method_version,
            canonical_hash(proposal),
        ):
            raise ValueError(
                "completed model invocation does not match actual proposal and configuration"
            )
        return execution
    return ReportExecutionRecord(
        scope=proposal.scope,
        compilation_id=proposal.compilation_id,
        invocation_id="p8invoke_" + uuid4().hex,
        role=configuration.role,
        task_name="phase8-" + configuration.role.value.lower(),
        method_version=configuration.method_version,
        actual_instruction_hash=configuration.instruction_hash,
        configuration_id=configuration.configuration_id,
        request_hash=canonical_hash(request),
        raw_response_hash=canonical_hash(proposal),
        validated_proposal_hash=canonical_hash(proposal),
        outcome="VALIDATED",
        observations=ReportExecutionObservations(observed_at=datetime.now(UTC)),
    )
