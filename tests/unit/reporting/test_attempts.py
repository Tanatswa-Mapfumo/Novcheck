"""Attempts use exact repository locators and immutable committed artifacts."""

from datetime import timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from novelty_harness.reporting.artifacts import (
    ReportArtifactKind,
    ReportAttemptState,
    ReportStatusEvent,
)
from novelty_harness.reporting.execution import (
    ReportCompilationConfiguration,
    ReportPortConfiguration,
    approved_role_configuration,
)
from novelty_harness.reporting.models import ReportLens, ReportOptions, ReportSemanticRole
from novelty_harness.reporting.repository import ReportAuthorityError
from tests.fixtures.phase8 import OBSERVED
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


def configuration(case):
    return ReportCompilationConfiguration(
        roles=tuple(
            approved_role_configuration(
                case.bundle.scope,
                "pending",
                role,
                ReportPortConfiguration(
                    mode="PORT_PROTOCOL", implementation="scripted-report-port"
                ),
            )
            for role in ReportSemanticRole
        )
    )


def begin(case, token, **kwargs):
    return case.repository.begin_report_compilation(
        case.bundle.scope.assessment_id,
        adjudication_id=case.frozen.adjudication_id,
        options=kwargs.pop("options", ReportOptions()),
        configuration=kwargs.pop("configuration", configuration(case)),
        attempt_token=token,
        **kwargs,
    )


def method_artifact(compilation):
    from novelty_harness.reporting.artifacts import make_report_artifact

    role = compilation.configuration.roles[0]
    return make_report_artifact(
        compilation, ReportArtifactKind.METHOD, role.method, method_version=role.method_version
    )


def status_artifact(compilation, predecessor, state, *, reason="Operational failure"):
    from novelty_harness.reporting.artifacts import make_report_artifact, report_status_event_id
    from novelty_harness.reporting.execution import bundle_policy_version

    proposal = ReportStatusEvent(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        event_id="pending",
        predecessor_id=predecessor.event_id,
        expected_state=predecessor.next_state,
        next_state=state,
        reason=reason,
        observed_at=OBSERVED,
    )
    proposal = proposal.model_copy(update={"event_id": report_status_event_id(proposal)})
    return make_report_artifact(
        compilation,
        ReportArtifactKind.STATUS,
        proposal,
        method_version=bundle_policy_version(compilation.configuration),
    )


def test_exact_attempt_replays_without_duplicate_or_foreign_artifact(report_case):
    assert hasattr(report_case.repository, "begin_report_compilation"), (
        "durable report attempts are absent"
    )
    first = begin(report_case, "exact")
    retry = begin(report_case, "exact")
    assert retry == first
    assert first.started_at.tzinfo is not None
    other = begin(report_case, "another")
    assert other.compilation_id != first.compilation_id
    changed = begin(report_case, "exact", options=ReportOptions(lens=ReportLens.ENGINEERING))
    assert changed.compilation_key != first.compilation_key
    artifact = method_artifact(first)
    repo = report_case.repository
    assert repo.record_report_artifact(first.compilation_id, artifact) == artifact.artifact_id
    assert repo.record_report_artifact(first.compilation_id, artifact) == artifact.artifact_id
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(other.compilation_id, artifact)
    committed = repo.load_report_artifacts(first.compilation_id)
    assert sum(a.artifact_id == artifact.artifact_id for a in committed) == 1
    assert {a.kind for a in committed} == {ReportArtifactKind.METHOD, ReportArtifactKind.STATUS}
    conflicting = artifact.model_copy(
        update={"document": artifact.document.model_copy(update={"instruction_hash": "a" * 64})}
    )
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(first.compilation_id, conflicting)


def test_status_chain_rejects_skip_fork_and_terminal_append(report_case):
    comp = begin(report_case, "states")
    repo = report_case.repository
    initial = next(
        a.document for a in repo.load_report_artifacts(comp.compilation_id) if a.kind == "STATUS"
    )
    # No valid plan contract exists yet, so even a syntactically legal step cannot advance.
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(
            comp.compilation_id, status_artifact(comp, initial, ReportAttemptState.PLANNED)
        )
    invalid = status_artifact(comp, initial, ReportAttemptState.FAILED)
    skipped = invalid.model_copy(
        update={
            "document": invalid.document.model_copy(
                update={"next_state": ReportAttemptState.VERIFIED}
            )
        }
    )
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(comp.compilation_id, skipped)
    repo.record_report_artifact(comp.compilation_id, invalid)
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(
            comp.compilation_id,
            status_artifact(comp, initial, ReportAttemptState.FAILED, reason="Forked failure"),
        )
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(comp.compilation_id, method_artifact(comp))
    assert repo.record_report_artifact(comp.compilation_id, invalid) == invalid.artifact_id
    assert begin(report_case, "states") == comp


def test_begin_rollback_leaves_no_partial_attempt(report_case):
    from novelty_harness.evidence.graph.report_models import ReportArtifactRow, ReportCompilationRow

    with Session(report_case.repository.engine) as session:
        before = tuple(session.scalars(select(ReportCompilationRow.compilation_id)))

    def fail_status(session, _context, _instances):
        if any(isinstance(row, ReportArtifactRow) for row in session.new):
            raise RuntimeError("injected status write failure")

    event.listen(Session, "before_flush", fail_status)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            begin(report_case, "rollback")
    finally:
        event.remove(Session, "before_flush", fail_status)
    with Session(report_case.repository.engine) as session:
        assert tuple(session.scalars(select(ReportCompilationRow.compilation_id))) == before
    assert begin(report_case, "rollback").attempt_token == "rollback"


def test_attempt_reopen_keeps_committed_output(report_case):
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )

    comp = begin(report_case, "reopen")
    repo = report_case.repository
    artifact = method_artifact(comp)
    repo.record_report_artifact(comp.compilation_id, artifact)
    database = repo.engine.url.database
    assert database is not None
    reopened = SqlAlchemyEvidenceGraphRepository(database)
    try:
        loaded = reopened.load_report_artifacts(comp.compilation_id)
        assert artifact in loaded
        replay = reopened.begin_report_compilation(
            comp.scope.assessment_id,
            adjudication_id=comp.scope.adjudication_id,
            options=comp.options,
            configuration=comp.configuration,
            attempt_token=comp.attempt_token,
        )
        assert replay == comp
    finally:
        reopened.close()


def test_wrong_bundle_digest_cannot_seed_begin(report_case):
    from novelty_harness.evidence.graph.report_models import ReportCompilationRow

    comp = begin(report_case, "digest-corrupt")
    with Session(report_case.repository.engine) as session, session.begin():
        row = session.get(ReportCompilationRow, comp.compilation_id)
        row.bundle_digest = "b" * 64
    with pytest.raises(ReportAuthorityError):
        begin(report_case, "digest-corrupt")


def test_unknown_registration_hash_rejected(report_case):
    from novelty_harness.reporting.artifacts import report_artifact_id

    comp = begin(report_case, "registration")
    artifact = method_artifact(comp)
    bad = artifact.model_copy(
        update={"document": artifact.document.model_copy(update={"instruction_hash": "a" * 64})}
    )
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(comp.compilation_id, bad)
    bad = bad.model_copy(update={"artifact_id": report_artifact_id(bad)})
    with pytest.raises(ReportAuthorityError) as rejected:
        report_case.repository.record_report_artifact(comp.compilation_id, bad)
    assert "not approved" in str(rejected.value.__cause__)
    cfg = configuration(report_case)
    unknown = cfg.model_copy(
        update={
            "roles": (
                cfg.roles[0].model_copy(update={"method_version": "unapproved"}),
                *cfg.roles[1:],
            )
        }
    )
    with pytest.raises(ReportAuthorityError):
        begin(report_case, "unapproved-config", configuration=unknown)
    assert (
        report_case.repository.record_report_artifact(comp.compilation_id, artifact)
        == artifact.artifact_id
    )


def test_artifact_provenance_not_supplied_by_trace(report_case):
    from novelty_harness.reporting.artifacts import make_report_artifact
    from novelty_harness.reporting.execution import (
        ReportExecutionObservations,
        ReportExecutionRecord,
    )

    comp = begin(report_case, "trace")
    role = comp.configuration.roles[0]
    document = ReportExecutionRecord(
        scope=comp.scope,
        compilation_id=comp.compilation_id,
        invocation_id="trace-only",
        role=role.role,
        task_name="plan",
        method_version=role.method_version,
        actual_instruction_hash=role.instruction_hash,
        configuration_id=role.configuration_id,
        request_hash="a" * 64,
        raw_response_hash="b" * 64,
        validated_proposal_hash="c" * 64,
        outcome="VALIDATED",
        observations=ReportExecutionObservations(observed_at=OBSERVED),
    )
    artifact = make_report_artifact(
        comp, ReportArtifactKind.EXECUTION, document, method_version=role.method_version
    )
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(comp.compilation_id, artifact)


def test_replay_preserves_original_status_observations(report_case):
    from novelty_harness.reporting.artifacts import make_report_artifact

    comp = begin(report_case, "observation-replay")
    repo = report_case.repository
    initial = next(a for a in repo.load_report_artifacts(comp.compilation_id) if a.kind == "STATUS")
    changed = initial.document.model_copy(
        update={"observed_at": initial.document.observed_at + timedelta(days=1)}
    )
    artifact = make_report_artifact(
        comp, ReportArtifactKind.STATUS, changed, method_version=initial.method_version
    )
    assert artifact.artifact_id == initial.artifact_id
    assert repo.record_report_artifact(comp.compilation_id, artifact) == initial.artifact_id
    assert initial in repo.load_report_artifacts(comp.compilation_id)


@pytest.mark.parametrize("attack", ["scope", "kind", "execution", "target"])
def test_foreign_or_unknown_artifact_is_rejected(report_case, attack):
    comp = begin(report_case, "foreign-" + attack)
    artifact = method_artifact(comp)
    if attack == "scope":
        artifact = artifact.model_copy(
            update={"scope": comp.scope.model_copy(update={"assessment_context_id": "foreign"})}
        )
    elif attack == "kind":
        data = artifact.model_dump(mode="json") | {"kind": "ARBITRARY_JSON"}
        with pytest.raises(ReportAuthorityError):
            report_case.repository.record_report_artifact(comp.compilation_id, data)
        return
    elif attack == "execution":
        artifact = artifact.model_copy(update={"execution_ref": "foreign-execution"})
    else:
        data = artifact.document.model_dump(mode="json") | {"target_id": "foreign-target"}
        data = artifact.model_dump(mode="json") | {"document": data}
        with pytest.raises(ReportAuthorityError):
            report_case.repository.record_report_artifact(comp.compilation_id, data)
        return
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(comp.compilation_id, artifact)
