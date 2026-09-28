"""SQLAlchemy 2.x ORM rows for the evidence graph. Infrastructure only."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SchemaVersionRow(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[str] = mapped_column(String(40), nullable=False)


class GraphNodeRow(Base):
    __tablename__ = "graph_nodes"

    node_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class GraphEdgeRow(Base):
    __tablename__ = "graph_edges"

    edge_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_node_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("graph_nodes.node_id"), nullable=False, index=True
    )
    target_node_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("graph_nodes.node_id"), nullable=False, index=True
    )
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class VerifiedEdgeRow(Base):
    __tablename__ = "verified_edges"

    edge_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    mcu_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class VerifiedChainRow(Base):
    __tablename__ = "verified_chains"

    edge_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("verified_edges.edge_id"), primary_key=True
    )
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class LineageClusterRow(Base):
    __tablename__ = "lineage_clusters"

    cluster_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class LineageClusterMemberRow(Base):
    __tablename__ = "lineage_cluster_members"

    source_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("graph_nodes.node_id"), primary_key=True
    )
    cluster_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("lineage_clusters.cluster_id"), nullable=False, index=True
    )
