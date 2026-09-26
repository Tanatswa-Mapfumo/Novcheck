import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from novelty_harness.domain.enums import AssessmentStage, EvidenceFamily, TraceStatus
from novelty_harness.ports.models import ProviderCapabilities
from novelty_harness.runtime.logging import configure_logging
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink, JsonlTraceSink, redact_mapping


def event(event_id: str = "trace_first") -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        assessment_id="asm_test",
        occurred_at=datetime(2026, 9, 26, tzinfo=UTC),
        stage=AssessmentStage.RECEIVED,
        component="test",
        status=TraceStatus.SUCCESS,
        data={"nested": [{"OPENAI_API_KEY": "test-only-secret"}], "input_tokens": 3},
    )


def test_canonical_hash_is_order_independent_and_content_sensitive() -> None:
    assert canonical_hash({"a": 1, "b": {"c": 2, "d": 3}}) == canonical_hash(
        {"b": {"d": 3, "c": 2}, "a": 1}
    )
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
    assert (
        canonical_hash({"a": 1})
        == "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862"
    )
    assert canonical_hash(event()) == canonical_hash(event())
    caps = ProviderCapabilities(
        evidence_families={EvidenceFamily.SOFTWARE, EvidenceFamily.SCHOLARLY}
    )
    data = caps.model_dump(mode="json")
    data["evidence_families"] = ["SCHOLARLY", "SOFTWARE"]
    assert canonical_hash(caps) == canonical_hash(data)
    with pytest.raises(ValueError):
        canonical_hash({"not_json": float("nan")})


def test_jsonl_sink_appends_redacted_round_trippable_events(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    sink = JsonlTraceSink(path)
    first, second = event(), event("trace_second")
    sink.emit(first)
    original_line = path.read_text()
    sink.emit(second)
    assert path.read_text().startswith(original_line)
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert [TraceEvent.model_validate_json(line).event_id for line in lines] == [
        "trace_first",
        "trace_second",
    ]
    assert "test-only-secret" not in path.read_text()
    assert json.loads(lines[0])["data"]["input_tokens"] == 3
    assert first.data["nested"] == [{"OPENAI_API_KEY": "test-only-secret"}]


def test_memory_sink_preserves_order_and_snapshots() -> None:
    sink = InMemoryTraceSink()
    first, second = event(), event("trace_second")
    sink.emit(first)
    sink.emit(second)
    first.data["later"] = "mutation"
    assert [item.event_id for item in sink.events] == ["trace_first", "trace_second"]
    assert "later" not in sink.events[0].data
    assert sink.events[0].data["nested"] == [{"OPENAI_API_KEY": "[REDACTED]"}]
    sink.events[0].data["external_mutation"] = True
    assert "external_mutation" not in sink.events[0].data


def test_concurrent_jsonl_writes_do_not_interleave(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    sinks = [JsonlTraceSink(path), JsonlTraceSink(path)]

    def emit(index: int) -> None:
        sinks[index % 2].emit(event(f"trace_{index}"))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(emit, range(40)))
    events = [TraceEvent.model_validate_json(line) for line in path.read_text().splitlines()]
    assert len(events) == 40
    assert len({item.event_id for item in events}) == 40


@pytest.mark.parametrize("field", ["latency_ms", "estimated_cost", "input_tokens", "output_tokens"])
def test_trace_rejects_negative_measurements(field: str) -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate({**event().model_dump(), field: -1})


def test_trace_schema_rejects_naive_timestamps_and_extra_fields() -> None:
    for extra in ({"occurred_at": datetime(2026, 9, 26)}, {"extra": True}):
        with pytest.raises(ValidationError):
            TraceEvent.model_validate({**event().model_dump(), **extra})


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "auth_token",
        "password",
        "secret",
        "authorization",
        "bearer",
        "OPENAI_API_KEY",
        "providerApiKey",
        "CLIENT-SECRET",
    ],
)
def test_recursive_redaction_preserves_counters_and_original(key: str) -> None:
    original = {"outer": [{key: "test-only-secret", "input_tokens": 12}], "output_tokens": 9}
    assert redact_mapping(original) == {
        "outer": [{key: "[REDACTED]", "input_tokens": 12}],
        "output_tokens": 9,
    }
    assert original["outer"] == [{key: "test-only-secret", "input_tokens": 12}]


def test_json_logging_contains_required_fields_and_utc_time(capsys) -> None:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        configure_logging("INFO")
        logging.getLogger("test.logger").info("fixture message")
        record = json.loads(capsys.readouterr().err)
        assert record["level"] == "INFO"
        assert record["logger"] == "test.logger"
        assert record["message"] == "fixture message"
        assert datetime.fromisoformat(record["timestamp"]).utcoffset().total_seconds() == 0
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = handlers
        root.setLevel(level)


def test_trace_sinks_redact_github_credentials_without_hiding_token_counters(
    tmp_path: Path,
) -> None:
    value = event().model_copy(
        update={
            "data": {
                "credentials": {"GITHUB_TOKEN": "test-only-github-secret"},
                "input_tokens": 10,
                "output_tokens": 20,
            }
        }
    )
    memory = InMemoryTraceSink()
    memory.emit(value)
    expected = {
        "credentials": {"GITHUB_TOKEN": "[REDACTED]"},
        "input_tokens": 10,
        "output_tokens": 20,
    }
    assert memory.events[0].data == expected
    path = tmp_path / "github-trace.jsonl"
    JsonlTraceSink(path).emit(value)
    assert TraceEvent.model_validate_json(path.read_text()).data == expected
    assert "test-only-github-secret" not in path.read_text()


@pytest.mark.parametrize("number", [float("inf"), float("-inf"), float("nan")])
def test_trace_nested_json_rejects_nonfinite_numbers(number: float) -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate({**event().model_dump(), "data": {"nested": [number]}})


@pytest.mark.parametrize("sink_type", [InMemoryTraceSink, JsonlTraceSink])
def test_trace_sinks_revalidate_mutated_nested_data(sink_type, tmp_path: Path) -> None:
    value = event()
    value.data["later"] = float("inf")
    sink = sink_type() if sink_type is InMemoryTraceSink else sink_type(tmp_path / "invalid.jsonl")
    with pytest.raises(ValidationError):
        sink.emit(value)
