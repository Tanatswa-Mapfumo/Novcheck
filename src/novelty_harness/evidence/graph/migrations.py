"""Schema creation and version metadata for the SQLite evidence graph."""

from datetime import UTC, datetime

from sqlalchemy import Engine, insert, inspect, select, update

from novelty_harness.evidence.graph import phase7_models, report_models
from novelty_harness.evidence.graph.models import PHASE6_EDGE_KINDS
from novelty_harness.evidence.graph.sqlalchemy_models import (
    Base,
    GraphEdgeRow,
    SchemaVersionRow,
    VerifiedEdgeRow,
)

SCHEMA_VERSION = 9


def schema_version(engine: Engine) -> int | None:
    """Return the persisted schema version, or ``None`` for an empty database."""
    with engine.connect() as connection:
        if "schema_version" not in inspect(connection).get_table_names():
            return None
        versions = connection.execute(select(SchemaVersionRow.version)).scalars().all()
    return max(versions) if versions else None


def ensure_schema(engine: Engine) -> int:
    """Create additive schema/metadata atomically without inventing authority.

    SQLite's legacy driver does not start a transaction for DDL. Explicit
    BEGIN IMMEDIATE makes table creation and metadata advancement one unit.
    All historical unsafe-migration guards remain before any schema mutation.
    """
    assert phase7_models.Phase7InputManifestRow.__tablename__ in Base.metadata.tables
    assert report_models.ReportCompilationRow.__tablename__ in Base.metadata.tables
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        existing_tables = set(inspect(connection).get_table_names())
        versions = (
            connection.execute(select(SchemaVersionRow.version)).scalars().all()
            if "schema_version" in existing_tables
            else ()
        )
        current = max(versions) if versions else None
        if current is not None and current > SCHEMA_VERSION:
            raise ValueError(
                f"Evidence graph schema version {current} is newer than supported "
                f"{SCHEMA_VERSION}; refusing to reinterpret"
            )
        if current is not None and current < SCHEMA_VERSION and current not in range(1, 9):
            raise ValueError(
                f"Evidence graph schema version {current} requires migration to {SCHEMA_VERSION}"
            )
        if current in {1, 2, 3} and "graph_edges" in existing_tables:
            unsafe = connection.execute(
                select(GraphEdgeRow.edge_id).where(
                    GraphEdgeRow.kind.in_([kind.value for kind in PHASE6_EDGE_KINDS])
                )
            ).first()
            if unsafe is not None:
                raise ValueError(
                    "Legacy Phase 6 graph edges lack the authoritative v6 contract; "
                    "migration is blocked until those edges are reprocessed"
                )
        if current in {2, 3} and "verified_edges" in existing_tables:
            if connection.execute(select(VerifiedEdgeRow.edge_id)).first() is not None:
                raise ValueError("Legacy verified edges require reprocessing before v6 migration")
        Base.metadata.create_all(connection)
        if current is None:
            connection.execute(
                insert(SchemaVersionRow).values(
                    version=SCHEMA_VERSION, applied_at=datetime.now(UTC).isoformat()
                )
            )
        elif current < SCHEMA_VERSION:
            # Existing semantic rows gain no commit membership. Empty Phase 7
            # and report tables never backfill authority from legacy artifacts.
            connection.execute(
                update(SchemaVersionRow)
                .where(SchemaVersionRow.version == current)
                .values(version=SCHEMA_VERSION, applied_at=datetime.now(UTC).isoformat())
            )
    return SCHEMA_VERSION
