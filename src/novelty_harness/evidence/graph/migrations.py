"""Schema creation and version metadata for the SQLite evidence graph."""

from datetime import UTC, datetime

from sqlalchemy import Engine, insert, select

from novelty_harness.evidence.graph.sqlalchemy_models import Base, SchemaVersionRow

SCHEMA_VERSION = 1


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

    Base.metadata.create_all(engine)
    current = schema_version(engine)
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
        raise ValueError(
            f"Evidence graph schema version {current} requires migration to {SCHEMA_VERSION}"
        )
    return current
