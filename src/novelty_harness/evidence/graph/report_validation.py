"""Shared in-transaction report closure validation; no semantic calls or providers."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView
from novelty_harness.reporting.artifacts import (
    ReportArtifact,
    ReportAttemptState,
    ReportStatusEvent,
)
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.ir import CompiledAssessmentReport, report_id, validate_report_ir
from novelty_harness.reporting.rendering import render_compiled_report, validate_rendition_parity
from novelty_harness.reporting.repository import ReportAuthorityError


def validate_compiled_report_in_session(
    session: Session,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    compilation_id: str,
    proposed: CompiledAssessmentReport,
) -> tuple[ReportInputBundle, tuple[ReportArtifact, ...]]:
    # Local import avoids a module cycle with the store's acceptance delegate.
    from novelty_harness.evidence.graph.report_store import (
        load_report_artifacts_in_session,
        load_report_compilation_in_session,
        report_attempt_state,
        revalidate_report_bundle_in_session,
    )

    try:
        proposed = _revalidate_proposal(proposed)
        compilation = load_report_compilation_in_session(session, compilation_id)
        bundle = revalidate_report_bundle_in_session(session, load_view_in_session, compilation)
        artifacts = load_report_artifacts_in_session(session, compilation, bundle)
        current = report_attempt_state(artifacts)
        if current.next_state not in {ReportAttemptState.VERIFIED, ReportAttemptState.ACCEPTED}:
            raise ReportAuthorityError("report acceptance requires completed VERIFIED state")
        if (
            proposed.scope != compilation.scope
            or proposed.compilation_id != compilation_id
            or proposed.ir.scope != compilation.scope
            or proposed.ir.compilation_id != compilation_id
            or proposed.report_id != report_id(proposed)
        ):
            raise ReportAuthorityError("compiled report scope or realized identity differs")
        # Only the separately joined terminal receipt is outside the report's
        # preacceptance dependency closure; rejected and failed calls stay inside.
        closure = tuple(
            a
            for a in artifacts
            if not (
                isinstance(a.document, ReportStatusEvent)
                and a.document.next_state == ReportAttemptState.ACCEPTED
            )
        )
        validate_report_ir(proposed.ir, bundle, compilation, closure)
        expected = (
            *proposed.ir.source_dependency_manifest,
            *proposed.ir.report_artifact_dependencies,
        )
        if proposed.dependencies != expected:
            raise ReportAuthorityError("compiled report does not retain the exact dependency set")
        provenance = proposed.ir.generation_provenance
        if (proposed.approved_versions, proposed.configuration_refs, proposed.execution_refs) != (
            provenance.approved_versions,
            provenance.configuration_refs,
            provenance.execution_refs,
        ):
            raise ReportAuthorityError("compiled method, configuration or execution refs differ")
        renditions = render_compiled_report(
            proposed, renderer_version=compilation.options.render_policy_version
        )
        validate_rendition_parity(proposed, renditions)
        return bundle, artifacts
    except ValueError as error:
        if isinstance(error, ReportAuthorityError):
            raise
        raise ReportAuthorityError(
            "compiled report closure failed authoritative validation"
        ) from error


def _revalidate_proposal(value: object) -> CompiledAssessmentReport:
    if not isinstance(value, CompiledAssessmentReport):
        raise ReportAuthorityError("an export or caller receipt is not a compiled proposal")
    return CompiledAssessmentReport.model_validate_json(value.model_dump_json())
