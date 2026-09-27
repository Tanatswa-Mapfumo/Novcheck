"""Circular provenance/dependency diagnostics.

Mutual citation between papers is ordinary and informational. Cycles through
confirmed dependency relations are material because they can make one
underlying lineage look like several independent confirmations. Cycles that
depend only on merely-possible relations remain warnings.
"""

from collections.abc import Sequence

from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.provenance._components import strongly_connected_components
from novelty_harness.evidence.provenance.models import (
    DEPENDENCY_RELATIONS,
    LineageConfidence,
    ProvenanceCycle,
    ProvenanceEdge,
    ProvenanceRelation,
)


def detect_provenance_cycles(
    sources: Sequence[SourceId],
    edges: Sequence[ProvenanceEdge],
) -> tuple[ProvenanceCycle, ...]:
    """Return each circular structure once, with honest severity."""

    known = sorted(set(sources))
    relevant = [
        edge
        for edge in edges
        if edge.relation != ProvenanceRelation.FOUND_BY
        and edge.source_id in known
        and edge.related_source_id in known
    ]
    outgoing: dict[str, list[str]] = {source_id: [] for source_id in known}
    for edge in relevant:
        outgoing[edge.source_id].append(edge.related_source_id)
    for source_id, targets in outgoing.items():
        outgoing[source_id] = sorted(set(targets))

    cycles: list[ProvenanceCycle] = []
    for component in strongly_connected_components(known, outgoing):
        if len(component) < 2:
            continue
        members = set(component)
        intra = [
            edge
            for edge in relevant
            if edge.source_id in members and edge.related_source_id in members
        ]
        relations = sorted({edge.relation.value for edge in intra})
        dependency_edges = [edge for edge in intra if edge.relation in DEPENDENCY_RELATIONS]
        if not dependency_edges:
            severity = "INFO"
            explanation = (
                "Circular citation among "
                + ", ".join(component)
                + "; citation alone does not establish dependency"
            )
        elif all(
            edge.lineage_confidence == LineageConfidence.CONFIRMED for edge in dependency_edges
        ):
            severity = "MATERIAL"
            explanation = (
                "Confirmed circular dependency among "
                + ", ".join(component)
                + "; the loop counts as one lineage"
            )
        else:
            severity = "WARNING"
            explanation = (
                "Possible circular dependency among "
                + ", ".join(component)
                + "; lineage remains uncertain"
            )
        cycles.append(
            ProvenanceCycle(
                source_ids=component,
                relation_types=tuple(ProvenanceRelation(relation) for relation in relations),
                severity=severity,
                explanation=explanation,
            )
        )
    return tuple(sorted(cycles, key=lambda cycle: cycle.source_ids))
