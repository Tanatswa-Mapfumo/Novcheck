from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from novelty_harness.domain.assessment import AssessmentRecord, AssessmentRequest, LifecycleEvent
from novelty_harness.domain.enums import AssessmentStage, AssessmentStatus, ResearchMode


def test_request_preserves_original_input_and_round_trips() -> None:
    request = AssessmentRequest(
        idea_id="idea_test", input_text="  Original input\n", as_of=date(2026, 9, 26)
    )
    assert request.input_text == "  Original input\n"
    assert request.mode == ResearchMode.STANDARD
    assert AssessmentRequest.model_validate_json(request.model_dump_json()) == request
    other = AssessmentRequest(idea_id="idea_other", input_text="x", as_of=request.as_of)
    request.user_evidence_refs.append("user-file")
    request.metadata["unknown"] = None
    assert other.user_evidence_refs == []
    assert other.metadata == {}


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_request_rejects_blank_input(text: str) -> None:
    with pytest.raises(ValidationError):
        AssessmentRequest(idea_id="idea_test", input_text=text, as_of=date(2026, 9, 26))


def test_record_and_event_round_trip_with_utc_timestamps() -> None:
    time = datetime(2026, 9, 26, 13, tzinfo=timezone(timedelta(hours=1)))
    request = AssessmentRequest(idea_id="idea_test", input_text="x", as_of=date(2026, 9, 26))
    record = AssessmentRecord(
        assessment_id="asm_test", request=request, created_at=time, updated_at=time
    )
    assert record.stage == AssessmentStage.RECEIVED
    assert record.status == AssessmentStatus.ACTIVE
    assert record.created_at.hour == 12
    assert record.created_at.tzinfo == UTC
    assert AssessmentRecord.model_validate_json(record.model_dump_json()) == record
    event = LifecycleEvent(
        event_id="life_test",
        assessment_id=record.assessment_id,
        event_type="STAGE_TRANSITION",
        from_value="RECEIVED",
        to_value="NORMALIZED",
        actor="test",
        reason="test transition",
        occurred_at=time,
    )
    assert LifecycleEvent.model_validate_json(event.model_dump_json()) == event
    assert event.occurred_at.tzinfo == UTC
    for field in ("created_at", "updated_at"):
        data = record.model_dump()
        data[field] = datetime(2026, 9, 26)
        with pytest.raises(ValidationError):
            AssessmentRecord.model_validate(data)
    with pytest.raises(ValidationError):
        LifecycleEvent.model_validate({**event.model_dump(), "occurred_at": datetime(2026, 9, 26)})


def test_assessment_contracts_reject_extra_fields_and_invalid_enum_strings() -> None:
    request = dict(idea_id="idea_test", input_text="x", as_of="2026-09-26")
    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate({**request, "unknown": True})
    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate({**request, "mode": "AUTO"})
    record = dict(
        assessment_id="asm_test",
        request=request,
        created_at="2026-09-26T12:00:00Z",
        updated_at="2026-09-26T12:00:00Z",
    )
    for field, value in (("stage", "UNKNOWN"), ("status", "UNKNOWN"), ("extra", 1)):
        with pytest.raises(ValidationError):
            AssessmentRecord.model_validate({**record, field: value})


def test_completed_record_requires_reported_stage_on_json_load() -> None:
    data = {
        "assessment_id": "asm_test",
        "request": {"idea_id": "idea_test", "input_text": "x", "as_of": "2026-09-26"},
        "stage": "RECEIVED",
        "status": "COMPLETED",
        "created_at": "2026-09-26T12:00:00Z",
        "updated_at": "2026-09-26T12:00:00Z",
    }
    import json

    with pytest.raises(ValidationError):
        AssessmentRecord.model_validate_json(json.dumps(data))
    data["stage"] = "REPORTED"
    assert AssessmentRecord.model_validate(data).status == AssessmentStatus.COMPLETED


@pytest.mark.parametrize(
    "changes",
    [
        {"from_value": "UNKNOWN_STAGE"},
        {"to_value": "COMPLETED"},
        {"actor": " \n"},
        {"reason": " \t"},
        {"to_value": "REPORTED"},
        {"event_type": "STATUS_TRANSITION", "from_value": "ACTIVE", "to_value": "NORMALIZED"},
        {"event_type": "STATUS_TRANSITION", "from_value": "FAILED", "to_value": "ACTIVE"},
        {"event_type": "STATUS_TRANSITION", "from_value": "BLOCKED", "to_value": "COMPLETED"},
    ],
)
def test_lifecycle_artifact_rejects_invalid_values_and_blank_audit_fields(
    changes: dict[str, str],
) -> None:
    data = {
        "event_id": "life_test",
        "assessment_id": "asm_test",
        "event_type": "STAGE_TRANSITION",
        "from_value": "RECEIVED",
        "to_value": "NORMALIZED",
        "actor": "test",
        "reason": "test",
        "occurred_at": "2026-09-26T12:00:00Z",
    }
    with pytest.raises(ValidationError):
        LifecycleEvent.model_validate({**data, **changes})


@pytest.mark.parametrize("number", [float("inf"), float("-inf"), float("nan")])
def test_request_metadata_rejects_nested_nonfinite_numbers(number: float) -> None:
    with pytest.raises(ValidationError):
        AssessmentRequest(
            idea_id="idea_test",
            input_text="x",
            as_of=date(2026, 9, 26),
            metadata={"nested": [number]},
        )
