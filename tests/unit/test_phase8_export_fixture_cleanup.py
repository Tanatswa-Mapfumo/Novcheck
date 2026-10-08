"""Export fixture lifetime controls; toy SQLite is not native authority proof."""

import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest

from tests.integration import test_phase8_slice as slice_tests


def source_case(tmp_path):
    path = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(path)) as database:
        database.execute("CREATE TABLE original (value TEXT)")
        database.execute("INSERT INTO original VALUES ('unchanged')")
        database.commit()
    frozen = SimpleNamespace(assessment_id="asm_cleanup", adjudication_id="p7frozen_cleanup")
    source = SimpleNamespace(
        repository=SimpleNamespace(engine=SimpleNamespace(url=SimpleNamespace(database=str(path)))),
        frozen=frozen,
    )
    return source, object(), path.read_bytes()


def install_observers(monkeypatch, source, *, fail_load=None, fail_backup=False, fail_close=False):
    connections = []
    repositories = []
    connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

        def backup(self, destination, **kwargs):
            super().backup(destination, **kwargs)
            if fail_backup:
                raise OSError("interrupted coherent copy")

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, factory=Connection, **kwargs)
        connections.append(connection)
        return connection

    class Repository:
        def __init__(self, path):
            self.path = path
            self.closed = False
            repositories.append(self)

        def load_frozen_adjudication(self, assessment_id, *, adjudication_id):
            assert (assessment_id, adjudication_id) == (
                source.frozen.assessment_id,
                source.frozen.adjudication_id,
            )
            if fail_load == "frozen":
                raise ValueError("recorded frozen load refusal")
            return source.frozen

        def load_report_input_bundle(self, assessment_id, *, adjudication_id):
            assert (assessment_id, adjudication_id) == (
                source.frozen.assessment_id,
                source.frozen.adjudication_id,
            )
            if fail_load == "bundle":
                raise ValueError("recorded bundle load refusal")
            return object()

        def close(self):
            self.closed = True
            if fail_close:
                raise OSError("recorded disposal failure")

    monkeypatch.setattr(slice_tests.sqlite3, "connect", tracked_connect)
    monkeypatch.setattr(slice_tests, "SqlAlchemyEvidenceGraphRepository", Repository)
    return connections, repositories


@pytest.mark.parametrize("failure", ["frozen", "bundle"])
def test_export_clone_closes_repository_when_native_load_fails(tmp_path, monkeypatch, failure):
    source, report, before = source_case(tmp_path)
    connections, repositories = install_observers(monkeypatch, source, fail_load=failure)
    private = tmp_path / "clone"
    private.mkdir()
    fixture = slice_tests.exported_case.__wrapped__((source, report), private)
    with pytest.raises(ValueError, match="load refusal"):
        next(fixture)
    assert repositories[0].closed
    assert all(connection.closed for connection in connections)
    assert not (private / "accepted-copy.sqlite").exists()
    assert open_source_bytes(source) == before


def open_source_bytes(source):
    from pathlib import Path

    return Path(source.repository.engine.url.database).read_bytes()


def test_export_clone_closes_copy_connections_before_yield(tmp_path, monkeypatch):
    source, report, before = source_case(tmp_path)
    connections, repositories = install_observers(monkeypatch, source)
    private = tmp_path / "clone"
    private.mkdir()
    fixture = slice_tests.exported_case.__wrapped__((source, report), private)
    try:
        case, returned = next(fixture)
        assert returned is report and case.repository is repositories[0]
        assert len(connections) == 2
        assert all(connection.closed for connection in connections)
    finally:
        fixture.close()
    assert repositories[0].closed
    assert not (private / "accepted-copy.sqlite").exists()
    assert open_source_bytes(source) == before


def test_export_clone_cleans_interrupted_database_copy(tmp_path, monkeypatch):
    source, report, before = source_case(tmp_path)
    connections, repositories = install_observers(monkeypatch, source, fail_backup=True)
    private = tmp_path / "clone"
    private.mkdir()
    fixture = slice_tests.exported_case.__wrapped__((source, report), private)
    with pytest.raises(OSError, match="interrupted coherent copy"):
        next(fixture)
    assert not repositories
    assert all(connection.closed for connection in connections)
    assert not (private / "accepted-copy.sqlite").exists()
    assert open_source_bytes(source) == before


def test_export_clone_removes_database_sidecars_on_interruption(tmp_path, monkeypatch):
    source, report, before = source_case(tmp_path)
    _, repositories = install_observers(monkeypatch, source)
    private = tmp_path / "clone"
    private.mkdir()
    fixture = slice_tests.exported_case.__wrapped__((source, report), private)
    next(fixture)
    for suffix in ("-journal", "-wal", "-shm"):
        (private / ("accepted-copy.sqlite" + suffix)).write_bytes(b"private sidecar")
    with pytest.raises(KeyboardInterrupt):
        fixture.throw(KeyboardInterrupt())
    assert repositories[0].closed
    assert not list(private.glob("accepted-copy.sqlite*"))
    assert open_source_bytes(source) == before


def test_export_clone_cleanup_survives_repository_disposal_failure(tmp_path, monkeypatch):
    source, report, before = source_case(tmp_path)
    _, repositories = install_observers(monkeypatch, source, fail_close=True)
    private = tmp_path / "clone"
    private.mkdir()
    fixture = slice_tests.exported_case.__wrapped__((source, report), private)
    next(fixture)
    with pytest.raises(OSError, match="disposal failure"):
        fixture.close()
    assert repositories[0].closed
    assert not (private / "accepted-copy.sqlite").exists()
    assert open_source_bytes(source) == before
