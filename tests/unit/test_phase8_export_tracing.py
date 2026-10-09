"""Export ordering/delivery controls; mocks do not certify accepted authority."""

from types import SimpleNamespace

import pytest

from novelty_harness.application.phase8_exports import export_compiled_report
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.unit.reporting.test_contracts import _compilation


def export_shapes(monkeypatch):
    compilation = _compilation()
    report = SimpleNamespace(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        report_id="p8report_export_shape",
        accepted_at=compilation.started_at,
    )
    renditions = SimpleNamespace(
        json="{}",
        yaml="{}",
        markdown="# Report",
        renderer_version="p8-render-v1",
        json_digest="a" * 64,
        yaml_digest="b" * 64,
        markdown_digest="c" * 64,
    )
    loads = []

    def native_load(assessment_id, *, report_id):
        assert (assessment_id, report_id) == (report.scope.assessment_id, report.report_id)
        loads.append(report_id)
        return report

    monkeypatch.setattr(
        "novelty_harness.application.phase8_exports.render_compiled_report",
        lambda loaded: renditions if loaded is report else None,
    )
    return report, SimpleNamespace(load_compiled_report=native_load), loads


def test_export_trace_is_after_native_load_and_all_three_files(monkeypatch, tmp_path):
    report, repository, loads = export_shapes(monkeypatch)
    events = []
    writer = RunArtifactWriter(tmp_path)

    class Sink:
        def emit(self, event):
            assert loads == [report.report_id]
            directory = tmp_path / report.scope.assessment_id / "reports" / report.report_id
            assert all(
                (directory / name).is_file() for name in ("report.json", "report.yaml", "report.md")
            )
            events.append(event)

    paths = export_compiled_report(
        report.scope.assessment_id,
        report_id=report.report_id,
        repository=repository,
        artifact_writer=writer,
        trace_sink=Sink(),
    )
    assert len(paths) == 3 and len(events) == 1
    assert events[0].reason_code == "REPORT_EXPORT_COMPLETE"
    assert events[0].data["report_id"] == report.report_id
    assert events[0].data["rendition_digests"] == ["a" * 64, "b" * 64, "c" * 64]


def test_failed_export_trace_does_not_replace_io_failure_and_retry_is_stable(monkeypatch, tmp_path):
    report, repository, loads = export_shapes(monkeypatch)
    sink = InMemoryTraceSink()

    class FailingWriter(RunArtifactWriter):
        def write_text(self, aid, name, text):
            if name.endswith(".yaml"):
                raise OSError("Secret disk diagnostic must not enter trace")
            return super().write_text(aid, name, text)

    with pytest.raises(OSError):
        export_compiled_report(
            report.scope.assessment_id,
            report_id=report.report_id,
            repository=repository,
            artifact_writer=FailingWriter(tmp_path),
            trace_sink=sink,
        )
    assert sink.events[0].reason_code == "REPORT_EXPORT_FAILED"
    assert sink.events[0].data["completed_formats"] == ["json"]
    assert "Secret disk" not in str(sink.events[0])
    writer = RunArtifactWriter(tmp_path)
    first = export_compiled_report(
        report.scope.assessment_id,
        report_id=report.report_id,
        repository=repository,
        artifact_writer=writer,
        trace_sink=sink,
    )
    second = export_compiled_report(
        report.scope.assessment_id,
        report_id=report.report_id,
        repository=repository,
        artifact_writer=writer,
        trace_sink=sink,
    )
    assert first == second
    assert sink.events[1] == sink.events[2]
    assert len(loads) == 3


def test_export_sink_failure_preserves_all_outputs(monkeypatch, tmp_path, caplog):
    report, repository, _ = export_shapes(monkeypatch)

    class FailingSink:
        def emit(self, event):
            raise OSError("recorded sink outage")

    paths = export_compiled_report(
        report.scope.assessment_id,
        report_id=report.report_id,
        repository=repository,
        artifact_writer=RunArtifactWriter(tmp_path),
        trace_sink=FailingSink(),
    )
    assert all(p.is_file() for p in paths)
    assert "trace delivery failed" in caplog.text.lower()


def test_render_failure_is_traced_after_authority_load_without_outputs(monkeypatch, tmp_path):
    report, repository, loads = export_shapes(monkeypatch)
    error = OSError("Secret renderer diagnostic")

    def fail_render(loaded):
        assert loaded is report
        assert loads == [report.report_id]
        raise error

    monkeypatch.setattr(
        "novelty_harness.application.phase8_exports.render_compiled_report", fail_render
    )
    sink = InMemoryTraceSink()
    with pytest.raises(OSError) as raised:
        export_compiled_report(
            report.scope.assessment_id,
            report_id=report.report_id,
            repository=repository,
            artifact_writer=RunArtifactWriter(tmp_path),
            trace_sink=sink,
        )
    assert raised.value is error
    assert len(sink.events) == 1
    assert sink.events[0].reason_code == "REPORT_EXPORT_FAILED"
    assert sink.events[0].data["failure_stage"] == "RENDERING"
    assert sink.events[0].data["completed_formats"] == []
    assert sink.events[0].data["rendition_digests"] is None
    assert "Secret renderer" not in str(sink.events[0])
    assert not list(tmp_path.rglob("report.*"))
