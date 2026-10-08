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


@pytest.mark.parametrize("kind", ["CONTEXT", "SOURCE_VERSION"])
def test_canonical_dependency_transplant_fails_load(acceptance_case, foreign_report_case, kind):
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
