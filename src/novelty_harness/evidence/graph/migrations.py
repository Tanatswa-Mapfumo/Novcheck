"""Schema creation and version metadata for the SQLite evidence graph."""

from datetime import UTC, datetime

from sqlalchemy import Engine, insert, inspect, select, update

from novelty_harness.evidence.graph.models import PHASE6_EDGE_KINDS
from novelty_harness.evidence.graph.sqlalchemy_models import (
    Base,
    GraphEdgeRow,
    SchemaVersionRow,
    VerifiedEdgeRow,
)

SCHEMA_VERSION = 4


def schema_version(engine: Engine) -> int | None:
    """Return the persisted schema version, or ``None`` for an empty database."""

    with engine.connect() as connection:
        versions = connection.execute(select(SchemaVersionRow.version)).scalars().all()
    if not versions:
        return None
    return max(versions)


def ensure_schema(engine: Engine) -> int:
    """Create the schema at the current version and verify version metadata.

    A database written by a newer schema is refused instead of being
    reinterpreted by older code.
    """

    existing_tables = set(inspect(engine).get_table_names())
    current = schema_version(engine) if "schema_version" in existing_tables else None
    if current in {1, 2, 3} and "graph_edges" in existing_tables:
        with engine.connect() as connection:
            unsafe = connection.execute(
                select(GraphEdgeRow.edge_id).where(
                    GraphEdgeRow.kind.in_([kind.value for kind in PHASE6_EDGE_KINDS])
                )
            ).first()
        if unsafe is not None:
            raise ValueError(
                "Legacy Phase 6 graph edges lack the authoritative v4 contract; "
                "migration is blocked until those edges are reprocessed"
            )
    if current in {2, 3} and "verified_edges" in existing_tables:
        with engine.connect() as connection:
            if connection.execute(select(VerifiedEdgeRow.edge_id)).first() is not None:
                raise ValueError("Legacy verified edges require reprocessing before v4 migration")
    Base.metadata.create_all(engine)
    if current is None:
        with engine.begin() as connection:
            connection.execute(
                insert(SchemaVersionRow).values(
                    version=SCHEMA_VERSION, applied_at=datetime.now(UTC).isoformat()
                )
            )
        return SCHEMA_VERSION
    if current > SCHEMA_VERSION:
        raise ValueError(
            f"Evidence graph schema version {current} is newer than supported "
            f"{SCHEMA_VERSION}; refusing to reinterpret"
        )
    if current < SCHEMA_VERSION:
        if current in {1, 2, 3}:
            # Legacy Phase 6 edges were blocked above. Metadata-only graphs migrate safely.
            with engine.begin() as connection:
                connection.execute(
                    update(SchemaVersionRow)
                    .where(SchemaVersionRow.version == current)
                    .values(version=SCHEMA_VERSION, applied_at=datetime.now(UTC).isoformat())
                )
            return SCHEMA_VERSION
        raise ValueError(
            f"Evidence graph schema version {current} requires migration to {SCHEMA_VERSION}"
        )
    return current
