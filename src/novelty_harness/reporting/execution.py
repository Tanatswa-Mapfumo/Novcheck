"""Application-owned methods and configuration shapes; actual call joins arrive separately."""

from types import MappingProxyType
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.reporting.models import (
    Digest,
    NonBlank,
    ReportContract,
    ReportScope,
    ReportScoped,
    ReportSemanticRole,
)
from novelty_harness.reporting.prompts import (
    RECOVERY_INSTRUCTION,
    SEMANTIC_METHODS,
    UNTRUSTED_CONTEXT_SUFFIX,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

ExecutionMode = Literal["SEMANTIC_RUNNER", "PORT_PROTOCOL", "NOT_CONFIGURED"]
APPROVED_REGISTRY = "p8-approved-methods-v1"
DETERMINISTIC_VERSIONS = (
    "p8-plan-firewall-v1",
    "p8-semantic-firewall-v1",
    "p8-fallback-v1",
    "p8-citations-v1",
    "p8-render-v1",
    "p8-summary-v1",
    "p8-lens-v1",
    "p8-bundle-v1",
    "p8-obligations-v1",
)


# Supported instructions remain immutable even when an invocation default moves.
SUPPORTED_SEMANTIC_METHODS = MappingProxyType(
    {(role, version): instruction for role, (version, instruction) in SEMANTIC_METHODS.items()}
)
DEFAULT_SEMANTIC_METHODS = MappingProxyType(
    {role: version for role, (version, _) in SEMANTIC_METHODS.items()}
)


def registered_instruction(
    role: ReportSemanticRole, version: str, *, recovery: bool = False, mode: str
) -> str:
    instruction = SUPPORTED_SEMANTIC_METHODS.get((role, version))
    if instruction is None or mode not in {"SEMANTIC_RUNNER", "PORT_PROTOCOL"}:
        raise ValueError("method version or mode is not approved")
    if recovery and role == ReportSemanticRole.REPAIR:
        raise ValueError("repair has no schema recovery")
    return (
        instruction
        + (RECOVERY_INSTRUCTION if recovery else "")
        + (UNTRUSTED_CONTEXT_SUFFIX if mode == "SEMANTIC_RUNNER" else "")
    )


class ReportSamplingSettings(ReportContract):
    contract_kind: Literal["phase8-report-sampling-settings-v1"] = (
        "phase8-report-sampling-settings-v1"
    )
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    seed: int | None = None


class ReportStructuredSettings(ReportContract):
    contract_kind: Literal["phase8-report-structured-settings-v1"] = (
        "phase8-report-structured-settings-v1"
    )
    schema_mode: Literal["STRICT", "PORT_PROTOCOL"] = "STRICT"
    max_transport_attempts: int = Field(default=1, ge=1)


class ReportPortConfiguration(ReportContract):
    contract_kind: Literal["phase8-report-port-configuration-v1"] = (
        "phase8-report-port-configuration-v1"
    )
    mode: ExecutionMode
    implementation: NonBlank
    provider: NonBlank | None = None
    model: NonBlank | None = None
    runtime_configuration_digest: Digest | None = None
    sampling: ReportSamplingSettings = Field(default_factory=ReportSamplingSettings)
    structured: ReportStructuredSettings = Field(default_factory=ReportStructuredSettings)

    @model_validator(mode="after")
    def mode_identity(self) -> "ReportPortConfiguration":
        if self.mode == "SEMANTIC_RUNNER" and (self.provider is None or self.model is None):
            raise ValueError("semantic runtime requires actual provider and model")
        if self.mode == "PORT_PROTOCOL" and self.provider is not None:
            raise ValueError("protocol port cannot claim a semantic provider")
        if self.mode == "NOT_CONFIGURED" and (self.provider is not None or self.model is not None):
            raise ValueError("absent port cannot claim model execution")
        return self


class ReportMethodRegistration(ReportScoped):
    contract_kind: Literal["phase8-report-method-registration-v1"] = (
        "phase8-report-method-registration-v1"
    )
    role: ReportSemanticRole
    method_version: NonBlank
    instruction_hash: Digest
    registry_id: NonBlank = APPROVED_REGISTRY
    mode: Literal["SEMANTIC_RUNNER", "PORT_PROTOCOL"]
    recovery: bool = False


def validate_method_registration(method: ReportMethodRegistration) -> None:
    method = ReportMethodRegistration.model_validate(method.model_dump(mode="json"))
    if method.registry_id != APPROVED_REGISTRY or method.instruction_hash != canonical_hash(
        registered_instruction(
            method.role, method.method_version, recovery=method.recovery, mode=method.mode
        )
    ):
        raise ValueError("method version/instruction is not approved")


class ReportRoleConfiguration(ReportScoped):
    contract_kind: Literal["phase8-report-role-configuration-v1"] = (
        "phase8-report-role-configuration-v1"
    )
    configuration_id: NonBlank
    role: ReportSemanticRole
    method_version: NonBlank
    instruction_hash: Digest
    port: ReportPortConfiguration

    @property
    def method(self) -> ReportMethodRegistration:
        if self.port.mode == "NOT_CONFIGURED":
            raise ValueError("unconfigured role has no invocation method")
        return ReportMethodRegistration(
            scope=self.scope,
            compilation_id=self.compilation_id,
            role=self.role,
            method_version=self.method_version,
            instruction_hash=self.instruction_hash,
            mode=self.port.mode,
        )


class ReportCompilationConfiguration(ReportContract):
    contract_kind: Literal["phase8-report-compilation-configuration-v1"] = (
        "phase8-report-compilation-configuration-v1"
    )
    roles: tuple[ReportRoleConfiguration, ...] = ()
    deterministic_versions: tuple[NonBlank, ...] = DETERMINISTIC_VERSIONS

    @model_validator(mode="after")
    def distinct_roles(self) -> "ReportCompilationConfiguration":
        if len({role.role for role in self.roles}) != len(self.roles):
            raise ValueError("duplicate report role configuration")
        if self.roles and any(
            (role.scope, role.compilation_id) != (self.roles[0].scope, self.roles[0].compilation_id)
            for role in self.roles
        ):
            raise ValueError("role configuration scope differs")
        if len(set(self.deterministic_versions)) != len(self.deterministic_versions):
            raise ValueError("duplicate deterministic policy version")
        return self


def approved_role_configuration(
    scope: ReportScope,
    compilation_id: str,
    role: ReportSemanticRole,
    port: ReportPortConfiguration,
    *,
    method_version: str | None = None,
) -> ReportRoleConfiguration:
    version = method_version if method_version is not None else DEFAULT_SEMANTIC_METHODS[role]
    if (role, version) not in SUPPORTED_SEMANTIC_METHODS:
        raise ValueError("method version is not supported")
    if port.mode == "NOT_CONFIGURED":
        instruction_hash = canonical_hash({"role": role.value, "mode": "NOT_CONFIGURED"})
    else:
        instruction_hash = canonical_hash(registered_instruction(role, version, mode=port.mode))
    config = ReportRoleConfiguration(
        scope=scope,
        compilation_id=compilation_id,
        configuration_id="pending",
        role=role,
        method_version=version,
        instruction_hash=instruction_hash,
        port=port,
    )
    identity = "p8config_" + canonical_hash(
        config.model_dump(mode="json", exclude={"configuration_id"})
    )
    return config.model_copy(update={"configuration_id": identity})


def bind_compilation_configuration(
    configuration: ReportCompilationConfiguration, scope: ReportScope, compilation_id: str
) -> ReportCompilationConfiguration:
    return ReportCompilationConfiguration(
        roles=tuple(
            approved_role_configuration(
                scope, compilation_id, role.role, role.port, method_version=role.method_version
            )
            for role in configuration.roles
        ),
        deterministic_versions=configuration.deterministic_versions,
    )


def configuration_key_content(
    configuration: ReportCompilationConfiguration,
) -> dict[str, JsonValue]:
    """Exclude allocated attempt bindings to avoid a key/compilation-ID cycle."""
    return {
        "roles": [
            role.model_dump(mode="json", exclude={"scope", "compilation_id", "configuration_id"})
            for role in sorted(configuration.roles, key=lambda role: role.role)
        ],
        "deterministic_versions": list(configuration.deterministic_versions),
    }


class ReportExecutionObservations(ReportContract):
    contract_kind: Literal["phase8-report-execution-observations-v1"] = (
        "phase8-report-execution-observations-v1"
    )
    observed_at: UTCDateTime
    tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)


class ReportExecutionRecord(ReportScoped):
    contract_kind: Literal["phase8-report-execution-record-v1"] = (
        "phase8-report-execution-record-v1"
    )
    invocation_id: NonBlank
    role: ReportSemanticRole
    task_name: NonBlank
    method_version: NonBlank
    actual_instruction_hash: Digest
    configuration_id: NonBlank
    request_hash: Digest
    raw_response_hash: Digest | None = None
    validated_proposal_hash: Digest | None = None
    outcome: Literal["VALIDATED", "INVALID", "PROVIDER_FAILURE"]
    recovery: bool = False
    predecessor_ref: NonBlank | None = None
    observations: ReportExecutionObservations

    @model_validator(mode="after")
    def outcome_hashes(self) -> "ReportExecutionRecord":
        if self.outcome == "VALIDATED" and (
            self.raw_response_hash is None or self.validated_proposal_hash is None
        ):
            raise ValueError("validated execution requires raw response and proposal hashes")
        if self.outcome != "VALIDATED" and self.validated_proposal_hash is not None:
            raise ValueError("failed execution cannot certify a validated proposal")
        if self.recovery and (
            self.predecessor_ref is None or self.role == ReportSemanticRole.REPAIR
        ):
            raise ValueError("recovery requires predecessor and cannot repair")
        return self
