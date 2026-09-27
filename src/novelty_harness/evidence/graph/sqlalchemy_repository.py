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

from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.graph.migrations import ensure_schema
from novelty_harness.evidence.graph.models import (
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
)
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster
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
    ) -> None:
        with Session(self._engine) as session, session.begin():
            self._verify_edge_endpoints(session, nodes, edges)
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

    def _persist_edge(self, session: Session, edge: GraphEdge) -> None:
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
