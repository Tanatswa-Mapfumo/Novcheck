"""Current method policy and exact repository execution joins."""

import json

from pydantic import JsonValue

from novelty_harness.adjudication.models import (
    Phase7Artifact,
    SemanticConfiguration,
    SemanticExecutionRecord,
)
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
from novelty_harness.runtime.tracing.hashing import canonical_hash

SEMANTIC_METHODS = {
    "PROSECUTION_CASE": (
        PROSECUTOR_PROMPT_VERSION,
        PROSECUTOR_INSTRUCTION + " When selected_target data is present, assess only that target.",
    ),
    "DEFENSE_CASE": (
        DEFENDER_PROMPT_VERSION,
        DEFENDER_INSTRUCTION + " When selected_target data is present, assess only that target.",
    ),
    "REBUTTAL": (REBUTTAL_PROMPT_VERSION, REBUTTAL_INSTRUCTION),
    "JUDGE_RUN": (JUDGE_RUBRIC_VERSION, JUDGE_INSTRUCTION),
}


def phase7_artifact_id(
    run_id: str, kind: str, document_json: str, execution: SemanticExecutionRecord | None = None
) -> str:
    payload: dict[str, JsonValue] = {"run_id": run_id, "kind": kind, "document_json": document_json}
    if execution is not None:
        payload["execution"] = execution.model_dump(mode="json", exclude={"latency_ms"})
    return "p7arg_" + canonical_hash(payload)


def validate_semantic_configuration(config: SemanticConfiguration) -> None:
    version, instruction = SEMANTIC_METHODS[config.semantic_kind]
    if config.prompt_version != version or config.prompt_hash != canonical_hash(instruction):
        raise ValueError("Semantic configuration prompt version/hash is not the approved method")
    if not config.provider_name or not config.model_config_id:
        raise ValueError("Semantic configuration provider/config identity is missing")
    if config.execution_mode == "SEMANTIC_RUNNER":
        if config.model_config_id != "p7model_" + canonical_hash(config.configuration):
            raise ValueError("Semantic model configuration hash differs")
        if config.configuration.get("provider") != config.provider_name:
            raise ValueError("Semantic provider configuration differs")


def validate_semantic_execution(
    artifact: Phase7Artifact, artifacts: tuple[Phase7Artifact, ...]
) -> None:
    if artifact.kind not in SEMANTIC_METHODS:
        if artifact.execution is not None:
            raise ValueError("Non-semantic artifact cannot claim a semantic execution")
        return
    execution = artifact.execution
    if execution is None:
        raise ValueError("Semantic artifact lacks authoritative execution provenance")
    registrations = [
        a
        for a in artifacts
        if a.kind == "SEMANTIC_CONFIGURATION" and a.artifact_id == execution.configuration_id
    ]
    if len(registrations) != 1:
        raise ValueError("Semantic execution has no committed configuration")
    registration = registrations[0]
    config = SemanticConfiguration.model_validate_json(registration.document_json)
    validate_semantic_configuration(config)
    if (
        registration.run_id,
        config.assessment_id,
        config.assessment_context_id,
        config.phase6_snapshot_id,
        config.target_id,
        config.semantic_kind,
    ) != (
        artifact.run_id,
        artifact.assessment_id,
        artifact.assessment_context_id,
        artifact.phase6_snapshot_id,
        artifact.target_id,
        artifact.kind,
    ):
        raise ValueError("Semantic execution configuration scope differs")
    for field in (
        "prompt_version",
        "prompt_hash",
        "model_config_id",
        "provider_name",
        "execution_mode",
    ):
        if getattr(execution, field) != getattr(config, field):
            raise ValueError("Semantic execution prompt/config differs from committed invocation")
    if config.execution_mode == "SEMANTIC_RUNNER":
        instruction = SEMANTIC_METHODS[artifact.kind][1]
        allowed_hashes = {
            canonical_hash(instruction + UNTRUSTED_CONTEXT_SUFFIX),
            canonical_hash(instruction + RECOVERY_INSTRUCTION + UNTRUSTED_CONTEXT_SUFFIX),
        }
        if execution.invocation_prompt_hash not in allowed_hashes:
            raise ValueError(
                "Semantic invocation prompt hash is not the approved instruction/recovery"
            )
        actual_config = config.configuration.get("config")
        if not isinstance(actual_config, dict) or execution.model_name != actual_config.get(
            "model"
        ):
            raise ValueError("Semantic execution model differs from invocation configuration")
    elif execution.invocation_prompt_hash != config.prompt_hash:
        raise ValueError("Port protocol prompt hash differs")
    document = json.loads(artifact.document_json)
    proposal = document["finding"] if artifact.kind == "JUDGE_RUN" else document
    if execution.proposal_hash != canonical_hash(proposal):
        raise ValueError("Semantic execution proposal hash differs")
    if "prompt_version" in proposal and proposal["prompt_version"] != execution.prompt_version:
        raise ValueError("Proposal prompt version differs from actual execution")
    if artifact.kind == "JUDGE_RUN" and (
        document["rubric_version"] != execution.prompt_version
        or document["model_config_id"] != execution.model_config_id
    ):
        raise ValueError("Judge rubric/model differs from actual execution")
    if not execution.request_hash or not execution.response_hash:
        raise ValueError("Semantic execution lacks request/response identity")
