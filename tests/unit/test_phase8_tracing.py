"""Delivery contract controls; shape artifacts do not certify native authority."""

from types import SimpleNamespace

import pytest

from novelty_harness.domain.enums import TraceStatus
from novelty_harness.reporting.artifacts import (
    ReportArtifactKind,
    ReportStatusEvent,
    make_report_artifact,
    report_status_event_id,
)
from novelty_harness.reporting.execution import ReportExecutionObservations, ReportExecutionRecord
from novelty_harness.reporting.repository import ReportAuthorityError
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase8 import OBSERVED
from tests.unit.reporting.test_contracts import _compilation


def committed_shapes(*, outcome="VALIDATED"):
    compilation = _compilation()
    status = ReportStatusEvent(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        event_id="pending",
        next_state="STARTED",
        reason="Secret prose must not enter trace",
        observed_at=OBSERVED,
    )
    status = status.model_copy(update={"event_id": report_status_event_id(status)})
    role = compilation.configuration.roles[0]
    execution = ReportExecutionRecord(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        invocation_id="invoke-trace-shape",
        role=role.role,
        task_name="recorded-task",
        method_version=role.method_version,
        actual_instruction_hash=role.instruction_hash,
        configuration_id=role.configuration_id,
        request_hash="a" * 64,
        raw_response_hash="b" * 64,
        validated_proposal_hash="c" * 64 if outcome == "VALIDATED" else None,
        outcome=outcome,
        observations=ReportExecutionObservations(
            observed_at=OBSERVED,
            tokens=12,
            cost_usd=0.03,
            latency_ms=4,
        ),
    )
    artifacts = tuple(
        make_report_artifact(compilation, kind, doc, method_version=version)
        for kind, doc, version in (
            (ReportArtifactKind.STATUS, status, "p8-bundle-v1"),
            (ReportArtifactKind.CONFIGURATION, role, role.method_version),
            (ReportArtifactKind.EXECUTION, execution, execution.method_version),
        )
    )
    return compilation, artifacts


class ReadOnlyRepository:
    def __init__(self, compilation, artifacts):
        self.compilation = compilation
        self.artifacts = artifacts
        self.loads = []

    def load_report_artifacts(self, compilation_id):
        assert compilation_id == self.compilation.compilation_id
        self.loads.append(compilation_id)
        return self.artifacts

    def __getattr__(self, name):
        raise AssertionError(f"Trace delivery must not call {name}")


def test_trace_retry_never_duplicates_semantic_execution():
    from novelty_harness.application.phase8_tracing import publish_report_events

    compilation, artifacts = committed_shapes()
    repository = ReadOnlyRepository(compilation, artifacts)
    sink = InMemoryTraceSink()
    assert publish_report_events(compilation.compilation_id, repository=repository, sink=sink) == ()
    first = sink.events
    repository.artifacts = tuple(reversed(artifacts))
    assert publish_report_events(compilation.compilation_id, repository=repository, sink=sink) == ()
    assert sink.events[len(first) :] == first
    execution = next(e for e in first if e.reason_code == "REPORT_EXECUTION_VALIDATED")
    assert execution.request_hash == "a" * 64
    assert execution.response_hash == "b" * 64
    assert execution.data["proposal_hash"] == "c" * 64
    assert execution.data["instruction_hash"] == artifacts[2].document.actual_instruction_hash
    assert execution.data["token_count"] == 12
    assert execution.estimated_cost == 0.03 and execution.latency_ms == 4
    assert len(repository.loads) == 2
    assert "Secret prose" not in str(first)


def test_sink_failure_returns_exact_retry_ids_and_keeps_delivering():
    from novelty_harness.application.phase8_tracing import publish_report_events

    compilation, artifacts = committed_shapes()
    repository = ReadOnlyRepository(compilation, artifacts)
    delivered = []

    class FailingSink:
        def emit(self, event):
            delivered.append(event)
            if event.reason_code == "REPORT_EXECUTION_VALIDATED":
                raise OSError("recorded sink failure")

    failed = publish_report_events(
        compilation.compilation_id, repository=repository, sink=FailingSink()
    )
    assert failed == tuple(
        e.event_id for e in delivered if e.reason_code == "REPORT_EXECUTION_VALIDATED"
    )
    assert len(delivered) == len(artifacts)
    assert repository.artifacts == artifacts


@pytest.mark.parametrize("outcome", ["INVALID", "PROVIDER_FAILURE"])
def test_failed_execution_never_projects_semantic_success(outcome):
    from novelty_harness.application.phase8_tracing import publish_report_events

    compilation, artifacts = committed_shapes(outcome=outcome)
    sink = InMemoryTraceSink()
    publish_report_events(
        compilation.compilation_id, repository=ReadOnlyRepository(compilation, artifacts), sink=sink
    )
    execution = next(e for e in sink.events if "EXECUTION" in e.reason_code)
    assert execution.status == TraceStatus.FAILURE
    assert execution.reason_code == "REPORT_EXECUTION_" + outcome
    assert execution.data["proposal_hash"] is None


def test_trace_only_or_revoked_authority_emits_nothing():
    from novelty_harness.application.phase8_tracing import publish_report_events

    sink = InMemoryTraceSink()

    def refused(locator):
        raise ReportAuthorityError("No committed native artifact closure")

    with pytest.raises(ReportAuthorityError):
        publish_report_events(
            "trace-only", repository=SimpleNamespace(load_report_artifacts=refused), sink=sink
        )
    assert sink.events == ()


@pytest.mark.parametrize("attack", ["foreign_compilation", "empty", "duplicate"])
def test_trace_checks_compilation_and_complete_start_before_delivery(attack):
    from novelty_harness.application.phase8_tracing import publish_report_events

    compilation, artifacts = committed_shapes()
    if attack == "foreign_compilation":
        artifacts = (artifacts[0].model_copy(update={"compilation_id": "foreign"}), *artifacts[1:])
    elif attack == "empty":
        artifacts = ()
    else:
        artifacts = (*artifacts, artifacts[0])
    sink = InMemoryTraceSink()
    with pytest.raises(ReportAuthorityError):
        publish_report_events(
            compilation.compilation_id,
            repository=ReadOnlyRepository(compilation, artifacts),
            sink=sink,
        )
    assert sink.events == ()


@pytest.mark.parametrize("disposition", ["REJECTED", "UNRESOLVED"])
def test_committed_composition_rejection_is_not_reported_as_success(disposition):
    from novelty_harness.application.phase8_tracing import publish_report_events
    from novelty_harness.reporting.verification import CompositionCheck

    compilation, artifacts = committed_shapes()
    check = CompositionCheck(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        narrative_digest="d" * 64,
        claims_digest="e" * 64,
        permission_digest="f" * 64,
        disposition=disposition,
        implicated_block_ids=("rejected-block",),
        implicated_question_ids=(2,),
        indeterminate_scope=False,
        reason_codes=("UNSUPPORTED_WHOLE_CLAIM",),
        reason="Untrusted prose is not logged",
    )
    artifact = make_report_artifact(
        compilation, ReportArtifactKind.COMPOSITION, check, method_version="report-composition-v1"
    )
    sink = InMemoryTraceSink()
    publish_report_events(
        compilation.compilation_id,
        repository=ReadOnlyRepository(compilation, (*artifacts, artifact)),
        sink=sink,
    )
    event = next(e for e in sink.events if e.data["artifact_kind"] == "COMPOSITION")
    assert event.status == TraceStatus.DEGRADED
    assert event.data["disposition"] == disposition
    assert event.data["reason_codes"] == ["UNSUPPORTED_WHOLE_CLAIM"]
    assert "Untrusted prose" not in str(event)


@pytest.mark.parametrize("disposition", ["REJECTED", "UNRESOLVED"])
def test_committed_verification_rejection_is_not_reported_as_success(disposition):
    from novelty_harness.application.phase8_tracing import publish_report_events
    from novelty_harness.reporting.verification import BlockCompleteness, ClaimVerificationBatch

    compilation, artifacts = committed_shapes()
    block = BlockCompleteness(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        block_id="rejected-block",
        text_digest="d" * 64,
        claims_digest="e" * 64,
        disposition=disposition,
        missing_assertion_spans=(),
        unmet_obligation_ids=(),
        unmet_qualification_refs=(),
        reason_codes=("UNSUPPORTED_CLAIM",),
        reason="Untrusted verification prose is not logged",
    )
    batch = ClaimVerificationBatch(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        question_id=2,
        context_digest="a" * 64,
        draft_digest="b" * 64,
        extraction_digest="c" * 64,
        dispositions=(),
        blocks=(block,),
    )
    artifact = make_report_artifact(
        compilation, ReportArtifactKind.VERIFICATION, batch, method_version="report-verification-v1"
    )
    sink = InMemoryTraceSink()
    publish_report_events(
        compilation.compilation_id,
        repository=ReadOnlyRepository(compilation, (*artifacts, artifact)),
        sink=sink,
    )
    event = next(e for e in sink.events if e.data["artifact_kind"] == "VERIFICATION")
    assert event.status == TraceStatus.DEGRADED
    assert event.data["dispositions"] == [disposition]
    assert event.data["reason_codes"] == ["UNSUPPORTED_CLAIM"]
    assert "Untrusted verification prose" not in str(event)


@pytest.mark.parametrize("revoked", [False, True, "foreign-report"])
def test_accepted_trace_reloads_exact_native_locator_before_any_delivery(revoked):
    from novelty_harness.application.phase8_tracing import publish_report_events

    compilation, artifacts = committed_shapes()
    accepted = ReportStatusEvent(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        event_id="pending",
        expected_state="VERIFIED",
        next_state="ACCEPTED",
        reason="Accepted compiled report report-exact",
        observed_at=OBSERVED,
        predecessor_id=artifacts[0].document.event_id,
    )
    accepted = accepted.model_copy(update={"event_id": report_status_event_id(accepted)})
    artifact = make_report_artifact(
        compilation, ReportArtifactKind.STATUS, accepted, method_version="p8-bundle-v1"
    )
    sink = InMemoryTraceSink()
    loads = []

    class AcceptedRepository(ReadOnlyRepository):
        def load_compiled_report(self, assessment_id, *, report_id):
            assert not sink.events
            assert assessment_id == compilation.scope.assessment_id
            assert report_id == "report-exact"
            loads.append(report_id)
            if revoked is True:
                raise ReportAuthorityError("Accepted closure was revoked")
            return SimpleNamespace(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                report_id="report-foreign" if revoked == "foreign-report" else report_id,
                accepted_at=OBSERVED,
                ir=SimpleNamespace(
                    citation_registry=SimpleNamespace(
                        method_version="p8-citations-v1", citations=()
                    )
                ),
            )

    repository = AcceptedRepository(compilation, (*artifacts, artifact))
    if revoked:
        with pytest.raises(ReportAuthorityError):
            publish_report_events(compilation.compilation_id, repository=repository, sink=sink)
        assert sink.events == ()
    else:
        assert (
            publish_report_events(compilation.compilation_id, repository=repository, sink=sink)
            == ()
        )
        event = next(e for e in sink.events if e.reason_code == "REPORT_STATUS_ACCEPTED")
        assert event.data["report_id"] == "report-exact"
    assert loads == ["report-exact"]


def test_accepted_citation_projection_is_retryable_metadata_after_native_load():
    from novelty_harness.application.phase8_tracing import publish_report_events

    compilation, artifacts = committed_shapes()
    accepted = ReportStatusEvent(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        event_id="pending",
        expected_state="VERIFIED",
        next_state="ACCEPTED",
        reason="Accepted compiled report report-citations",
        observed_at=OBSERVED,
        predecessor_id=artifacts[0].document.event_id,
    )
    accepted = accepted.model_copy(update={"event_id": report_status_event_id(accepted)})
    artifact = make_report_artifact(
        compilation, ReportArtifactKind.STATUS, accepted, method_version="p8-bundle-v1"
    )
    citation = SimpleNamespace(
        citation_id="cite-native",
        display_number=1,
        source_id="source-native",
        source_version_id="version-native",
        passage_id="passage-native",
        comparison_id="comparison-native",
        commit_id="commit-native",
        commitment_ids=("commitment-native",),
        claim_ids=("claim-native",),
        external_link="https://example.invalid/secret",
        limitations=("Private evidence prose",),
    )
    sink = InMemoryTraceSink()
    before_delivery = [0]

    class AcceptedRepository(ReadOnlyRepository):
        def load_compiled_report(self, assessment_id, *, report_id):
            assert len(sink.events) == before_delivery[0]
            assert assessment_id == compilation.scope.assessment_id
            assert report_id == "report-citations"
            return SimpleNamespace(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                report_id=report_id,
                accepted_at=OBSERVED,
                ir=SimpleNamespace(
                    citation_registry=SimpleNamespace(
                        method_version="p8-citations-v1", citations=(citation,)
                    )
                ),
            )

    repository = AcceptedRepository(compilation, (*artifacts, artifact))
    assert publish_report_events(compilation.compilation_id, repository=repository, sink=sink) == ()
    first = sink.events
    event = next(e for e in first if e.reason_code == "REPORT_CITATIONS_RESOLVED")
    assert event.data["report_id"] == "report-citations"
    assert event.data["citation_method_version"] == "p8-citations-v1"
    assert event.data["citation_ancestry"] == [
        {
            "citation_id": "cite-native",
            "display_number": 1,
            "source_id": "source-native",
            "source_version_id": "version-native",
            "passage_id": "passage-native",
            "comparison_id": "comparison-native",
            "commit_id": "commit-native",
            "commitment_ids": ["commitment-native"],
            "claim_ids": ["claim-native"],
        }
    ]
    assert "Private evidence prose" not in str(first)
    assert "example.invalid" not in str(first)
    assert any(e.reason_code == "REPORT_ACCEPTED_REPORT_RELOADED" for e in first)
    before_delivery[0] = len(first)
    assert publish_report_events(compilation.compilation_id, repository=repository, sink=sink) == ()
    assert sink.events[len(first) :] == first

    class FailingCitationSink:
        def emit(self, value):
            if value.reason_code == "REPORT_CITATIONS_RESOLVED":
                raise OSError("private failure prose")

    before_delivery[0] = len(sink.events)
    failed = publish_report_events(
        compilation.compilation_id, repository=repository, sink=FailingCitationSink()
    )
    assert failed == (event.event_id,)
