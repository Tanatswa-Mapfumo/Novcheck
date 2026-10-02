"""Public Phase 6 graph reads agree with the assessment authority boundary."""

import json

import pytest
from sqlalchemy import text

from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentAuthorityError
from novelty_harness.evidence.graph.models import GraphEdgeKind
from novelty_harness.evidence.graph.repository import Phase6CommitReceipt
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from tests.adversarial.test_phase6_r15_assessment_authority import _load_committed_matrix_case
from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase6_for_ledger


def test_r15_proposition_membership_revocation_hides_direct_from_every_reader(tmp_path) -> None:
    repository, view, _, _ = _load_committed_matrix_case(tmp_path, "DIRECT_PRECEDENT")
    try:
        relation = next(
            item
            for item in view.authorized_graph_relations
            if item.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
        )
        edge = relation.edge
        proposition_id = relation.proposition_node.node_id
        direct_kind = frozenset({GraphEdgeKind.DIRECT_PRECEDENT})
        assert repository.get_edge(edge.edge_id) == edge
        assert repository.get_node(proposition_id) == relation.proposition_node
        assert edge in repository.edges(kinds=direct_kind)
        assert edge.target_node_id in {
            node.node_id for node in repository.neighbors(edge.source_node_id, kinds=direct_kind)
        }
        assert (
            repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
            == view
        )

        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase6_graph_node_memberships WHERE node_id = :node_id"),
                {"node_id": proposition_id},
            )

        assert repository.get_node(proposition_id) is None
        assert repository.get_edge(edge.edge_id) is None
        assert edge not in repository.edges(kinds=direct_kind)
        assert edge.target_node_id not in {
            node.node_id for node in repository.neighbors(edge.source_node_id, kinds=direct_kind)
        }
        with pytest.raises(Phase6AssessmentAuthorityError):
            repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
    finally:
        repository.close()


def _assert_relation_absent(repository, view, relation) -> None:
    edge = relation.edge
    kind = frozenset({edge.kind})
    assert repository.get_edge(edge.edge_id) is None
    assert edge not in repository.edges(kinds=kind)
    assert edge.target_node_id not in {
        node.node_id for node in repository.neighbors(edge.source_node_id, kinds=kind)
    }
    with pytest.raises(Phase6AssessmentAuthorityError):
        repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)


@pytest.mark.parametrize(
    "mutation",
    [
        "edge_membership",
        "node_membership",
        "node_row",
        "edge_row",
        "edge_source",
        "edge_target",
        "edge_kind",
        "edge_verified_id",
        "edge_classification_id",
        "edge_citation",
        "node_identity",
        "sibling_edge_membership",
    ],
)
def test_r15_all_public_relation_readers_agree_on_projection_corruption(
    tmp_path, mutation: str
) -> None:
    repository, view, _, _ = _load_committed_matrix_case(tmp_path, "DIRECT_PRECEDENT")
    try:
        relation = next(
            item
            for item in view.authorized_graph_relations
            if item.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
        )
        edge = relation.edge
        proposition_id = relation.proposition_node.node_id
        if mutation in {"node_row", "edge_row"}:
            raw = repository.engine.raw_connection()
            try:
                raw.driver_connection.execute("PRAGMA foreign_keys=OFF")
                if mutation == "node_row":
                    raw.driver_connection.execute(
                        "DELETE FROM graph_nodes WHERE node_id = ?", (proposition_id,)
                    )
                else:
                    raw.driver_connection.execute(
                        "DELETE FROM graph_edges WHERE edge_id = ?", (edge.edge_id,)
                    )
                raw.driver_connection.commit()
            finally:
                raw.close()
        elif mutation in {"edge_membership", "node_membership", "sibling_edge_membership"}:
            with repository.engine.begin() as connection:
                if mutation == "node_membership":
                    connection.execute(
                        text("DELETE FROM phase6_graph_node_memberships WHERE node_id = :id"),
                        {"id": proposition_id},
                    )
                else:
                    sibling_id = next(
                        item.edge.edge_id
                        for item in view.authorized_graph_relations
                        if item.edge.edge_id != edge.edge_id
                    )
                    connection.execute(
                        text("DELETE FROM phase6_graph_edge_memberships WHERE edge_id = :id"),
                        {"id": edge.edge_id if mutation == "edge_membership" else sibling_id},
                    )
        else:
            table = "graph_nodes" if mutation == "node_identity" else "graph_edges"
            id_column = "node_id" if mutation == "node_identity" else "edge_id"
            identity = proposition_id if mutation == "node_identity" else edge.edge_id
            with repository.engine.begin() as connection:
                document = json.loads(
                    connection.execute(
                        text(f"SELECT document_json FROM {table} WHERE {id_column} = :id"),
                        {"id": identity},
                    ).scalar_one()
                )
                if mutation == "node_identity":
                    document["attributes"]["proposition_id"] = "prop_foreign"
                elif mutation == "edge_source":
                    document["source_node_id"] = "src_foreign"
                elif mutation == "edge_target":
                    document["target_node_id"] = "mcu_foreign"
                elif mutation == "edge_kind":
                    document["kind"] = "COMPONENT_PRECEDENT"
                elif mutation == "edge_verified_id":
                    document["attributes"]["verified_edge_id"] = "vedge_foreign"
                elif mutation == "edge_classification_id":
                    document["attributes"]["classification_id"] = "cls_foreign"
                else:
                    document["attributes"]["passage_ids"] = ["pass_foreign"]
                connection.execute(
                    text(f"UPDATE {table} SET document_json = :document WHERE {id_column} = :id"),
                    {"document": json.dumps(document), "id": identity},
                )
        _assert_relation_absent(repository, view, relation)
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["edge_manifest", "node_manifest", "different_manifests"])
async def test_r15_foreign_or_split_manifest_hides_relation_from_all_readers(
    tmp_path, mutation: str
) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        relation = next(
            item
            for item in view.authorized_graph_relations
            if item.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
        )
        foreign = [item for item in view.commit_ids if item != relation.commit_id]
        assert len(foreign) >= 2
        with repository.engine.begin() as connection:
            if mutation in {"edge_manifest", "different_manifests"}:
                connection.execute(
                    text(
                        "UPDATE phase6_graph_edge_memberships SET commit_id = :commit "
                        "WHERE edge_id = :id"
                    ),
                    {"commit": foreign[0], "id": relation.edge.edge_id},
                )
            if mutation in {"node_manifest", "different_manifests"}:
                connection.execute(
                    text(
                        "UPDATE phase6_graph_node_memberships SET commit_id = :commit "
                        "WHERE node_id = :id"
                    ),
                    {
                        "commit": foreign[1] if mutation == "different_manifests" else foreign[0],
                        "id": relation.proposition_node.node_id,
                    },
                )
        assert repository.get_edge(relation.edge.edge_id) is None
        assert relation.edge not in repository.edges(kinds=frozenset({relation.edge.kind}))
        assert relation.edge.target_node_id not in {
            node.node_id
            for node in repository.neighbors(
                relation.edge.source_node_id, kinds=frozenset({relation.edge.kind})
            )
        }
        with pytest.raises(Phase6AssessmentAuthorityError):
            repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
    finally:
        repository.close()


@pytest.mark.parametrize(
    "case",
    [
        "DIRECT_PRECEDENT",
        "CONTRADICTS",
        "STRONG_PARTIAL_PRECEDENT",
        "COMPONENT_PRECEDENT",
        "ANALOGOUS",
        "NO_MATCH",
    ],
)
def test_r15_every_graph_backed_relation_requires_companion_proposition(
    tmp_path, case: str
) -> None:
    repository, view, _, _ = _load_committed_matrix_case(tmp_path, case)
    try:
        assert view.authorized_graph_relations
        for relation in view.authorized_graph_relations:
            assert repository.get_edge(relation.edge.edge_id) == relation.edge
        proposition_id = view.authorized_graph_relations[0].proposition_node.node_id
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase6_graph_node_memberships WHERE node_id = :id"),
                {"id": proposition_id},
            )
        for relation in view.authorized_graph_relations:
            assert repository.get_edge(relation.edge.edge_id) is None
            assert relation.edge not in repository.edges(kinds=frozenset({relation.edge.kind}))
            assert relation.edge.target_node_id not in {
                node.node_id
                for node in repository.neighbors(
                    relation.edge.source_node_id, kinds=frozenset({relation.edge.kind})
                )
            }
        with pytest.raises(Phase6AssessmentAuthorityError):
            repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
    finally:
        repository.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "node_membership_classification",
        "node_membership_verified",
        "edge_membership_classification",
        "edge_membership_verified",
        "node_label",
        "node_row_kind",
        "edge_row_kind",
        "edge_row_source",
        "edge_row_target",
        "proposition_mapping",
        "proposition_citations",
        "edge_verification_ref",
        "sibling_edge_citation",
    ],
)
def test_r15_fresh_projection_authority_variants(tmp_path, mutation: str) -> None:
    repository, view, _, _ = _load_committed_matrix_case(tmp_path, "DIRECT_PRECEDENT")
    try:
        relation = next(
            item
            for item in view.authorized_graph_relations
            if item.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
        )
        edge = relation.edge
        node_id = relation.proposition_node.node_id
        sibling = next(
            item.edge
            for item in view.authorized_graph_relations
            if item.edge.edge_id != edge.edge_id
        )
        raw = repository.engine.raw_connection()
        try:
            connection = raw.driver_connection
            connection.execute("PRAGMA foreign_keys=OFF")
            if mutation.startswith(("node_membership", "edge_membership")):
                is_node = mutation.startswith("node_membership")
                table = (
                    "phase6_graph_node_memberships" if is_node else "phase6_graph_edge_memberships"
                )
                identity_kind = mutation.split("membership_", 1)[1]
                column = "verified_edge_id" if identity_kind == "verified" else "classification_id"
                id_column = "node_id" if is_node else "edge_id"
                connection.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {id_column} = ?",
                    ("foreign_identity", node_id if is_node else edge.edge_id),
                )
            elif mutation in {
                "node_row_kind",
                "edge_row_kind",
                "edge_row_source",
                "edge_row_target",
            }:
                is_node = mutation == "node_row_kind"
                table = "graph_nodes" if is_node else "graph_edges"
                column = (
                    "kind"
                    if mutation.endswith("kind")
                    else mutation.removeprefix("edge_row_") + "_node_id"
                )
                id_column = "node_id" if is_node else "edge_id"
                connection.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {id_column} = ?",
                    (
                        "CITES" if column == "kind" else "foreign_endpoint",
                        node_id if is_node else edge.edge_id,
                    ),
                )
            else:
                is_node = mutation in {"node_label", "proposition_mapping", "proposition_citations"}
                table = "graph_nodes" if is_node else "graph_edges"
                id_column = "node_id" if is_node else "edge_id"
                identity = (
                    node_id
                    if is_node
                    else (sibling.edge_id if mutation == "sibling_edge_citation" else edge.edge_id)
                )
                document = json.loads(
                    connection.execute(
                        f"SELECT document_json FROM {table} WHERE {id_column} = ?",
                        (identity,),
                    ).fetchone()[0]
                )
                if mutation == "node_label":
                    document["label"] = "Foreign proposition"
                elif mutation == "proposition_mapping":
                    document["attributes"]["mapping_id"] = "map_foreign"
                elif mutation == "proposition_citations":
                    document["attributes"]["passage_ids"] = ["pass_foreign"]
                elif mutation == "edge_verification_ref":
                    document["verification"]["verified_edge_id"] = "vedge_foreign"
                else:
                    document["attributes"]["passage_ids"] = ["pass_foreign"]
                connection.execute(
                    f"UPDATE {table} SET document_json = ? WHERE {id_column} = ?",
                    (json.dumps(document), identity),
                )
            connection.commit()
        finally:
            raw.close()
        _assert_relation_absent(repository, view, relation)
    finally:
        repository.close()


def test_r15_semantic_receipt_survives_revocation_without_graph_relation(tmp_path) -> None:
    repository, view, classification, _ = _load_committed_matrix_case(tmp_path, "DIRECT_PRECEDENT")
    try:
        comparison = view.committed_comparisons[0]
        chain = comparison.comparison.comparison.chain
        receipt = Phase6CommitReceipt(
            commit_id=comparison.commit_id,
            assessment_id=view.assessment_id,
            committed_edge_ids=(chain.edge.edge_id,),
            committed_classification_ids=(classification.classification_id,),
        )
        assert repository.resolve_phase6_commit(receipt).comparisons
        relation = next(
            item
            for item in view.authorized_graph_relations
            if item.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase6_graph_node_memberships WHERE node_id = :id"),
                {"id": relation.proposition_node.node_id},
            )
        assert repository.resolve_phase6_commit(receipt).comparisons
        _assert_relation_absent(repository, view, relation)
    finally:
        repository.close()
