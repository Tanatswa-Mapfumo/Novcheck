"""Test-only coherent SQLite images; membership never certifies native authority.

Callers must supply a real repository validator before using this for native
fixtures. No production repository, model or validation boundary is cached.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SnapshotIdentity:
    recipe_digest: str
    environment_digest: str
    schema_version: int
    assessment_id: str
    adjudication_id: str
    context_id: str
    snapshot_id: str
    authority_digest: str | None = None

    def __post_init__(self):
        digests = (self.recipe_digest, self.environment_digest)
        if self.authority_digest is not None:
            digests += (self.authority_digest,)
        for value in digests:
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("identity requires lowercase SHA-256 digests")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("schema version must be a positive integer")
        for value in (self.assessment_id, self.adjudication_id, self.context_id, self.snapshot_id):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError("exact nonblank native locators required")


@dataclass(frozen=True)
class SQLiteBaseline:
    database_path: Path
    identity: SnapshotIdentity
    sha256: str
    size_bytes: int


Validator = Callable[[Path], SnapshotIdentity]
Observer = Callable[[dict], None]


@contextmanager
def _timed(stage: str, observe: Observer | None):
    started = time.perf_counter()
    outcome = "FAILED"
    try:
        yield
        outcome = "PASSED"
    finally:
        if observe is not None:
            observe({"stage": stage, "seconds": time.perf_counter() - started, "outcome": outcome})


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sync_directory(directory: Path):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exclusive_json(path: Path, value: dict):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _closed_image(path: Path):
    # Baselines must be independent closed images, never a raw live-WAL copy.
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise ValueError("baseline has a journal sidecar")
    if path.is_symlink() or not path.is_file():
        raise ValueError("baseline must be a regular independent file")


def _coherent_backup(source: Path, destination: Path):
    if source.is_symlink() or not source.is_file():
        raise ValueError("source must be an existing regular SQLite database")
    # Exclusive reservation avoids overwriting any existing database or evidence.
    with destination.open("xb"):
        pass
    read = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    write = sqlite3.connect(destination, timeout=5)
    deadline = time.monotonic() + 30

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup did not complete within 30 seconds")

    try:
        read.backup(write, pages=256, progress=progress, sleep=0.01)
        # A backup from WAL may retain WAL mode in its header. Normalize only the
        # private snapshot, close/checkpoint it, and never touch source mode.
        write.execute("PRAGMA journal_mode=DELETE")
        if write.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite snapshot integrity failure")
    finally:
        write.close()
        read.close()
    _closed_image(destination)


def _validate(
    path: Path, identity: SnapshotIdentity, validate: Validator, observe: Observer | None
):
    before = file_digest(path)
    with _timed("native_validation", observe):
        actual = validate(path)
        if type(actual) is not SnapshotIdentity or actual != identity:
            raise ValueError("validator returned foreign schema, provenance or native scope")
    _closed_image(path)
    if file_digest(path) != before:
        raise ValueError("read validation mutated the fixture image")


def create_snapshot(
    source: Path,
    directory: Path,
    *,
    identity: SnapshotIdentity,
    validate: Validator,
    observe: Observer | None = None,
) -> SQLiteBaseline:
    """Publish once after coherent backup and mandatory validation.

    Failed/interrupted directories remain diagnostic evidence but have no ready
    manifest and cannot be reused. Use a new directory for a subsequent build.
    """
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    database = directory / "baseline.sqlite"
    with _timed("publication", observe):
        with _timed("sqlite_backup", observe):
            _coherent_backup(source, database)
        _validate(database, identity, validate, observe)
        result = SQLiteBaseline(database, identity, file_digest(database), database.stat().st_size)
        database.chmod(0o400)
        with database.open("rb") as stream:
            os.fsync(stream.fileno())
        pending = directory / "manifest.pending.json"
        _exclusive_json(
            pending,
            {
                "format": "novcheck-test-sqlite-baseline-v1",
                "identity": asdict(identity),
                "database": database.name,
                "sha256": result.sha256,
                "size_bytes": result.size_bytes,
            },
        )
        # The directory was exclusively created and is private; ready appears last.
        pending.rename(directory / "ready.json")
        (directory / "ready.json").chmod(0o400)
        _sync_directory(directory)
    return result


def load_snapshot(directory: Path, *, expected_identity: SnapshotIdentity) -> SQLiteBaseline:
    """Check stored bytes/provenance; cloning still requires native validation."""
    with (directory / "ready.json").open(encoding="utf-8") as stream:
        value = json.load(stream, object_pairs_hook=_unique_mapping)
    if set(value) != {"format", "identity", "database", "sha256", "size_bytes"}:
        raise ValueError("invalid manifest fields")
    if (
        value["format"] != "novcheck-test-sqlite-baseline-v1"
        or value["database"] != "baseline.sqlite"
    ):
        raise ValueError("unsupported or foreign baseline manifest")
    actual = SnapshotIdentity(**value["identity"])
    if actual != expected_identity:
        raise ValueError("baseline identity mismatch")
    database = directory / "baseline.sqlite"
    _closed_image(database)
    if type(value["size_bytes"]) is not int or database.stat().st_size != value["size_bytes"]:
        raise ValueError("baseline size mismatch")
    if file_digest(database) != value["sha256"]:
        raise ValueError("baseline checksum mismatch")
    return SQLiteBaseline(database, actual, value["sha256"], value["size_bytes"])


def clone_snapshot(
    baseline: SQLiteBaseline,
    destination: Path,
    *,
    expected_identity: SnapshotIdentity,
    validate: Validator,
    observe: Observer | None = None,
) -> Path:
    """Private writable byte copy, independently natively revalidated on each use."""
    with _timed("cache_validation", observe):
        current = load_snapshot(baseline.database_path.parent, expected_identity=expected_identity)
        if current != baseline:
            raise ValueError("baseline handle differs from published manifest")
    reserved = False
    try:
        with _timed("database_copy", observe):
            with destination.open("xb") as output:
                reserved = True
                destination.chmod(0o600)
                with current.database_path.open("rb") as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            if file_digest(destination) != current.sha256:
                raise ValueError("private copy checksum mismatch")
            if (
                load_snapshot(current.database_path.parent, expected_identity=expected_identity)
                != current
            ):
                raise ValueError("baseline changed during copying")
        _validate(destination, expected_identity, validate, observe)
        return destination
    except BaseException:
        # Only our exclusively reserved disposable copy is removed, never source
        # data, forensic evidence, ready baselines or a caller's existing file.
        if reserved:
            for suffix in ("", "-wal", "-shm", "-journal"):
                Path(str(destination) + suffix).unlink(missing_ok=True)
        raise
