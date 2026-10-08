"""Derived exports only after repository-authoritative report loading."""

from pathlib import Path

from novelty_harness.domain.ids import AssessmentId
from novelty_harness.reporting.rendering import render_compiled_report
from novelty_harness.reporting.repository import ReportRepository
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter


class Phase8ReportingError(RuntimeError):
    """An operational report failure after upstream adjudication is frozen."""


def export_compiled_report(
    assessment_id: AssessmentId,
    *,
    report_id: str,
    repository: ReportRepository,
    artifact_writer: RunArtifactWriter,
) -> tuple[Path, Path, Path]:
    report = repository.load_compiled_report(assessment_id, report_id=report_id)
    renditions = render_compiled_report(report)
    directory = f"reports/{report.report_id}"
    return (
        artifact_writer.write_text(assessment_id, f"{directory}/report.json", renditions.json),
        artifact_writer.write_text(assessment_id, f"{directory}/report.yaml", renditions.yaml),
        artifact_writer.write_text(assessment_id, f"{directory}/report.md", renditions.markdown),
    )
