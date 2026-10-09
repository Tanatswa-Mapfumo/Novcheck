"""Retryable delivery of committed reporting metadata; trace is never authority."""

from pydantic import JsonValue

from novelty_harness.domain.enums import AssessmentStage, TraceStatus
from novelty_harness.reporting.artifacts import ReportArtifact, ReportStatusEvent
from novelty_harness.reporting.execution import ReportExecutionRecord, ReportRoleConfiguration
from novelty_harness.reporting.fallback import FallbackRecord
from novelty_harness.reporting.firewall import FirewallResult
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
    # Accepted status alone is insufficient: reload the exact accepted report
    # before delivering ANY events for an accepted attempt.
    for artifact in artifacts:
        document = artifact.document
        if isinstance(document, ReportStatusEvent) and document.next_state == "ACCEPTED":
            prefix = "Accepted compiled report "
            if not document.reason.startswith(prefix):
                raise ReportAuthorityError("accepted trace lacks exact report locator")
            report = repository.load_compiled_report(
                start.scope.assessment_id, report_id=document.reason[len(prefix) :]
            )
            if report.compilation_id != compilation_id or report.scope != start.scope:
                raise ReportAuthorityError("accepted trace report belongs to another attempt")
            del report
    failed = []
    for artifact in sorted(artifacts, key=lambda a: a.artifact_id):
        event = _event(artifact, start, configurations)
        try:
            sink.emit(event)
        except Exception:
            failed.append(event.event_id)
    return tuple(failed)


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
