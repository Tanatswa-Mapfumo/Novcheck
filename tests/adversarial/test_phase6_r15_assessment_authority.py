"""R15 adversarial checks for repository-derived graph authority."""

import json
import sqlite3

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_candidate_record_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentAuthorityError
from novelty_harness.evidence.graph.migrations import ensure_schema
from novelty_harness.evidence.graph.models import GraphEdgeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
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
from novelty_harness.evidence.mapping.dimensions import ComparisonDimension, MCUComparisonProfile
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.precedent.models import PrecedentClassification
from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
from novelty_harness.evidence.verification.integrity import (
    VerifiedEvidenceChain,
    verified_comparison,
)
from novelty_harness.evidence.verification.models import CommitmentStateRecord, SupportVerification
from novelty_harness.runtime.tracing.hashing import canonical_json
from tests.adversarial.test_phase6_r10_content_authority import _authority_nodes, _chain_for_content
from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase6_for_ledger
from tests.unit.evidence.verification.test_eligibility import AS_OF, NOW, PASSAGE_TEXT, verification


def _matrix_chain(case: str) -> VerifiedEvidenceChain:
    baseline = _chain_for_content(PASSAGE_TEXT)
    proposition = baseline.proposition
    bundle = baseline.bundle
    relation_by_case = {
        "SUPPORTS": (SupportVerificationState.SUPPORTED, PrecedentState.DIRECT_PRECEDENT),
        "DIRECT_PRECEDENT": (SupportVerificationState.SUPPORTED, PrecedentState.DIRECT_PRECEDENT),
        "CONTRADICTS": (
            SupportVerificationState.CONTRADICTED,
            PrecedentState.CONTRADICTORY_EVIDENCE,
        ),
        "COMPONENT_PRECEDENT": (
            SupportVerificationState.PARTIALLY_SUPPORTED,
            PrecedentState.COMPONENT_PRECEDENT_ONLY,
        ),
        "NO_MATCH": (
            SupportVerificationState.NOT_SUPPORTED,
            PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
        ),
        "UNRESOLVED": (SupportVerificationState.INSUFFICIENT_CONTEXT, PrecedentState.UNRESOLVED),
    }
    if case in relation_by_case:
        state, relation = relation_by_case[case]
        judged = verification(state)
    elif case == "SCOPED_PARTIAL":
        relation = PrecedentState.ANALOGOUS_PRECEDENT
        scoped = next(
            item for item in baseline.verification.commitment_states if item.commitment_id == "mech"
        ).model_copy(
            update={
                "state": "PARTIALLY_SUPPORTED",
                "supported_subset": "The controller opens the valve above the threshold.",
                "unsupported_remainder": "The controller also logs that threshold event.",
            }
        )
        states = tuple(
            scoped if item.commitment_id == scoped.commitment_id else item
            for item in baseline.verification.commitment_states
        )
        judged = SupportVerification.model_validate(
            baseline.verification.model_copy(
                update={
                    "state": SupportVerificationState.PARTIALLY_SUPPORTED,
                    "commitment_states": states,
                    "supported_portions": ("The controller opens the valve above the threshold.",),
                    "unsupported_portions": ("The controller also logs that threshold event.",),
                }
            ).model_dump(mode="json")
        )
    elif case in {"STRONG_PARTIAL_PRECEDENT", "ANALOGOUS"}:
        commitment_states = baseline.verification.commitment_states
        if case == "STRONG_PARTIAL_PRECEDENT":
            relation = PrecedentState.STRONG_PARTIAL_PRECEDENT
            extra = baseline.proposition.commitments[0].model_copy(
                update={
                    "commitment_id": "feature_extra",
                    "dimension": ComparisonDimension.FEATURES,
                    "text": "the load is remotely logged",
                }
            )
            commitments = (*baseline.proposition.commitments, extra)
            proposition = baseline.proposition.model_copy(update={"commitments": commitments})
            claim = baseline.bundle.claim.model_copy(update={"commitments": commitments})
            bundle = baseline.bundle.model_copy(update={"claim": claim})
            extra_state = CommitmentStateRecord(
                commitment_id=extra.commitment_id,
                dimension=extra.dimension,
                state="NOT_SUPPORTED",
                rationale="No passage supports remote logging",
                passage_ids=baseline.edge.passage_ids,
            )
            judged = SupportVerification.model_validate(
                baseline.verification.model_copy(
                    update={
                        "state": SupportVerificationState.PARTIALLY_SUPPORTED,
                        "commitment_states": (*commitment_states, extra_state),
                        "material_commitment_ids": tuple(
                            item.commitment_id for item in commitments
                        ),
                        "unsupported_portions": (extra.text,),
                    }
                ).model_dump(mode="json")
            )
        else:
            relation = PrecedentState.ANALOGOUS_PRECEDENT
            unsupported_id = "mech"
            supported_id = "outcome"
            updated_states = tuple(
                item.model_copy(
                    update={
                        "state": "NOT_SUPPORTED"
                        if item.commitment_id == unsupported_id
                        else "SUPPORTED",
                        "rationale": "Matrix case support state",
                    }
                )
                for item in commitment_states
            )
            unsupported = next(
                item
                for item in baseline.proposition.commitments
                if item.commitment_id == unsupported_id
            )
            supported = next(
                item
                for item in baseline.proposition.commitments
                if item.commitment_id == supported_id
            )
            judged = SupportVerification.model_validate(
                baseline.verification.model_copy(
                    update={
                        "state": SupportVerificationState.PARTIALLY_SUPPORTED,
                        "commitment_states": updated_states,
                        "supported_portions": (supported.text,),
                        "unsupported_portions": (unsupported.text,),
                    }
                ).model_dump(mode="json")
            )
            proposition = baseline.proposition
            bundle = baseline.bundle
    else:
        raise AssertionError(f"Unknown graph relation matrix case: {case}")

    mapping = baseline.mapping.model_copy(
        update={"source_version_id": baseline.version.version_id if baseline.version else None}
    )
    edge = build_verified_evidence_edge(
        mapping=mapping,
        verification=judged,
        proposition=proposition,
        source=baseline.source,
        bundle=bundle,
        version=baseline.version,
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id=baseline.assessment_id,
        relation=relation,
    )
    return VerifiedEvidenceChain.model_validate(
        baseline.model_copy(
            update={
                "proposition": proposition,
                "mapping": mapping,
                "bundle": bundle,
                "verification": judged,
                "edge": edge,
            }
        ).model_dump(mode="json")
    )


def _load_committed_matrix_case(tmp_path, case: str):
    chain = _matrix_chain(case)
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    graph_nodes, graph_edges = verified_edge_graph_fragment(
        (chain.edge,),
        (classification,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"{case}.sqlite")
    receipt = repository.upsert(
        nodes=(*_authority_nodes(chain), *graph_nodes),
        edges=graph_edges,
        verified_edges=(chain.edge,),
        verified_chains=(chain,),
        classified_comparisons=(
            ClassifiedComparison(comparison=comparison, classification=classification),
        ),
    )
    assert receipt is not None
    target = Phase6TargetLedgerRecord(
        snapshot_id="pending",
        assessment_id=chain.assessment_id,
        profile=MCUComparisonProfile(
            target_id=chain.edge.mcu_id,
            label="Graph relation matrix target",
            statement="One local matrix assessment target",
        ),
    )
    candidate = Phase6CandidateLedgerRecord(
        snapshot_id="pending",
        assessment_id=chain.assessment_id,
        target_id=chain.edge.mcu_id,
        source_id=chain.source.source_id,
        source_version_id=chain.version.version_id if chain.version else None,
        source_content_hash=chain.source.content_hash,
        version_content_hash=chain.version.content_hash if chain.version else None,
        source_access_state=chain.source.access_state,
        version_access_state=chain.version.access_state if chain.version else None,
        decision="ASSESSED",
        projection_intent="GRAPH_BACKED",
        commit_id=receipt.commit_id,
        verified_edge_id=chain.edge.edge_id,
        classification_id=classification.classification_id,
    )
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="pending",
        assessment_id=chain.assessment_id,
        as_of=chain.edge.chronology.as_of,
        method_version="phase6-r15-relation-matrix-v1",
        max_sources_per_mcu=1,
        max_versions_per_source=1,
        max_expansions=0,
        window_chars=0,
        target_record_ids=(),
        candidate_record_ids=(),
        derived_record_ids=(),
        lineage_cluster_ids=(),
        commit_ids=(receipt.commit_id,),
        coverage=Phase6CoverageLedger(),
        audit_refs=(),
        completed_at=NOW,
    )
    snapshot_id = phase6_assessment_snapshot_id(
        snapshot, targets=(target,), candidates=(candidate,), derived=()
    )
    target = target.model_copy(update={"snapshot_id": snapshot_id})
    candidate = candidate.model_copy(update={"snapshot_id": snapshot_id})
    snapshot = snapshot.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": (phase6_target_record_id(target),),
            "candidate_record_ids": (phase6_candidate_record_id(candidate),),
        }
    )
    repository.record_phase6_assessment(
        snapshot, targets=(target,), candidates=(candidate,), derived=()
    )
    view = repository.load_phase6_assessment(chain.assessment_id, snapshot_id=snapshot_id)
    return repository, view, classification, graph_edges


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
async def test_caller_created_view_and_receipt_do_not_change_repository_read(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        loaded = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert loaded.authorized_graph_relations
        caller_view = loaded.model_copy(update={"authorized_graph_relations": ()})
        caller_receipt = result.commit_receipts[0].model_copy(
            update={"commit_id": "p6commit_forged"}
        )
        assert not caller_view.authorized_graph_relations
        with pytest.raises(ValueError):
            repository.resolve_phase6_commit(caller_receipt)
        assert (
            repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
            == loaded
        )
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


@pytest.mark.parametrize(
    ("case", "expected_relation", "expected_kinds", "expected_status"),
    [
        (
            "SUPPORTS",
            PrecedentState.DIRECT_PRECEDENT,
            {GraphEdgeKind.SUPPORTS, GraphEdgeKind.DIRECT_PRECEDENT},
            "GRAPH_AUTHORIZED",
        ),
        (
            "DIRECT_PRECEDENT",
            PrecedentState.DIRECT_PRECEDENT,
            {GraphEdgeKind.SUPPORTS, GraphEdgeKind.DIRECT_PRECEDENT},
            "GRAPH_AUTHORIZED",
        ),
        (
            "CONTRADICTS",
            PrecedentState.CONTRADICTORY_EVIDENCE,
            {GraphEdgeKind.CONTRADICTS},
            "GRAPH_AUTHORIZED",
        ),
        (
            "STRONG_PARTIAL_PRECEDENT",
            PrecedentState.STRONG_PARTIAL_PRECEDENT,
            {GraphEdgeKind.STRONG_PARTIAL_PRECEDENT},
            "GRAPH_AUTHORIZED",
        ),
        (
            "COMPONENT_PRECEDENT",
            PrecedentState.COMPONENT_PRECEDENT_ONLY,
            {GraphEdgeKind.COMPONENT_PRECEDENT},
            "GRAPH_AUTHORIZED",
        ),
        (
            "ANALOGOUS",
            PrecedentState.ANALOGOUS_PRECEDENT,
            {GraphEdgeKind.ANALOGOUS},
            "GRAPH_AUTHORIZED",
        ),
        (
            "NO_MATCH",
            PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
            {GraphEdgeKind.NO_MATCH},
            "GRAPH_AUTHORIZED",
        ),
        (
            "UNRESOLVED",
            PrecedentState.UNRESOLVED,
            set(),
            "NONRELATIONAL_STATUS",
        ),
    ],
)
def test_loader_preserves_exact_projected_graph_relation_matrix(
    tmp_path, case, expected_relation, expected_kinds, expected_status
) -> None:
    repository, view, classification, expected_edges = _load_committed_matrix_case(tmp_path, case)
    try:
        assert classification.relation == expected_relation
        assert len(view.committed_comparisons) == 1
        comparison = view.committed_comparisons[0]
        assert comparison.projection_status == expected_status
        actual_kinds = {item.edge.kind for item in view.authorized_graph_relations}
        assert actual_kinds == expected_kinds
        assert set(comparison.graph_edge_ids) == {item.edge_id for item in expected_edges}
        assert {item.edge.edge_id for item in view.authorized_graph_relations} == {
            item.edge_id for item in expected_edges
        }
        if expected_status == "NONRELATIONAL_STATUS":
            assert comparison.proposition_node_id is None
            assert view.authorized_graph_relations == ()
        else:
            assert comparison.proposition_node_id is not None
            assert all(
                item.proposition_node.node_id == comparison.proposition_node_id
                for item in view.authorized_graph_relations
            )
    finally:
        repository.close()


def test_superficial_similarity_fragment_does_not_create_relation_edges() -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    unsupported = verification(SupportVerificationState.NOT_SUPPORTED)
    edge = build_verified_evidence_edge(
        mapping=chain.mapping,
        verification=unsupported,
        proposition=chain.proposition,
        source=chain.source,
        bundle=chain.bundle,
        version=chain.version,
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id=chain.assessment_id,
        relation=PrecedentState.SUPERFICIAL_SIMILARITY,
    )
    classification = PrecedentClassification(
        classification_id="cls_superficial_matrix",
        source_id=edge.source_id,
        source_version_id=edge.source_version_id,
        mcu_id=edge.mcu_id,
        mapping_id=edge.mapping_id,
        verification_id=edge.verification_id,
        relation=PrecedentState.SUPERFICIAL_SIMILARITY,
        basis=("Superficial similarity matrix fixture",),
        classifier_version="precedent-classifier-v2",
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    nodes, edges = verified_edge_graph_fragment(
        (edge,),
        (classification,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    assert any(node.kind.value == "EVIDENCE_PROPOSITION" for node in nodes)
    assert edges == ()
