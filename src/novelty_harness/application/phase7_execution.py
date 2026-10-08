"""Trusted application invocation envelopes for model adapters and protocol ports."""

from pydantic import JsonValue

from novelty_harness.adjudication.execution import SEMANTIC_METHODS
from novelty_harness.adjudication.models import (
    SemanticConfiguration,
    SemanticExecutionRecord,
    TargetScoped,
)
from novelty_harness.application.phase7_model_adapter import Phase7ModelAdapter
from novelty_harness.runtime.tracing.hashing import canonical_hash


def invocation_configuration(port: object, kind: str, scope: TargetScoped) -> SemanticConfiguration:
    version, instruction = SEMANTIC_METHODS[kind]
    if isinstance(port, Phase7ModelAdapter):
        configuration = port.execution_configuration
        mode = "SEMANTIC_RUNNER"
        provider = str(configuration["provider"])
        config_id = port.model_config_id
    else:
        implementation = type(port).__module__ + "." + type(port).__qualname__
        declared = getattr(port, "model_config_id", None)
        configuration = {"implementation": implementation, "declared_config_id": declared}
        mode = "PORT_PROTOCOL"
        provider = "port:" + implementation
        config_id = (
            str(declared) if declared is not None else "p7model_" + canonical_hash(configuration)
        )
    return SemanticConfiguration.model_validate(
        {
            **scope.model_dump(
                include={
                    "assessment_id",
                    "assessment_context_id",
                    "phase6_snapshot_id",
                    "target_id",
                }
            ),
            "semantic_kind": kind,
            "prompt_version": version,
            "prompt_hash": canonical_hash(instruction),
            "model_config_id": config_id,
            "provider_name": provider,
            "execution_mode": mode,
            "configuration": configuration,
        }
    )


def completed_invocation(
    port: object,
    proposal: TargetScoped,
    configuration: SemanticConfiguration,
    configuration_id: str,
    request: JsonValue,
) -> SemanticExecutionRecord:
    if invocation_configuration(port, configuration.semantic_kind, proposal) != configuration:
        raise ValueError("Semantic invocation configuration changed")
    if isinstance(port, Phase7ModelAdapter):
        execution = port.execution_for(proposal)
    else:
        execution = SemanticExecutionRecord(
            invocation_prompt_hash=configuration.prompt_hash,
            prompt_version=configuration.prompt_version,
            prompt_hash=configuration.prompt_hash,
            model_config_id=configuration.model_config_id,
            provider_name=configuration.provider_name,
            execution_mode="PORT_PROTOCOL",
            request_hash=canonical_hash(request),
            response_hash=canonical_hash(proposal),
            proposal_hash=canonical_hash(proposal),
        )
    return execution.model_copy(update={"configuration_id": configuration_id})
