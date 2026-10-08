"""Real closure gates for cache routing; execute alone under the native guard.

These construct actual Phase6/7 authority. They are pending capacity profiling,
not part of the small mechanical controls and never run implicitly during setup.
"""

import sqlite3
from dataclasses import replace

import pytest

from tests.fixtures.native_baselines import native_report_validator, report_identity
from tests.fixtures.phase8 import make_report_case
from tests.fixtures.sqlite_baselines import clone_snapshot, create_snapshot, file_digest


@pytest.fixture
def baseline(tmp_path):
    source = tmp_path / "source"
    case = make_report_case(source)
    try:
        identity = report_identity(case, recipe_digest="a" * 64, environment_digest="b" * 64)
    finally:
        case.repository.close()
    del case
    database = source / "asm_research" / "phase5" / "evidence_graph.sqlite3"
    return create_snapshot(
        database,
        tmp_path / "baseline",
        identity=identity,
        validate=native_report_validator(identity),
    )


def test_native_clone_reopen_preserves_exact_closure_and_isolation(baseline, tmp_path):
    expected = baseline.identity
    validate = native_report_validator(expected)
    first = clone_snapshot(
        baseline, tmp_path / "first.db", expected_identity=expected, validate=validate
    )
    original = file_digest(baseline.database_path)
    # Storage-corruption attack retained; a cache hit cannot rescue revoked closure.
    with sqlite3.connect(first) as database:
        database.execute("PRAGMA foreign_keys=OFF")
        database.execute("DELETE FROM phase7_artifacts WHERE kind='GATE_C'")
    from novelty_harness.reporting.repository import ReportAuthorityError

    with pytest.raises(ReportAuthorityError):
        validate(first)
    second = clone_snapshot(
        baseline, tmp_path / "second.db", expected_identity=expected, validate=validate
    )
    assert validate(second) == expected
    assert file_digest(baseline.database_path) == original
    assert first.stat().st_ino != second.stat().st_ino


def test_native_schema_reuse_cannot_silently_migrate(baseline, tmp_path):
    expected = baseline.identity
    private = clone_snapshot(
        baseline,
        tmp_path / "copy.db",
        expected_identity=expected,
        validate=native_report_validator(expected),
    )
    with sqlite3.connect(private) as database:
        database.execute("UPDATE schema_version SET version=8")
    with pytest.raises(ValueError, match="schema"):
        native_report_validator(expected)(private)
    with sqlite3.connect(private) as database:
        assert database.execute("SELECT version FROM schema_version").fetchall() == [(8,)]


def test_native_scope_and_bundle_digest_are_revalidated(baseline, tmp_path):
    expected = baseline.identity
    private = clone_snapshot(
        baseline,
        tmp_path / "copy.db",
        expected_identity=expected,
        validate=native_report_validator(expected),
    )
    with pytest.raises(ValueError, match="authority"):
        native_report_validator(replace(expected, authority_digest="c" * 64))(private)
    with pytest.raises(ValueError, match="authority"):
        native_report_validator(replace(expected, context_id="foreign"))(private)


def test_reusable_native_recipe_builds_once_and_revalidates_each_private_copy(tmp_path):
    from tests.fixtures.native_baselines import reusable_report_case

    builds = []
    events = []

    def build(path):
        builds.append(path)
        return make_report_case(path)

    first = reusable_report_case(
        tmp_path / "cache",
        tmp_path / "one.db",
        recipe_digest="a" * 64,
        environment_digest="b" * 64,
        builder=build,
        observe=events.append,
    )
    first_digest = first.bundle.bundle_digest
    first.repository.close()
    del first
    second = reusable_report_case(
        tmp_path / "cache",
        tmp_path / "two.db",
        recipe_digest="a" * 64,
        environment_digest="b" * 64,
        builder=build,
        observe=events.append,
    )
    try:
        assert second.bundle.bundle_digest == first_digest
        assert len(builds) == 1
        stages = [event["stage"] for event in events]
        assert stages.count("fixture_construction") == 1
        assert stages.count("database_copy") == 2
        assert stages.count("native_validation") == 3  # publication and both clones
        assert stages.count("cache_hit") == 1
    finally:
        second.repository.close()
