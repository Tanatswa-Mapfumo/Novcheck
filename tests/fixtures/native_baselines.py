"""Verified native SQLite adapter; cache membership never grants authority."""

import fcntl
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from scripts.recovery.local_batches import execution_identity
from tests.fixtures.sqlite_baselines import (
    SnapshotIdentity,
    _timed,
    clone_snapshot,
    create_snapshot,
    load_snapshot,
)


def report_identity(case, *, recipe_digest: str, environment_digest: str) -> SnapshotIdentity:
    from novelty_harness.evidence.graph.migrations import schema_version

    scope = case.bundle.scope
    return SnapshotIdentity(
        recipe_digest=recipe_digest,
        environment_digest=environment_digest,
        schema_version=schema_version(case.repository.engine),
        assessment_id=scope.assessment_id,
        adjudication_id=scope.adjudication_id,
        context_id=scope.assessment_context_id,
        snapshot_id=scope.phase6_snapshot_id,
        authority_digest=case.bundle.bundle_digest,
    )


def _open_report_case(path: Path, expected: SnapshotIdentity):
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )
    from tests.fixtures.phase8 import ReportCase

    if expected.authority_digest is None:
        raise ValueError("native baseline requires an exact upstream bundle digest")
    # Reject schema changes before repository initialization can migrate them.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as database:
        versions = database.execute("SELECT version FROM schema_version").fetchall()
    if versions != [(expected.schema_version,)]:
        raise ValueError("cached native schema differs from the exact baseline")
    repository = SqlAlchemyEvidenceGraphRepository(path)
    try:
        bundle = repository.load_report_input_bundle(
            expected.assessment_id, adjudication_id=expected.adjudication_id
        )
        scope = bundle.scope
        actual = SnapshotIdentity(
            recipe_digest=expected.recipe_digest,
            environment_digest=expected.environment_digest,
            schema_version=expected.schema_version,
            assessment_id=scope.assessment_id,
            adjudication_id=scope.adjudication_id,
            context_id=scope.assessment_context_id,
            snapshot_id=scope.phase6_snapshot_id,
            authority_digest=bundle.bundle_digest,
        )
        if actual != expected:
            raise ValueError("native authority differs from fixture provenance")
        # The native transactional bundle loader already validated this exact
        # frozen closure; this is its actual result, not deserialized cache JSON.
        return ReportCase(repository, bundle.frozen_adjudication, bundle)
    except BaseException:
        repository.close()
        raise


def native_report_validator(expected: SnapshotIdentity):
    """Exact native bundle/frozen revalidation on a real private database."""
    if expected.authority_digest is None:
        raise ValueError("native baseline requires an exact upstream bundle digest")

    def validate(path: Path):
        case = _open_report_case(path, expected)
        try:
            return report_identity(
                case,
                recipe_digest=expected.recipe_digest,
                environment_digest=expected.environment_digest,
            )
        finally:
            case.repository.close()

    return validate


def reusable_report_case(
    cache_root, destination, *, recipe_digest, environment_digest, builder, observe=None
):
    """Reuse genuinely frozen upstream authority after the owning native gates pass.

    Builder receives a private source directory and returns a genuinely committed
    ReportCase. Keep independent construction/migration/concurrency tests on their
    original path. A cache hit always validates the copied native authority.
    """
    from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION

    # Native reuse independently binds actual current source, modes, new files,
    # interpreter and installed environment, even if a caller supplied a stale
    # recipe label. The caller labels still distinguish scenario options.
    actual_execution, _, _ = execution_identity(Path.cwd(), Path(sys.executable))
    recipe_digest = hashlib.sha256(
        json.dumps([recipe_digest, actual_execution], separators=(",", ":")).encode()
    ).hexdigest()
    environment_digest = hashlib.sha256(
        json.dumps([environment_digest, actual_execution], separators=(",", ":")).encode()
    ).hexdigest()
    key = hashlib.sha256(
        json.dumps(
            [recipe_digest, environment_digest, SCHEMA_VERSION], separators=(",", ":")
        ).encode()
    ).hexdigest()
    cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = cache_root / key
    with (cache_root / (key + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        image = directory / "image"
        if not directory.exists():
            directory.mkdir(mode=0o700)
            case = None
            try:
                with _timed("fixture_construction", observe):
                    case = builder(directory / "source")
                expected = report_identity(
                    case, recipe_digest=recipe_digest, environment_digest=environment_digest
                )
            finally:
                if case is not None:
                    with _timed("fixture_teardown", observe):
                        case.repository.close()
            del case
            source = directory / "source" / "asm_research" / "phase5" / "evidence_graph.sqlite3"
            baseline = create_snapshot(
                source,
                image,
                identity=expected,
                validate=native_report_validator(expected),
                observe=observe,
            )
        else:
            # Missing ready metadata is an interrupted/failed cache, never a hit.
            with (image / "ready.json").open(encoding="utf-8") as stream:
                stored = json.load(stream)
            expected = SnapshotIdentity(**stored["identity"])
            if (
                expected.recipe_digest != recipe_digest
                or expected.environment_digest != environment_digest
                or expected.schema_version != SCHEMA_VERSION
            ):
                raise ValueError("cache source/environment/schema provenance changed")
            baseline = load_snapshot(image, expected_identity=expected)
            if observe is not None:
                observe({"stage": "cache_hit", "seconds": 0.0, "outcome": "PASSED"})
        loaded = []

        def validate_private(path):
            case = _open_report_case(path, expected)
            loaded.append(case)
            return report_identity(
                case, recipe_digest=recipe_digest, environment_digest=environment_digest
            )

        try:
            clone_snapshot(
                baseline,
                destination,
                expected_identity=expected,
                validate=validate_private,
                observe=observe,
            )
            return loaded.pop()
        except BaseException:
            for case in loaded:
                case.repository.close()
            raise


VERIFIED_PROJECTION_OWNERS = frozenset(
    {
        "tests.unit.reporting.test_obligations",
        "tests.unit.reporting.test_uncertainty",
    }
)


def fixture_route(owner, mode):
    """Keep construction/mutation/migration owners on independent setup."""
    if mode not in ("original", "cached"):
        raise ValueError("unknown fixture mode")
    return mode if owner in VERIFIED_PROJECTION_OWNERS else "original"


def owned_report_case(owner, destination, *, mode, cache_root, observe=None):
    """Reuse only the measured upstream recipe, always on a private database.

    The original route remains available for exact paired regression measurements.
    Explicit observation clocks belong to this new synthetic recipe; historical
    records and independent construction owners retain their original inputs.
    """
    from tests.fixtures.phase8 import make_report_case
    from tests.fixtures.recorded_clock import recorded_observation_clock
    from tests.integration.test_phase6_evidence_pipeline import NOW

    route = fixture_route(owner, mode)
    if owner not in VERIFIED_PROJECTION_OWNERS:
        return make_report_case(destination, observe=observe)

    def build(path):
        with recorded_observation_clock(NOW) as clock:
            return make_report_case(path, observe=observe, observation_clock=clock)

    if route == "original":
        with _timed("fixture_construction", observe):
            return build(destination)
    recipe = hashlib.sha256(
        json.dumps(
            {
                "recipe_version": "verified-projection-upstream-v1",
                "synthetic_observation_clock": NOW.isoformat(),
                "unassessable": False,
                "clock_controls": "explicit-provider-normalization-and-utc-defaults-v1",
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    environment, _, _ = execution_identity(Path.cwd(), Path(sys.executable))
    return reusable_report_case(
        cache_root,
        destination / "evidence_graph.sqlite3",
        recipe_digest=recipe,
        environment_digest=environment,
        builder=build,
        observe=observe,
    )
