"""Mechanical cache controls; toy SQLite rows do not establish native authority.

Prepared before implementation. Native Phase6/7 revalidation tests remain a
separate required gate before any existing fixture is routed through this cache.
"""

import sqlite3
from dataclasses import replace

import pytest


def api():
    from tests.fixtures.sqlite_baselines import (
        SnapshotIdentity,
        clone_snapshot,
        create_snapshot,
    )

    return SnapshotIdentity, create_snapshot, clone_snapshot


def seed(path, *, wal=False):
    connection = sqlite3.connect(path)
    if wal:
        connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE facts(value TEXT NOT NULL)")
    connection.execute("INSERT INTO facts VALUES ('original')")
    connection.commit()
    return connection


def identity():
    model, _, _ = api()
    return model(
        recipe_digest="a" * 64,
        environment_digest="b" * 64,
        schema_version=9,
        assessment_id="asm_mechanical_only",
        adjudication_id="p7frozen_mechanical_only",
        context_id="p7ctx_mechanical_only",
        snapshot_id="p6snap_mechanical_only",
    )


def validator(expected, calls):
    def validate(path):
        # Observable strict read callback, not a mock native authority certificate.
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT value FROM facts").fetchall() == [("original",)]
        calls.append(path)
        return expected

    return validate


def test_private_clone_mutation_preserves_baseline_and_second_clone(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    calls = []
    baseline = create(
        source, tmp_path / "baseline", identity=expected, validate=validator(expected, calls)
    )
    before = baseline.database_path.read_bytes()
    first = clone(
        baseline,
        tmp_path / "one.db",
        expected_identity=expected,
        validate=validator(expected, calls),
    )
    with sqlite3.connect(first) as connection:
        connection.execute("UPDATE facts SET value='changed'")
    second = clone(
        baseline,
        tmp_path / "two.db",
        expected_identity=expected,
        validate=validator(expected, calls),
    )
    assert baseline.database_path.read_bytes() == before
    assert baseline.database_path.stat().st_ino != first.stat().st_ino
    assert second.stat().st_ino != first.stat().st_ino
    with sqlite3.connect(second) as connection:
        assert connection.execute("SELECT value FROM facts").fetchall() == [("original",)]
    assert len(calls) == 3  # Published copy and each private clone validated independently.


@pytest.mark.parametrize(
    "field,value",
    [
        ("recipe_digest", "c" * 64),
        ("environment_digest", "d" * 64),
        ("schema_version", 8),
        ("context_id", "foreign_context"),
        ("snapshot_id", "foreign_snapshot"),
        ("adjudication_id", "foreign_adjudication"),
    ],
)
def test_wrong_recipe_schema_or_scope_cannot_reuse_baseline(tmp_path, field, value):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    baseline = create(
        source, tmp_path / "baseline", identity=expected, validate=validator(expected, [])
    )
    wrong = replace(expected, **{field: value})
    destination = tmp_path / "wrong.db"
    with pytest.raises(ValueError):
        clone(baseline, destination, expected_identity=wrong, validate=validator(wrong, []))
    assert not destination.exists()


def test_changed_baseline_checksum_rejected_before_clone(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    baseline = create(
        source, tmp_path / "baseline", identity=expected, validate=validator(expected, [])
    )
    baseline.database_path.chmod(0o600)  # Simulate owner tampering with a read-only image.
    with baseline.database_path.open("ab") as stream:
        stream.write(b"changed after publication")
    destination = tmp_path / "wrong.db"
    with pytest.raises(ValueError):
        clone(baseline, destination, expected_identity=expected, validate=validator(expected, []))
    assert not destination.exists()


def test_live_wal_source_copy_is_coherent_without_changing_source(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    connection = seed(source, wal=True)
    try:
        expected = identity()
        baseline = create(
            source,
            tmp_path / "baseline",
            identity=expected,
            validate=validator(expected, []),
        )
        copied = clone(
            baseline,
            tmp_path / "copy.db",
            expected_identity=expected,
            validate=validator(expected, []),
        )
        assert copied.exists()
        assert connection.execute("SELECT value FROM facts").fetchall() == [("original",)]
    finally:
        connection.close()


def test_failed_validation_never_publishes_ready_baseline(tmp_path):
    _, create, _ = api()
    source = tmp_path / "source.db"
    seed(source).close()
    directory = tmp_path / "baseline"

    def reject(path):
        raise ValueError("native validator rejects copied authority")

    with pytest.raises(ValueError):
        create(source, directory, identity=identity(), validate=reject)
    assert not (directory / "ready.json").exists()


def test_clone_cannot_replace_native_validation_with_cache_membership(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    baseline = create(
        source, tmp_path / "baseline", identity=expected, validate=validator(expected, [])
    )

    def revoked(path):
        raise ValueError("revoked native authority")

    with pytest.raises(ValueError, match="revoked native authority"):
        clone(baseline, tmp_path / "copy.db", expected_identity=expected, validate=revoked)


def test_validator_foreign_locator_cannot_publish_matching_manifest(tmp_path):
    _, create, _ = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    with pytest.raises(ValueError):
        create(
            source,
            tmp_path / "baseline",
            identity=expected,
            validate=lambda path: replace(expected, context_id="foreign"),
        )
    assert not (tmp_path / "baseline" / "ready.json").exists()


def test_existing_destination_is_never_overwritten(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    baseline = create(
        source, tmp_path / "baseline", identity=expected, validate=validator(expected, [])
    )
    destination = tmp_path / "existing.db"
    destination.write_bytes(b"unrelated work")
    with pytest.raises(FileExistsError):
        clone(baseline, destination, expected_identity=expected, validate=validator(expected, []))
    assert destination.read_bytes() == b"unrelated work"


def test_interrupted_publication_is_not_reusable(tmp_path):
    from tests.fixtures.sqlite_baselines import load_snapshot

    _, create, _ = api()
    source = tmp_path / "source.db"
    seed(source).close()
    directory = tmp_path / "baseline"

    def interrupt(path):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        create(source, directory, identity=identity(), validate=interrupt)
    with pytest.raises(FileNotFoundError):
        load_snapshot(directory, expected_identity=identity())
    with pytest.raises(FileExistsError):
        create(source, directory, identity=identity(), validate=validator(identity(), []))


def test_validation_cannot_mutate_a_published_or_cloned_image(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    baseline = create(
        source, tmp_path / "baseline", identity=expected, validate=validator(expected, [])
    )

    def mutate(path):
        with sqlite3.connect(path) as database:
            database.execute("UPDATE facts SET value='changed'")
        return expected

    destination = tmp_path / "mutated.db"
    with pytest.raises(ValueError, match="mutated"):
        clone(baseline, destination, expected_identity=expected, validate=mutate)
    assert not destination.exists()
    with sqlite3.connect(baseline.database_path) as database:
        assert database.execute("SELECT value FROM facts").fetchall() == [("original",)]


def test_timing_events_include_copy_and_native_validation_without_fake_builds(tmp_path):
    _, create, clone = api()
    source = tmp_path / "source.db"
    seed(source).close()
    expected = identity()
    events = []
    baseline = create(
        source,
        tmp_path / "baseline",
        identity=expected,
        validate=validator(expected, []),
        observe=events.append,
    )
    clone(
        baseline,
        tmp_path / "one.db",
        expected_identity=expected,
        validate=validator(expected, []),
        observe=events.append,
    )
    names = [event["stage"] for event in events]
    assert names.count("native_validation") == 2
    assert names.count("sqlite_backup") == 1
    assert names.count("database_copy") == 1
    assert all(event["outcome"] == "PASSED" and event["seconds"] >= 0 for event in events)


def test_backup_constructor_failure_closes_already_open_source(tmp_path, monkeypatch):
    from tests.fixtures import sqlite_baselines

    source = tmp_path / "source.db"
    seed(source).close()
    original = sqlite3.connect
    opened = []

    class TrackedRead:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def close(self):
            self.closed = True
            self.connection.close()

    def fail_write(path, *args, **kwargs):
        if kwargs.get("uri"):
            result = TrackedRead(original(path, *args, **kwargs))
            opened.append(result)
            return result
        raise sqlite3.OperationalError("write connection failed")

    monkeypatch.setattr(sqlite_baselines.sqlite3, "connect", fail_write)
    with pytest.raises(sqlite3.OperationalError):
        sqlite_baselines.create_snapshot(
            source, tmp_path / "baseline", identity=identity(), validate=validator(identity(), [])
        )
    assert len(opened) == 1
    assert opened[0].closed
    assert not (tmp_path / "baseline" / "ready.json").exists()


def test_recorded_observation_clock_restores_defaults_after_interruption():
    import time
    from datetime import UTC, datetime

    from novelty_harness.domain.base import utc_now
    from tests.fixtures.recorded_clock import recorded_observation_clock

    observed = datetime(2026, 9, 26, 12, tzinfo=UTC)
    started = time.monotonic()
    with pytest.raises(RuntimeError):
        with recorded_observation_clock(observed) as clock:
            assert clock() == utc_now() == observed
            assert time.monotonic() >= started
            raise RuntimeError("interrupted synthetic fixture")
    assert utc_now() != observed
    with pytest.raises(ValueError):
        with recorded_observation_clock(observed.replace(tzinfo=None)):
            pytest.fail("naive observation time admitted")
