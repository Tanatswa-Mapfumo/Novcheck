"""Map canonical sources, provenance and retrieval paths into graph nodes/edges.

Discovery provenance is preserved at three levels: the canonical source node
keeps every discovery path as data, every path creates ``DISCOVERED_BY`` edges
to its ``Query`` and logical ``SearchRun`` nodes, and expansion seeds create
``FOUND_BY``/``CITES`` relations. Identical repeated paths collapse through
deterministic edge identities; different queries, strategies or seeds do not.
"""

from collections.abc import Sequence

from pydantic import JsonValue

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import QueryId, SearchRunId
from novelty_harness.evidence.graph.models import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    graph_edge_id_for,
)
from novelty_harness.evidence.normalization.models import (
    DiscoveryPath,
    SourceRecord,
    SourceVersionRecord,
)
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.provenance.models import ProvenanceEdge, ProvenanceRelation
from novelty_harness.runtime.tracing.hashing import canonical_hash

_RELATION_TO_EDGE: dict[ProvenanceRelation, GraphEdgeKind] = {
    ProvenanceRelation.CITES: GraphEdgeKind.CITES,
    ProvenanceRelation.DERIVES_FROM: GraphEdgeKind.DERIVES_FROM,
    # The graph's Phase 5 edge set folds reposts into the derivation family.
    ProvenanceRelation.REPOSTS: GraphEdgeKind.DERIVES_FROM,
    ProvenanceRelation.VERSION_OF: GraphEdgeKind.VERSION_OF,
    ProvenanceRelation.PATENT_FAMILY_OF: GraphEdgeKind.PATENT_FAMILY_OF,
    ProvenanceRelation.IMPLEMENTS: GraphEdgeKind.IMPLEMENTS,
    ProvenanceRelation.DOCUMENTS: GraphEdgeKind.DOCUMENTS,
    ProvenanceRelation.FOUND_BY: GraphEdgeKind.FOUND_BY,
}


def source_graph_node(
    source: SourceRecord,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> GraphNode:
    return GraphNode(
        node_id=source.source_id,
        kind=GraphNodeKind.SOURCE,
        label=source.canonical_title,
        attributes={
            "source_type": source.source_type.value,
            "access_state": source.access_state.value,
            "identifiers": source.identifiers.model_dump(mode="json"),
            "content_hash": source.content_hash,
            "discovery_paths": [path.model_dump(mode="json") for path in source.discovery_paths],
            "discovery_queries": list(source.discovery_queries),
            "limitations": list(source.limitations),
        },
        observed_at=observed_at,
        provenance=provenance,
    )


def version_graph_node(
    version: SourceVersionRecord,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> GraphNode:
    return GraphNode(
        node_id=version.version_id,
        kind=GraphNodeKind.SOURCE_VERSION,
        label=version.version_label,
        attributes={
            "source_id": version.source_id,
            "version_kind": version.version_kind.value,
            "content_hash": version.content_hash,
            "access_state": version.access_state.value,
            "predecessor_version_id": version.predecessor_version_id,
        },
        observed_at=observed_at,
        provenance=provenance,
    )


def passage_graph_node(
    passage: PassageRecord,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> GraphNode:
    return GraphNode(
        node_id=passage.passage_id,
        kind=GraphNodeKind.PASSAGE,
        label=None,
        attributes={
            "source_id": passage.source_id,
            "source_version_id": passage.source_version_id,
            "content_hash": passage.content_hash,
            "access_state": passage.access_state.value,
            "locator": passage.locator.model_dump(mode="json"),
            "limitations": list(passage.limitations),
        },
        observed_at=observed_at,
        provenance=provenance,
    )


def logical_search_run_id(path: DiscoveryPath) -> SearchRunId:
    """Stable logical search-run identity for a retrieval branch.

    Phase 4 does not yet attach physical run identifiers to candidates, so the
    logical run groups one provider/strategy/query/seed/family branch. When a
    physical run ID exists it is carried on the discovery path and used
    instead.
    """

    if path.search_run_id is not None:
        return path.search_run_id
    return "run_" + canonical_hash(
        {
            "provider_name": path.provider_name,
            "strategy": path.strategy.value,
            "evidence_family": path.evidence_family.value,
            "query_id": path.query_id,
            "seed_provider": path.seed_source.provider_name if path.seed_source else None,
            "seed_id": path.seed_source.provider_source_id if path.seed_source else None,
            "mcu_id": path.mcu_id,
        }
    )


def _query_node(
    query_id: QueryId, *, observed_at: UTCDateTime, provenance: ArtifactProvenance
) -> GraphNode:
    return GraphNode(
        node_id=query_id,
        kind=GraphNodeKind.QUERY,
        label=query_id,
        observed_at=observed_at,
        provenance=provenance,
    )


def _search_run_node(
    run_id: SearchRunId,
    path: DiscoveryPath,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> GraphNode:
    return GraphNode(
        node_id=run_id,
        kind=GraphNodeKind.SEARCH_RUN,
        label=f"{path.provider_name}:{path.strategy.value}",
        attributes={
            "provider_name": path.provider_name,
            "strategy": path.strategy.value,
            "mechanism": path.mechanism.value,
            "evidence_family": path.evidence_family.value,
            "query_id": path.query_id,
            "mcu_id": path.mcu_id,
            "seed_provider": path.seed_source.provider_name if path.seed_source else None,
            "seed_id": path.seed_source.provider_source_id if path.seed_source else None,
        },
        observed_at=observed_at,
        provenance=provenance,
    )


def discovery_graph(
    sources: Sequence[SourceRecord],
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
    """Build source/query/search-run nodes and their discovery edges."""

    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}

    def add_edge(edge: GraphEdge) -> None:
        edges.setdefault(edge.edge_id, edge)

    for source in sources:
        nodes[source.source_id] = source_graph_node(
            source, observed_at=observed_at, provenance=provenance
        )
        for path in source.discovery_paths:
            path_key: JsonValue = list(path.path_key())
            if path.query_id is not None:
                query_id = path.query_id
                nodes.setdefault(
                    query_id,
                    _query_node(query_id, observed_at=observed_at, provenance=provenance),
                )
                add_edge(
                    GraphEdge(
                        edge_id=graph_edge_id_for(
                            GraphEdgeKind.DISCOVERED_BY, source.source_id, query_id, path_key
                        ),
                        kind=GraphEdgeKind.DISCOVERED_BY,
                        source_node_id=source.source_id,
                        target_node_id=query_id,
                        attributes={"discovery_path_key": path_key},
                        observed_at=observed_at,
                        provenance=provenance,
                    )
                )
            run_id = logical_search_run_id(path)
            nodes.setdefault(
                run_id,
                _search_run_node(run_id, path, observed_at=observed_at, provenance=provenance),
            )
            add_edge(
                GraphEdge(
                    edge_id=graph_edge_id_for(
                        GraphEdgeKind.DISCOVERED_BY, source.source_id, run_id, path_key
                    ),
                    kind=GraphEdgeKind.DISCOVERED_BY,
                    source_node_id=source.source_id,
                    target_node_id=run_id,
                    attributes={"discovery_path_key": path_key},
                    observed_at=observed_at,
                    provenance=provenance,
                )
            )
    return (
        tuple(nodes[key] for key in sorted(nodes)),
        tuple(edges[key] for key in sorted(edges)),
    )


def provenance_graph_edges(edges: Sequence[ProvenanceEdge]) -> tuple[GraphEdge, ...]:
    """Project domain provenance relations onto Phase 5 graph edge kinds."""

    projected: dict[str, GraphEdge] = {}
    for edge in edges:
        kind = _RELATION_TO_EDGE[edge.relation]
        attributes: dict[str, JsonValue] = {
            "provenance_edge_id": edge.edge_id,
            "relation": edge.relation.value,
            "lineage_confidence": edge.lineage_confidence.value,
            "evidence": list(edge.evidence),
            "limitations": list(edge.limitations),
        }
        graph_edge = GraphEdge(
            edge_id=graph_edge_id_for(kind, edge.source_id, edge.related_source_id, edge.edge_id),
            kind=kind,
            source_node_id=edge.source_id,
            target_node_id=edge.related_source_id,
            attributes=attributes,
            observed_at=edge.observed_at,
            provenance=edge.provenance,
        )
        projected[graph_edge.edge_id] = graph_edge
    return tuple(projected[key] for key in sorted(projected))
