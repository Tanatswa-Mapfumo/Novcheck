import logging
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from novelty_harness.domain.assessment import AssessmentRecord, AssessmentRequest
from novelty_harness.domain.enums import AssessmentStage as Stage
from novelty_harness.domain.enums import AssessmentStatus as Status
from novelty_harness.domain.state_machine import (
    InvalidLifecycleTransition,
    advance_stage,
    can_advance_stage,
    can_change_status,
    change_status,
    complete_assessment,
)

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)
STAGES = list(Stage)
STATUS_POLICY = {
    Status.ACTIVE: {Status.PARTIAL, Status.ABSTAINED, Status.BLOCKED, Status.FAILED},
    Status.PARTIAL: {Status.ACTIVE, Status.ABSTAINED, Status.BLOCKED, Status.FAILED},
    Status.ABSTAINED: {Status.ACTIVE, Status.PARTIAL, Status.BLOCKED, Status.FAILED},
    Status.BLOCKED: {Status.ACTIVE, Status.FAILED},
    Status.FAILED: set(),
    Status.COMPLETED: set(),
}


def record(stage: Stage = Stage.RECEIVED, status: Status = Status.ACTIVE) -> AssessmentRecord:
    return AssessmentRecord(
        assessment_id="asm_test",
        request=AssessmentRequest(idea_id="idea_test", input_text="x", as_of=date(2026, 9, 26)),
        stage=stage,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize("current", STAGES)
@pytest.mark.parametrize("target", STAGES)
def test_only_adjacent_forward_stages_are_allowed(current: Stage, target: Stage) -> None:
    allowed = STAGES.index(target) == STAGES.index(current) + 1
    assert can_advance_stage(current, target) is allowed
    before = record(current)
    if not allowed:
        with pytest.raises(InvalidLifecycleTransition) as error:
            advance_stage(before, target, actor="test", reason="transition")
        assert current.value in str(error.value)
        assert target.value in str(error.value)
        return
    after, event = advance_stage(
        before, target, actor="test", reason="transition", occurred_at=NOW + timedelta(seconds=1)
    )
    assert after is not before
    assert before.stage == current
    assert after.stage == target
    assert after.updated_at == NOW + timedelta(seconds=1)
    assert event.assessment_id == before.assessment_id
    assert event.from_value == current.value
    assert event.to_value == target.value
    assert event.event_type == "STAGE_TRANSITION"
    assert event.actor == "test" and event.reason == "transition"
    assert event.occurred_at == after.updated_at


@pytest.mark.parametrize("status", list(Status))
def test_run_status_controls_stage_progression(status: Status) -> None:
    before = record(status=status)
    if status in (Status.BLOCKED, Status.FAILED, Status.COMPLETED):
        with pytest.raises(InvalidLifecycleTransition):
            advance_stage(before, Stage.NORMALIZED, actor="test", reason="test")
    else:
        after, _ = advance_stage(before, Stage.NORMALIZED, actor="test", reason="test")
        assert after.status == status
        assert after.stage == Stage.NORMALIZED


@pytest.mark.parametrize("current", list(Status))
@pytest.mark.parametrize("target", list(Status))
def test_status_policy_and_audit(current: Status, target: Status) -> None:
    allowed = target in STATUS_POLICY[current]
    assert can_change_status(current, target) is allowed
    before = record(status=current)
    if not allowed:
        with pytest.raises(InvalidLifecycleTransition):
            change_status(before, target, actor="test", reason="test")
    else:
        after, event = change_status(before, target, actor="test", reason="test", occurred_at=NOW)
        assert before.status == current
        assert after.status == target
        assert after.stage == before.stage
        assert event.from_value == current.value
        assert event.to_value == target.value
        assert event.event_type == "STATUS_TRANSITION"
        assert event.occurred_at == NOW


@pytest.mark.parametrize("status", list(Status))
def test_completion_requires_reported_and_eligible_status(status: Status) -> None:
    with pytest.raises(InvalidLifecycleTransition):
        complete_assessment(record(status=status), actor="test", reason="test")
    before = record(Stage.REPORTED, status)
    if status in (Status.ACTIVE, Status.PARTIAL, Status.ABSTAINED):
        after, event = complete_assessment(before, actor="test", reason="finished", occurred_at=NOW)
        assert after.stage == Stage.REPORTED
        assert after.status == Status.COMPLETED
        assert before.status == status
        assert event.to_value == "COMPLETED"
    else:
        with pytest.raises(InvalidLifecycleTransition):
            complete_assessment(before, actor="test", reason="test")


@pytest.mark.parametrize("operation", [advance_stage, change_status, complete_assessment])
@pytest.mark.parametrize("field", ["actor", "reason"])
def test_transition_requires_nonblank_audit_fields(operation, field: str) -> None:
    kwargs = {"actor": "test", "reason": "test", field: " \n"}
    args = (
        (record(Stage.REPORTED),)
        if operation is complete_assessment
        else (
            (record(), Stage.NORMALIZED)
            if operation is advance_stage
            else (record(), Status.PARTIAL)
        )
    )
    with pytest.raises(ValueError):
        operation(*args, **kwargs)


def test_timestamps_are_validated_and_normalized() -> None:
    with pytest.raises(ValidationError):
        advance_stage(
            record(),
            Stage.NORMALIZED,
            actor="test",
            reason="test",
            occurred_at=datetime(2026, 9, 26),
        )
    after, event = advance_stage(
        record(),
        Stage.NORMALIZED,
        actor="test",
        reason="test",
        occurred_at=datetime(2026, 9, 26, 13, tzinfo=timezone(timedelta(hours=1))),
    )
    assert after.updated_at == NOW
    assert event.occurred_at.tzinfo == UTC


def test_invalid_transition_is_an_explicit_logged_error(caplog) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(InvalidLifecycleTransition):
        advance_stage(record(), Stage.REPORTED, actor="test", reason="test")
    assert "RECEIVED" in caplog.text
    assert "REPORTED" in caplog.text
