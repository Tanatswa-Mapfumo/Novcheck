"""Map Phase 6 propositions, verified edges and classifications into the graph.

Every decisive/precedent edge carries an eligibility reference to the verified
evidence edge it came from. Phase 7 owns argumentation; Phase 6 never stores a
final novelty verdict.
"""

from collections.abc import Sequence

from pydantic import JsonValue

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.enums import PrecedentState
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.graph.models import (
    EdgeVerificationRef,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    graph_edge_id_for,
)
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.precedent.models import PrecedentClassification
from novelty_harness.evidence.verification.models import VerifiedEvidenceEdge
from novelty_harness.runtime.tracing.hashing import canonical_hash

_CLASSIFICATION_TO_EDGE: dict[PrecedentState, GraphEdgeKind] = {
    PrecedentState.DIRECT_PRECEDENT: GraphEdgeKind.DIRECT_PRECEDENT,
    PrecedentState.STRONG_PARTIAL_PRECEDENT: GraphEdgeKind.STRONG_PARTIAL_PRECEDENT,
    PrecedentState.COMPONENT_PRECEDENT_ONLY: GraphEdgeKind.COMPONENT_PRECEDENT,
    PrecedentState.ANALOGOUS_PRECEDENT: GraphEdgeKind.ANALOGOUS,
    PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED: GraphEdgeKind.NO_MATCH,
}


def proposition_node_id(edge: VerifiedEvidenceEdge) -> str:
    return "prop_" + canonical_hash(
        {
            "verified_edge_id": edge.edge_id,
            "proposition_id": edge.proposition_id,
            "source_id": edge.source_id,
            "source_version_id": edge.source_version_id,
            "verification_id": edge.verification_id,
        }
    )


def proposition_graph_node(
    edge: VerifiedEvidenceEdge,
    classification: PrecedentClassification | None,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> GraphNode:
    attributes: dict[str, JsonValue] = {
        "proposition_id": edge.proposition_id,
        "proposition": edge.proposition,
        "mcu_id": edge.mcu_id,
        "mapping_id": edge.mapping_id,
        "verification_id": edge.verification_id,
        "verified_edge_id": edge.edge_id,
        "passage_ids": list(edge.passage_ids),
        "support_state": edge.support_state.value,
        "decisive": edge.decisive,
        "chronology_state": edge.chronology.state,
        "comparison": edge.comparison.model_dump(mode="json"),
        "relation": classification.relation.value if classification else None,
        "scope": "LOCAL_SOURCE_MCU",
        "global_absence_claim_permitted": False,
        "quality_tier": edge.quality_tier.value if edge.quality_tier else None,
        "mapper_prompt_version": edge.mapper_prompt_version,
        "verifier_prompt_version": edge.verifier_prompt_version,
        "verifier_rubric_version": edge.verifier_rubric_version,
    }
    return GraphNode(
        node_id=proposition_node_id(edge),
        kind=GraphNodeKind.EVIDENCE_PROPOSITION,
        label=edge.proposition,
        attributes=attributes,
        observed_at=observed_at,
        provenance=provenance,
    )


def verified_edge_graph_fragment(
    edges: Sequence[VerifiedEvidenceEdge],
    classifications: Sequence[PrecedentClassification],
    *,
    passages: Sequence[PassageRecord] = (),
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> tuple[tuple[GraphNode, ...], tuple[GraphEdge, ...]]:
    """Build proposition nodes and verified/precedent graph edges."""

    by_identity: dict[tuple[str, str, str | None, str, str, str], PrecedentClassification] = {}
    for classification in classifications:
        if classification.verification_id is None:
            continue
        key = (
            classification.verification_id,
            classification.source_id,
            classification.source_version_id,
            classification.mcu_id,
            classification.mapping_id,
            classification.relation.value,
        )
        if key in by_identity:
            raise ValueError("Duplicate classification for one verified comparison")
        by_identity[key] = classification
    nodes: dict[str, GraphNode] = {}
    graph_edges: dict[str, GraphEdge] = {}

    for passage in passages:
        node = GraphNode(
            node_id=passage.passage_id,
            kind=GraphNodeKind.PASSAGE,
            label=None,
            attributes={
                "source_id": passage.source_id,
                "source_version_id": passage.source_version_id,
                "content_hash": passage.content_hash,
                "access_state": passage.access_state.value,
                "locator": passage.locator.model_dump(mode="json"),
            },
            observed_at=observed_at,
            provenance=provenance,
        )
        nodes.setdefault(node.node_id, node)

    for edge in edges:
        candidates = [
            classification
            for key, classification in by_identity.items()
            if key[0] == edge.verification_id
        ]
        if len(candidates) > 1:
            raise ValueError("Ambiguous classification for verified edge")
        classification = candidates[0] if candidates else None
        if classification is not None and (
            classification.source_id != edge.source_id
            or classification.source_version_id != edge.source_version_id
            or classification.mcu_id != edge.mcu_id
            or classification.mapping_id != edge.mapping_id
            or (edge.relation is not None and classification.relation != edge.relation)
            or classification.decisive
            != (edge.decisive and classification.relation == PrecedentState.DIRECT_PRECEDENT)
        ):
            raise ValueError("Classification identity differs from verified edge")
        attributes: dict[str, JsonValue] = {
            "verified_edge_id": edge.edge_id,
            "proposition_node_id": proposition_node_id(edge),
            "proposition_id": edge.proposition_id,
            "support_state": edge.support_state.value,
            "decisive": edge.decisive,
            "relation": classification.relation.value if classification else None,
            "scope": "LOCAL_SOURCE_MCU",
            "global_absence_claim_permitted": False,
            "passage_ids": list(edge.passage_ids),
            "chronology_state": edge.chronology.state,
            "quality_tier": edge.quality_tier.value if edge.quality_tier else None,
        }
        if classification is not None:
            attributes["classification_id"] = classification.classification_id
            attributes["classification_basis"] = list(classification.basis)
        verification = EdgeVerificationRef(
            verified_edge_id=edge.edge_id,
            support_state=edge.support_state,
            decisive=edge.decisive,
            precedent_relation=classification.relation if classification else edge.relation,
        )
        nodes[proposition_node_id(edge)] = proposition_graph_node(
            edge, classification, observed_at=observed_at, provenance=provenance
        )

        support_kind: GraphEdgeKind | None = None
        if edge.support_state.value == "SUPPORTED":
            support_kind = GraphEdgeKind.SUPPORTS
        elif edge.support_state.value == "CONTRADICTED":
            support_kind = GraphEdgeKind.CONTRADICTS
        if support_kind is not None:
            support = GraphEdge(
                edge_id=graph_edge_id_for(support_kind, edge.source_id, edge.mcu_id, edge.edge_id),
                kind=support_kind,
                source_node_id=edge.source_id,
                target_node_id=edge.mcu_id,
                attributes=attributes,
                verification=verification,
                observed_at=observed_at,
                provenance=provenance,
            )
            graph_edges[support.edge_id] = support

        if classification is not None:
            precedent_kind = _CLASSIFICATION_TO_EDGE.get(classification.relation)
            if precedent_kind is not None:
                precedent = GraphEdge(
                    edge_id=graph_edge_id_for(
                        precedent_kind,
                        edge.source_id,
                        edge.mcu_id,
                        edge.edge_id + ":" + precedent_kind.value,
                    ),
                    kind=precedent_kind,
                    source_node_id=edge.source_id,
                    target_node_id=edge.mcu_id,
                    attributes={
                        **attributes,
                        "local_only": True,
                        "stitched_multi_source": False,
                    },
                    verification=verification,
                    observed_at=observed_at,
                    provenance=provenance,
                )
                graph_edges[precedent.edge_id] = precedent

    return (
        tuple(nodes[key] for key in sorted(nodes)),
        tuple(graph_edges[key] for key in sorted(graph_edges)),
    )


def phase6_graph_provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="implemented",
        component="phase6_graph_mapping",
        detail="Verified evidence edges with eligibility refs; no Phase 7 adjudication.",
    )


__all__ = [
    "phase6_graph_provenance",
    "proposition_graph_node",
    "proposition_node_id",
    "verified_edge_graph_fragment",
]
