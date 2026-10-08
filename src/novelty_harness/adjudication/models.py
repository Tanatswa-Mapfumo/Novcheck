"""Shared identities and run vocabulary for real Phase 7 artifacts."""

from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, JsonValue

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.ids import AssessmentId


class Phase7RunState(StrEnum):
    CASE_BUILT = "CASE_BUILT"
    FIRST_PASSES_COMPLETE = "FIRST_PASSES_COMPLETE"
    ESCALATION_PENDING = "ESCALATION_PENDING"
    SUPERSEDED_BY_NEW_ASSESSMENT_STATE = "SUPERSEDED_BY_NEW_ASSESSMENT_STATE"
    JUDGING = "JUDGING"
    FROZEN = "FROZEN"
    ABSTAINED = "ABSTAINED"
    FAILED = "FAILED"


class Phase7Scoped(ContractModel):
    model_config = ConfigDict(frozen=True)
    assessment_id: AssessmentId
    assessment_context_id: str
    phase6_snapshot_id: str


class TargetScoped(Phase7Scoped):
    target_id: str


class TargetRef(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-target-ref-v1"] = "phase7-target-ref-v1"
    kind: Literal["MCU", "COMBINATION"]
    id: str


class Phase7RunRecord(Phase7Scoped):
    contract_kind: Literal["phase7-run-v1"] = "phase7-run-v1"
    run_id: str
    attempt_token: str
    case_id: str
    state: Phase7RunState = Phase7RunState.CASE_BUILT


class Phase7RunTransition(Phase7Scoped):
    contract_kind: Literal["phase7-run-transition-v1"] = "phase7-run-transition-v1"
    transition_id: str
    run_id: str
    predecessor_id: str | None = None
    state: Phase7RunState
    reason: str | None = None


class SemanticConfiguration(TargetScoped):
    """Application configuration sealed before semantic execution."""

    contract_kind: Literal["phase7-semantic-configuration-v1"] = "phase7-semantic-configuration-v1"
    semantic_kind: Literal["PROSECUTION_CASE", "DEFENSE_CASE", "REBUTTAL", "JUDGE_RUN"]
    prompt_version: str
    prompt_hash: str
    model_config_id: str
    provider_name: str
    execution_mode: Literal["SEMANTIC_RUNNER", "PORT_PROTOCOL"]
    configuration: dict[str, JsonValue]


class SemanticExecutionRecord(ContractModel):
    """Actual invocation and validated output; never model-proposed authority."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-semantic-execution-v1"] = "phase7-semantic-execution-v1"
    invocation_prompt_hash: str
    configuration_id: str = "unbound"
    prompt_version: str
    prompt_hash: str
    model_config_id: str
    provider_name: str
    execution_mode: Literal["SEMANTIC_RUNNER", "PORT_PROTOCOL"]
    request_hash: str
    response_hash: str
    proposal_hash: str
    model_name: str | None = None
    provider_version: str | None = None
    latency_ms: float | None = None


class Phase7Artifact(TargetScoped):
    contract_kind: Literal["phase7-artifact-v2"] = "phase7-artifact-v2"
    artifact_id: str
    run_id: str
    kind: str
    document_json: str
    execution: SemanticExecutionRecord | None = None
