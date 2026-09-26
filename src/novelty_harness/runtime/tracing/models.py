from pydantic import ConfigDict, Field, JsonValue

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import AssessmentStage, TraceStatus
from novelty_harness.domain.ids import AssessmentId, MCUId, TraceEventId


class TraceEvent(ContractModel):
    model_config = ConfigDict(frozen=True)
    event_id: TraceEventId
    assessment_id: AssessmentId
    occurred_at: UTCDateTime
    stage: AssessmentStage
    component: str
    status: TraceStatus
    mcu_id: MCUId | None = None
    provider_name: str | None = None
    provider_version: str | None = None
    request_hash: str | None = None
    response_hash: str | None = None
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    estimated_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reason_code: str | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)
