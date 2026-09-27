"""Conservative provenance lineage clustering and independence counting.

A cluster groups sources that share one underlying evidentiary origin through
documented lineage. Only confirmed dependency relations collapse lineage;
citation-only, discovery-only and merely possible relations never do. Raw
source count is therefore never an independence count.
"""

from collections.abc import Sequence

from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.normalization.models import SourceRecord
from novelty_harness.evidence.provenance._components import strongly_connected_components
from novelty_harness.evidence.provenance.models import (
    DEPENDENCY_RELATIONS,
    EvidenceLineageCluster,
    LineageConfidence,
    ProvenanceEdge,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


def _union_find_components(
    nodes: Sequence[str], edges: Sequence[tuple[str, str]]
) -> list[tuple[str, ...]]:
    parent = {node: node for node in nodes}

    def root(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in edges:
        left_root, right_root = root(left), root(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)
    grouped: dict[str, list[str]] = {}
    for node in nodes:
        grouped.setdefault(root(node), []).append(node)
    return [tuple(sorted(members)) for _, members in sorted(grouped.items())]


def build_lineage_clusters(
    sources: Sequence[SourceRecord],
    edges: Sequence[ProvenanceEdge],
) -> tuple[EvidenceLineageCluster, ...]:
    """Cluster sources by confirmed dependency lineage and count real roots.

    Every source belongs to exactly one cluster, including singleton clusters,
    so summing ``independent_roots`` equals the independent evidence count
    rather than the raw source count.
    """

    source_ids = sorted({source.source_id for source in sources})
    known = set(source_ids)
    collapsing: list[tuple[str, str]] = []
    possible_ambiguities: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    unknown_ambiguities: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    relation_counts: dict[str, list[str]] = {source_id: [] for source_id in source_ids}

    for edge in edges:
        known_endpoints = edge.source_id in known and edge.related_source_id in known
        if not known_endpoints:
            for endpoint in (edge.source_id, edge.related_source_id):
                if endpoint in known:
                    unknown_ambiguities[endpoint].append(
                        f"{edge.relation.value} edge references source(s) outside this "
                        "normalization: lineage incomplete"
                    )
            continue
        if edge.lineage_confidence == LineageConfidence.CONFIRMED:
            if edge.relation in DEPENDENCY_RELATIONS:
                collapsing.append((edge.source_id, edge.related_source_id))
                relation_counts[edge.source_id].append(edge.relation.value)
            continue
        if edge.relation in DEPENDENCY_RELATIONS:
            message = (
                f"Possible {edge.relation.value} from {edge.source_id} to "
                f"{edge.related_source_id} was not collapsed"
            )
            possible_ambiguities[edge.source_id].append(message)
            possible_ambiguities[edge.related_source_id].append(message)

    clusters: list[EvidenceLineageCluster] = []
    for members in _union_find_components(source_ids, collapsing):
        member_set = set(members)
        outgoing: dict[str, list[str]] = {member: [] for member in members}
        for source_id, related_source_id in collapsing:
            if source_id in member_set and related_source_id in member_set:
                outgoing[source_id].append(related_source_id)
        for node in outgoing:
            outgoing[node] = sorted(set(outgoing[node]))

        components = strongly_connected_components(members, outgoing)
        component_of = {member: component[0] for component in components for member in component}
        condensed_edges = {
            component[0]: sorted(
                {
                    component_of[target]
                    for member in component
                    for target in outgoing.get(member, ())
                    if component_of[target] != component[0]
                }
            )
            for component in components
        }
        root_components = [
            component for component in components if not condensed_edges[component[0]]
        ]
        roots = tuple(sorted(component[0] for component in root_components))

        ambiguities: list[str] = []
        for member in members:
            ambiguities.extend(possible_ambiguities[member])
            ambiguities.extend(unknown_ambiguities[member])
        cyclic = [component for component in components if len(component) > 1]
        for component in cyclic:
            ambiguities.append(
                "Circular dependency among " + ", ".join(component) + "; counted as one lineage"
            )

        relation_names = sorted(
            {relation for member in members for relation in relation_counts.get(member, [])}
        )
        rationale = [
            f"{len(members)} source(s) in this lineage",
            "Confirmed dependency relations: " + (", ".join(relation_names) or "none"),
            f"{len(roots)} independent root(s): " + ", ".join(roots),
        ]
        clusters.append(
            EvidenceLineageCluster(
                cluster_id="lin_" + _cluster_hash(members),
                source_ids=members,
                root_source_ids=roots,
                independent_roots=len(roots),
                rationale=tuple(rationale),
                unresolved_ambiguities=tuple(dict.fromkeys(ambiguities)),
            )
        )
    return tuple(sorted(clusters, key=lambda cluster: cluster.cluster_id))


def _cluster_hash(members: Sequence[str]) -> str:
    return canonical_hash(list(members))


def independent_evidence_count(clusters: Sequence[EvidenceLineageCluster]) -> int:
    """Sum of independent roots; never the raw source or cluster count."""

    return sum(cluster.independent_roots for cluster in clusters)


def cluster_for_source(
    clusters: Sequence[EvidenceLineageCluster], source_id: SourceId
) -> EvidenceLineageCluster | None:
    for cluster in clusters:
        if source_id in cluster.source_ids:
            return cluster
    return None
