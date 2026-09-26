import socket
from datetime import UTC, date, datetime

import pytest

from novelty_harness.domain.assessment import AssessmentRecord, AssessmentRequest, LifecycleEvent
from novelty_harness.domain.enums import (
    AssessmentStage as Stage,
)
from novelty_harness.domain.enums import (
    AssessmentStatus as Status,
)
from novelty_harness.domain.enums import (
    TraceStatus,
)
from novelty_harness.domain.ids import new_trace_event_id
from novelty_harness.domain.state_machine import advance_stage, change_status, complete_assessment
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.providers import _MockProvider


def test_phase0_lifecycle_smoke_without_providers_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Phase 0 lifecycle smoke must not call providers or open sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(_MockProvider, "_respond", forbidden)
    time = datetime(2026, 9, 26, 12, tzinfo=UTC)
    request = AssessmentRequest(
        idea_id="idea_smoke", input_text="Lifecycle fixture", as_of=date(2026, 9, 26)
    )
    record = AssessmentRecord(
        assessment_id="asm_smoke", request=request, created_at=time, updated_at=time
    )
    assert (record.stage, record.status) == (Stage.RECEIVED, Status.ACTIVE)
    sink = InMemoryTraceSink()
    lifecycle: list[LifecycleEvent] = []

    def trace(event: LifecycleEvent) -> None:
        lifecycle.append(event)
        sink.emit(
            TraceEvent(
                event_id=new_trace_event_id(),
                assessment_id=record.assessment_id,
                occurred_at=event.occurred_at,
                stage=record.stage,
                component=event.actor,
                status=TraceStatus.SUCCESS,
                reason_code=event.event_type,
                data={"lifecycle_event": event.model_dump(mode="json")},
            )
        )

    for target in list(Stage)[1:]:
        if target == Stage.SEARCH_PLANNED:
            record, event = change_status(
                record, Status.PARTIAL, actor="smoke", reason="fixture partial", occurred_at=time
            )
            trace(event)
        if target == Stage.SCREENING:
            assert record.status == Status.PARTIAL
            record, event = change_status(
                record, Status.ACTIVE, actor="smoke", reason="fixture resume", occurred_at=time
            )
            trace(event)
        if target == Stage.FINDINGS_FROZEN:
            record, event = change_status(
                record,
                Status.ABSTAINED,
                actor="smoke",
                reason="fixture abstention",
                occurred_at=time,
            )
            trace(event)
        record, event = advance_stage(
            record, target, actor="smoke", reason="contract progression", occurred_at=time
        )
        trace(event)
    assert (record.stage, record.status) == (Stage.REPORTED, Status.ABSTAINED)
    record, event = complete_assessment(
        record, actor="smoke", reason="fixture complete", occurred_at=time
    )
    trace(event)
    assert (record.stage, record.status) == (Stage.REPORTED, Status.COMPLETED)
    assert AssessmentRecord.model_validate_json(record.model_dump_json()) == record
    assert len(lifecycle) == len(sink.events) == 21
    for event, traced in zip(lifecycle, sink.events, strict=True):
        assert LifecycleEvent.model_validate_json(event.model_dump_json()) == event
        assert TraceEvent.model_validate_json(traced.model_dump_json()) == traced
        assert LifecycleEvent.model_validate(traced.data["lifecycle_event"]) == event
