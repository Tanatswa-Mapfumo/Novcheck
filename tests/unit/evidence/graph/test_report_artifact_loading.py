"""Strict row decoding and bounded memory; synthetic rows confer no authority."""

import gc
import json
import tracemalloc

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from novelty_harness.evidence.graph.report_models import ReportArtifactRow
from novelty_harness.reporting.artifacts import (
    ReportArtifactKind,
    ReportStatusEvent,
    make_report_artifact,
    report_status_event_id,
)
from novelty_harness.reporting.repository import ReportAuthorityError
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json
from tests.fixtures.phase8 import OBSERVED
from tests.unit.reporting.test_contracts import _compilation


@pytest.fixture
def row_database(tmp_path):
    # Only the relational row mechanics are exercised here. Multiple initial
    # status documents deliberately do not form an authoritative attempt.
    compilation = _compilation()
    engine = create_engine(f"sqlite:///{tmp_path / 'rows.sqlite'}")
    ReportArtifactRow.__table__.create(engine)
    expected = []
    with engine.begin() as connection:
        for index in range(24):
            status = ReportStatusEvent(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                event_id="pending",
                next_state="STARTED",
                reason=f"row {index:02d}: " + "x" * 131072,
                observed_at=OBSERVED,
            )
            status = status.model_copy(update={"event_id": report_status_event_id(status)})
            artifact = make_report_artifact(
                compilation, ReportArtifactKind.STATUS, status, method_version="p8-bundle-v1"
            )
            wire = canonical_json(artifact)
            expected.append((artifact.artifact_id, canonical_hash(artifact), len(wire)))
            connection.execute(
                ReportArtifactRow.__table__.insert().values(
                    artifact_id=artifact.artifact_id,
                    compilation_id=artifact.compilation_id,
                    assessment_id=artifact.scope.assessment_id,
                    adjudication_id=artifact.scope.adjudication_id,
                    context_id=artifact.scope.assessment_context_id,
                    snapshot_id=artifact.scope.phase6_snapshot_id,
                    kind=artifact.kind.value,
                    question_id=artifact.question_id,
                    cluster_origin_id=artifact.cluster_origin_id,
                    execution_artifact_id=artifact.execution_ref,
                    document_json=wire,
                )
            )
    try:
        yield engine, compilation.compilation_id, sorted(expected)
    finally:
        engine.dispose()


def test_row_decode_does_not_retain_all_serialized_documents(row_database, record_property):
    from novelty_harness.evidence.graph.report_store import _read_report_artifact_documents

    engine, locator, expected = row_database
    gc.collect()
    with Session(engine) as session:
        session.execute(text("BEGIN"))
        tracemalloc.start()
        try:
            artifacts = _read_report_artifact_documents(session, locator)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    # Parsed text must remain live. Allow one row's encoding/parse temporaries
    # and structural overhead, but not another full serialized collection.
    document_bytes = sum(size for _, _, size in expected)
    record_property("decode_peak_bytes", peak)
    record_property("document_bytes", document_bytes)
    assert peak < document_bytes * 1.75, (peak, document_bytes)
    assert [(a.artifact_id, canonical_hash(a)) for a in artifacts] == [
        (identity, digest) for identity, digest, _ in expected
    ]


@pytest.mark.parametrize(
    "column,value",
    [
        ("artifact_id", "p8artifact_foreign"),
        ("assessment_id", "asm_foreign"),
        ("adjudication_id", "p7frozen_foreign"),
        ("context_id", "p7ctx_foreign"),
        ("snapshot_id", "p6snap_foreign"),
        ("kind", "FALLBACK"),
        ("question_id", 1),
        ("cluster_origin_id", "foreign-cluster"),
        ("execution_artifact_id", "foreign-execution"),
    ],
)
def test_row_decode_preserves_exact_column_checks(row_database, column, value):
    from novelty_harness.evidence.graph.report_store import _read_report_artifact_documents

    engine, locator, expected = row_database
    with engine.begin() as connection:
        connection.execute(
            text(f"UPDATE report_artifacts SET {column}=:value WHERE artifact_id=:identity"),
            {"value": value, "identity": expected[-1][0]},
        )
    with Session(engine) as session:
        with pytest.raises(ReportAuthorityError, match="columns or content differ"):
            _read_report_artifact_documents(session, locator)


def test_row_decode_rejects_noncanonical_bytes(row_database):
    from novelty_harness.evidence.graph.report_store import _read_report_artifact_documents

    engine, locator, expected = row_database
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE report_artifacts SET document_json=document_json || ' ' "
                "WHERE artifact_id=:identity"
            ),
            {"identity": expected[-1][0]},
        )
    with Session(engine) as session:
        with pytest.raises(ReportAuthorityError, match="columns or content differ"):
            _read_report_artifact_documents(session, locator)


def test_row_decode_keeps_strict_schema_and_empty_selection(row_database):
    from novelty_harness.evidence.graph.report_store import _read_report_artifact_documents

    engine, locator, expected = row_database
    with Session(engine) as session:
        assert _read_report_artifact_documents(session, "p8run_absent") == ()
    with engine.begin() as connection:
        identity = expected[-1][0]
        wire = connection.execute(
            text("SELECT document_json FROM report_artifacts WHERE artifact_id=:identity"),
            {"identity": identity},
        ).scalar_one()
        payload = json.loads(wire)
        payload["trusted"] = True
        connection.execute(
            text("UPDATE report_artifacts SET document_json=:wire WHERE artifact_id=:identity"),
            {"wire": json.dumps(payload), "identity": identity},
        )
    with Session(engine) as session:
        with pytest.raises(ValidationError, match="Extra inputs"):
            _read_report_artifact_documents(session, locator)
