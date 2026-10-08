from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, inspect, text
from sqlalchemy.exc import IntegrityError

from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION, ensure_schema, schema_version
from novelty_harness.evidence.graph.models import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository, GraphDirection
from novelty_harness.evidence.graph.sqlalchemy_models import GraphEdgeRow
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.provenance.clustering import build_lineage_clusters
from novelty_harness.evidence.provenance.models import (
    LineageConfidence,
    ProvenanceRelation,
)
from tests.fixtures.phase5 import make_edge, make_source, phase5_provenance

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("sqlalchemy-repository-test")


def node(
    node_id: str, kind: GraphNodeKind = GraphNodeKind.SOURCE, **overrides: object
) -> GraphNode:
    values: dict[str, object] = {
        "node_id": node_id,
        "kind": kind,
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return GraphNode.model_validate(values)


def graph_edge(
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


def sample_batch():
    nodes = (
        node("src_a", label="Source A"),
        node("src_b", label="Source B"),
        node("qry_1", GraphNodeKind.QUERY, label="query one"),
        node("run_1", GraphNodeKind.SEARCH_RUN, label="run one"),
    )
    edges = (
        graph_edge("gedge_cites", GraphEdgeKind.CITES, "src_a", "src_b"),
        graph_edge("gedge_discovered", GraphEdgeKind.DISCOVERED_BY, "src_a", "qry_1"),
        graph_edge("gedge_run", GraphEdgeKind.DISCOVERED_BY, "src_a", "run_1"),
    )
    return nodes, edges


def test_repository_satisfies_protocol_and_returns_domain_models() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    assert isinstance(repository, EvidenceGraphRepository)
    nodes, edges = sample_batch()
    repository.upsert(nodes=nodes, edges=edges)
    loaded = repository.get_node("src_a")
    assert isinstance(loaded, GraphNode)
    assert loaded == nodes[0]
    loaded_edge = repository.get_edge("gedge_cites")
    assert isinstance(loaded_edge, GraphEdge) and loaded_edge == edges[0]
    repository.close()


def test_reopen_persists_nodes_edges_and_lineage(tmp_path) -> None:
    database = tmp_path / "graph.sqlite3"
    source_a = make_source("src_alpha")
    source_b = make_source("src_beta")
    provenance = make_edge(
        "src_alpha",
        "src_beta",
        relation=ProvenanceRelation.VERSION_OF,
        lineage_confidence=LineageConfidence.CONFIRMED,
    )
    clusters = build_lineage_clusters((source_a, source_b), (provenance,))
    repository = SqlAlchemyEvidenceGraphRepository(database)
    repository.upsert(
        nodes=(
            node("src_alpha", label="alpha"),
            node("src_beta", label="beta"),
        ),
        edges=(graph_edge("gedge_v", GraphEdgeKind.VERSION_OF, "src_alpha", "src_beta"),),
        clusters=clusters,
    )
    repository.close()

    reopened = SqlAlchemyEvidenceGraphRepository(database)
    assert schema_version(reopened.engine) == SCHEMA_VERSION
    assert [item.node_id for item in reopened.nodes()] == ["src_alpha", "src_beta"]
    assert len(reopened.edges()) == 1
    persisted_cluster = reopened.lineage_cluster_for_source("src_alpha")
    assert persisted_cluster == clusters[0]
    assert reopened.lineage_clusters() == clusters
    reopened.close()


def test_neighbors_and_filters(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    nodes, edges = sample_batch()
    repository.upsert(nodes=nodes, edges=edges)
    outbound = repository.neighbors("src_a")
    assert {item.node_id for item in outbound} == {"src_b", "qry_1", "run_1"}
    citations_only = repository.neighbors("src_a", kinds=frozenset({GraphEdgeKind.CITES}))
    assert [item.node_id for item in citations_only] == ["src_b"]
    inbound = repository.neighbors("src_b", direction=GraphDirection.IN)
    assert [item.node_id for item in inbound] == ["src_a"]
    assert len(repository.nodes(kinds=frozenset({GraphNodeKind.QUERY}))) == 1
    repository.close()


def test_dangling_endpoints_are_rejected_and_rolled_back(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    with pytest.raises(ValueError, match="dangling endpoint"):
        repository.upsert(
            nodes=(node("src_a"),),
            edges=(graph_edge("gedge_bad", GraphEdgeKind.CITES, "src_a", "src_missing"),),
        )
    assert repository.nodes() == ()
    repository.close()


def test_database_foreign_keys_are_enforced_below_the_repository(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    repository.upsert(nodes=(node("src_a"),))
    with repository.engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(GraphEdgeRow).values(
                    edge_id="gedge_raw",
                    kind="CITES",
                    source_node_id="src_a",
                    target_node_id="src_missing",
                    document_json="{}",
                )
            )
    repository.close()


def test_batch_failure_rolls_back_every_write(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    existing = node("src_existing", label="original label")
    repository.upsert(nodes=(existing,))
    conflicting = node("src_existing", label="different label")
    added = node("src_new")
    with pytest.raises(ValueError, match="already exists with different content"):
        repository.upsert(nodes=(added, conflicting))
    assert repository.get_node("src_new") is None
    assert repository.get_node("src_existing") == existing
    repository.close()


def test_repeated_persistence_is_idempotent(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    nodes, edges = sample_batch()
    repository.upsert(nodes=nodes, edges=edges)
    first_nodes = repository.nodes()
    first_edges = repository.edges()
    repository.upsert(nodes=nodes, edges=edges)
    assert repository.nodes() == first_nodes
    assert repository.edges() == first_edges
    repository.close()


def test_identical_edge_identity_with_different_content_is_rejected(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    repository.upsert(nodes=(node("src_a"), node("src_b")))
    first = graph_edge("gedge_1", GraphEdgeKind.CITES, "src_a", "src_b")
    repository.upsert(edges=(first,))
    changed = graph_edge(
        "gedge_1", GraphEdgeKind.CITES, "src_a", "src_b", attributes={"note": "changed"}
    )
    with pytest.raises(ValueError, match="different content"):
        repository.upsert(edges=(changed,))
    assert repository.get_edge("gedge_1") == first
    repository.close()


def test_schema_version_metadata_is_verified(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "graph.sqlite3")
    assert ensure_schema(repository.engine) == SCHEMA_VERSION
    assert schema_version(repository.engine) == SCHEMA_VERSION
    with repository.engine.begin() as connection:
        connection.execute(text("INSERT INTO schema_version VALUES (99, 'future')"))
    with pytest.raises(ValueError, match="newer than supported"):
        ensure_schema(repository.engine)
    repository.close()


@pytest.mark.parametrize("old_version", [4, 5, 6])
def test_v4_v5_v6_migration_creates_empty_phase6_ledger(tmp_path, old_version: int) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"v{old_version}.sqlite3")
    with repository.engine.begin() as connection:
        connection.execute(
            text("UPDATE schema_version SET version = :version"), {"version": old_version}
        )

    assert ensure_schema(repository.engine) == SCHEMA_VERSION
    assert schema_version(repository.engine) == SCHEMA_VERSION
    expected_tables = {
        "phase6_assessment_snapshots",
        "phase6_assessment_targets",
        "phase6_assessment_candidates",
        "phase6_assessment_derived",
    }
    assert expected_tables <= set(inspect(repository.engine).get_table_names())
    with repository.engine.connect() as connection:
        for table in sorted(expected_tables):
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
    repository.close()


def test_in_memory_database_survives_multiple_sessions() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(nodes=(node("src_a"),))
    repository.upsert(nodes=(node("src_b"),))
    assert [item.node_id for item in repository.nodes()] == ["src_a", "src_b"]
    repository.close()


def test_lineage_membership_cannot_be_moved_between_clusters(tmp_path) -> None:
    database = tmp_path / "graph.sqlite3"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    source_a = make_source("src_alpha")
    source_b = make_source("src_beta")
    first = build_lineage_clusters(
        (source_a, source_b),
        (
            make_edge(
                "src_alpha",
                "src_beta",
                relation=ProvenanceRelation.VERSION_OF,
                lineage_confidence=LineageConfidence.CONFIRMED,
            ),
        ),
    )[0]
    second = build_lineage_clusters((source_b,), ())[0]
    repository.upsert(nodes=(node("src_alpha"), node("src_beta")), clusters=(first,))
    with pytest.raises(ValueError, match="already belongs to lineage cluster"):
        repository.upsert(clusters=(second,))
    repository.close()
