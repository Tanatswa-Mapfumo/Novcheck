from datetime import UTC, datetime

import pytest

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.models import (
    PHASE5_EDGE_KINDS,
    PHASE6_EDGE_KINDS,
    GraphEdge,
    GraphEdgeKind,
    GraphNodeKind,
)
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    proposition_node_id,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.precedent.models import PrecedentClassification
from tests.fixtures.phase5 import make_passage, phase5_provenance
from tests.unit.evidence.verification.test_eligibility import (
    build,
    proposition,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("phase6-mapping-test")


def classification(
    edge,
    relation: PrecedentState,
    *,
    decisive: bool = False,
) -> PrecedentClassification:
    values: dict[str, object] = {
        "classification_id": "cls_" + edge.edge_id,
        "source_id": edge.source_id,
        "source_version_id": edge.source_version_id,
        "mcu_id": edge.mcu_id,
        "mapping_id": edge.mapping_id,
        "verification_id": edge.verification_id,
        "relation": relation,
        "decisive": decisive,
        "basis": ("phase6 mapping fixture",),
        "classifier_version": "precedent-classifier-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    if relation == PrecedentState.STRONG_PARTIAL_PRECEDENT:
        values["missing_elements"] = ("relay",)
    elif relation == PrecedentState.COMPONENT_PRECEDENT_ONLY:
        values["missing_relationships"] = ("sensor controls relay",)
        values["configuration_gap"] = "configuration not identified"
    elif relation == PrecedentState.ANALOGOUS_PRECEDENT:
        values["functional_similarity"] = (proposition().commitments[0].dimension,)
        values["missing_relationships"] = ("sensor controls relay",)
    elif relation == PrecedentState.CONTRADICTORY_EVIDENCE:
        values["contradictions"] = ("opposite direction stated",)
    return PrecedentClassification.model_validate(values)


def test_supported_decisive_edge_creates_proposition_support_and_direct_edges() -> None:
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    assert edge.decisive
    classified = classification(edge, PrecedentState.DIRECT_PRECEDENT, decisive=True)
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    proposition_nodes = [node for node in nodes if node.kind == GraphNodeKind.EVIDENCE_PROPOSITION]
    assert len(proposition_nodes) == 1
    node = proposition_nodes[0]
    assert node.node_id == proposition_node_id(edge)
    assert node.attributes["support_state"] == "SUPPORTED"
    assert node.attributes["decisive"] is True
    assert node.attributes["scope"] == "LOCAL_SOURCE_MCU"
    kinds = {item.kind for item in graph_edges}
    assert kinds == {GraphEdgeKind.SUPPORTS, GraphEdgeKind.DIRECT_PRECEDENT}
    direct = next(item for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    assert direct.verification is not None and direct.verification.decisive
    assert direct.attributes["proposition_node_id"] == node.node_id
    assert direct.attributes["global_absence_claim_permitted"] is False


def test_contradicted_edge_creates_only_a_contradicts_edge() -> None:
    edge = build(
        SupportVerificationState.CONTRADICTED,
        relation=PrecedentState.CONTRADICTORY_EVIDENCE,
    )
    classified = classification(edge, PrecedentState.CONTRADICTORY_EVIDENCE)
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    assert len([node for node in nodes if node.kind == GraphNodeKind.EVIDENCE_PROPOSITION]) == 1
    assert [item.kind for item in graph_edges] == [GraphEdgeKind.CONTRADICTS]
    assert graph_edges[0].verification is not None
    assert graph_edges[0].verification.support_state == SupportVerificationState.CONTRADICTED


def test_unsupported_and_insufficient_edges_create_no_supporting_graph_edge() -> None:
    for state in (
        SupportVerificationState.NOT_SUPPORTED,
        SupportVerificationState.INSUFFICIENT_CONTEXT,
    ):
        edge = build(state)
        nodes, graph_edges = verified_edge_graph_fragment(
            (edge,), (), observed_at=NOW, provenance=phase6_graph_provenance()
        )
        assert len([node for node in nodes if node.kind == GraphNodeKind.EVIDENCE_PROPOSITION]) == 1
        assert graph_edges == ()


def test_partial_and_no_match_classifications_keep_their_graph_kinds() -> None:
    partial_edge = build(SupportVerificationState.PARTIALLY_SUPPORTED)
    partial = classification(partial_edge, PrecedentState.STRONG_PARTIAL_PRECEDENT, decisive=False)
    nodes, graph_edges = verified_edge_graph_fragment(
        (partial_edge,), (partial,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    assert {item.kind for item in graph_edges} == {GraphEdgeKind.STRONG_PARTIAL_PRECEDENT}
    assert all(not item.verification.decisive for item in graph_edges if item.verification)

    absent_edge = build(SupportVerificationState.NOT_SUPPORTED)
    absent = classification(
        absent_edge, PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED, decisive=False
    )
    _, absent_edges = verified_edge_graph_fragment(
        (absent_edge,), (absent,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    assert [item.kind for item in absent_edges] == [GraphEdgeKind.NO_MATCH]
    assert absent_edges[0].attributes["local_only"] is True
    assert absent_edges[0].attributes["global_absence_claim_permitted"] is False


def test_expanded_context_passages_get_graph_nodes() -> None:
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    window = make_passage(
        "src_1",
        text="Expanded context window.",
        passage_id="pass_window",
        source_version_id="srcv_1_v1",
        provenance=ORIGIN,
    )
    nodes, _ = verified_edge_graph_fragment(
        (edge,),
        (classification(edge, PrecedentState.DIRECT_PRECEDENT, decisive=True),),
        passages=(window,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    passage_nodes = [node for node in nodes if node.kind == GraphNodeKind.PASSAGE]
    assert [node.node_id for node in passage_nodes] == ["pass_window"]


def test_repository_persists_phase6_fragment_and_rejects_ineligible_direct_edges() -> None:
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    classified = classification(edge, PrecedentState.DIRECT_PRECEDENT, decisive=True)
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    from novelty_harness.evidence.graph.models import GraphNode

    existing = (
        GraphNode(
            node_id=edge.source_id,
            kind=GraphNodeKind.SOURCE,
            label="Source",
            observed_at=NOW,
            provenance=ORIGIN,
        ),
        GraphNode(
            node_id="mcu_1",
            kind=GraphNodeKind.MCU,
            label="MCU",
            observed_at=NOW,
            provenance=ORIGIN,
        ),
    )
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(nodes=existing)
    repository.upsert(nodes=nodes, edges=graph_edges, verified_edges=(edge,))
    assert (
        repository.get_edge(
            next(
                item.edge_id for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT
            )
        )
        is not None
    )

    direct = next(item for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    tampered = GraphEdge.model_construct(
        **{**direct.model_dump(mode="python"), "verification": None}
    )
    with pytest.raises(ValueError, match="verification reference"):
        repository.upsert(edges=(tampered,))
    repository.close()


def test_phase6_graph_kinds_are_exactly_the_verified_set() -> None:
    assert PHASE6_EDGE_KINDS == frozenset(
        {
            GraphEdgeKind.SUPPORTS,
            GraphEdgeKind.CHALLENGES,
            GraphEdgeKind.CONTRADICTS,
            GraphEdgeKind.DIRECT_PRECEDENT,
            GraphEdgeKind.STRONG_PARTIAL_PRECEDENT,
            GraphEdgeKind.COMPONENT_PRECEDENT,
            GraphEdgeKind.ANALOGOUS,
            GraphEdgeKind.NO_MATCH,
        }
    )
    assert not PHASE5_EDGE_KINDS & PHASE6_EDGE_KINDS
