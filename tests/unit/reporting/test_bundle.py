"""Report bundles rejoin repository authority; pure projections confer none."""

import pytest
from sqlalchemy import event, text

from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture


@pytest.fixture
def frozen_case(tmp_path):
    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    repository.freeze_phase7_adjudication(run.run_id, proposed)
    frozen = repository.load_frozen_adjudication(
        packet.assessment_id, adjudication_id=proposed.adjudication_id
    )
    try:
        yield packet, repository, frozen
    finally:
        repository.close()


def test_bundle_revalidates_one_exact_authority_closure(frozen_case):
    packet, repository, frozen = frozen_case
    begins = []

    def observe(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.strip() == "BEGIN":
            begins.append(statement)

    event.listen(repository.engine, "before_cursor_execute", observe)
    try:
        assert callable(getattr(repository, "load_report_input_bundle", None)), (
            "report bundle loader is absent"
        )
        bundle = repository.load_report_input_bundle(
            packet.assessment_id, adjudication_id=frozen.adjudication_id
        )
    finally:
        event.remove(repository.engine, "before_cursor_execute", observe)
    assert begins == ["BEGIN"]
    assert bundle.scope.adjudication_id == frozen.adjudication_id
    assert bundle.frozen_adjudication == frozen
    assert bundle.as_of == packet.as_of
    assert bundle.cir == packet.manifest.cir
    assert bundle.graph_or_version == packet.manifest.mcu_graph
    assert bundle.target_profiles == packet.phase6_view.targets
    assert bundle.target_findings == frozen.target_findings
    assert bundle.overall_finding == frozen.overall_finding
    assert bundle.research_state == packet.manifest
    assert bundle.eligible_comparisons == packet.comparisons
    assert bundle.authorized_relations == packet.authorized_relations
    assert bundle.cited_passages == packet.cited_passages
    assert bundle.source_metadata
    for observation in bundle.source_metadata:
        comparison = next(
            c
            for c in bundle.eligible_comparisons
            if c.comparison.classification.classification_id
            == observation.comparison_refs[0].native_id
        )
        chain = comparison.comparison.comparison.chain
        assert observation.source == chain.source
        assert observation.version == chain.version
    assert all(p.passage.attestation for p in bundle.cited_passages)
    kinds = {d.authority_ref.kind for d in bundle.dependency_manifest}
    assert {
        "FROZEN",
        "CONTEXT",
        "INPUT_MANIFEST",
        "CIR",
        "GRAPH",
        "TARGET",
        "TARGET_FINDING",
        "OVERALL_FINDING",
        "GATE",
        "ROLE",
        "COMPARISON",
        "COMMIT",
        "PASSAGE",
        "SOURCE",
    } <= kinds
    assert len({d.dependency_id for d in bundle.dependency_manifest}) == len(
        bundle.dependency_manifest
    )
    from novelty_harness.reporting.bundle import report_bundle_digest

    assert bundle.bundle_digest == report_bundle_digest(bundle)


def test_bundle_refuses_export_or_caller_frozen_shape(frozen_case):
    from novelty_harness.reporting.repository import ReportAuthorityError

    packet, repository, frozen = frozen_case
    for locator in (frozen.model_dump_json(), "p7frozen_caller_created"):
        with pytest.raises(ReportAuthorityError):
            repository.load_report_input_bundle(packet.assessment_id, adjudication_id=locator)
    with pytest.raises(TypeError):
        repository.load_report_input_bundle(
            packet.assessment_id, adjudication_id=frozen.adjudication_id, frozen_adjudication=frozen
        )


def test_bundle_source_metadata_preserves_conflicting_observations(frozen_case):
    from novelty_harness.reporting.bundle import project_source_metadata
    from novelty_harness.reporting.models import ReportScope, authority_dependency_id

    packet, repository, frozen = frozen_case
    bundle = repository.load_report_input_bundle(
        packet.assessment_id, adjudication_id=frozen.adjudication_id
    )
    first = packet.comparisons[0]
    chain = first.comparison.comparison.chain
    changed_source = chain.source.model_copy(
        update={"canonical_title": "Earlier metadata observation"}
    )
    original_second = next(
        c
        for c in packet.comparisons[1:]
        if c.comparison.comparison.chain.source.source_id == chain.source.source_id
    )
    second_chain = original_second.comparison.comparison.chain.model_copy(
        update={"source": changed_source}
    )
    second = original_second.model_copy(
        update={
            "comparison": original_second.comparison.model_copy(
                update={
                    "comparison": original_second.comparison.comparison.model_copy(
                        update={"chain": second_chain}
                    )
                }
            )
        }
    )
    # This pure shape projection cannot seed a repository compilation; the actual loader above
    # supplies only committed comparisons. Two observations must not overwrite one another.
    view = packet.phase6_view.model_copy(update={"committed_comparisons": (first, second)})
    observations = project_source_metadata(
        view, ReportScope.model_validate(bundle.scope.model_dump())
    )
    assert [o.source.canonical_title for o in observations] == [
        chain.source.canonical_title,
        "Earlier metadata observation",
    ]
    assert observations[0].source.source_id == observations[1].source.source_id
    refs = [o.source_ref for o in observations]
    assert authority_dependency_id(refs[0]) != authority_dependency_id(refs[1])
    assert (
        observations[0].conflicting_observation_refs
        and observations[1].conflicting_observation_refs
    )


def test_bundle_keeps_complete_residual_and_decisive_closure(frozen_case):
    packet, repository, frozen = frozen_case
    bundle = repository.load_report_input_bundle(
        packet.assessment_id, adjudication_id=frozen.adjudication_id
    )
    for admitted, original in zip(bundle.eligible_comparisons, packet.comparisons, strict=True):
        assert admitted == original  # Full native chain, including residual/context/chronology.
        assert (
            admitted.comparison.comparison.chain.verification
            == original.comparison.comparison.chain.verification
        )
        assert admitted.cited_passages == original.cited_passages
    refs = {d.authority_ref.native_id for d in bundle.dependency_manifest}
    assert {r for t in frozen.target_findings for r in t.decisive_phase6_ids} <= refs


@pytest.mark.parametrize("attack", ["target", "snapshot"])
def test_bundle_foreign_target_or_snapshot_fails(frozen_case, attack):
    from novelty_harness.reporting.repository import ReportAuthorityError

    packet, repository, frozen = frozen_case
    with repository.engine.begin() as connection:
        if attack == "snapshot":
            # Keep FK-valid row columns; corrupt the actual sealed document instead.
            row = connection.execute(
                text("SELECT document_json FROM phase7_frozen_manifests WHERE adjudication_id=:id"),
                {"id": frozen.adjudication_id},
            ).scalar_one()
            connection.execute(
                text(
                    "UPDATE phase7_frozen_manifests SET document_json=:doc "
                    "WHERE adjudication_id=:id"
                ),
                {
                    "id": frozen.adjudication_id,
                    "doc": row.replace(frozen.phase6_snapshot_id, "p6snap_foreign"),
                },
            )
        else:
            row = frozen.model_dump(mode="json")
            row["target_findings"][0]["target_id"] = "mcu_foreign"
            from novelty_harness.runtime.tracing.hashing import canonical_json

            connection.execute(
                text(
                    "UPDATE phase7_frozen_manifests SET document_json=:doc "
                    "WHERE adjudication_id=:id"
                ),
                {"id": frozen.adjudication_id, "doc": canonical_json(row)},
            )
    with pytest.raises(ReportAuthorityError):
        repository.load_report_input_bundle(
            packet.assessment_id, adjudication_id=frozen.adjudication_id
        )


@pytest.mark.parametrize("dependency", ["gate", "judge", "passage"])
def test_bundle_missing_gate_judge_or_passage_fails(frozen_case, dependency):
    from novelty_harness.reporting.repository import ReportAuthorityError

    packet, repository, frozen = frozen_case
    # Dependency deletion intentionally bypasses FK enforcement to model storage corruption.
    with repository.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        if dependency == "passage":
            connection.execute(
                text("DELETE FROM graph_nodes WHERE node_id=:id"),
                {"id": packet.cited_passages[0].passage.passage_id},
            )
        else:
            kind = "GATE_C" if dependency == "gate" else "JUDGE_RUN"
            connection.execute(
                text(
                    "DELETE FROM phase7_artifacts WHERE artifact_id="
                    "(SELECT artifact_id FROM phase7_artifacts WHERE kind=:kind LIMIT 1)"
                ),
                {"kind": kind},
            )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    with pytest.raises(ReportAuthorityError):
        repository.load_report_input_bundle(
            packet.assessment_id, adjudication_id=frozen.adjudication_id
        )


def test_bundle_semantic_only_never_creates_relation(frozen_case):
    import asyncio
    from dataclasses import replace

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from novelty_harness.adjudication.packet import build_adjudication_case
    from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase
    from novelty_harness.application.phase7 import run_phase7
    from novelty_harness.domain.enums import SufficiencyState
    from novelty_harness.evidence.graph.assessment_ledger import (
        Phase6AssessmentSnapshotRecord,
        Phase6TargetLedgerRecord,
        phase6_assessment_snapshot_id,
        phase6_candidate_record_id,
        phase6_target_record_id,
    )
    from novelty_harness.evidence.graph.sqlalchemy_models import Phase6AssessmentSnapshotRow
    from tests.integration.test_phase7_slice import _real_ports
    from tests.unit.adjudication.test_roles import scope

    packet, repository, frozen = frozen_case
    with Session(repository.engine) as session:
        row = session.scalars(
            select(Phase6AssessmentSnapshotRow).where(
                Phase6AssessmentSnapshotRow.snapshot_id == packet.phase6_snapshot_id
            )
        ).one()
        original = Phase6AssessmentSnapshotRecord.model_validate_json(row.document_json)
    candidates = tuple(
        c.model_copy(update={"snapshot_id": "pending", "projection_intent": "SEMANTIC_ONLY"})
        if c.decision == "ASSESSED"
        else c.model_copy(update={"snapshot_id": "pending"})
        for c in packet.phase6_view.candidate_outcomes
    )
    targets = tuple(
        Phase6TargetLedgerRecord(
            snapshot_id="pending", assessment_id=packet.assessment_id, profile=p
        )
        for p in packet.target_profiles
    )
    facts = original.model_copy(update={"derived_record_ids": ()})
    snapshot_id = phase6_assessment_snapshot_id(
        facts, targets=targets, candidates=candidates, derived=()
    )
    targets = tuple(t.model_copy(update={"snapshot_id": snapshot_id}) for t in targets)
    candidates = tuple(c.model_copy(update={"snapshot_id": snapshot_id}) for c in candidates)
    snapshot = facts.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": tuple(phase6_target_record_id(t) for t in targets),
            "candidate_record_ids": tuple(phase6_candidate_record_id(c) for c in candidates),
        }
    )
    # Reconstruct an admitted semantic-only historical projection, as in the
    # frozen Phase 6 regression control. The old graph-backed frozen result is
    # deliberately no longer authoritative; the new run has no parent binding.
    with repository.engine.begin() as connection:
        for table in ("phase6_graph_edge_memberships", "phase6_graph_node_memberships"):
            connection.execute(text(f"DELETE FROM {table}"))
        for comparison in packet.phase6_view.committed_comparisons:
            for edge_id in comparison.graph_edge_ids:
                connection.execute(
                    text("DELETE FROM graph_edges WHERE edge_id=:id"), {"id": edge_id}
                )
            if comparison.proposition_node_id is not None:
                connection.execute(
                    text("DELETE FROM graph_nodes WHERE node_id=:id"),
                    {"id": comparison.proposition_node_id},
                )
    repository.record_phase6_assessment(
        snapshot, targets=targets, candidates=candidates, derived=()
    )
    manifest = packet.manifest.model_copy(
        update={
            "phase6_snapshot_id": snapshot_id,
            "sufficiency": packet.manifest.sufficiency.model_copy(
                update={"state": SufficiencyState.INSUFFICIENT}
            ),
        }
    )
    context = repository.seal_phase7_context(
        packet.assessment_id, snapshot_id=snapshot_id, manifest=manifest
    )
    view = repository.load_phase6_assessment(packet.assessment_id, snapshot_id=snapshot_id)
    successor = build_adjudication_case(context, view)
    assert {c.projection_status for c in view.committed_comparisons} == {"SEMANTIC_ONLY"}

    class EmptyRole:
        def __init__(self, prosecution):
            self.prosecution = prosecution
            self.index = 0

        async def propose(self, given):
            target = sorted(successor.target_ids)[self.index]
            self.index += 1
            if self.prosecution:
                return ProsecutionCase(
                    **scope(given, target), case_id="empty-pro-" + target, challenges=()
                )
            return DefenseCase(**scope(given, target), case_id="empty-def-" + target, points=())

    ports = replace(_real_ports(successor), prosecutor=EmptyRole(True), defender=EmptyRole(False))
    new_frozen = asyncio.run(
        run_phase7(
            packet.assessment_id, context_id=context.context_id, repository=repository, ports=ports
        )
    )
    bundle = repository.load_report_input_bundle(
        packet.assessment_id, adjudication_id=new_frozen.adjudication_id
    )
    assert {c.projection_status for c in bundle.eligible_comparisons} == {"SEMANTIC_ONLY"}
    assert bundle.authorized_relations == ()
    assert not any(d.authority_ref.kind == "GRAPH_RELATION" for d in bundle.dependency_manifest)


def test_bundle_holds_consistent_transaction_during_dependency_change(frozen_case, tmp_path):
    import sqlite3

    from novelty_harness.reporting.repository import ReportAuthorityError

    packet, repository, frozen = frozen_case
    # WAL lets a separate writer commit during the reader's authority checks.
    with repository.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    injected = False

    def mutate_after_frozen_read(_conn, _cursor, statement, _parameters, _context, _many):
        nonlocal injected
        if not injected and statement.lstrip().startswith("SELECT phase7_frozen_manifests."):
            injected = True
            with sqlite3.connect(repository.engine.url.database) as writer:
                writer.execute(
                    "DELETE FROM phase7_frozen_dependencies WHERE adjudication_id=?",
                    (frozen.adjudication_id,),
                )

    event.listen(repository.engine, "after_cursor_execute", mutate_after_frozen_read)
    try:
        bundle = repository.load_report_input_bundle(
            packet.assessment_id, adjudication_id=frozen.adjudication_id
        )
        assert injected
        assert bundle.frozen_adjudication == frozen
    finally:
        event.remove(repository.engine, "after_cursor_execute", mutate_after_frozen_read)
    with pytest.raises(ReportAuthorityError):
        repository.load_report_input_bundle(
            packet.assessment_id, adjudication_id=frozen.adjudication_id
        )


def test_bundle_retains_derived_and_lineage_context(frozen_case):
    packet, repository, frozen = frozen_case
    bundle = repository.load_report_input_bundle(
        packet.assessment_id, adjudication_id=frozen.adjudication_id
    )
    closure = bundle.judge_resolutions_and_limitations
    assert closure.phase6_view.multi_source_context == packet.phase6_view.multi_source_context
    assert closure.phase6_view.patent_screenings == packet.phase6_view.patent_screenings
    assert closure.phase6_view.lineage == packet.phase6_view.lineage
    state_ref = next(
        d.authority_ref
        for d in bundle.dependency_manifest
        if d.authority_ref.kind == "RESEARCH_STATE" and d.authority_ref.path == ()
    )
    assert state_ref.path == ()  # The sealed manifest is the native research-state record.
