"""R15 adversarial checks for repository-derived graph authority."""

import json
import sqlite3

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_candidate_record_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentAuthorityError
from novelty_harness.evidence.graph.migrations import ensure_schema
from novelty_harness.evidence.graph.phase6_mapping import verified_edge_graph_fragment
from novelty_harness.evidence.graph.sqlalchemy_models import (
    GraphEdgeRow,
    GraphNodeRow,
    Phase6AssessmentCandidateRow,
    Phase6AssessmentDerivedRow,
    Phase6AssessmentSnapshotRow,
    Phase6AssessmentTargetRow,
    Phase6GraphEdgeMembershipRow,
    Phase6GraphNodeMembershipRow,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.runtime.tracing.hashing import canonical_json
from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase6_for_ledger


@pytest.mark.asyncio
async def test_direct_relation_is_available_after_exact_replay(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        first = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        second = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        direct = [
            relation
            for relation in first.authorized_graph_relations
            if relation.edge.kind.value == "DIRECT_PRECEDENT"
        ]
        assert direct
        assert first == second
        assert all(item.proposition_node.kind.value == "EVIDENCE_PROPOSITION" for item in direct)
        relations_by_comparison: dict[tuple[str, str, str], set[str]] = {}
        for item in first.authorized_graph_relations:
            key = (
                item.commit_id,
                str(item.verified_edge_id),
                str(item.classification_id),
            )
            relations_by_comparison.setdefault(key, set()).add(item.edge.edge_id)
        for comparison in first.committed_comparisons:
            chain = comparison.comparison.comparison.chain
            classification = comparison.comparison.classification
            _, expected_edges = verified_edge_graph_fragment(
                (chain.edge,),
                (classification,),
                observed_at=chain.edge.observed_at,
                provenance=chain.edge.provenance,
            )
            expected_ids = {item.edge_id for item in expected_edges}
            actual_ids = relations_by_comparison.get(
                (
                    comparison.commit_id,
                    str(chain.edge.edge_id),
                    str(classification.classification_id),
                ),
                set(),
            )
            if comparison.projection_status == "GRAPH_AUTHORIZED":
                assert set(comparison.graph_edge_ids) == expected_ids
                assert actual_ids == expected_ids
            elif comparison.projection_status == "NONRELATIONAL_STATUS":
                assert not expected_ids
            else:
                assert comparison.projection_status == "SEMANTIC_ONLY"
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "edge_membership",
        "node_membership",
        "edge_row",
        "node_row",
        "citation",
        "malformed_row",
        "foreign_manifest",
    ],
)
async def test_graph_corruption_never_becomes_no_direct(tmp_path, corruption: str) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        before = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        direct = next(
            item
            for item in before.authorized_graph_relations
            if item.edge.kind.value == "DIRECT_PRECEDENT"
        )
        with Session(repository._engine) as session:
            if corruption == "edge_membership":
                session.delete(session.get(Phase6GraphEdgeMembershipRow, direct.edge.edge_id))
            elif corruption == "node_membership":
                session.delete(
                    session.get(Phase6GraphNodeMembershipRow, direct.proposition_node.node_id)
                )
            elif corruption == "citation":
                row = session.get(GraphEdgeRow, direct.edge.edge_id)
                document = json.loads(row.document_json)
                document["attributes"]["passage_ids"] = []
                row.document_json = json.dumps(document, separators=(",", ":"), sort_keys=True)
            elif corruption == "malformed_row":
                row = session.get(GraphEdgeRow, direct.edge.edge_id)
                row.document_json = "not-json"
            else:
                membership = session.get(Phase6GraphEdgeMembershipRow, direct.edge.edge_id)
                another_commit = next(
                    commit_id for commit_id in before.commit_ids if commit_id != direct.commit_id
                )
                membership.commit_id = another_commit
            if corruption not in {"edge_row", "node_row"}:
                session.commit()
        if corruption in {"edge_row", "node_row"}:
            raw = repository.engine.raw_connection()
            try:
                raw.driver_connection.execute("PRAGMA foreign_keys=OFF")
                if corruption == "edge_row":
                    raw.driver_connection.execute(
                        "DELETE FROM graph_edges WHERE edge_id = ?", (direct.edge.edge_id,)
                    )
                else:
                    raw.driver_connection.execute(
                        "DELETE FROM graph_nodes WHERE node_id = ?",
                        (direct.proposition_node.node_id,),
                    )
                raw.driver_connection.commit()
            finally:
                raw.close()

        with pytest.raises(Phase6AssessmentAuthorityError):
            repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_v5_migration_does_not_recreate_graph_membership(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        direct = next(
            item
            for item in view.authorized_graph_relations
            if item.edge.kind.value == "DIRECT_PRECEDENT"
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase6_graph_edge_memberships WHERE edge_id = :edge_id"),
                {"edge_id": direct.edge.edge_id},
            )
            connection.execute(
                text("DELETE FROM phase6_graph_node_memberships WHERE node_id = :node_id"),
                {"node_id": direct.proposition_node.node_id},
            )
            connection.execute(text("UPDATE schema_version SET version = 5"))
        assert ensure_schema(repository.engine) == 7
        with pytest.raises(Phase6AssessmentAuthorityError):
            repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_explicit_semantic_only_candidate_has_no_graph_authority(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        with Session(repository.engine) as session:
            snapshot_row = session.get(Phase6AssessmentSnapshotRow, result.snapshot_id)
            old_snapshot = Phase6AssessmentSnapshotRecord.model_validate_json(
                snapshot_row.document_json
            )
            old_targets = tuple(
                Phase6TargetLedgerRecord.model_validate_json(row.document_json)
                for row in session.query(Phase6AssessmentTargetRow)
                .filter_by(snapshot_id=result.snapshot_id)
                .all()
            )
            old_candidates = tuple(
                Phase6CandidateLedgerRecord.model_validate_json(row.document_json)
                for row in session.query(Phase6AssessmentCandidateRow)
                .filter_by(snapshot_id=result.snapshot_id)
                .all()
            )
        candidate = next(item for item in old_candidates if item.decision == "ASSESSED")
        semantic_candidate = candidate.model_copy(update={"projection_intent": "SEMANTIC_ONLY"})
        pending_candidates = (semantic_candidate.model_copy(update={"snapshot_id": "pending"}),)
        pending_targets = tuple(
            item.model_copy(update={"snapshot_id": "pending"}) for item in old_targets
        )
        snapshot_facts = old_snapshot.model_copy(
            update={"commit_ids": (candidate.commit_id,), "derived_record_ids": ()}
        )
        new_snapshot_id = phase6_assessment_snapshot_id(
            snapshot_facts,
            targets=pending_targets,
            candidates=pending_candidates,
            derived=(),
        )
        targets = tuple(
            item.model_copy(update={"snapshot_id": new_snapshot_id}) for item in old_targets
        )
        candidates = (semantic_candidate.model_copy(update={"snapshot_id": new_snapshot_id}),)
        snapshot = snapshot_facts.model_copy(
            update={
                "snapshot_id": new_snapshot_id,
                "target_record_ids": tuple(phase6_target_record_id(item) for item in targets),
                "candidate_record_ids": tuple(
                    phase6_candidate_record_id(item) for item in candidates
                ),
                "derived_record_ids": (),
            }
        )
        assert (
            phase6_assessment_snapshot_id(
                snapshot, targets=targets, candidates=candidates, derived=()
            )
            == new_snapshot_id
        )

        classified = next(
            item
            for item in repository.resolve_phase6_commit(
                next(
                    receipt
                    for receipt in result.commit_receipts
                    if receipt.commit_id == candidate.commit_id
                )
            ).comparisons
            if item.comparison.chain.edge.edge_id == candidate.verified_edge_id
        )
        chain = classified.comparison.chain
        expected_nodes, expected_edges = verified_edge_graph_fragment(
            (chain.edge,),
            (classified.classification,),
            observed_at=chain.edge.observed_at,
            provenance=chain.edge.provenance,
        )
        with Session(repository.engine) as session, session.begin():
            old_target_rows = (
                session.query(Phase6AssessmentTargetRow)
                .filter_by(snapshot_id=result.snapshot_id)
                .all()
            )
            old_candidate_rows = (
                session.query(Phase6AssessmentCandidateRow)
                .filter_by(snapshot_id=result.snapshot_id)
                .all()
            )
            old_derived_rows = (
                session.query(Phase6AssessmentDerivedRow)
                .filter_by(snapshot_id=result.snapshot_id)
                .all()
            )
            for row in (*old_candidate_rows, *old_derived_rows, *old_target_rows):
                session.delete(row)
            session.delete(session.get(Phase6AssessmentSnapshotRow, result.snapshot_id))
            session.flush()
            for edge in expected_edges:
                session.delete(session.get(Phase6GraphEdgeMembershipRow, edge.edge_id))
                session.delete(session.get(GraphEdgeRow, edge.edge_id))
            for node in expected_nodes:
                if node.node_id == chain.source.source_id:
                    continue
                session.delete(session.get(Phase6GraphNodeMembershipRow, node.node_id))
                session.delete(session.get(GraphNodeRow, node.node_id))
            session.add(
                Phase6AssessmentSnapshotRow(
                    snapshot_id=new_snapshot_id,
                    assessment_id=snapshot.assessment_id,
                    document_json=canonical_json(snapshot),
                )
            )
            session.flush()
            for item in targets:
                session.add(
                    Phase6AssessmentTargetRow(
                        record_id=phase6_target_record_id(item),
                        snapshot_id=new_snapshot_id,
                        assessment_id=item.assessment_id,
                        target_id=item.profile.target_id,
                        document_json=canonical_json(item),
                    )
                )
            session.flush()
            for item in candidates:
                session.add(
                    Phase6AssessmentCandidateRow(
                        record_id=phase6_candidate_record_id(item),
                        snapshot_id=new_snapshot_id,
                        assessment_id=item.assessment_id,
                        target_id=item.target_id,
                        source_id=item.source_id,
                        source_version_id=item.source_version_id,
                        commit_id=item.commit_id,
                        document_json=canonical_json(item),
                    )
                )

        view = repository.load_phase6_assessment("asm_research", snapshot_id=new_snapshot_id)
        assert len(view.committed_comparisons) == 1
        assert view.committed_comparisons[0].projection_status == "SEMANTIC_ONLY"
        assert view.committed_comparisons[0].graph_edge_ids == ()
        assert view.authorized_graph_relations == ()
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_membership_cannot_change_between_snapshot_and_graph_reads(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    database = graph_database(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    blocked: list[bool] = []

    def try_concurrent_membership_delete(
        _connection, _cursor, statement, _parameters, _context, _many
    ) -> None:
        if "FROM phase6_graph_node_memberships" not in statement:
            return
        try:
            with sqlite3.connect(database, timeout=0) as writer:
                writer.execute("DELETE FROM phase6_graph_node_memberships")
        except sqlite3.OperationalError as exc:
            blocked.append("locked" in str(exc).casefold())

    event.listen(repository.engine, "after_cursor_execute", try_concurrent_membership_delete)
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
    finally:
        event.remove(repository.engine, "after_cursor_execute", try_concurrent_membership_delete)
        repository.close()
    assert view.authorized_graph_relations
    assert blocked and all(blocked)
