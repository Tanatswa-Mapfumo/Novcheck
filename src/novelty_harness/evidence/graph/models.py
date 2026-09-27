"""Storage-independent evidence graph domain.

The graph is the central analytical structure of the harness. Phase 5
populates only canonical/lineage edges; adjudicated edge kinds are reserved
and rejected here so no Phase 5 component can silently create a Phase 6
finding.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import GraphEdgeId
from novelty_harness.runtime.tracing.hashing import canonical_hash


class GraphNodeKind(StrEnum):
    IDEA = "IDEA"
    MCU = "MCU"
    FEATURE = "FEATURE"
    RELATIONSHIP = "RELATIONSHIP"
    SOURCE = "SOURCE"
    SOURCE_VERSION = "SOURCE_VERSION"
    PASSAGE = "PASSAGE"
    EVIDENCE_PROPOSITION = "EVIDENCE_PROPOSITION"
    ENTITY = "ENTITY"
    QUERY = "QUERY"
    SEARCH_RUN = "SEARCH_RUN"


class GraphEdgeKind(StrEnum):
    # Phase 5 canonical/provenance edges.
    CITES = "CITES"
    PREDATES = "PREDATES"
    DISCOVERED_BY = "DISCOVERED_BY"
    DERIVES_FROM = "DERIVES_FROM"
    VERSION_OF = "VERSION_OF"
    PATENT_FAMILY_OF = "PATENT_FAMILY_OF"
    IMPLEMENTS = "IMPLEMENTS"
    DOCUMENTS = "DOCUMENTS"
    FOUND_BY = "FOUND_BY"
    # Reserved for Phase 6+ adjudication; Phase 5 must not create these.
    SUPPORTS = "SUPPORTS"
    CHALLENGES = "CHALLENGES"
    DIRECT_PRECEDENT = "DIRECT_PRECEDENT"
    STRONG_PARTIAL_PRECEDENT = "STRONG_PARTIAL_PRECEDENT"
    COMPONENT_PRECEDENT = "COMPONENT_PRECEDENT"
    ANALOGOUS = "ANALOGOUS"
    NO_MATCH = "NO_MATCH"
    CONTRADICTS = "CONTRADICTS"


PHASE5_EDGE_KINDS = frozenset(
    {
        GraphEdgeKind.CITES,
        GraphEdgeKind.PREDATES,
        GraphEdgeKind.DISCOVERED_BY,
        GraphEdgeKind.DERIVES_FROM,
        GraphEdgeKind.VERSION_OF,
        GraphEdgeKind.PATENT_FAMILY_OF,
        GraphEdgeKind.IMPLEMENTS,
        GraphEdgeKind.DOCUMENTS,
        GraphEdgeKind.FOUND_BY,
    }
)

RESERVED_EDGE_KINDS = frozenset(GraphEdgeKind) - PHASE5_EDGE_KINDS

_NODE_ID_PREFIXES: dict[GraphNodeKind, str] = {
    GraphNodeKind.IDEA: "idea_",
    GraphNodeKind.MCU: "mcu_",
    GraphNodeKind.FEATURE: "feat_",
    GraphNodeKind.RELATIONSHIP: "rel_",
    GraphNodeKind.SOURCE: "src_",
    GraphNodeKind.SOURCE_VERSION: "srcv_",
    GraphNodeKind.PASSAGE: "pass_",
    GraphNodeKind.EVIDENCE_PROPOSITION: "prop_",
    GraphNodeKind.ENTITY: "ent_",
    GraphNodeKind.QUERY: "qry_",
    GraphNodeKind.SEARCH_RUN: "run_",
}


def node_id_prefix(kind: GraphNodeKind) -> str:
    return _NODE_ID_PREFIXES[kind]


def graph_edge_id_for(
    kind: GraphEdgeKind,
    source_node_id: str,
    target_node_id: str,
    key: JsonValue = None,
) -> GraphEdgeId:
    """Deterministic graph edge identity for content-addressed deduplication."""

    return "gedge_" + canonical_hash(
        {
            "kind": kind.value,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "key": key,
        }
    )


class GraphNode(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-graph-node-v1"] = "evidence-graph-node-v1"

    node_id: NonBlankText
    kind: GraphNodeKind
    label: NonBlankText | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def identity_matches_kind(self) -> Self:
        if not self.node_id.startswith(node_id_prefix(self.kind)):
            raise ValueError(
                f"{self.kind.value} node ids must start with {node_id_prefix(self.kind)!r}"
            )
        return self


class GraphEdge(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-graph-edge-v1"] = "evidence-graph-edge-v1"

    edge_id: GraphEdgeId
    kind: GraphEdgeKind
    source_node_id: NonBlankText
    target_node_id: NonBlankText
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def phase5_only_and_distinct(self) -> Self:
        if self.kind in RESERVED_EDGE_KINDS:
            raise ValueError(
                f"{self.kind.value} is reserved for Phase 6+ adjudication and cannot "
                "be created as a Phase 5 graph edge"
            )
        if self.source_node_id == self.target_node_id:
            raise ValueError("A graph edge cannot point at a single node")
        return self


class EvidenceGraph(ContractModel):
    """A complete, self-consistent graph snapshot."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-graph-v1"] = "evidence-graph-v1"

    graph_id: NonBlankText
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()

    @model_validator(mode="after")
    def referentially_consistent(self) -> Self:
        node_ids = [node.node_id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Duplicate graph node identities")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Duplicate graph edge identities")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source_node_id not in known or edge.target_node_id not in known:
                raise ValueError(f"Dangling graph edge {edge.edge_id}")
        return self

    def node(self, node_id: str) -> GraphNode | None:
        return next((node for node in self.nodes if node.node_id == node_id), None)

    def node_ids_of_kind(self, kind: GraphNodeKind) -> tuple[str, ...]:
        return tuple(node.node_id for node in self.nodes if node.kind == kind)

    def neighbors(
        self, node_id: str, *, direction: Literal["OUT", "IN", "BOTH"] = "OUT"
    ) -> tuple[GraphNode, ...]:
        found: list[str] = []
        for edge in self.edges:
            if direction in {"OUT", "BOTH"} and edge.source_node_id == node_id:
                found.append(edge.target_node_id)
            if direction in {"IN", "BOTH"} and edge.target_node_id == node_id:
                found.append(edge.source_node_id)
        wanted = sorted(set(found))
        return tuple(node for node in self.nodes if node.node_id in wanted)
