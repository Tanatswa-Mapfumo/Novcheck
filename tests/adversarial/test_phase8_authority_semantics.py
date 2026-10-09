"""Report authority attacks start with actual upstream and committed local records."""

import pytest
from sqlalchemy import text

from novelty_harness.reporting.repository import ReportAuthorityError
from tests.unit.evidence.graph.test_report_store import (
    _accepted_count,
    _rehash_report,
    _report_candidate,
)
from tests.unit.evidence.graph.test_report_store import acceptance_case as _acceptance_case
from tests.unit.evidence.graph.test_report_store import acceptance_source as _acceptance_source

acceptance_source = _acceptance_source
acceptance_case = _acceptance_case


def test_missing_verification_cannot_be_replaced_by_supported_trace(acceptance_case):
    compilation, proposed, _ = _report_candidate(acceptance_case)
    first = proposed.ir.sections[0]
    forged = first.model_copy(
        update={
            "blocks": tuple(
                b.model_copy(
                    update={
                        "origin": "GENERATIVE_ACCEPTED",
                        "verification_refs": ("supported-trace-only",),
                    }
                )
                for b in first.blocks
            )
        }
    )
    attack = _rehash_report(
        proposed.model_copy(
            update={
                "ir": proposed.ir.model_copy(
                    update={"sections": (forged, *proposed.ir.sections[1:])}
                )
            }
        )
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, attack)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


@pytest.mark.parametrize("kind", ["GATE", "JUDGE_RESOLUTION", "SOURCE_VERSION", "PASSAGE"])
def test_wrong_source_version_or_missing_gate_judge_fails_accept(acceptance_case, kind):
    compilation, proposed, _ = _report_candidate(acceptance_case)
    deps = tuple(
        d for d in proposed.dependencies if d.authority_ref is None or d.authority_ref.kind != kind
    )
    assert len(deps) < len(proposed.dependencies)
    attack = _rehash_report(proposed.model_copy(update={"dependencies": deps}))
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, attack)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


@pytest.mark.parametrize("attack_kind", ["second_repair", "fake_execution"])
def test_second_repair_or_fake_execution_cannot_accept(acceptance_case, attack_kind):
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import ReportArtifactRow
    from novelty_harness.evidence.graph.report_store import _artifact_row
    from novelty_harness.reporting.artifacts import report_artifact_id
    from novelty_harness.reporting.drafts import SectionDraftFragment
    from novelty_harness.reporting.execution import ReportExecutionRecord
    from novelty_harness.reporting.models import ReportSemanticRole
    from novelty_harness.reporting.prompts import approved_instruction
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    compilation, proposed, artifacts = _report_candidate(
        acceptance_case,
        failed=attack_kind == "fake_execution",
        repair=attack_kind == "second_repair",
    )
    extra_execution = None
    if attack_kind == "second_repair":
        original = next(a for a in artifacts if isinstance(a.document, SectionDraftFragment))
        fragment = original.document
        changed = fragment.model_copy(
            update={
                "blocks": tuple(
                    b.model_copy(update={"block_id": b.block_id + "-again"})
                    for b in fragment.blocks
                )
            }
        )
        execution = next(a for a in artifacts if a.artifact_id == original.execution_ref)
        extra_execution = execution.model_copy(
            update={
                "document": execution.document.model_copy(
                    update={
                        "invocation_id": execution.document.invocation_id + "-again",
                        "validated_proposal_hash": canonical_hash(changed),
                    }
                )
            }
        )
        extra_execution = extra_execution.model_copy(
            update={"artifact_id": report_artifact_id(extra_execution)}
        )
        attack = original.model_copy(
            update={"document": changed, "execution_ref": extra_execution.artifact_id}
        )
    else:
        original = next(a for a in artifacts if isinstance(a.document, ReportExecutionRecord))
        # Schema-valid, canonically rehashed actual instruction from a different
        # approved role still cannot join the registered writer invocation.
        changed = original.document.model_copy(
            update={
                "actual_instruction_hash": canonical_hash(
                    approved_instruction(ReportSemanticRole.EXTRACTOR, mode="PORT_PROTOCOL")
                )
            }
        )
        attack = original.model_copy(update={"document": changed})
    attack = attack.model_copy(update={"artifact_id": report_artifact_id(attack)})
    assert report_artifact_id(attack) == attack.artifact_id != original.artifact_id
    with Session(acceptance_case.repository.engine) as session:
        if attack_kind == "fake_execution":
            row = session.get(ReportArtifactRow, original.artifact_id)
            session.delete(row)
            session.flush()
        if extra_execution is not None:
            session.add(_artifact_row(extra_execution))
            session.flush()
        session.add(_artifact_row(attack))
        session.commit()
    expected_reason = (
        "second semantic fragment"
        if attack_kind == "second_repair"
        else "matching approved method/instruction"
    )
    with pytest.raises(ReportAuthorityError, match=expected_reason):
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, proposed)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


def test_model_vote_cannot_authorize_rejected_claim(acceptance_case):
    compilation, proposed, _ = _report_candidate(acceptance_case, generative=True)
    # Alter one actual verdict disposition after valid proof construction; a
    # supported surrounding report/majority cannot authorize that material claim.
    with acceptance_case.repository.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE report_artifacts SET document_json=replace(document_json, "
                '\'"disposition":"SUPPORTED"\', \'"disposition":"REJECTED"\') '
                "WHERE kind='VERIFICATION'"
            )
        )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, proposed)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


@pytest.fixture(scope="module")
def foreign_report_case(tmp_path_factory):
    from tests.fixtures.phase8 import make_report_scenario

    case = make_report_scenario(tmp_path_factory.mktemp("foreign-report"), "DIRECT")
    try:
        yield case
    finally:
        case.repository.close()


def _rewrite_accepted_report(case, original, changed):
    """Consistently rehash the manifest, dependency arms and terminal receipt."""
    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import (
        CompiledReportRow,
        ReportArtifactRow,
        ReportDependencyRow,
    )
    from novelty_harness.evidence.graph.report_store import (
        _accepted_header_id,
        _artifact_row,
        _dependency_row,
        _validate_dependency_rows,
        load_report_compilation_in_session,
    )
    from novelty_harness.reporting.artifacts import (
        ReportArtifact,
        report_artifact_id,
        report_status_event_id,
    )
    from novelty_harness.reporting.ir import report_id
    from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

    changed = _rehash_report(changed)
    assert changed.report_id == report_id(changed)
    with Session(case.repository.engine) as session:
        compilation = load_report_compilation_in_session(session, original.compilation_id)
        statuses = tuple(
            session.scalars(select(ReportArtifactRow).where(ReportArtifactRow.kind == "STATUS"))
        )
        terminal_row = next(r for r in statuses if '"next_state":"ACCEPTED"' in r.document_json)
        terminal = ReportArtifact.model_validate_json(terminal_row.document_json)
        status = terminal.document.model_copy(
            update={"reason": f"Accepted compiled report {changed.report_id}"}
        )
        status = status.model_copy(update={"event_id": report_status_event_id(status)})
        replacement = terminal.model_copy(update={"document": status})
        replacement = replacement.model_copy(
            update={"artifact_id": report_artifact_id(replacement)}
        )
        session.delete(terminal_row)
        session.execute(
            delete(ReportDependencyRow).where(ReportDependencyRow.report_id == original.report_id)
        )
        row = session.get(CompiledReportRow, original.report_id)
        row.report_id = changed.report_id
        row.document_json = canonical_json(changed)
        row.ir_digest = canonical_hash(changed.ir)
        row.bundle_digest = changed.ir.bundle_digest
        session.flush()
        session.add(_artifact_row(replacement))
        session.add_all(_dependency_row(changed, d) for d in changed.dependencies)
        session.flush()
        # Prove the attack survives canonical identities, exact row arms and FKs.
        assert _accepted_header_id(session, compilation) == changed.report_id
        _validate_dependency_rows(session, changed)
        assert not session.execute(text("PRAGMA foreign_key_check")).all()
        session.commit()
    return changed


def _canonical_dependency_transplant(acceptance_case, foreign_report_case, kind):
    from novelty_harness.reporting.models import ReportDependency, authority_dependency_id
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case)
    assert (
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )
        == report
    )
    foreign = next(
        d.authority_ref
        for d in foreign_report_case.bundle.dependency_manifest
        if d.authority_ref.kind == kind
        and (
            kind != "CONTEXT"
            or d.authority_ref.native_id == foreign_report_case.bundle.scope.assessment_context_id
        )
    )
    original = next(
        d
        for d in report.ir.source_dependency_manifest
        if d.authority_ref.kind == kind
        and (kind != "CONTEXT" or d.authority_ref.native_id == report.scope.assessment_context_id)
        and (kind != "SOURCE_VERSION" or d.authority_ref.native_id != foreign.native_id)
    )
    assert foreign.native_id != original.authority_ref.native_id
    # Keep the exact cited comparison path while substituting a different real
    # source version; it cannot be rebound to the original comparison's content.
    rebound = foreign.model_copy(
        update={"scope": report.scope, "path": original.authority_ref.path}
    )
    substituted = ReportDependency(
        dependency_kind="UPSTREAM",
        dependency_id=authority_dependency_id(rebound),
        expected_digest=rebound.digest,
        authority_ref=rebound,
    )
    upstream = tuple(
        substituted if d == original else d for d in report.ir.source_dependency_manifest
    )
    attack = _rewrite_accepted_report(
        acceptance_case,
        report,
        report.model_copy(
            update={
                "ir": report.ir.model_copy(update={"source_dependency_manifest": upstream}),
                "dependencies": (*upstream, *report.ir.report_artifact_dependencies),
            }
        ),
    )
    return report, attack


@pytest.mark.parametrize("kind", ["CONTEXT", "SOURCE_VERSION"])
def test_canonical_dependency_transplant_fails_load(acceptance_case, foreign_report_case, kind):
    report, attack = _canonical_dependency_transplant(acceptance_case, foreign_report_case, kind)
    with pytest.raises(
        ReportAuthorityError, match="closure failed authoritative validation"
    ) as failure:
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=attack.report_id
        )
    assert "exact frozen projections" in str(failure.value.__cause__)
    assert _accepted_count(
        acceptance_case, type("Run", (), {"compilation_id": report.compilation_id})()
    ) == (1, 1)


def _corrupt(case, statement, parameters=None):
    # Deletion deliberately simulates corruption beyond normal FK-enforced writes.
    with case.repository.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(text(statement), parameters or {})
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest.mark.parametrize("dependency", ["gate", "judge", "verification", "passage"])
def test_load_missing_gate_judge_verification_or_passage_fails(acceptance_case, dependency):
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case, generative=dependency == "verification")
    if dependency == "passage":
        _corrupt(
            acceptance_case,
            "DELETE FROM graph_nodes WHERE node_id=:id",
            {"id": acceptance_case.bundle.cited_passages[0].passage.passage_id},
        )
    elif dependency == "verification":
        _corrupt(acceptance_case, "DELETE FROM report_artifacts WHERE kind='VERIFICATION'")
    else:
        _corrupt(
            acceptance_case,
            "DELETE FROM phase7_artifacts WHERE artifact_id="
            "(SELECT artifact_id FROM phase7_artifacts WHERE kind=:kind LIMIT 1)",
            {"kind": "GATE_C" if dependency == "gate" else "JUDGE_RUN"},
        )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_load_revoked_phase6_relation_fails(acceptance_case):
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case)
    _corrupt(
        acceptance_case,
        "DELETE FROM phase6_graph_edge_memberships WHERE edge_id=:id",
        {"id": acceptance_case.bundle.authorized_relations[0].edge.edge_id},
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


@pytest.mark.parametrize("attack", ["context", "actual_prompt", "snapshot", "terminal"])
def test_load_replaced_context_or_stale_actual_prompt_fails(acceptance_case, attack):
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case, failed=attack == "actual_prompt")
    table, condition = {
        "context": ("phase7_assessment_contexts", "1=1"),
        "actual_prompt": ("report_artifacts", "kind='EXECUTION'"),
        "snapshot": ("phase6_assessment_snapshots", "1=1"),
        "terminal": (
            "report_artifacts",
            "kind='STATUS' AND document_json LIKE '%\"next_state\":\"ACCEPTED\"%'",
        ),
    }[attack]
    _corrupt(acceptance_case, f"UPDATE {table} SET document_json='{{}}' WHERE {condition}")
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_changed_source_content_rejected_even_with_same_title(acceptance_case):
    import json

    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case)
    with acceptance_case.repository.engine.begin() as connection:
        row = connection.execute(
            text("SELECT edge_id, document_json FROM verified_chains LIMIT 1")
        ).one()
        document = json.loads(row.document_json)
        source = document["source"]
        title = source["canonical_title"]
        source["canonical_url"] = "https://example.invalid/changed-authority"
        assert source["canonical_title"] == title
        connection.execute(
            text("UPDATE verified_chains SET document_json=:doc WHERE edge_id=:id"),
            {"doc": json.dumps(document), "id": row.edge_id},
        )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_missing_rejected_call_dependency_fails_read(acceptance_case):
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case, failed=True)
    execution_ids = {
        d.report_artifact_id
        for d in report.dependencies
        if d.report_artifact_id in report.execution_refs
    }
    assert execution_ids
    with acceptance_case.repository.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM report_dependencies WHERE report_artifact_id=:id"),
            {"id": next(iter(execution_ids))},
        )
    with pytest.raises(ReportAuthorityError, match="dependency rows"):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_deleted_comparison_does_not_become_unassessable_report(acceptance_case):
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case)
    _corrupt(acceptance_case, "DELETE FROM verified_classifications")
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_supported_older_version_loads_without_default_relabel(acceptance_case, monkeypatch):
    from novelty_harness.reporting import execution
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case, generative=True)
    writer = next(
        role
        for role in acceptance_case.repository.load_report_artifacts(report.compilation_id)
        if role.kind == "METHOD" and role.document.role == "WRITER"
    )
    old_version = writer.document.method_version
    # A newly selected default may coexist with still-supported immutable v1.
    monkeypatch.setattr(
        execution,
        "DEFAULT_SEMANTIC_METHODS",
        {**execution.DEFAULT_SEMANTIC_METHODS, writer.document.role: "p8-write-v2"},
    )
    loaded = acceptance_case.repository.load_compiled_report(
        report.scope.assessment_id, report_id=report.report_id
    )
    assert loaded == report
    assert old_version in loaded.approved_versions


def test_withdrawn_policy_fails_but_new_default_alone_does_not(acceptance_case, monkeypatch):
    from novelty_harness.reporting import execution
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case, generative=True)
    writer = next(
        role
        for role in acceptance_case.repository.load_report_artifacts(report.compilation_id)
        if role.kind == "METHOD" and role.document.role == "WRITER"
    )
    key = (writer.document.role, writer.document.method_version)
    monkeypatch.setattr(
        execution,
        "SUPPORTED_SEMANTIC_METHODS",
        {k: v for k, v in execution.SUPPORTED_SEMANTIC_METHODS.items() if k != key},
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


@pytest.mark.parametrize("arm", ["UPSTREAM", "REPORT_ARTIFACT"])
@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_report_read_requires_exact_dependency_rows(acceptance_case, arm, mutation):
    from sqlalchemy.orm import Session

    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case)
    dependency = next(d for d in report.dependencies if d.dependency_kind == arm)
    if mutation == "missing":
        _corrupt(
            acceptance_case,
            "DELETE FROM report_dependencies WHERE dependency_kind=:arm AND dependency_id=:id",
            {"arm": arm, "id": dependency.dependency_id},
        )
    elif mutation == "digest":
        _corrupt(
            acceptance_case,
            "UPDATE report_dependencies SET expected_digest=:digest "
            "WHERE dependency_kind=:arm AND dependency_id=:id",
            {"digest": "f" * 64, "arm": arm, "id": dependency.dependency_id},
        )
    else:
        # One extra, correctly typed row must fail exact equality as well.
        with Session(acceptance_case.repository.engine) as session:
            if arm == "UPSTREAM":
                from novelty_harness.reporting.models import (
                    ReportDependency,
                    authority_dependency_id,
                )

                original = dependency.authority_ref
                ref = original.model_copy(update={"path": (*original.path, "extra")})
                extra = ReportDependency(
                    dependency_kind=arm,
                    dependency_id=authority_dependency_id(ref),
                    expected_digest=ref.digest,
                    authority_ref=ref,
                )
            else:
                from sqlalchemy import select

                from novelty_harness.evidence.graph.report_models import ReportArtifactRow
                from novelty_harness.reporting.artifacts import ReportArtifact
                from novelty_harness.reporting.models import ReportDependency
                from novelty_harness.runtime.tracing.hashing import canonical_hash

                row = next(
                    r
                    for r in session.scalars(
                        select(ReportArtifactRow).where(ReportArtifactRow.kind == "STATUS")
                    )
                    if '"next_state":"ACCEPTED"' in r.document_json
                )
                terminal = ReportArtifact.model_validate_json(row.document_json)
                extra = ReportDependency(
                    dependency_kind=arm,
                    dependency_id=terminal.artifact_id,
                    report_artifact_id=terminal.artifact_id,
                    expected_digest=canonical_hash(terminal),
                )
            from novelty_harness.evidence.graph.report_store import _dependency_row

            session.add(_dependency_row(report, extra))
            session.commit()
    with pytest.raises(ReportAuthorityError, match="dependency row"):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_rehashed_actual_instruction_cannot_authorize_loaded_report(acceptance_case):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import ReportArtifactRow
    from novelty_harness.reporting.artifacts import (
        ReportArtifact,
        report_artifact_id,
        report_artifact_semantic_content,
    )
    from novelty_harness.reporting.models import ReportDependency, ReportSemanticRole
    from novelty_harness.reporting.prompts import approved_instruction
    from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json
    from tests.unit.evidence.graph.test_report_store import _accepted_report

    report = _accepted_report(acceptance_case, failed=True)
    with acceptance_case.repository.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        with Session(bind=connection) as session:
            row = session.scalars(
                select(ReportArtifactRow).where(ReportArtifactRow.kind == "EXECUTION")
            ).one()
            original = ReportArtifact.model_validate_json(row.document_json)
            changed = original.model_copy(
                update={
                    "document": original.document.model_copy(
                        update={
                            "actual_instruction_hash": canonical_hash(
                                approved_instruction(
                                    ReportSemanticRole.EXTRACTOR, mode="PORT_PROTOCOL"
                                )
                            )
                        }
                    )
                }
            )
            changed = changed.model_copy(update={"artifact_id": report_artifact_id(changed)})
            row.artifact_id = changed.artifact_id
            row.document_json = canonical_json(changed)
            session.commit()
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    dependency = ReportDependency(
        dependency_kind="REPORT_ARTIFACT",
        dependency_id=changed.artifact_id,
        report_artifact_id=changed.artifact_id,
        expected_digest=canonical_hash(report_artifact_semantic_content(changed)),
    )
    local = tuple(
        dependency if d.report_artifact_id == original.artifact_id else d
        for d in report.ir.report_artifact_dependencies
    )
    refs = tuple(
        sorted(
            changed.artifact_id if r == original.artifact_id else r for r in report.execution_refs
        )
    )
    ir = report.ir.model_copy(
        update={
            "report_artifact_dependencies": local,
            "generation_provenance": report.ir.generation_provenance.model_copy(
                update={"execution_refs": refs}
            ),
        }
    )
    attack = _rewrite_accepted_report(
        acceptance_case,
        report,
        report.model_copy(
            update={
                "ir": ir,
                "dependencies": (*ir.source_dependency_manifest, *local),
                "execution_refs": refs,
            }
        ),
    )
    with pytest.raises(ReportAuthorityError, match="matching approved method/instruction"):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=attack.report_id
        )


def test_report_success_trace_follows_commit_and_cannot_authorize_text(acceptance_case):
    from novelty_harness.application.phase8_tracing import publish_report_events
    from novelty_harness.reporting.execution import ReportExecutionRecord
    from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink

    compilation, proposed, _ = _report_candidate(acceptance_case, generative=True)
    report_id = acceptance_case.repository.accept_compiled_report(
        compilation.compilation_id, proposed
    )
    accepted = acceptance_case.repository.load_compiled_report(
        compilation.scope.assessment_id, report_id=report_id
    )
    calls = []

    class FailingSink(InMemoryTraceSink):
        def emit(self, event):
            # A separate native read must already see acceptance before success delivery.
            assert (
                acceptance_case.repository.load_compiled_report(
                    compilation.scope.assessment_id, report_id=report_id
                )
                == accepted
            )
            calls.append(event)
            if event.reason_code == "REPORT_STATUS_ACCEPTED":
                raise OSError("recorded delivery failure after acceptance")
            super().emit(event)

    failed = publish_report_events(
        compilation.compilation_id, repository=acceptance_case.repository, sink=FailingSink()
    )
    assert failed == tuple(e.event_id for e in calls if e.reason_code == "REPORT_STATUS_ACCEPTED")
    assert (
        acceptance_case.repository.load_compiled_report(
            compilation.scope.assessment_id, report_id=report_id
        )
        == accepted
    )
    committed = acceptance_case.repository.load_report_artifacts(compilation.compilation_id)
    expected = {
        a.artifact_id: a.document.request_hash
        for a in committed
        if isinstance(a.document, ReportExecutionRecord)
    }
    assert {
        e.data["artifact_id"]: e.request_hash
        for e in calls
        if e.reason_code.startswith("REPORT_EXECUTION_")
    } == expected
    sink = InMemoryTraceSink()
    assert (
        publish_report_events(
            compilation.compilation_id, repository=acceptance_case.repository, sink=sink
        )
        == ()
    )
    assert {e.event_id for e in sink.events} == {e.event_id for e in calls}
    assert acceptance_case.repository.load_report_artifacts(compilation.compilation_id) == committed
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            compilation.scope.assessment_id, report_id=sink.events[0].event_id
        )


def test_full_generative_report_repair_acceptance_replay_and_revocation(acceptance_case, tmp_path):
    """Integrated native boundary; pending execution is not acceptance evidence."""
    from collections import Counter

    from novelty_harness.application.phase8_exports import export_compiled_report
    from novelty_harness.ports.reporting import ReportPorts
    from novelty_harness.reporting.execution import ReportExecutionRecord
    from novelty_harness.reporting.models import ReportSemanticRole
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
    from tests.integration.test_phase8_compiler import (
        RecordedCompilerPort,
        assert_complete,
        compile_report,
        generous_options,
        upstream_rows,
    )
    from tests.unit.reporting.test_repair import ScriptedSections

    class RepairingCompiler(RecordedCompilerPort):
        def __init__(self):
            super().__init__()
            self.localized = ScriptedSections()

        async def write(self, context):
            if context.question_id == 2:
                self.operation("write", 2)
                return await self.localized.write(context)
            return await super().write(context)

        async def extract(self, context):
            if context.draft.question_id == 2:
                self.operation("extract", 2)
                return await self.localized.extract(context)
            return await super().extract(context)

        async def verify(self, context):
            if context.draft.question_id == 2:
                self.operation("verify", 2)
                return await self.localized.verify(context)
            return await super().verify(context)

        async def repair(self, context):
            self.operation("repair", context.cluster.question_id)
            return await self.localized.repair(context)

    port = RepairingCompiler()
    ports = ReportPorts(planner=port, writer=port, extractor=port, verifier=port)
    options = generous_options()
    before = upstream_rows(acceptance_case)
    report = compile_report(
        acceptance_case, token="integrated-closure", port=port, ports=ports, options=options
    )
    assert_complete(acceptance_case, report)
    assert any(b.origin == "GENERATIVE_ACCEPTED" for s in report.ir.sections for b in s.blocks)
    repairs = Counter(
        context.cluster.origin_id for name, context in port.localized.calls if name == "repair"
    )
    assert repairs and all(count == 1 for count in repairs.values())
    artifacts = acceptance_case.repository.load_report_artifacts(report.compilation_id)
    repair_executions = [
        a
        for a in artifacts
        if isinstance(a.document, ReportExecutionRecord)
        and a.document.role == ReportSemanticRole.REPAIR
    ]
    assert len(repair_executions) == sum(repairs.values())
    calls = tuple(port.calls), tuple(port.localized.calls)
    replay = compile_report(
        acceptance_case,
        token="integrated-closure",
        ports=ports,
        options=options,
        repository=acceptance_case.repository,
    )
    assert replay == report
    assert (tuple(port.calls), tuple(port.localized.calls)) == calls
    assert upstream_rows(acceptance_case) == before
    writer = RunArtifactWriter(tmp_path / "exports")
    paths = export_compiled_report(
        report.scope.assessment_id,
        report_id=report.report_id,
        repository=acceptance_case.repository,
        artifact_writer=writer,
    )
    assert all(path.is_file() for path in paths)
    original_bytes = tuple(path.read_bytes() for path in paths)
    _corrupt(
        acceptance_case,
        "DELETE FROM phase6_graph_edge_memberships WHERE edge_id=:id",
        {"id": acceptance_case.bundle.authorized_relations[0].edge.edge_id},
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )
    with pytest.raises(ReportAuthorityError):
        export_compiled_report(
            report.scope.assessment_id,
            report_id=report.report_id,
            repository=acceptance_case.repository,
            artifact_writer=writer,
        )
    assert tuple(path.read_bytes() for path in paths) == original_bytes
    assert (tuple(port.calls), tuple(port.localized.calls)) == calls


def test_complete_fallback_cannot_hide_missing_value_or_uncertainty(acceptance_case, tmp_path):
    """Native compiler/load/export closure; execution remains a required gate."""
    import json

    import yaml

    from novelty_harness.application.phase8_exports import export_compiled_report
    from novelty_harness.reporting.models import ReportProposalError
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
    from tests.integration.test_phase8_compiler import (
        assert_complete,
        compile_report,
        upstream_rows,
    )

    before = upstream_rows(acceptance_case)
    report = compile_report(acceptance_case, token="fallback-material-closure")
    assert_complete(acceptance_case, report)
    assert all(
        block.origin == "DETERMINISTIC_FALLBACK"
        for section in report.ir.sections
        for block in section.blocks
    )
    assert not report.execution_refs
    assert not acceptance_case.frozen.value_findings
    assert any(item.kind == "NO_VALUE_ASSESSMENT" for item in report.ir.value_availability)
    assert all(
        item.kind != "AUTHORITATIVE_VALUE_FINDING" and item.maturity is None
        for item in report.ir.value_availability
    )
    assert report.ir.uncertainty_summary
    assert all(
        item.scope == report.scope and item.authority_refs for item in report.ir.uncertainty_summary
    )
    summary = report.ir.compact_summary
    assert summary is not None
    assert summary.value_availability == report.ir.value_availability
    assert summary.uncertainty == report.ir.uncertainty_summary
    for envelope in acceptance_case.bundle.language_envelopes:
        target = next(target for target in summary.targets if target.target == envelope.target)
        assert target.verdict == envelope.verdict
        assert target.claim_scope == envelope.claim_scope
        assert target.permitted_classes == envelope.permitted_classes
        assert target.limitations == envelope.required_limitations

    paths = export_compiled_report(
        report.scope.assessment_id,
        report_id=report.report_id,
        repository=acceptance_case.repository,
        artifact_writer=RunArtifactWriter(tmp_path / "fallback-exports"),
    )
    assert len(paths) == 3 and all(path.is_file() for path in paths)
    for path, parser in ((paths[0], json.load), (paths[1], yaml.safe_load)):
        with path.open() as stream:
            exported = parser(stream)
        assert exported["report_id"] == report.report_id
        assert exported["ir"]["value_availability"] == [
            item.model_dump(mode="json") for item in report.ir.value_availability
        ]
        assert exported["ir"]["uncertainty_summary"] == [
            item.model_dump(mode="json") for item in report.ir.uncertainty_summary
        ]
        assert tuple(section["question_id"] for section in exported["ir"]["sections"]) == tuple(
            range(1, 10)
        )
        del exported
    # Inspect the public Markdown projections independently, reading only their
    # lines rather than retaining another complete rendition beside the IR.
    projections = {"Value availability": [], "Uncertainty": []}
    active = None
    with paths[2].open() as stream:
        for line in stream:
            if line.startswith("## "):
                title = line[3:].strip()
                active = title if title in projections else None
            elif active is not None:
                projections[active].append(line.replace("\\_", "_"))
    value_text = "".join(projections["Value availability"])
    assert "NO_VALUE_ASSESSMENT" in value_text
    assert "AUTHORITATIVE_VALUE_FINDING" not in value_text
    uncertainty_text = "".join(projections["Uncertainty"])
    assert all(item.uncertainty_id in uncertainty_text for item in report.ir.uncertainty_summary)
    del projections, value_text, uncertainty_text

    # Rehash both the full IR and summary consistently; matching hashes cannot
    # excuse a missing native projection, even when Q6/Q9 prose stays intact.
    for field in ("value_availability", "uncertainty_summary"):
        summary_field = "uncertainty" if field == "uncertainty_summary" else field
        changed_ir = report.ir.model_copy(
            update={
                field: (),
                "compact_summary": summary.model_copy(update={summary_field: ()}),
            }
        )
        forged = _rehash_report(report.model_copy(update={"ir": changed_ir}))
        assert forged.report_id != report.report_id
        with pytest.raises(
            ReportAuthorityError, match="closure failed authoritative validation"
        ) as failure:
            acceptance_case.repository.accept_compiled_report(report.compilation_id, forged)
        assert isinstance(failure.value.__cause__, ReportProposalError)
        assert str(failure.value.__cause__) == (
            "IR differs from exact frozen projections, actual proofs or deterministic summary"
        )
        assert _accepted_count(
            acceptance_case, type("Run", (), {"compilation_id": report.compilation_id})()
        ) == (1, 1)
        del failure, changed_ir, forged
    assert upstream_rows(acceptance_case) == before
    assert (
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )
        == report
    )


@pytest.mark.parametrize("kind", ["CONTEXT", "SOURCE_VERSION"])
def test_consistent_hashes_do_not_rescue_wrong_version_or_context(
    acceptance_case, foreign_report_case, tmp_path, kind
):
    """Canonical rows and valid FKs cannot authorize a foreign native closure."""
    from novelty_harness.application.phase8_exports import export_compiled_report
    from novelty_harness.reporting.models import ReportProposalError
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
    from tests.integration.test_phase8_compiler import upstream_rows

    before = upstream_rows(acceptance_case)
    report, attack = _canonical_dependency_transplant(acceptance_case, foreign_report_case, kind)
    destination = tmp_path / "denied-exports"
    with pytest.raises(
        ReportAuthorityError, match="closure failed authoritative validation"
    ) as failure:
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=attack.report_id
        )
    assert isinstance(failure.value.__cause__, ReportProposalError)
    assert "exact frozen projections" in str(failure.value.__cause__)
    del failure
    with pytest.raises(
        ReportAuthorityError, match="closure failed authoritative validation"
    ) as failure:
        export_compiled_report(
            report.scope.assessment_id,
            report_id=attack.report_id,
            repository=acceptance_case.repository,
            artifact_writer=RunArtifactWriter(destination),
        )
    assert isinstance(failure.value.__cause__, ReportProposalError)
    assert "exact frozen projections" in str(failure.value.__cause__)
    del failure
    assert not any(path.is_file() for path in destination.rglob("*"))
    assert upstream_rows(acceptance_case) == before
    assert _accepted_count(
        acceptance_case, type("Run", (), {"compilation_id": report.compilation_id})()
    ) == (1, 1)


@pytest.mark.parametrize(
    "votes", [("SUPPORTED", "SUPPORTED", "REJECTED"), ("REJECTED", "SUPPORTED", "SUPPORTED")]
)
def test_ordered_model_votes_cannot_accept_rejected_material_claim(acceptance_case, votes):
    """Ordered support prose cannot override an exact typed material rejection."""
    from novelty_harness.reporting.verification import ClaimVerificationBatch
    from tests.integration.test_phase8_compiler import (
        RecordedCompilerPort,
        assert_complete,
        compile_report,
        generous_options,
        upstream_rows,
    )

    class VotingProsePort(RecordedCompilerPort):
        async def verify(self, context):
            batch = await super().verify(context)
            if context.question_id != 1:
                return batch
            first = context.extraction.claims[0]
            reason = "Ordered recorded model opinions: " + ", ".join(votes)
            return batch.model_copy(
                update={
                    "dispositions": tuple(
                        disposition.model_copy(
                            update={
                                "disposition": "REJECTED",
                                "reason_codes": ("UNSUPPORTED_PROPOSITION",),
                                "reason": reason,
                            }
                        )
                        if disposition.claim_id == first.claim_id
                        else disposition
                        for disposition in batch.dispositions
                    ),
                }
            )

        async def repair(self, context):
            self.operation("repair", context.cluster.question_id)
            raise RuntimeError("recorded repair unavailable; votes cannot supply a repair")

    before = upstream_rows(acceptance_case)
    port = VotingProsePort()
    report = compile_report(
        acceptance_case, token="ordered-votes", port=port, options=generous_options()
    )
    assert_complete(acceptance_case, report)
    artifacts = acceptance_case.repository.load_report_artifacts(report.compilation_id)
    rejected = tuple(
        artifact
        for artifact in artifacts
        if isinstance(artifact.document, ClaimVerificationBatch)
        and artifact.question_id == 1
        and not artifact.document.accepted
    )
    assert rejected
    assert votes.count("SUPPORTED") > votes.count("REJECTED")
    for artifact in rejected:
        # A completeness rejection must not mask a missing claim-disposition guard.
        assert all(block.disposition == "SUPPORTED" for block in artifact.document.blocks)
        dispositions = tuple(
            item for item in artifact.document.dispositions if item.disposition == "REJECTED"
        )
        assert dispositions
        assert all(
            item.reason == "Ordered recorded model opinions: " + ", ".join(votes)
            for item in dispositions
        )
    first = report.ir.sections[0]
    assert all(block.origin == "DETERMINISTIC_FALLBACK" for block in first.blocks)
    assert any(
        block.origin == "GENERATIVE_ACCEPTED"
        for section in report.ir.sections[1:]
        for block in section.blocks
    )
    rejected_ids = {artifact.artifact_id for artifact in rejected}
    assert rejected_ids <= {item.report_artifact_id for item in report.dependencies}
    assert not rejected_ids & {
        reference for block in first.blocks for reference in block.verification_refs
    }
    assert upstream_rows(acceptance_case) == before


@pytest.mark.parametrize("boundary", ["EXTRACTION", "COMPOSITION"])
def test_hidden_heading_assertion_crosses_extraction_and_composition_boundary(
    acceptance_case, boundary
):
    """Actual heading text crosses both semantic boundaries before native acceptance."""
    from novelty_harness.reporting.claims import TextSpan
    from novelty_harness.reporting.verification import ClaimVerificationBatch, CompositionCheck
    from tests.integration.test_phase8_compiler import (
        RecordedCompilerPort,
        assert_complete,
        compile_report,
        generous_options,
        upstream_rows,
    )

    assertion = "Together, the known components establish universal novelty for the whole proposal."

    class HiddenHeadingPort(RecordedCompilerPort):
        async def write(self, context):
            draft = await super().write(context)
            if context.question_id == 1:
                heading = draft.blocks[0].model_copy(update={"kind": "HEADING", "text": assertion})
                draft = draft.model_copy(update={"blocks": (heading, *draft.blocks[1:])})
                self.drafts[1] = draft
            return draft

        async def extract(self, context):
            proposal = await super().extract(context)
            if context.question_id != 1 or boundary != "EXTRACTION":
                return proposal
            heading_id = context.draft.blocks[0].block_id
            omitted = {claim.claim_id for claim in proposal.claims if claim.block_id == heading_id}
            assert omitted
            return proposal.model_copy(
                update={
                    "claims": tuple(
                        claim for claim in proposal.claims if claim.claim_id not in omitted
                    ),
                    "basis_links": tuple(
                        link for link in proposal.basis_links if link.claim_id not in omitted
                    ),
                    "block_accounts": tuple(
                        account.model_copy(
                            update={"claim_ids": (), "non_material_reason": "Decorative heading"}
                        )
                        if account.block_id == heading_id
                        else account
                        for account in proposal.block_accounts
                    ),
                }
            )

        async def verify(self, context):
            batch = await super().verify(context)
            if context.question_id != 1 or boundary != "EXTRACTION":
                return batch
            heading = context.draft.blocks[0]
            return batch.model_copy(
                update={
                    "blocks": tuple(
                        block.model_copy(
                            update={
                                "disposition": "REJECTED",
                                "missing_assertion_spans": (
                                    TextSpan(start=0, end=len(heading.text)),
                                ),
                                "reason_codes": ("MISSING_MATERIAL_ASSERTION",),
                            }
                        )
                        if block.block_id == heading.block_id
                        else block
                        for block in batch.blocks
                    ),
                }
            )

        async def repair(self, context):
            self.operation("repair", context.cluster.question_id)
            raise RuntimeError("recorded repair unavailable; hidden heading must fall back")

        async def check_composition(self, context):
            if boundary == "EXTRACTION":
                return await super().check_composition(context)
            self.operation("composition")
            heading = context.drafts[0].blocks[0]
            assert heading.kind == "HEADING" and heading.text == assertion
            assert any(
                claim.normalized_assertion == assertion for claim in context.extractions[0].claims
            )
            return CompositionCheck(
                scope=context.scope,
                compilation_id=context.compilation_id,
                narrative_digest=context.narrative_digest,
                claims_digest=context.claims_digest,
                permission_digest=context.permission_digest,
                disposition="REJECTED",
                implicated_block_ids=(heading.block_id,),
                implicated_question_ids=(1,),
                indeterminate_scope=False,
                reason_codes=("WHOLE_SCOPE_DRIFT",),
                reason="Recorded heading implies a stronger whole than the frozen permission",
            )

    before = upstream_rows(acceptance_case)
    port = HiddenHeadingPort()
    report = compile_report(
        acceptance_case, token="hidden-heading-" + boundary, port=port, options=generous_options()
    )
    assert_complete(acceptance_case, report)
    artifacts = acceptance_case.repository.load_report_artifacts(report.compilation_id)
    local = tuple(
        artifact.document
        for artifact in artifacts
        if isinstance(artifact.document, ClaimVerificationBatch) and artifact.question_id == 1
    )
    assert local
    if boundary == "EXTRACTION":
        assert any(
            "MISSING_MATERIAL_ASSERTION" in block.reason_codes and block.missing_assertion_spans
            for check in local
            for block in check.blocks
        )
    else:
        assert all(check.accepted for check in local)
        assert any(
            isinstance(artifact.document, CompositionCheck)
            and not artifact.document.accepted
            and artifact.document.implicated_question_ids == (1,)
            and "WHOLE_SCOPE_DRIFT" in artifact.document.reason_codes
            for artifact in artifacts
        )
    assert all(block.origin == "DETERMINISTIC_FALLBACK" for block in report.ir.sections[0].blocks)
    assert all(
        block.draft_block.text != assertion
        for section in report.ir.sections
        for block in section.blocks
    )
    assert upstream_rows(acceptance_case) == before
