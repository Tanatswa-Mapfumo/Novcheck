"""Storage-independent evidence graph repository protocol.

Implementations return domain models, never storage rows, and batch writes
(``upsert``) are transactional: a failure must leave the graph unchanged.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, Self, runtime_checkable

from pydantic import ConfigDict, model_validator

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
    """Reference to a repository commit; never proof of authority by itself."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-commit-receipt-v2"] = "phase6-commit-receipt-v2"
    commit_id: str | None = None
    assessment_id: AssessmentId
    committed_edge_ids: tuple[EvidenceEdgeId, ...]
    committed_classification_ids: tuple[ClassificationId, ...]


class Phase6CommitRecord(ContractModel):
    """Immutable transaction manifest for one assessed Phase 6 comparison batch."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-commit-record-v1"] = "phase6-commit-record-v1"
    commit_id: str
    assessment_id: AssessmentId
    committed_edge_ids: tuple[EvidenceEdgeId, ...]
    committed_classification_ids: tuple[ClassificationId, ...]

    @model_validator(mode="after")
    def paired_unique_artifacts(self) -> Self:
        if not self.committed_edge_ids or len(self.committed_edge_ids) != len(
            self.committed_classification_ids
        ):
            raise ValueError("Phase 6 commit requires paired edge and classification IDs")
        if len(set(self.committed_edge_ids)) != len(self.committed_edge_ids) or len(
            set(self.committed_classification_ids)
        ) != len(self.committed_classification_ids):
            raise ValueError("Phase 6 commit IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class ResolvedPhase6Commit:
    """Repository-loaded semantics for a validated persisted commit."""

    record: Phase6CommitRecord
    comparisons: tuple[ClassifiedComparison, ...]


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

        Phase 6 graph edges and proposition nodes are derived only from the
        classified semantic comparisons committed in this transaction. Their
        repository membership links them to its persisted commit manifest.
        Re-persisting identical content is idempotent; different content under
        an existing identity is an error because history is append-only.
        """
        ...

    def resolve_phase6_commit(self, receipt: Phase6CommitReceipt) -> ResolvedPhase6Commit:
        """Resolve a receipt to a persisted manifest and its validated semantic artifacts."""
        ...

    def get_node(self, node_id: str) -> GraphNode | None:
        """Return ordinary nodes and commit-authorized Phase 6 proposition nodes."""
        ...

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        """Return ordinary edges and commit-authorized Phase 6 relations."""
        ...

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
