"""Locator-based reporting authority port, separate from upstream mutation."""

from typing import Protocol

from novelty_harness.domain.ids import AssessmentId
from novelty_harness.reporting.artifacts import ReportArtifact, ReportCompilationRecord
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.execution import ReportCompilationConfiguration
from novelty_harness.reporting.ir import CompiledAssessmentReport
from novelty_harness.reporting.models import BundlePolicyVersion, ReportOptions


class ReportAuthorityError(ValueError):
    """Report authority validation failed; no downgraded report may be returned."""


class ReportRepository(Protocol):
    def load_report_input_bundle(
        self,
        assessment_id: AssessmentId,
        *,
        adjudication_id: str,
        bundle_version: BundlePolicyVersion = "p8-bundle-v2",
    ) -> ReportInputBundle: ...

    def begin_report_compilation(
        self,
        assessment_id: AssessmentId,
        *,
        adjudication_id: str,
        options: ReportOptions,
        configuration: ReportCompilationConfiguration,
        attempt_token: str | None = None,
    ) -> ReportCompilationRecord: ...

    def record_report_artifact(self, compilation_id: str, artifact: ReportArtifact) -> str: ...

    def load_report_artifacts(self, compilation_id: str) -> tuple[ReportArtifact, ...]: ...

    def accept_compiled_report(
        self, compilation_id: str, proposed: CompiledAssessmentReport
    ) -> str: ...

    def load_compiled_report(
        self, assessment_id: AssessmentId, *, report_id: str
    ) -> CompiledAssessmentReport: ...
