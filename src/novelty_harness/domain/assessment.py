from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import AssessmentStage, AssessmentStatus, ResearchMode
from novelty_harness.domain.ids import AssessmentId, IdeaId, LifecycleEventId
from novelty_harness.domain.lifecycle_policy import (
    REPORTABLE_STATUSES,
    can_advance_stage,
    can_change_status,
)


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

    @model_validator(mode="after")
    def require_reported_completion(self) -> Self:
        if self.status == AssessmentStatus.COMPLETED and self.stage != AssessmentStage.REPORTED:
            raise ValueError("COMPLETED assessments must be at REPORTED")
        return self


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

    @field_validator("actor", "reason")
    @classmethod
    def require_audit_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("actor and reason must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def require_canonical_transition(self) -> Self:
        if self.event_type == "STAGE_TRANSITION":
            allowed = can_advance_stage(
                AssessmentStage(self.from_value), AssessmentStage(self.to_value)
            )
        else:
            current, target = AssessmentStatus(self.from_value), AssessmentStatus(self.to_value)
            allowed = (
                current in REPORTABLE_STATUSES
                if target == AssessmentStatus.COMPLETED
                else can_change_status(current, target)
            )
        if not allowed:
            raise ValueError(f"Invalid lifecycle artifact: {self.from_value} -> {self.to_value}")
        return self
