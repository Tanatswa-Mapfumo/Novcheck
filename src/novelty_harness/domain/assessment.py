from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, field_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import AssessmentStage, AssessmentStatus, ResearchMode
from novelty_harness.domain.ids import AssessmentId, IdeaId, LifecycleEventId


class AssessmentRequest(ContractModel):
    idea_id: IdeaId
    input_text: str
    as_of: date
    mode: ResearchMode = ResearchMode.STANDARD
    title: str | None = None
    user_evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("input_text")
    @classmethod
    def require_input(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("input_text must contain non-whitespace text")
        return value


class AssessmentRecord(ContractModel):
    model_config = ConfigDict(frozen=True)
    assessment_id: AssessmentId
    request: AssessmentRequest
    stage: AssessmentStage = AssessmentStage.RECEIVED
    status: AssessmentStatus = AssessmentStatus.ACTIVE
    created_at: UTCDateTime
    updated_at: UTCDateTime


class LifecycleEvent(ContractModel):
    model_config = ConfigDict(frozen=True)
    event_id: LifecycleEventId
    assessment_id: AssessmentId
    event_type: Literal["STAGE_TRANSITION", "STATUS_TRANSITION"]
    from_value: str
    to_value: str
    actor: str
    reason: str
    occurred_at: UTCDateTime
