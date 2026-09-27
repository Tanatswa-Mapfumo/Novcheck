from datetime import UTC, datetime

from novelty_harness.evidence.graph.models import (
    PHASE5_EDGE_KINDS,
    EvidenceGraph,
    GraphEdgeKind,
    GraphNodeKind,
)
from novelty_harness.evidence.graph.retrieval_mapping import (
    discovery_graph,
    logical_search_run_id,
    passage_graph_node,
    provenance_graph_edges,
    source_graph_node,
    version_graph_node,
)
from novelty_harness.evidence.provenance.models import ProvenanceRelation
from novelty_harness.research.retrieval.models import RetrievalStrategy
from tests.fixtures.phase5 import (
    make_discovery_path,
    make_edge,
    make_passage,
    make_source,
    make_version,
    phase5_provenance,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("retrieval-mapping-test")


def test_same_source_from_three_providers_keeps_every_path() -> None:
    source = make_source(
        "src_shared",
        discovery_queries=("qry_openalex", "qry_crossref", "qry_s2"),
        discovery_paths=(
            make_discovery_path(
                provider_name="openalex",
                provider_source_id="https://openalex.org/W1",
                strategy=RetrievalStrategy.LEXICAL,
                query_id="qry_openalex",
            ),
            make_discovery_path(
                provider_name="crossref",
                provider_source_id="10.9999/doi",
                strategy=RetrievalStrategy.SEMANTIC,
                query_id="qry_crossref",
            ),
            make_discovery_path(
                provider_name="semantic_scholar",
                provider_source_id="b" * 40,
                strategy=RetrievalStrategy.LEXICAL,
                query_id="qry_s2",
            ),
        ),
    )
    nodes, edges = discovery_graph((source,), observed_at=NOW, provenance=ORIGIN)
    source_nodes = [node for node in nodes if node.kind == GraphNodeKind.SOURCE]
    query_nodes = [node for node in nodes if node.kind == GraphNodeKind.QUERY]
    run_nodes = [node for node in nodes if node.kind == GraphNodeKind.SEARCH_RUN]
    assert len(source_nodes) == 1 and len(query_nodes) == 3 and len(run_nodes) == 3
    source_node = source_nodes[0]
    assert len(source_node.attributes["discovery_paths"]) == 3
    discovered_to_queries = [
        edge
        for edge in edges
        if edge.kind == GraphEdgeKind.DISCOVERED_BY
        and source_node.node_id == edge.source_node_id
        and edge.target_node_id.startswith("qry_")
    ]
    assert {edge.target_node_id for edge in discovered_to_queries} == {
        "qry_openalex",
        "qry_crossref",
        "qry_s2",
    }
    graph = EvidenceGraph(graph_id="graph_1", nodes=tuple(nodes), edges=tuple(edges))
    assert graph.node_ids_of_kind(GraphNodeKind.QUERY) == (
        "qry_crossref",
        "qry_openalex",
        "qry_s2",
    )


def test_citation_expansion_retains_its_seed() -> None:
    seed = make_source(
        "src_seed",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-seed", strategy=RetrievalStrategy.LEXICAL, query_id="qry_1"
            ),
        ),
    )
    discovered = make_source(
        "src_predecessor",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-pred",
                strategy=RetrievalStrategy.CITATION_BACKWARD,
                query_id=None,
                seed_source={"provider_name": "openalex", "provider_source_id": "W-seed"},
            ),
        ),
    )
    nodes, edges = discovery_graph((seed, discovered), observed_at=NOW, provenance=ORIGIN)
    run_nodes = {node.node_id: node for node in nodes if node.kind == GraphNodeKind.SEARCH_RUN}
    discovered_run = next(
        node for node in run_nodes.values() if node.attributes["seed_id"] == "W-seed"
    )
    assert discovered_run.attributes["strategy"] == RetrievalStrategy.CITATION_BACKWARD.value
    assert discovered_run.attributes["seed_provider"] == "openalex"
    assert logical_search_run_id(discovered.discovery_paths[0]) == discovered_run.node_id

    provenance = (
        make_edge(
            "src_predecessor",
            "src_seed",
            relation=ProvenanceRelation.FOUND_BY,
        ),
        make_edge(
            "src_predecessor",
            "src_seed",
            relation=ProvenanceRelation.CITES,
        ),
    )
    graph_edges = provenance_graph_edges(provenance)
    assert {(edge.kind, edge.source_node_id, edge.target_node_id) for edge in graph_edges} == {
        (GraphEdgeKind.FOUND_BY, "src_predecessor", "src_seed"),
        (GraphEdgeKind.CITES, "src_predecessor", "src_seed"),
    }
    assert all(edge.kind in PHASE5_EDGE_KINDS for edge in graph_edges)


def test_identical_repeated_paths_collapse_without_losing_provenance() -> None:
    repeated = make_discovery_path(provider_source_id="W1", query_id="qry_1")
    also_repeated = make_discovery_path(provider_source_id="W1", query_id="qry_1", local_rank=9)
    source = make_source("src_repeat", discovery_paths=(repeated, also_repeated))
    nodes, edges = discovery_graph((source,), observed_at=NOW, provenance=ORIGIN)
    assert len([node for node in nodes if node.kind == GraphNodeKind.QUERY]) == 1
    assert len([node for node in nodes if node.kind == GraphNodeKind.SEARCH_RUN]) == 1
    assert len(edges) == 2  # one DISCOVERED_BY to the query, one to the search run
    # The source node still carries every discovery path as data.
    source_node = next(node for node in nodes if node.kind == GraphNodeKind.SOURCE)
    assert len(source_node.attributes["discovery_paths"]) == 2


def test_distinct_strategies_do_not_collapse_into_one_run() -> None:
    source = make_source(
        "src_two_mechanisms",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W1", strategy=RetrievalStrategy.LEXICAL, query_id="qry_1"
            ),
            make_discovery_path(
                provider_source_id="W1", strategy=RetrievalStrategy.SEMANTIC, query_id="qry_2"
            ),
        ),
    )
    nodes, edges = discovery_graph((source,), observed_at=NOW, provenance=ORIGIN)
    runs = [node for node in nodes if node.kind == GraphNodeKind.SEARCH_RUN]
    assert len(runs) == 2
    assert {node.attributes["strategy"] for node in runs} == {"LEXICAL", "SEMANTIC"}
    assert sum(1 for edge in edges if edge.target_node_id.startswith("run_")) == 2


def test_version_and_passage_nodes_are_storage_independent_domain_views() -> None:
    version = make_version("src_alpha")
    passage = make_passage("src_alpha")
    version_node = version_graph_node(version, observed_at=NOW, provenance=ORIGIN)
    passage_node = passage_graph_node(passage, observed_at=NOW, provenance=ORIGIN)
    assert version_node.kind == GraphNodeKind.SOURCE_VERSION
    assert version_node.node_id == version.version_id
    assert passage_node.kind == GraphNodeKind.PASSAGE
    assert passage_node.attributes["content_hash"] == passage.content_hash
    source_node = source_graph_node(make_source("src_alpha"), observed_at=NOW, provenance=ORIGIN)
    assert source_node.attributes["access_state"] == "FULL_TEXT"


def test_no_adjudication_edges_are_ever_projected() -> None:
    relations = (
        ProvenanceRelation.CITES,
        ProvenanceRelation.DERIVES_FROM,
        ProvenanceRelation.REPOSTS,
        ProvenanceRelation.VERSION_OF,
        ProvenanceRelation.PATENT_FAMILY_OF,
        ProvenanceRelation.IMPLEMENTS,
        ProvenanceRelation.DOCUMENTS,
        ProvenanceRelation.FOUND_BY,
    )
    edges = tuple(
        make_edge("src_a", f"src_b_{index}", relation=relation)
        for index, relation in enumerate(relations)
    )
    projected = provenance_graph_edges(edges)
    assert len(projected) == len(relations)
    assert all(edge.kind in PHASE5_EDGE_KINDS for edge in projected)
    assert GraphEdgeKind.DERIVES_FROM in {edge.kind for edge in projected}
