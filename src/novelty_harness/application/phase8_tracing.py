"""Retryable delivery of committed reporting metadata; trace is never authority."""

from itertools import chain

from pydantic import JsonValue

from novelty_harness.domain.enums import AssessmentStage, TraceStatus
from novelty_harness.reporting.artifacts import ReportArtifact, ReportStatusEvent
from novelty_harness.reporting.execution import ReportExecutionRecord, ReportRoleConfiguration
from novelty_harness.reporting.fallback import FallbackRecord
from novelty_harness.reporting.firewall import FirewallResult
from novelty_harness.reporting.ir import CompiledAssessmentReport
from novelty_harness.reporting.plan import ReportPlan
from novelty_harness.reporting.repository import ReportAuthorityError, ReportRepository
from novelty_harness.reporting.verification import ClaimVerificationBatch, CompositionCheck
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink


def publish_report_events(
    compilation_id: str, *, repository: ReportRepository, sink: TraceSink
) -> tuple[str, ...]:
    """Reload native committed closure, then emit metadata with stable retry IDs.

    No proposal text, raw provider responses, credentials or arbitrary status
    prose enters a trace. Sink failures are returned independently of acceptance.
    Callers may retry this read-only operation; delivery never invokes a port.
    """
    artifacts = repository.load_report_artifacts(compilation_id)
    starts = tuple(
        a.document
        for a in artifacts
        if isinstance(a.document, ReportStatusEvent) and a.document.expected_state is None
    )
    if len(starts) != 1 or len({a.artifact_id for a in artifacts}) != len(artifacts):
        raise ReportAuthorityError("report trace requires one complete committed attempt")
    start = starts[0]
    if any(a.compilation_id != compilation_id or a.scope != start.scope for a in artifacts):
        raise ReportAuthorityError("report trace artifact scope or compilation differs")
    configurations = {
        a.document.configuration_id: a.document
        for a in artifacts
        if isinstance(a.document, ReportRoleConfiguration)
    }
    accepted_events: tuple[TraceEvent, ...] = ()
    # Accepted status alone is insufficient: reload the exact accepted report
    # before delivering ANY events for an accepted attempt.
    for artifact in artifacts:
        document = artifact.document
        if isinstance(document, ReportStatusEvent) and document.next_state == "ACCEPTED":
            prefix = "Accepted compiled report "
            if not document.reason.startswith(prefix):
                raise ReportAuthorityError("accepted trace lacks exact report locator")
            locator = document.reason[len(prefix) :]
            report = repository.load_compiled_report(start.scope.assessment_id, report_id=locator)
            if (
                report.report_id != locator
                or report.compilation_id != compilation_id
                or report.scope != start.scope
            ):
                raise ReportAuthorityError("accepted trace report belongs to another attempt")
            accepted_events = _accepted_report_events(report)
            del report
    failed: list[str] = []
    events = (
        _event(a, start, configurations) for a in sorted(artifacts, key=lambda a: a.artifact_id)
    )
    plan_events = (
        _plan_firewall_event(a, start)
        for a in sorted(artifacts, key=lambda a: a.artifact_id)
        if isinstance(a.document, ReportPlan)
    )
    for event in chain(
        (_attempt_load_event(artifacts, start),), events, plan_events, accepted_events
    ):
        try:
            sink.emit(event)
        except Exception:
            failed.append(event.event_id)
    return tuple(failed)


def _plan_firewall_event(artifact: ReportArtifact, start: ReportStatusEvent) -> TraceEvent:
    """Append explicit planning origin without rewriting legacy artifact events."""
    plan = artifact.document
    if not isinstance(plan, ReportPlan):
        raise ReportAuthorityError("plan trace requires a committed coverage-validated plan")
    data: dict[str, JsonValue] = {
        "compilation_id": artifact.compilation_id,
        "adjudication_id": artifact.scope.adjudication_id,
        "assessment_context_id": artifact.scope.assessment_context_id,
        "phase6_snapshot_id": artifact.scope.phase6_snapshot_id,
        "artifact_id": artifact.artifact_id,
        "artifact_kind": "PLAN_FIREWALL",
        "method_version": artifact.method_version,
        "execution_ref": artifact.execution_ref,
        "plan_id": plan.plan_id,
        "origin": plan.origin,
        "bundle_digest": plan.bundle_digest,
        "proposal_digest": plan.proposal_digest,
        "validation_method": plan.validation_method,
    }
    return TraceEvent(
        event_id="trace_"
        + canonical_hash(
            {"projection": "p8-plan-firewall-trace-v1", "artifact_id": artifact.artifact_id}
        ),
        assessment_id=artifact.scope.assessment_id,
        occurred_at=start.observed_at,
        stage=AssessmentStage.REPORTED,
        component="phase8",
        status=TraceStatus.DEGRADED if plan.origin == "COVERAGE_FALLBACK" else TraceStatus.SUCCESS,
        reason_code="REPORT_PLAN_FIREWALL_" + plan.origin,
        data=data,
    )


def _attempt_load_event(
    artifacts: tuple[ReportArtifact, ...], start: ReportStatusEvent
) -> TraceEvent:
    """Describe a revalidated committed closure, never a new semantic call."""
    statuses = tuple(a.document for a in artifacts if isinstance(a.document, ReportStatusEvent))
    predecessors = {s.predecessor_id for s in statuses if s.predecessor_id is not None}
    terminal = tuple(s for s in statuses if s.event_id not in predecessors)
    if len(terminal) != 1:
        raise ReportAuthorityError("report trace requires one current committed status")
    current = terminal[0]
    artifact_ids: list[JsonValue] = [
        a.artifact_id for a in sorted(artifacts, key=lambda a: a.artifact_id)
    ]
    identity: dict[str, JsonValue] = {
        "projection": "p8-attempt-load-trace-v1",
        "compilation_id": start.compilation_id,
        "committed_artifact_ids": artifact_ids,
    }
    data: dict[str, JsonValue] = {
        "compilation_id": start.compilation_id,
        "adjudication_id": start.scope.adjudication_id,
        "assessment_context_id": start.scope.assessment_context_id,
        "phase6_snapshot_id": start.scope.phase6_snapshot_id,
        "artifact_kind": "COMMITTED_ATTEMPT_LOAD",
        "status_event_id": current.event_id,
        "current_state": current.next_state.value,
        "committed_artifact_ids": artifact_ids,
    }
    return TraceEvent(
        event_id="trace_" + canonical_hash(identity),
        assessment_id=start.scope.assessment_id,
        occurred_at=current.observed_at,
        stage=AssessmentStage.REPORTED,
        component="phase8",
        status=TraceStatus.FAILURE if current.next_state == "FAILED" else TraceStatus.SUCCESS,
        reason_code="REPORT_ATTEMPT_RELOADED",
        data=data,
    )


def _event(
    artifact: ReportArtifact,
    start: ReportStatusEvent,
    configurations: dict[str, ReportRoleConfiguration],
) -> TraceEvent:
    document = artifact.document
    data: dict[str, JsonValue] = {
        "compilation_id": artifact.compilation_id,
        "adjudication_id": artifact.scope.adjudication_id,
        "assessment_context_id": artifact.scope.assessment_context_id,
        "phase6_snapshot_id": artifact.scope.phase6_snapshot_id,
        "artifact_id": artifact.artifact_id,
        "artifact_kind": artifact.kind.value,
        "method_version": artifact.method_version,
        "question_id": artifact.question_id,
        "cluster_origin_id": artifact.cluster_origin_id,
        "execution_ref": artifact.execution_ref,
    }
    status = TraceStatus.SUCCESS
    reason = "REPORT_" + artifact.kind.value + "_COMMITTED"
    occurred = start.observed_at
    request_hash = response_hash = provider = None
    latency = cost = None
    if isinstance(document, ReportExecutionRecord):
        status = TraceStatus.SUCCESS if document.outcome == "VALIDATED" else TraceStatus.FAILURE
        reason = "REPORT_EXECUTION_" + document.outcome
        occurred = document.observations.observed_at
        request_hash, response_hash = document.request_hash, document.raw_response_hash
        latency, cost = document.observations.latency_ms, document.observations.cost_usd
        configuration = configurations.get(document.configuration_id)
        provider = configuration.port.provider if configuration else None
        data.update(
            {
                "invocation_id": document.invocation_id,
                "role": document.role.value,
                "configuration_id": document.configuration_id,
                "instruction_hash": document.actual_instruction_hash,
                "proposal_hash": document.validated_proposal_hash,
                "recovery": document.recovery,
                "predecessor_ref": document.predecessor_ref,
                "token_count": document.observations.tokens,
            }
        )
    elif isinstance(document, ReportStatusEvent):
        occurred = document.observed_at
        reason = "REPORT_STATUS_" + document.next_state.value
        status = TraceStatus.FAILURE if document.next_state == "FAILED" else TraceStatus.SUCCESS
        data.update(
            {
                "status_event_id": document.event_id,
                "predecessor_id": document.predecessor_id,
                "next_state": document.next_state.value,
            }
        )
        if document.next_state == "ACCEPTED":
            data["report_id"] = document.reason.removeprefix("Accepted compiled report ")
    elif isinstance(document, FirewallResult):
        status = TraceStatus.SUCCESS if document.accepted else TraceStatus.DEGRADED
        data.update(
            {
                "reason_codes": list(document.reason_codes),
                "claims_hash": document.claims_digest,
                "basis_hash": document.basis_digest,
                "draft_hash": document.draft_digest,
            }
        )
    elif isinstance(document, ClaimVerificationBatch):
        status = TraceStatus.SUCCESS if document.accepted else TraceStatus.DEGRADED
        results = (*document.dispositions, *document.blocks)
        data.update(
            {
                "dispositions": [item.disposition.value for item in results],
                "reason_codes": list(
                    dict.fromkeys(code for item in results for code in item.reason_codes)
                ),
                "context_hash": document.context_digest,
                "draft_hash": document.draft_digest,
                "extraction_hash": document.extraction_digest,
                "claim_ids": [item.claim_id for item in document.dispositions],
                "block_ids": [item.block_id for item in document.blocks],
            }
        )
    elif isinstance(document, CompositionCheck):
        status = TraceStatus.SUCCESS if document.accepted else TraceStatus.DEGRADED
        data.update(
            {
                "disposition": document.disposition.value,
                "reason_codes": list(document.reason_codes),
                "implicated_question_ids": list(document.implicated_question_ids),
                "implicated_block_ids": list(document.implicated_block_ids),
                "narrative_hash": document.narrative_digest,
            }
        )
    elif isinstance(document, FallbackRecord):
        status = TraceStatus.DEGRADED
        data.update(
            {
                "bundle_digest": document.bundle_digest,
                "fallback_version": document.method_version,
                "origin": "DETERMINISTIC_FALLBACK",
            }
        )
    return TraceEvent(
        event_id="trace_"
        + canonical_hash({"projection": "p8-trace-v1", "artifact_id": artifact.artifact_id}),
        assessment_id=artifact.scope.assessment_id,
        occurred_at=occurred,
        stage=AssessmentStage.REPORTED,
        component="phase8",
        status=status,
        provider_name=provider,
        request_hash=request_hash,
        response_hash=response_hash,
        latency_ms=latency,
        estimated_cost=cost,
        reason_code=reason,
        data=data,
    )


def _accepted_report_events(report: CompiledAssessmentReport) -> tuple[TraceEvent, ...]:
    """Project only locator/ancestry metadata from a native revalidated report.

    Event observations refer to the committed acceptance, not a fabricated new
    semantic execution. Neither the ancestry hash nor a delivery receipt is an
    authority certificate. Raw source text and URLs never enter these events.
    """
    common: dict[str, JsonValue] = {
        "report_id": report.report_id,
        "compilation_id": report.compilation_id,
        "adjudication_id": report.scope.adjudication_id,
        "assessment_context_id": report.scope.assessment_context_id,
        "phase6_snapshot_id": report.scope.phase6_snapshot_id,
    }
    ancestry: list[JsonValue] = [
        {
            "citation_id": citation.citation_id,
            "display_number": citation.display_number,
            "source_id": citation.source_id,
            "source_version_id": citation.source_version_id,
            "passage_id": citation.passage_id,
            "comparison_id": citation.comparison_id,
            "commit_id": citation.commit_id,
            "commitment_ids": list(citation.commitment_ids),
            "claim_ids": list(citation.claim_ids),
        }
        for citation in report.ir.citation_registry.citations
    ]
    events: list[TraceEvent] = []
    projections: tuple[tuple[str, dict[str, JsonValue]], ...] = (
        ("REPORT_ACCEPTED_REPORT_RELOADED", common),
        (
            "REPORT_CITATIONS_RESOLVED",
            {
                **common,
                "citation_method_version": report.ir.citation_registry.method_version,
                "citation_ancestry": ancestry,
                "citation_ancestry_hash": canonical_hash(ancestry),
            },
        ),
    )
    for reason, data in projections:
        events.append(
            TraceEvent(
                event_id="trace_"
                + canonical_hash(
                    {
                        "projection": "p8-accepted-trace-v1",
                        "report_id": report.report_id,
                        "reason": reason,
                    }
                ),
                assessment_id=report.scope.assessment_id,
                occurred_at=report.accepted_at,
                stage=AssessmentStage.REPORTED,
                component="phase8",
                status=TraceStatus.SUCCESS,
                reason_code=reason,
                data=data,
            )
        )
    return tuple(events)
