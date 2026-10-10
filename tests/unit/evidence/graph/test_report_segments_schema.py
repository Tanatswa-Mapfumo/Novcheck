"""Additive schema v10 never rewrites accepted inline documents or invents authority."""

import pytest
from sqlalchemy import event, inspect, text

from novelty_harness.evidence.graph.migrations import ensure_schema, schema_version
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository


@pytest.mark.parametrize("fail_commit", [False, True])
def test_v9_additive_segments_migration_is_atomic_and_preserves_existing_bytes(
    tmp_path, fail_commit
):
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "migration.db")
    try:
        with repository.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS compiled_report_document_chunks")
            connection.execute(text("UPDATE schema_version SET version=9"))
            # A legacy inert payload is not report authority. Every existing table is observed.
            connection.exec_driver_sql(
                "CREATE TABLE legacy_bytes (id INTEGER PRIMARY KEY, value BLOB NOT NULL)"
            )
            connection.exec_driver_sql("INSERT INTO legacy_bytes VALUES (1, X'00FF80')")
        names = set(inspect(repository.engine).get_table_names()) - {"schema_version"}

        def snapshot():
            with repository.engine.connect() as connection:
                return {
                    name: tuple(
                        tuple(row) for row in connection.exec_driver_sql(f'SELECT * FROM "{name}"')
                    )
                    for name in sorted(names)
                }

        before = snapshot()

        def fail(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("UPDATE schema_version"):
                raise RuntimeError("injected v10 metadata failure")

        if fail_commit:
            event.listen(repository.engine, "before_cursor_execute", fail)
            try:
                with pytest.raises(RuntimeError, match="injected v10 metadata failure"):
                    ensure_schema(repository.engine)
            finally:
                event.remove(repository.engine, "before_cursor_execute", fail)
            assert schema_version(repository.engine) == 9
            assert (
                "compiled_report_document_chunks"
                not in inspect(repository.engine).get_table_names()
            )
            assert snapshot() == before
        assert ensure_schema(repository.engine) == 10
        assert snapshot() == before
        with repository.engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM compiled_report_document_chunks"
                ).scalar_one()
                == 0
            )
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert ensure_schema(repository.engine) == 10
    finally:
        repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(tmp_path / "migration.db")
    try:
        assert schema_version(reopened.engine) == 10
        with reopened.engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT value FROM legacy_bytes"
            ).scalar_one() == bytes([0, 255, 128])
    finally:
        reopened.close()
