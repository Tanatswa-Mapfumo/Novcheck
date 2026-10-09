"""Derived exports only after repository-authoritative report loading."""

import logging
from pathlib import Path

from pydantic import JsonValue

from novelty_harness.domain.enums import AssessmentStage, TraceStatus
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.reporting.ir import CompiledAssessmentReport
from novelty_harness.reporting.rendering import ReportRenditions, render_compiled_report
from novelty_harness.reporting.repository import ReportRepository
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink


class Phase8ReportingError(RuntimeError):
    """An operational report failure after upstream adjudication is frozen."""


def export_compiled_report(
    assessment_id: AssessmentId,
    *,
    report_id: str,
    repository: ReportRepository,
    artifact_writer: RunArtifactWriter,
    trace_sink: TraceSink | None = None,
) -> tuple[Path, Path, Path]:
    report = repository.load_compiled_report(assessment_id, report_id=report_id)
    renditions: ReportRenditions | None = None
    directory = f"reports/{report.report_id}"
    paths: list[Path] = []
    completed: list[JsonValue] = []
    try:
        renditions = render_compiled_report(report)
        for format_name, filename, content in (
            ("json", "report.json", renditions.json),
            ("yaml", "report.yaml", renditions.yaml),
            ("markdown", "report.md", renditions.markdown),
        ):
            paths.append(
                artifact_writer.write_text(assessment_id, f"{directory}/{filename}", content)
            )
            completed.append(format_name)
    except Exception:
        if trace_sink is not None:
            _trace_export(report, renditions, completed, trace_sink, failed=True)
        raise
    if trace_sink is not None:
        _trace_export(report, renditions, completed, trace_sink, failed=False)
    return paths[0], paths[1], paths[2]


def _trace_export(
    report: CompiledAssessmentReport,
    renditions: ReportRenditions | None,
    completed: list[JsonValue],
    sink: TraceSink,
    *,
    failed: bool,
) -> None:
    # Export/trace delivery never certifies authority or changes report identity.
    reason = "REPORT_EXPORT_FAILED" if failed else "REPORT_EXPORT_COMPLETE"
    digests: list[JsonValue] | None = (
        [renditions.json_digest, renditions.yaml_digest, renditions.markdown_digest]
        if renditions is not None
        else None
    )
    event = TraceEvent(
        event_id="trace_"
        + canonical_hash(
            {
                "projection": "p8-export-trace-v1",
                "report_id": report.report_id,
                "reason": reason,
                "completed_formats": completed,
                "digests": digests,
            }
        ),
        assessment_id=report.scope.assessment_id,
        occurred_at=report.accepted_at,
        stage=AssessmentStage.REPORTED,
        component="phase8.exports",
        status=TraceStatus.FAILURE if failed else TraceStatus.SUCCESS,
        reason_code=reason,
        data={
            "report_id": report.report_id,
            "compilation_id": report.compilation_id,
            "adjudication_id": report.scope.adjudication_id,
            "assessment_context_id": report.scope.assessment_context_id,
            "phase6_snapshot_id": report.scope.phase6_snapshot_id,
            "renderer_version": renditions.renderer_version if renditions is not None else None,
            "completed_formats": list(completed),
            "rendition_digests": digests,
            "failure_stage": ("RENDERING" if renditions is None else "WRITE") if failed else None,
        },
    )
    try:
        sink.emit(event)
    except Exception:
        logging.getLogger(__name__).warning(
            "Report export trace delivery failed; retry export_compiled_report",
            extra={"report_id": report.report_id, "failed_event_id": event.event_id},
        )
