"""SQLAlchemy 2.x evidence graph repository over SQLite.

Returns domain models only. Batch writes are transactional; identical
re-persistence is idempotent; different content under an existing identity is
rejected because graph history is append-only.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from novelty_harness.domain.enums import PrecedentState
from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.graph.migrations import ensure_schema
from novelty_harness.evidence.graph.models import (
    PHASE6_EDGE_KINDS,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from novelty_harness.evidence.graph.repository import GraphDirection
from novelty_harness.evidence.graph.sqlalchemy_models import (
    GraphEdgeRow,
    GraphNodeRow,
    LineageClusterMemberRow,
    LineageClusterRow,
    VerifiedChainRow,
    VerifiedEdgeRow,
)
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster
from novelty_harness.evidence.verification.gates import validate_verified_chain
from novelty_harness.evidence.verification.integrity import VerifiedEvidenceChain
from novelty_harness.evidence.verification.models import VerifiedEvidenceEdge
from novelty_harness.runtime.tracing.hashing import canonical_json


def _sqlite_engine(database: Path | None) -> Engine:
    if database is None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class SqlAlchemyEvidenceGraphRepository:
    """First storage implementation of the evidence graph repository protocol."""

    def __init__(self, database: Path | str | None = None) -> None:
        path = Path(database) if database is not None else None
        self._engine = _sqlite_engine(path)
        ensure_schema(self._engine)

    @property
    def engine(self) -> Engine:
        return self._engine

    def upsert(
        self,
        *,
        nodes: Sequence[GraphNode] = (),
        edges: Sequence[GraphEdge] = (),
        clusters: Sequence[EvidenceLineageCluster] = (),
        verified_edges: Sequence[VerifiedEvidenceEdge] = (),
        verified_chains: Sequence[VerifiedEvidenceChain] = (),
    ) -> None:
        with Session(self._engine) as session, session.begin():
            self._verify_edge_endpoints(session, nodes, edges)
            for verified in verified_edges:
                self._persist_verified_edge(session, verified)
            for chain in verified_chains:
                self._persist_verified_chain(session, chain, nodes)
            self._verify_phase6_edges(session, edges, verified_edges, verified_chains)
            for node in nodes:
                self._persist_node(session, node)
            for edge in edges:
                self._persist_edge(session, edge)
            for cluster in clusters:
                self._persist_cluster(session, cluster)

    def _verify_edge_endpoints(
        self,
        session: Session,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge],
    ) -> None:
        batch_ids = {node.node_id for node in nodes}
        persisted = set(session.scalars(select(GraphNodeRow.node_id)).all())
        known = batch_ids | persisted
        for edge in edges:
            for endpoint in (edge.source_node_id, edge.target_node_id):
                if endpoint not in known:
                    raise ValueError(
                        f"Graph edge {edge.edge_id} has a dangling endpoint: {endpoint}"
                    )

    def _persist_node(self, session: Session, node: GraphNode) -> None:
        document = canonical_json(node)
        row = session.get(GraphNodeRow, node.node_id)
        if row is None:
            session.add(
                GraphNodeRow(
                    node_id=node.node_id,
                    kind=node.kind.value,
                    label=node.label,
                    document_json=document,
                )
            )
            return
        if row.document_json != document:
            raise ValueError(
                f"Graph node {node.node_id} already exists with different content; "
                "history is append-only"
            )

    def _persist_verified_edge(self, session: Session, verified: VerifiedEvidenceEdge) -> None:
        document = canonical_json(verified)
        row = session.get(VerifiedEdgeRow, verified.edge_id)
        if row is None:
            session.add(
                VerifiedEdgeRow(
                    edge_id=verified.edge_id,
                    source_id=verified.source_id,
                    mcu_id=verified.mcu_id,
                    document_json=document,
                )
            )
            return
        if row.document_json != document:
            raise ValueError(
                f"Verified edge {verified.edge_id} already exists with different content; "
                "history is append-only"
            )

    def _resolve_verified_edge(
        self, session: Session, verified_edge_id: str
    ) -> VerifiedEvidenceEdge | None:
        row = session.get(VerifiedEdgeRow, verified_edge_id)
        if row is None:
            return None
        return VerifiedEvidenceEdge.model_validate_json(row.document_json)

    def _resolve_verified_chain(
        self, session: Session, verified_edge_id: str
    ) -> VerifiedEvidenceChain | None:
        row = session.get(VerifiedChainRow, verified_edge_id)
        return VerifiedEvidenceChain.model_validate_json(row.document_json) if row else None

    def _persist_verified_chain(
        self,
        session: Session,
        chain: VerifiedEvidenceChain,
        batch_nodes: Sequence[GraphNode],
    ) -> None:
        cited = validate_verified_chain(chain)
        by_id = {node.node_id: node for node in batch_nodes}

        def node(identity: str) -> GraphNode | None:
            present = by_id.get(identity)
            if present is not None:
                return present
            row = session.get(GraphNodeRow, identity)
            return GraphNode.model_validate_json(row.document_json) if row else None

        source_node = node(chain.source.source_id)
        if source_node is None or source_node.kind != GraphNodeKind.SOURCE:
            raise ValueError("Verified semantic chain has no persisted source node")
        if chain.version is not None:
            version_node = node(chain.version.version_id)
            if (
                version_node is None
                or version_node.kind != GraphNodeKind.SOURCE_VERSION
                or version_node.attributes.get("source_id") != chain.source.source_id
            ):
                raise ValueError("Verified semantic chain has no matching source-version node")
        for passage in cited:
            passage_node = node(passage.passage_id)
            if (
                passage_node is None
                or passage_node.kind != GraphNodeKind.PASSAGE
                or passage_node.attributes.get("source_id") != passage.source_id
                or passage_node.attributes.get("source_version_id") != passage.source_version_id
                or passage_node.attributes.get("content_hash") != passage.content_hash
            ):
                raise ValueError(
                    f"Verified semantic chain cites unresolved passage {passage.passage_id}"
                )
        document = canonical_json(chain)
        row = session.get(VerifiedChainRow, chain.edge.edge_id)
        if row is None:
            session.add(VerifiedChainRow(edge_id=chain.edge.edge_id, document_json=document))
        elif row.document_json != document:
            raise ValueError(
                f"Verified semantic chain {chain.edge.edge_id} already exists "
                "with different content"
            )

    def _verify_phase6_edges(
        self,
        session: Session,
        edges: Sequence[GraphEdge],
        batch: Sequence[VerifiedEvidenceEdge],
        chains: Sequence[VerifiedEvidenceChain],
    ) -> None:
        """Resolve every Phase 6 verification reference against a real artifact."""

        batch_by_id = {verified.edge_id: verified for verified in batch}
        chain_by_id = {chain.edge.edge_id: chain for chain in chains}
        expected_relation = {
            GraphEdgeKind.DIRECT_PRECEDENT: PrecedentState.DIRECT_PRECEDENT,
            GraphEdgeKind.STRONG_PARTIAL_PRECEDENT: PrecedentState.STRONG_PARTIAL_PRECEDENT,
            GraphEdgeKind.COMPONENT_PRECEDENT: PrecedentState.COMPONENT_PRECEDENT_ONLY,
            GraphEdgeKind.ANALOGOUS: PrecedentState.ANALOGOUS_PRECEDENT,
            GraphEdgeKind.NO_MATCH: PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
        }
        for edge in edges:
            if edge.kind not in PHASE6_EDGE_KINDS:
                continue
            reference = edge.verification
            if reference is None:
                raise ValueError(
                    f"Phase 6 graph edge {edge.edge_id} lacks a verification reference"
                )
            verified = batch_by_id.get(reference.verified_edge_id) or self._resolve_verified_edge(
                session, reference.verified_edge_id
            )
            if verified is None:
                raise ValueError(
                    f"Graph edge {edge.edge_id} references unknown verified edge "
                    f"{reference.verified_edge_id}"
                )
            chain = chain_by_id.get(reference.verified_edge_id) or self._resolve_verified_chain(
                session, reference.verified_edge_id
            )
            if chain is None:
                raise ValueError(f"Graph edge {edge.edge_id} has no resolved semantic chain")
            validate_verified_chain(chain)
            if chain.edge != verified:
                raise ValueError("Graph edge semantic chain differs from verified artifact")
            if verified.source_id != edge.source_node_id or verified.mcu_id != edge.target_node_id:
                raise ValueError(
                    f"Graph edge {edge.edge_id} endpoints do not match the verified artifact"
                )
            if (
                verified.support_state != reference.support_state
                or verified.decisive != reference.decisive
                or verified.relation != reference.precedent_relation
            ):
                raise ValueError(
                    f"Graph edge {edge.edge_id} support state, decisiveness or relation "
                    "does not match the verified artifact"
                )
            relation_expected = expected_relation.get(edge.kind)
            if relation_expected is not None and verified.relation != relation_expected:
                raise ValueError(
                    f"Graph edge {edge.edge_id} kind does not match the verified relation"
                )
            if reference.decisive and (
                not verified.eligibility.decisive or verified.chronology.state != "PREDATES_CUTOFF"
            ):
                raise ValueError(
                    f"Graph edge {edge.edge_id} claims decisiveness without eligible chronology"
                )

    def _persist_edge(self, session: Session, edge: GraphEdge) -> None:
        if edge.kind in PHASE6_EDGE_KINDS:
            if edge.verification is None or (
                edge.kind == GraphEdgeKind.DIRECT_PRECEDENT and not edge.verification.decisive
            ):
                raise ValueError("Phase 6 graph edges require an eligible verification reference")
        document = canonical_json(edge)
        row = session.get(GraphEdgeRow, edge.edge_id)
        if row is None:
            session.add(
                GraphEdgeRow(
                    edge_id=edge.edge_id,
                    kind=edge.kind.value,
                    source_node_id=edge.source_node_id,
                    target_node_id=edge.target_node_id,
                    document_json=document,
                )
            )
            return
        if row.document_json != document:
            raise ValueError(
                f"Graph edge {edge.edge_id} already exists with different content; "
                "history is append-only"
            )

    def _persist_cluster(self, session: Session, cluster: EvidenceLineageCluster) -> None:
        document = canonical_json(cluster)
        row = session.get(LineageClusterRow, cluster.cluster_id)
        if row is None:
            session.add(LineageClusterRow(cluster_id=cluster.cluster_id, document_json=document))
        elif row.document_json != document:
            raise ValueError(
                f"Lineage cluster {cluster.cluster_id} already exists with different content; "
                "history is append-only"
            )
        session.flush()
        for source_id in cluster.source_ids:
            existing = session.get(LineageClusterMemberRow, source_id)
            if existing is not None:
                if existing.cluster_id != cluster.cluster_id:
                    raise ValueError(
                        f"Source {source_id} already belongs to lineage cluster "
                        f"{existing.cluster_id}"
                    )
                continue
            session.add(LineageClusterMemberRow(source_id=source_id, cluster_id=cluster.cluster_id))

    def get_node(self, node_id: str) -> GraphNode | None:
        with Session(self._engine) as session:
            row = session.get(GraphNodeRow, node_id)
            return GraphNode.model_validate_json(row.document_json) if row else None

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        with Session(self._engine) as session:
            row = session.get(GraphEdgeRow, edge_id)
            return GraphEdge.model_validate_json(row.document_json) if row else None

    def nodes(self, *, kinds: frozenset[GraphNodeKind] | None = None) -> tuple[GraphNode, ...]:
        statement = select(GraphNodeRow).order_by(GraphNodeRow.node_id)
        if kinds is not None:
            statement = statement.where(GraphNodeRow.kind.in_([kind.value for kind in kinds]))
        with Session(self._engine) as session:
            rows = session.scalars(statement).all()
        return tuple(GraphNode.model_validate_json(row.document_json) for row in rows)

    def edges(
        self,
        *,
        node_id: str | None = None,
        direction: GraphDirection = GraphDirection.OUT,
        kinds: frozenset[GraphEdgeKind] | None = None,
    ) -> tuple[GraphEdge, ...]:
        statement = select(GraphEdgeRow).order_by(GraphEdgeRow.edge_id)
        if node_id is not None:
            if direction == GraphDirection.OUT:
                statement = statement.where(GraphEdgeRow.source_node_id == node_id)
            elif direction == GraphDirection.IN:
                statement = statement.where(GraphEdgeRow.target_node_id == node_id)
            else:
                statement = statement.where(
                    (GraphEdgeRow.source_node_id == node_id)
                    | (GraphEdgeRow.target_node_id == node_id)
                )
        if kinds is not None:
            statement = statement.where(GraphEdgeRow.kind.in_([kind.value for kind in kinds]))
        with Session(self._engine) as session:
            rows = session.scalars(statement).all()
        return tuple(GraphEdge.model_validate_json(row.document_json) for row in rows)

    def neighbors(
        self,
        node_id: str,
        *,
        direction: GraphDirection = GraphDirection.OUT,
        kinds: frozenset[GraphEdgeKind] | None = None,
    ) -> tuple[GraphNode, ...]:
        edge_rows = self.edges(node_id=node_id, direction=direction, kinds=kinds)
        neighbour_ids: set[str] = set()
        for edge in edge_rows:
            if edge.source_node_id == node_id:
                neighbour_ids.add(edge.target_node_id)
            if edge.target_node_id == node_id:
                neighbour_ids.add(edge.source_node_id)
        with Session(self._engine) as session:
            rows = session.scalars(
                select(GraphNodeRow)
                .where(GraphNodeRow.node_id.in_(sorted(neighbour_ids)))
                .order_by(GraphNodeRow.node_id)
            ).all()
        return tuple(GraphNode.model_validate_json(row.document_json) for row in rows)

    def lineage_cluster_for_source(self, source_id: SourceId) -> EvidenceLineageCluster | None:
        with Session(self._engine) as session:
            member = session.get(LineageClusterMemberRow, source_id)
            if member is None:
                return None
            row = session.get(LineageClusterRow, member.cluster_id)
        return EvidenceLineageCluster.model_validate_json(row.document_json) if row else None

    def lineage_clusters(self) -> tuple[EvidenceLineageCluster, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(LineageClusterRow).order_by(LineageClusterRow.cluster_id)
            ).all()
        return tuple(EvidenceLineageCluster.model_validate_json(row.document_json) for row in rows)

    def close(self) -> None:
        self._engine.dispose()
