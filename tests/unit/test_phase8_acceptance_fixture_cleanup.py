"""Acceptance-copy lifetime controls; toy SQLite confers no report authority."""

from types import SimpleNamespace

import pytest

from tests.integration import test_phase8_slice as slice_tests
from tests.unit.evidence.graph import test_report_store as store_tests
from tests.unit.test_phase8_export_fixture_cleanup import (
    install_observers,
    open_source_bytes,
    source_case,
)


def acceptance_clone(tmp_path, monkeypatch, **failures):
    source, _, before = source_case(tmp_path)
    source.bundle = SimpleNamespace(
        scope=SimpleNamespace(assessment_id=source.frozen.assessment_id)
    )
    connections, repositories = install_observers(monkeypatch, source, **failures)
    monkeypatch.setattr(
        store_tests,
        "SqlAlchemyEvidenceGraphRepository",
        slice_tests.SqlAlchemyEvidenceGraphRepository,
    )
    private = tmp_path / "clone"
    private.mkdir()
    fixture = store_tests.acceptance_case.__wrapped__(source, private)
    return fixture, private, source, before, connections, repositories


@pytest.mark.parametrize("failure", ["frozen", "bundle"])
def test_acceptance_clone_closes_copy_connections_on_load_refusal(tmp_path, monkeypatch, failure):
    fixture, private, source, before, connections, repositories = acceptance_clone(
        tmp_path, monkeypatch, fail_load=failure
    )
    with pytest.raises(ValueError, match="load refusal"):
        next(fixture)
    assert repositories[0].closed
    assert len(connections) == 2 and all(c.closed for c in connections)
    assert not list(private.glob("report-authority.db*"))
    assert open_source_bytes(source) == before


def test_acceptance_clone_closes_connections_before_yield(tmp_path, monkeypatch):
    fixture, private, source, before, connections, repositories = acceptance_clone(
        tmp_path, monkeypatch
    )
    try:
        case = next(fixture)
        assert case.repository is repositories[0]
        assert len(connections) == 2 and all(c.closed for c in connections)
    finally:
        fixture.close()
    assert repositories[0].closed
    assert not list(private.glob("report-authority.db*"))
    assert open_source_bytes(source) == before


def test_acceptance_clone_removes_interrupted_copy(tmp_path, monkeypatch):
    fixture, private, source, before, connections, repositories = acceptance_clone(
        tmp_path, monkeypatch, fail_backup=True
    )
    with pytest.raises(OSError, match="interrupted coherent copy"):
        next(fixture)
    assert not repositories
    assert len(connections) == 2 and all(c.closed for c in connections)
    assert not list(private.glob("report-authority.db*"))
    assert open_source_bytes(source) == before


def test_acceptance_clone_removes_copy_on_constructor_failure(tmp_path, monkeypatch):
    fixture, private, source, before, connections, repositories = acceptance_clone(
        tmp_path, monkeypatch
    )

    def refuse_repository(_path):
        raise OSError("recorded repository construction failure")

    monkeypatch.setattr(store_tests, "SqlAlchemyEvidenceGraphRepository", refuse_repository)
    with pytest.raises(OSError, match="construction failure"):
        next(fixture)
    assert not repositories
    assert len(connections) == 2 and all(c.closed for c in connections)
    assert not list(private.glob("report-authority.db*"))
    assert open_source_bytes(source) == before


def test_acceptance_clone_removes_sidecars_after_interruption(tmp_path, monkeypatch):
    fixture, private, source, before, _, repositories = acceptance_clone(tmp_path, monkeypatch)
    next(fixture)
    for suffix in ("-journal", "-wal", "-shm"):
        (private / ("report-authority.db" + suffix)).write_bytes(b"private sidecar")
    with pytest.raises(KeyboardInterrupt):
        fixture.throw(KeyboardInterrupt())
    assert repositories[0].closed
    assert not list(private.glob("report-authority.db*"))
    assert open_source_bytes(source) == before


def test_acceptance_clone_removes_copy_when_disposal_raises(tmp_path, monkeypatch):
    fixture, private, source, before, _, repositories = acceptance_clone(
        tmp_path, monkeypatch, fail_close=True
    )
    next(fixture)
    with pytest.raises(OSError, match="disposal failure"):
        fixture.close()
    assert repositories[0].closed
    assert not list(private.glob("report-authority.db*"))
    assert open_source_bytes(source) == before


acceptance_source = store_tests.acceptance_source
acceptance_case = store_tests.acceptance_case


def test_acceptance_clone_preserves_native_frozen_bundle_and_source(
    acceptance_source, acceptance_case
):
    import hashlib
    from pathlib import Path

    from novelty_harness.runtime.tracing.hashing import canonical_hash

    source_path = Path(acceptance_source.repository.engine.url.database)

    def source_digest():
        digest = hashlib.sha256()
        with source_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                digest.update(chunk)
        return digest.hexdigest()

    before = source_digest()
    source_rows = store_tests._upstream_rows(acceptance_source.repository)
    frozen = acceptance_case.repository.load_frozen_adjudication(
        acceptance_source.frozen.assessment_id,
        adjudication_id=acceptance_source.frozen.adjudication_id,
    )
    assert frozen == acceptance_source.frozen == acceptance_case.frozen
    bundle = acceptance_case.repository.load_report_input_bundle(
        frozen.assessment_id, adjudication_id=frozen.adjudication_id
    )
    assert bundle.scope == acceptance_source.bundle.scope
    assert bundle.bundle_digest == acceptance_source.bundle.bundle_digest
    assert canonical_hash(bundle.model_dump(mode="json")) == canonical_hash(
        acceptance_source.bundle.model_dump(mode="json")
    )
    assert store_tests._upstream_rows(acceptance_case.repository) == source_rows
    assert source_digest() == before
