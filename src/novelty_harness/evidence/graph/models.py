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
from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
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

#: Phase 6 verified evidence edges; each requires an eligible verification ref.
PHASE6_EDGE_KINDS = frozenset(GraphEdgeKind) - PHASE5_EDGE_KINDS

PRECEDENT_EDGE_KINDS = frozenset(
    {
        GraphEdgeKind.DIRECT_PRECEDENT,
        GraphEdgeKind.STRONG_PARTIAL_PRECEDENT,
        GraphEdgeKind.COMPONENT_PRECEDENT,
        GraphEdgeKind.ANALOGOUS,
        GraphEdgeKind.NO_MATCH,
    }
)

#: Backwards-compatible Phase 5 name: edge kinds Phase 5 must never create.
RESERVED_EDGE_KINDS = PHASE6_EDGE_KINDS

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


class EdgeVerificationRef(ContractModel):
    """Eligibility evidence required for every Phase 6 verified graph edge."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["edge-verification-ref-v1"] = "edge-verification-ref-v1"

    verified_edge_id: NonBlankText
    support_state: SupportVerificationState
    decisive: bool
    precedent_relation: PrecedentState | None = None
    scope: Literal["LOCAL_SOURCE_MCU"] = "LOCAL_SOURCE_MCU"


class GraphEdge(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-graph-edge-v1"] = "evidence-graph-edge-v1"

    edge_id: GraphEdgeId
    kind: GraphEdgeKind
    source_node_id: NonBlankText
    target_node_id: NonBlankText
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    verification: EdgeVerificationRef | None = None
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def phase_boundaries_and_eligibility(self) -> Self:
        if self.source_node_id == self.target_node_id:
            raise ValueError("A graph edge cannot point at a single node")
        if self.kind in PHASE5_EDGE_KINDS:
            if self.verification is not None:
                raise ValueError("Phase 5 provenance edges must not carry verification refs")
            return self
        if self.verification is None:
            raise ValueError(f"{self.kind.value} requires an eligible verification reference")
        if self.kind == GraphEdgeKind.DIRECT_PRECEDENT:
            if not self.verification.decisive:
                raise ValueError("DIRECT_PRECEDENT requires decisive verified evidence")
            if self.verification.support_state != SupportVerificationState.SUPPORTED:
                raise ValueError("DIRECT_PRECEDENT requires fully supported evidence")
            if self.verification.precedent_relation not in {
                None,
                PrecedentState.DIRECT_PRECEDENT,
            }:
                raise ValueError("DIRECT_PRECEDENT ref carries another relation")
        elif self.kind == GraphEdgeKind.SUPPORTS:
            if self.verification.support_state != SupportVerificationState.SUPPORTED:
                raise ValueError("SUPPORTS requires verified support")
        elif self.kind == GraphEdgeKind.CONTRADICTS:
            if self.verification.support_state != SupportVerificationState.CONTRADICTED:
                raise ValueError("CONTRADICTS requires a verified contradiction")
        elif self.kind in {
            GraphEdgeKind.STRONG_PARTIAL_PRECEDENT,
            GraphEdgeKind.COMPONENT_PRECEDENT,
            GraphEdgeKind.ANALOGOUS,
        }:
            if self.verification.support_state not in {
                SupportVerificationState.SUPPORTED,
                SupportVerificationState.PARTIALLY_SUPPORTED,
            }:
                raise ValueError(f"{self.kind.value} requires verified partial or full support")
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
