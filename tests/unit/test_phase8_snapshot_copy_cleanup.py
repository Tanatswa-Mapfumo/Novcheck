"""Snapshot connection lifetime; toy SQLite never confers native authority."""

import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest

from tests.unit.evidence.graph import test_report_store as store_tests


@pytest.mark.parametrize("helper", ["candidate", "accepted"])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("fail_backup", [False, True])
def test_report_snapshot_copy_closes_connections_before_load_or_serialization(
    tmp_path, monkeypatch, helper, cached, fail_backup
):
    from sqlalchemy import orm

    from novelty_harness.reporting.ir import CompiledAssessmentReport

    original = tmp_path / "original.sqlite"
    database = tmp_path / "private.sqlite"
    for path in (original, database):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE original (value TEXT)")
            connection.execute("INSERT INTO original VALUES ('unchanged')")
            connection.commit()
    before = original.read_bytes()
    connections = []
    original_connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

        def backup(self, target):
            super().backup(target)
            if fail_backup:
                raise OSError("controlled snapshot interruption")

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, factory=Connection, **kwargs)
        connections.append(connection)
        return connection

    def checked_boundary():
        assert all(connection.closed for connection in connections), (
            "snapshot connections remain open at the next native load or serialization boundary"
        )

    class Report:
        report_id = "toy-report"
        compilation_id = "toy-compilation"

        def model_dump_json(self):
            checked_boundary()
            return "toy serialized report"

    report = Report()
    compilation = SimpleNamespace(compilation_id=report.compilation_id)

    def native_load(_):
        checked_boundary()
        raise ValueError("controlled native load refusal")

    repository = SimpleNamespace(
        engine=SimpleNamespace(url=SimpleNamespace(database=str(database)), dispose=lambda: None),
        load_report_artifacts=native_load,
        accept_compiled_report=lambda *_: report.report_id,
    )
    case = SimpleNamespace(
        bundle=SimpleNamespace(bundle_digest="toy-bundle"), repository=repository
    )
    candidate_key = ("toy-bundle", "candidate", False, False, False)
    accepted_key = ("toy-bundle", False, False)
    candidate_cache = {candidate_key: (original, report.compilation_id, "toy")} if cached else {}
    accepted_cache = {accepted_key: (original, "toy")} if cached else {}
    monkeypatch.setattr(store_tests, "_candidate_snapshots", candidate_cache)
    monkeypatch.setattr(store_tests, "_accepted_snapshots", accepted_cache)
    monkeypatch.setattr(store_tests, "_report_counts", lambda _: {"reports": 0})
    monkeypatch.setattr(
        store_tests, "_build_report_candidate", lambda *_, **__: (compilation, report, ())
    )
    if helper == "accepted":
        monkeypatch.setattr(
            store_tests, "_report_candidate", lambda *_, **__: (compilation, report, ())
        )

    def parse(_):
        checked_boundary()
        return report

    monkeypatch.setattr(CompiledAssessmentReport, "model_validate_json", parse)

    class Session:
        def __init__(self, _):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, *_):
            return SimpleNamespace(document_json="toy")

    monkeypatch.setattr(orm, "Session", Session)
    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    call = store_tests._report_candidate if helper == "candidate" else store_tests._accepted_report
    if fail_backup:
        with pytest.raises(OSError, match="snapshot interruption"):
            call(case)
    elif helper == "candidate" and cached:
        with pytest.raises(ValueError, match="native load refusal"):
            call(case)
    else:
        result = call(case)
        assert (result[1] if helper == "candidate" else result) is report
    assert len(connections) == 2
    assert all(connection.closed for connection in connections)
    assert original.read_bytes() == before
    with closing(original_connect(database)) as connection:
        assert connection.execute("SELECT value FROM original").fetchall() == [("unchanged",)]
    if fail_backup:
        assert len(candidate_cache) == (1 if cached else 0)
        assert len(accepted_cache) == (1 if cached else 0)
