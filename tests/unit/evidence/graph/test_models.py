from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from novelty_harness.domain.enums import SupportVerificationState
from novelty_harness.evidence.graph.models import (
    PHASE5_EDGE_KINDS,
    PHASE6_EDGE_KINDS,
    EdgeVerificationRef,
    EvidenceGraph,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    node_id_prefix,
)
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository, GraphDirection
from tests.fixtures.phase5 import phase5_provenance

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("graph-model-test")


def node(node_id: str, kind: GraphNodeKind, **overrides: object) -> GraphNode:
    values: dict[str, object] = {
        "node_id": node_id,
        "kind": kind,
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return GraphNode.model_validate(values)


def edge(
    edge_id: str,
    kind: GraphEdgeKind,
    source: str,
    target: str,
    **overrides: object,
) -> GraphEdge:
    values: dict[str, object] = {
        "edge_id": edge_id,
        "kind": kind,
        "source_node_id": source,
        "target_node_id": target,
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return GraphEdge.model_validate(values)


def sample_nodes() -> tuple[GraphNode, GraphNode, GraphNode, GraphNode]:
    return (
        node("src_a", GraphNodeKind.SOURCE, label="Source A"),
        node("src_b", GraphNodeKind.SOURCE, label="Source B"),
        node("qry_1", GraphNodeKind.QUERY, label="query one"),
        node("run_1", GraphNodeKind.SEARCH_RUN, label="search run one"),
    )


def test_node_identity_must_match_its_kind() -> None:
    assert node_id_prefix(GraphNodeKind.SOURCE) == "src_"
    with pytest.raises(ValidationError):
        node("idea_1", GraphNodeKind.SOURCE)
    with pytest.raises(ValidationError):
        node("src_1", GraphNodeKind.IDEA)
    with pytest.raises(ValidationError):
        node("src_1", GraphNodeKind.SOURCE, unexpected=True)


def test_phase6_edges_require_eligible_verification_and_phase5_edges_forbid_it() -> None:
    assert GraphEdgeKind.DIRECT_PRECEDENT in PHASE6_EDGE_KINDS
    assert GraphEdgeKind.SUPPORTS in PHASE6_EDGE_KINDS
    assert GraphEdgeKind.CITES in PHASE5_EDGE_KINDS
    # Phase 6 kinds cannot exist without an eligibility reference.
    with pytest.raises(ValidationError):
        edge("gedge_1", GraphEdgeKind.DIRECT_PRECEDENT, "src_a", "src_b")
    with pytest.raises(ValidationError):
        edge("gedge_1", GraphEdgeKind.SUPPORTS, "src_a", "src_b")
    supported_ref = EdgeVerificationRef(
        verified_edge_id="edge_1",
        support_state=SupportVerificationState.SUPPORTED,
        decisive=True,
    )
    partial_ref = EdgeVerificationRef(
        verified_edge_id="edge_1",
        support_state=SupportVerificationState.PARTIALLY_SUPPORTED,
        decisive=False,
    )
    contradicted_ref = EdgeVerificationRef(
        verified_edge_id="edge_1",
        support_state=SupportVerificationState.CONTRADICTED,
        decisive=False,
    )
    assert (
        edge(
            "gedge_ok",
            GraphEdgeKind.DIRECT_PRECEDENT,
            "src_a",
            "src_b",
            verification=supported_ref,
        ).kind
        == GraphEdgeKind.DIRECT_PRECEDENT
    )
    assert (
        edge(
            "gedge_ok",
            GraphEdgeKind.STRONG_PARTIAL_PRECEDENT,
            "src_a",
            "src_b",
            verification=partial_ref,
        ).kind
        == GraphEdgeKind.STRONG_PARTIAL_PRECEDENT
    )
    assert (
        edge(
            "gedge_ok",
            GraphEdgeKind.CONTRADICTS,
            "src_a",
            "src_b",
            verification=contradicted_ref,
        ).kind
        == GraphEdgeKind.CONTRADICTS
    )
    # A non-decisive reference cannot create a direct-precedent graph edge.
    with pytest.raises(ValidationError):
        edge(
            "gedge_bad",
            GraphEdgeKind.DIRECT_PRECEDENT,
            "src_a",
            "src_b",
            verification=partial_ref,
        )
    with pytest.raises(ValidationError):
        edge(
            "gedge_bad",
            GraphEdgeKind.SUPPORTS,
            "src_a",
            "src_b",
            verification=partial_ref,
        )
    # Phase 5 provenance edges must not carry verification refs.
    with pytest.raises(ValidationError):
        edge(
            "gedge_bad",
            GraphEdgeKind.CITES,
            "src_a",
            "src_b",
            verification=supported_ref,
        )
    # Phase 5 kinds are accepted without verification.
    accepted = edge("gedge_1", GraphEdgeKind.DISCOVERED_BY, "src_a", "qry_1")
    assert accepted.kind == GraphEdgeKind.DISCOVERED_BY


def test_graph_rejects_dangling_and_duplicate_identities() -> None:
    nodes = sample_nodes()
    good = EvidenceGraph(
        graph_id="graph_1",
        nodes=nodes,
        edges=(
            edge("gedge_1", GraphEdgeKind.CITES, "src_a", "src_b"),
            edge("gedge_2", GraphEdgeKind.DISCOVERED_BY, "src_a", "qry_1"),
        ),
    )
    with pytest.raises(ValidationError):
        EvidenceGraph(
            graph_id="graph_1",
            nodes=nodes[:1],
            edges=(edge("gedge_1", GraphEdgeKind.CITES, "src_a", "src_missing"),),
        )
    with pytest.raises(ValidationError):
        EvidenceGraph(graph_id="graph_1", nodes=(*nodes, nodes[0]))
    with pytest.raises(ValidationError):
        EvidenceGraph(
            graph_id="graph_1",
            nodes=nodes,
            edges=(
                edge("gedge_1", GraphEdgeKind.CITES, "src_a", "src_b"),
                edge("gedge_1", GraphEdgeKind.CITES, "src_b", "src_a"),
            ),
        )
    with pytest.raises(ValidationError):
        edge("gedge_1", GraphEdgeKind.CITES, "src_a", "src_a")
    assert good.node("src_a") is not None


def test_graph_neighbors_support_direction_and_kind_filters() -> None:
    graph = EvidenceGraph(
        graph_id="graph_1",
        nodes=sample_nodes(),
        edges=(
            edge("gedge_1", GraphEdgeKind.CITES, "src_a", "src_b"),
            edge("gedge_2", GraphEdgeKind.DISCOVERED_BY, "src_a", "qry_1"),
        ),
    )
    outbound = graph.neighbors("src_a")
    assert {item.node_id for item in outbound} == {"src_b", "qry_1"}
    inbound = graph.neighbors("src_b", direction="IN")
    assert [item.node_id for item in inbound] == ["src_a"]
    both = graph.neighbors("src_a", direction="BOTH")
    assert {item.node_id for item in both} == {"src_b", "qry_1"}
    assert graph.neighbors(
        "qry_1",
        direction="IN",
    ) == graph.neighbors("qry_1", direction="IN")


def test_graph_models_and_protocol_are_storage_independent() -> None:
    import novelty_harness.evidence.graph.models as models_module
    import novelty_harness.evidence.graph.repository as repository_module

    for module in (models_module, repository_module):
        source = module.__file__
        assert source is not None
        text = open(source).read()
        assert "sqlalchemy" not in text.lower()

    class InMemoryRepository:
        def upsert(self, *, nodes=(), edges=(), clusters=()):  # type: ignore[no-untyped-def]
            pass

        def resolve_phase6_commit(self, receipt):  # type: ignore[no-untyped-def]
            raise ValueError("No persisted Phase 6 commit")

        def record_phase6_assessment(self, snapshot, *, targets=(), candidates=(), derived=()):  # type: ignore[no-untyped-def]
            return snapshot.snapshot_id

        def get_node(self, node_id: str) -> GraphNode | None:
            return None

        def get_edge(self, edge_id: str) -> GraphEdge | None:
            return None

        def nodes(self, *, kinds=None):  # type: ignore[no-untyped-def]
            return ()

        def edges(self, *, node_id=None, direction=GraphDirection.OUT, kinds=None):  # type: ignore[no-untyped-def]
            return ()

        def neighbors(self, node_id, *, direction=GraphDirection.OUT, kinds=None):  # type: ignore[no-untyped-def]
            return ()

        def lineage_cluster_for_source(self, source_id):  # type: ignore[no-untyped-def]
            return None

        def lineage_clusters(self):  # type: ignore[no-untyped-def]
            return ()

        def close(self) -> None:
            pass

    assert isinstance(InMemoryRepository(), EvidenceGraphRepository)
