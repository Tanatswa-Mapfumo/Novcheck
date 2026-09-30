"""Storage-independent evidence graph repository protocol.

Implementations return domain models, never storage rows, and batch writes
(``upsert``) are transactional: a failure must leave the graph unchanged.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.ids import AssessmentId, ClassificationId, EvidenceEdgeId, SourceId
from novelty_harness.evidence.graph.models import (
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from novelty_harness.evidence.precedent.gates import ClassifiedComparison
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster
from novelty_harness.evidence.verification.integrity import VerifiedEvidenceChain
from novelty_harness.evidence.verification.models import VerifiedEvidenceEdge


class GraphDirection(StrEnum):
    OUT = "OUT"
    IN = "IN"
    BOTH = "BOTH"


class ContentAuthorityError(ValueError):
    """A semantic artifact conflicts with immutable stored content authority."""


class Phase6CommitReceipt(ContractModel):
    """Phase 6 identities confirmed only after the repository transaction commits."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-commit-receipt-v1"] = "phase6-commit-receipt-v1"
    assessment_id: AssessmentId
    committed_edge_ids: tuple[EvidenceEdgeId, ...]
    committed_classification_ids: tuple[ClassificationId, ...]


@runtime_checkable
class EvidenceGraphRepository(Protocol):
    def upsert(
        self,
        *,
        nodes: Sequence[GraphNode] = (),
        edges: Sequence[GraphEdge] = (),
        clusters: Sequence[EvidenceLineageCluster] = (),
        verified_edges: Sequence[VerifiedEvidenceEdge] = (),
        verified_chains: Sequence[VerifiedEvidenceChain] = (),
        classified_comparisons: Sequence[ClassifiedComparison] = (),
    ) -> Phase6CommitReceipt | None:
        """Atomically insert-or-verify nodes, edges, clusters and verified edges.

        Phase 6 graph edges must resolve their verification reference against a
        persisted verified artifact inside the same transaction. Re-persisting
        identical content is idempotent; different content under an existing
        identity is an error because history is append-only.
        """
        ...

    def get_node(self, node_id: str) -> GraphNode | None: ...

    def get_edge(self, edge_id: str) -> GraphEdge | None: ...

    def nodes(self, *, kinds: frozenset[GraphNodeKind] | None = None) -> tuple[GraphNode, ...]: ...

    def edges(
        self,
        *,
        node_id: str | None = None,
        direction: GraphDirection = GraphDirection.OUT,
        kinds: frozenset[GraphEdgeKind] | None = None,
    ) -> tuple[GraphEdge, ...]: ...

    def neighbors(
        self,
        node_id: str,
        *,
        direction: GraphDirection = GraphDirection.OUT,
        kinds: frozenset[GraphEdgeKind] | None = None,
    ) -> tuple[GraphNode, ...]: ...

    def lineage_cluster_for_source(self, source_id: SourceId) -> EvidenceLineageCluster | None: ...

    def lineage_clusters(self) -> tuple[EvidenceLineageCluster, ...]: ...

    def close(self) -> None: ...
