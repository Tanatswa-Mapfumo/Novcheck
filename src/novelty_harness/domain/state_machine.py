import logging
from datetime import datetime
from typing import Literal

from novelty_harness.domain.assessment import AssessmentRecord, LifecycleEvent
from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import AssessmentStage, AssessmentStatus
from novelty_harness.domain.ids import new_lifecycle_event_id

_STAGES = tuple(AssessmentStage)
_REPORTABLE = {AssessmentStatus.ACTIVE, AssessmentStatus.PARTIAL, AssessmentStatus.ABSTAINED}
_STATUS_TARGETS: dict[AssessmentStatus, set[AssessmentStatus]] = {
    AssessmentStatus.ACTIVE: {
        AssessmentStatus.PARTIAL,
        AssessmentStatus.ABSTAINED,
        AssessmentStatus.BLOCKED,
        AssessmentStatus.FAILED,
    },
    AssessmentStatus.PARTIAL: {
        AssessmentStatus.ACTIVE,
        AssessmentStatus.ABSTAINED,
        AssessmentStatus.BLOCKED,
        AssessmentStatus.FAILED,
    },
    AssessmentStatus.ABSTAINED: {
        AssessmentStatus.ACTIVE,
        AssessmentStatus.PARTIAL,
        AssessmentStatus.BLOCKED,
        AssessmentStatus.FAILED,
    },
    AssessmentStatus.BLOCKED: {AssessmentStatus.ACTIVE, AssessmentStatus.FAILED},
    AssessmentStatus.FAILED: set(),
    AssessmentStatus.COMPLETED: set(),
}


class InvalidLifecycleTransition(ValueError):
    def __init__(self, current: str, target: str) -> None:
        message = f"Invalid lifecycle transition: {current} -> {target}"
        logging.getLogger(__name__).error(message)
        super().__init__(message)


def can_advance_stage(current: AssessmentStage, target: AssessmentStage) -> bool:
    return _STAGES.index(target) == _STAGES.index(current) + 1


def can_change_status(current: AssessmentStatus, target: AssessmentStatus) -> bool:
    return target in _STATUS_TARGETS[current]


def _transition(
    record: AssessmentRecord,
    field: Literal["stage", "status"],
    target: AssessmentStage | AssessmentStatus,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None,
) -> tuple[AssessmentRecord, LifecycleEvent]:
    if not actor.strip() or not reason.strip():
        raise ValueError("actor and reason must contain non-whitespace text")
    event = LifecycleEvent(
        event_id=new_lifecycle_event_id(),
        assessment_id=record.assessment_id,
        event_type="STAGE_TRANSITION" if field == "stage" else "STATUS_TRANSITION",
        from_value=getattr(record, field).value,
        to_value=target.value,
        actor=actor,
        reason=reason,
        occurred_at=occurred_at if occurred_at is not None else utc_now(),
    )
    updated = record.model_copy(update={field: target, "updated_at": event.occurred_at}, deep=True)
    return updated, event


def advance_stage(
    record: AssessmentRecord,
    target: AssessmentStage,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> tuple[AssessmentRecord, LifecycleEvent]:
    if record.status not in _REPORTABLE or not can_advance_stage(record.stage, target):
        raise InvalidLifecycleTransition(
            f"{record.stage.value}/{record.status.value}", target.value
        )
    return _transition(record, "stage", target, actor=actor, reason=reason, occurred_at=occurred_at)


def change_status(
    record: AssessmentRecord,
    target: AssessmentStatus,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> tuple[AssessmentRecord, LifecycleEvent]:
    if not can_change_status(record.status, target):
        raise InvalidLifecycleTransition(record.status.value, target.value)
    return _transition(
        record, "status", target, actor=actor, reason=reason, occurred_at=occurred_at
    )


def complete_assessment(
    record: AssessmentRecord,
    *,
    actor: str,
    reason: str,
    occurred_at: datetime | None = None,
) -> tuple[AssessmentRecord, LifecycleEvent]:
    if record.stage != AssessmentStage.REPORTED or record.status not in _REPORTABLE:
        raise InvalidLifecycleTransition(
            f"{record.stage.value}/{record.status.value}", AssessmentStatus.COMPLETED.value
        )
    return _transition(
        record,
        "status",
        AssessmentStatus.COMPLETED,
        actor=actor,
        reason=reason,
        occurred_at=occurred_at,
    )
