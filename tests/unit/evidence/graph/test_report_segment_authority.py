import pytest
from sqlalchemy import event, text

from tests.unit.evidence.graph.test_report_store import (
    _accepted_count,
    _report_candidate,
    _upstream_rows,
)
from tests.unit.evidence.graph.test_report_store import acceptance_case as _acceptance_case
from tests.unit.evidence.graph.test_report_store import acceptance_source as _acceptance_source

acceptance_case = _acceptance_case
acceptance_source = _acceptance_source

"""Schema v10 authority remains the complete native report, never segment hashes."""


def test_segmented_acceptance_load_replay_and_export_preserve_native_report(
    acceptance_case, monkeypatch, tmp_path
):
    from novelty_harness.application.phase8_exports import export_compiled_report
    from novelty_harness.evidence.graph import report_store
    from novelty_harness.evidence.graph.report_document import DocumentManifest
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
    from novelty_harness.runtime.tracing.hashing import canonical_json

    case = acceptance_case
    compilation, proposed, artifacts = _report_candidate(case)
    del artifacts
    before = _upstream_rows(case.repository)
    monkeypatch.setattr(report_store, "_inline_document_capacity", lambda *_: 0)
    assert (
        case.repository.accept_compiled_report(compilation.compilation_id, proposed)
        == proposed.report_id
    )
    with case.repository.engine.connect() as connection:
        encoded = connection.execute(
            text("SELECT document_json FROM compiled_reports WHERE report_id=:id"),
            {"id": proposed.report_id},
        ).scalar_one()
        manifest = DocumentManifest.model_validate_json(encoded)
        chunks = connection.execute(
            text("SELECT COUNT(*) FROM compiled_report_document_chunks WHERE report_id=:id"),
            {"id": proposed.report_id},
        ).scalar_one()
    assert manifest.report_id == proposed.report_id
    assert chunks == manifest.chunk_count > 1
    loaded = case.repository.load_compiled_report(
        compilation.scope.assessment_id, report_id=proposed.report_id
    )
    assert loaded == proposed.model_copy(update={"accepted_at": loaded.accepted_at})
    assert manifest.byte_length == len(canonical_json(loaded).encode("utf-8"))
    assert _accepted_count(case, compilation) == (1, 1)
    del loaded
    assert (
        case.repository.accept_compiled_report(compilation.compilation_id, proposed)
        == proposed.report_id
    )
    assert _accepted_count(case, compilation) == (1, 1)
    from novelty_harness.reporting.models import ReportProposalError
    from novelty_harness.reporting.repository import ReportAuthorityError
    from tests.unit.evidence.graph.test_report_store import _rehash_report

    assert proposed.ir.uncertainty_summary
    assert proposed.ir.compact_summary is not None
    changed_ir = proposed.ir.model_copy(
        update={
            "uncertainty_summary": (),
            "compact_summary": proposed.ir.compact_summary.model_copy(update={"uncertainty": ()}),
        }
    )
    forged = _rehash_report(proposed.model_copy(update={"ir": changed_ir}))
    with pytest.raises(
        ReportAuthorityError, match="closure failed authoritative validation"
    ) as refusal:
        case.repository.accept_compiled_report(compilation.compilation_id, forged)
    assert isinstance(refusal.value.__cause__, ReportProposalError)
    assert str(refusal.value.__cause__) == (
        "IR differs from exact frozen projections, actual proofs or deterministic summary"
    )
    del refusal, changed_ir, forged
    assert _accepted_count(case, compilation) == (1, 1)
    # Existing renderer/authority owners independently retain exact public parity.
    paths = export_compiled_report(
        compilation.scope.assessment_id,
        report_id=proposed.report_id,
        repository=case.repository,
        artifact_writer=RunArtifactWriter(tmp_path / "segmented-exports"),
    )
    assert len(paths) == 3 and all(path.is_file() and path.stat().st_size > 0 for path in paths)
    assert _upstream_rows(case.repository) == before


def test_segmented_publication_failure_rolls_back_every_row(acceptance_case, monkeypatch):
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph import report_store
    from novelty_harness.evidence.graph.report_models import (
        CompiledReportChunkRow,
        ReportArtifactRow,
        ReportDependencyRow,
    )

    case = acceptance_case
    compilation, proposed, artifacts = _report_candidate(case)
    del artifacts
    before = _upstream_rows(case.repository)
    monkeypatch.setattr(report_store, "_inline_document_capacity", lambda *_: 0)
    for selected in (CompiledReportChunkRow, ReportDependencyRow, ReportArtifactRow):

        def fail(session, _context, _instances):
            if any(isinstance(row, selected) for row in session.new):
                raise RuntimeError("injected segmented publication failure")

        event.listen(Session, "before_flush", fail)
        try:
            with pytest.raises(RuntimeError, match="injected segmented publication failure"):
                case.repository.accept_compiled_report(compilation.compilation_id, proposed)
        finally:
            event.remove(Session, "before_flush", fail)
        assert _accepted_count(case, compilation) == (0, 0)
        with case.repository.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM compiled_report_document_chunks")
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(text("SELECT COUNT(*) FROM report_dependencies")).scalar_one()
                == 0
            )
        assert _upstream_rows(case.repository) == before


def test_segment_corruption_and_rehashed_semantics_never_authorize_native_report(
    acceptance_case, monkeypatch
):
    from dataclasses import replace

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph import report_store
    from novelty_harness.evidence.graph.report_document import (
        DocumentChunk,
        document_manifest,
        encode_document,
    )
    from novelty_harness.evidence.graph.report_models import (
        CompiledReportChunkRow,
        CompiledReportRow,
    )
    from novelty_harness.reporting.repository import ReportAuthorityError
    from novelty_harness.runtime.tracing.hashing import canonical_json

    case = acceptance_case
    compilation, proposed, artifacts = _report_candidate(case)
    del artifacts
    before = _upstream_rows(case.repository)
    monkeypatch.setattr(report_store, "_inline_document_capacity", lambda *_: 0)
    case.repository.accept_compiled_report(compilation.compilation_id, proposed)
    with Session(case.repository.engine) as session:
        header = session.get(CompiledReportRow, proposed.report_id)
        original_manifest = header.document_json
        originals = [
            DocumentChunk(
                row.report_id,
                row.ordinal,
                row.codec,
                row.byte_length,
                row.content_digest,
                row.payload,
            )
            for row in session.scalars(
                select(CompiledReportChunkRow)
                .where(CompiledReportChunkRow.report_id == proposed.report_id)
                .order_by(CompiledReportChunkRow.ordinal)
            )
        ]
    assert len(originals) > 1

    def restore():
        with case.repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM compiled_report_document_chunks WHERE report_id=:id"),
                {"id": proposed.report_id},
            )
            connection.execute(
                text("UPDATE compiled_reports SET document_json=:wire WHERE report_id=:id"),
                {"wire": original_manifest, "id": proposed.report_id},
            )
        with Session(case.repository.engine) as session:
            session.add_all([CompiledReportChunkRow(**vars(chunk)) for chunk in originals])
            session.commit()

    for attack in ("missing", "extra", "order", "payload", "codec", "digest"):
        restore()
        with case.repository.engine.begin() as connection:
            if attack == "missing":
                connection.execute(
                    text(
                        "DELETE FROM compiled_report_document_chunks "
                        "WHERE report_id=:id AND ordinal=0"
                    ),
                    {"id": proposed.report_id},
                )
            elif attack == "extra":
                item = replace(originals[-1], ordinal=len(originals))
                connection.execute(CompiledReportChunkRow.__table__.insert().values(**vars(item)))
            elif attack == "order":
                for destination, source in ((0, originals[1]), (1, originals[0])):
                    connection.execute(
                        text(
                            "UPDATE compiled_report_document_chunks "
                            "SET payload=:payload, byte_length=:length, content_digest=:digest "
                            "WHERE report_id=:id AND ordinal=:ordinal"
                        ),
                        {
                            "payload": source.payload,
                            "length": source.byte_length,
                            "digest": source.content_digest,
                            "id": proposed.report_id,
                            "ordinal": destination,
                        },
                    )
            elif attack == "payload":
                connection.execute(
                    text(
                        "UPDATE compiled_report_document_chunks SET payload=X'00' "
                        "WHERE report_id=:id AND ordinal=0"
                    ),
                    {"id": proposed.report_id},
                )
            elif attack == "codec":
                connection.execute(
                    text(
                        "UPDATE compiled_report_document_chunks SET codec='unknown' "
                        "WHERE report_id=:id AND ordinal=0"
                    ),
                    {"id": proposed.report_id},
                )
            elif attack == "digest":
                connection.execute(
                    text(
                        "UPDATE compiled_report_document_chunks SET content_digest=:digest "
                        "WHERE report_id=:id AND ordinal=0"
                    ),
                    {"id": proposed.report_id, "digest": "0" * 64},
                )
        with pytest.raises(
            ReportAuthorityError, match="report read failed authoritative validation"
        ) as refusal:
            case.repository.load_compiled_report(
                compilation.scope.assessment_id, report_id=proposed.report_id
            )
        assert isinstance(refusal.value.__cause__, ValueError)
        assert "segmented report" in str(refusal.value.__cause__)
        del refusal
        assert _accepted_count(case, compilation) == (1, 1)
        assert _upstream_rows(case.repository) == before
    restore()
    loaded = case.repository.load_compiled_report(
        compilation.scope.assessment_id, report_id=proposed.report_id
    )
    assert loaded == proposed.model_copy(update={"accepted_at": loaded.accepted_at})
    # Canonical and consistently compressed metadata cannot rescue a changed logical header.
    changed = loaded.model_copy(update={"report_id": "rpt_foreign"})
    wire = canonical_json(changed)
    manifest = document_manifest(proposed.report_id, wire)
    with case.repository.engine.begin() as connection:
        connection.execute(
            text("DELETE FROM compiled_report_document_chunks WHERE report_id=:id"),
            {"id": proposed.report_id},
        )
        connection.execute(
            text("UPDATE compiled_reports SET document_json=:wire WHERE report_id=:id"),
            {"wire": canonical_json(manifest), "id": proposed.report_id},
        )
    with Session(case.repository.engine) as session:
        session.add_all(
            [
                CompiledReportChunkRow(**vars(chunk))
                for chunk in encode_document(proposed.report_id, wire)
            ]
        )
        session.commit()
    with pytest.raises(ReportAuthorityError, match="header columns, identity or scope differ"):
        case.repository.load_compiled_report(
            compilation.scope.assessment_id, report_id=proposed.report_id
        )
    restore()
    assert (
        case.repository.load_compiled_report(
            compilation.scope.assessment_id, report_id=proposed.report_id
        )
        == loaded
    )
    assert _upstream_rows(case.repository) == before


def test_v9_inline_accepted_bytes_survive_v10_migration_and_native_reload(acceptance_case):
    from novelty_harness.evidence.graph.migrations import ensure_schema, schema_version
    from novelty_harness.runtime.tracing.hashing import canonical_json

    case = acceptance_case
    compilation, proposed, artifacts = _report_candidate(case)
    del artifacts
    before = _upstream_rows(case.repository)
    # This native fixture fits the actual unchanged SQLite limit.
    case.repository.accept_compiled_report(compilation.compilation_id, proposed)
    with case.repository.engine.connect() as connection:
        wire = connection.execute(
            text("SELECT document_json FROM compiled_reports WHERE report_id=:id"),
            {"id": proposed.report_id},
        ).scalar_one()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM compiled_report_document_chunks")
            ).scalar_one()
            == 0
        )
    with case.repository.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE compiled_report_document_chunks")
        connection.execute(text("UPDATE schema_version SET version=9"))
    assert ensure_schema(case.repository.engine) == 10
    assert schema_version(case.repository.engine) == 10
    with case.repository.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT document_json FROM compiled_reports WHERE report_id=:id"),
                {"id": proposed.report_id},
            ).scalar_one()
            == wire
        )
    loaded = case.repository.load_compiled_report(
        compilation.scope.assessment_id, report_id=proposed.report_id
    )
    assert canonical_json(loaded) == wire
    assert loaded == proposed.model_copy(update={"accepted_at": loaded.accepted_at})
    assert _upstream_rows(case.repository) == before
