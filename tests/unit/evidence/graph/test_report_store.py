"""Report persistence starts with additive migration, never authority backfill."""

from contextlib import closing

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError

from novelty_harness.evidence.graph.migrations import ensure_schema, schema_version
from novelty_harness.evidence.graph.sqlalchemy_models import Base
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

REPORT_TABLES = {
    "report_compilations",
    "report_artifacts",
    "compiled_reports",
    "report_dependencies",
}


def _v8_topology(repository):
    tables = [table for table in Base.metadata.sorted_tables if table.name in REPORT_TABLES]
    Base.metadata.drop_all(repository.engine, tables=tables)
    with repository.engine.begin() as connection:
        connection.execute(text("UPDATE schema_version SET version=8"))
    assert not REPORT_TABLES & set(inspect(repository.engine).get_table_names())


def _upstream_rows(repository):
    result = {}
    with repository.engine.connect() as connection:
        for name in sorted(
            set(inspect(connection).get_table_names()) - REPORT_TABLES - {"schema_version"}
        ):
            result[name] = tuple(
                sorted(tuple(row) for row in connection.execute(text(f'SELECT * FROM "{name}"')))
            )
    return result


def _report_counts(repository):
    with repository.engine.connect() as connection:
        return {
            name: connection.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()
            for name in REPORT_TABLES
        }


def test_v8_migrates_to_empty_v9_preserving_authority(tmp_path):
    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        frozen = repository.load_frozen_adjudication(
            packet.assessment_id, adjudication_id=proposed.adjudication_id
        )
        _v8_topology(repository)
        before = _upstream_rows(repository)
        assert ensure_schema(repository.engine) == 9
        assert schema_version(repository.engine) == 9
        assert REPORT_TABLES <= set(inspect(repository.engine).get_table_names())
        assert _upstream_rows(repository) == before
        assert _report_counts(repository) == dict.fromkeys(REPORT_TABLES, 0)
        assert (
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=frozen.adjudication_id
            )
            == frozen
        )
        with repository.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        repository.close()


@pytest.mark.parametrize("populated", [False, True])
def test_v9_initialization_reopen_and_migration_rollback(tmp_path, populated):
    if populated:
        packet, repository, run, proposed = _freeze_fixture(tmp_path)
        repository.freeze_phase7_adjudication(run.run_id, proposed)
    else:
        repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "empty.db")
    database = repository.engine.url.database
    try:
        _v8_topology(repository)
        before = _upstream_rows(repository)

        def fail_before_version_commit(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("UPDATE schema_version"):
                raise RuntimeError("injected schema version failure")

        event.listen(repository.engine, "before_cursor_execute", fail_before_version_commit)
        try:
            with pytest.raises(RuntimeError, match="injected schema version failure"):
                ensure_schema(repository.engine)
        finally:
            event.remove(repository.engine, "before_cursor_execute", fail_before_version_commit)
        assert schema_version(repository.engine) == 8
        assert not REPORT_TABLES & set(inspect(repository.engine).get_table_names())
        assert _upstream_rows(repository) == before
        assert ensure_schema(repository.engine) == 9
        assert ensure_schema(repository.engine) == 9
    finally:
        repository.close()
    from pathlib import Path

    reopened = SqlAlchemyEvidenceGraphRepository(Path(database))
    try:
        assert ensure_schema(reopened.engine) == 9
        assert _report_counts(reopened) == dict.fromkeys(REPORT_TABLES, 0)
        if populated:
            assert (
                reopened.load_frozen_adjudication(
                    packet.assessment_id, adjudication_id=proposed.adjudication_id
                )
                == proposed
            )
    finally:
        reopened.close()


def test_v9_refuses_newer_and_unsafe_legacy_schema(tmp_path):
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "future.db")
    try:
        _v8_topology(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("UPDATE schema_version SET version=10"))
        before = set(inspect(repository.engine).get_table_names())
        with pytest.raises(ValueError, match="newer"):
            ensure_schema(repository.engine)
        assert set(inspect(repository.engine).get_table_names()) == before
    finally:
        repository.close()
    _, repository, _, _ = _freeze_fixture(tmp_path / "unsafe")
    try:
        _v8_topology(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("UPDATE schema_version SET version=3"))
        with pytest.raises(ValueError, match="Legacy"):
            ensure_schema(repository.engine)
        assert schema_version(repository.engine) == 3
        assert not REPORT_TABLES & set(inspect(repository.engine).get_table_names())
    finally:
        repository.close()


@pytest.mark.parametrize("field", ["assessment_id", "adjudication_id", "context_id", "snapshot_id"])
def test_v9_fk_rejects_foreign_report_scope(tmp_path, field):
    from novelty_harness.evidence.graph.report_models import ReportArtifactRow, ReportCompilationRow

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        scope = dict(
            assessment_id=packet.assessment_id,
            adjudication_id=proposed.adjudication_id,
            context_id=packet.assessment_context_id,
            snapshot_id=packet.phase6_snapshot_id,
        )
        with repository.engine.begin() as connection:
            connection.execute(
                ReportCompilationRow.__table__.insert().values(
                    compilation_id="p8run_relational",
                    compilation_key="key",
                    attempt_token="one",
                    bundle_digest="a" * 64,
                    options_digest="b" * 64,
                    configuration_digest="c" * 64,
                    document_json="{}",
                    **scope,
                )
            )
        bad_scope = {**scope, field: "foreign"}
        with pytest.raises(IntegrityError):
            with repository.engine.begin() as connection:
                connection.execute(
                    ReportArtifactRow.__table__.insert().values(
                        artifact_id="p8artifact_foreign",
                        compilation_id="p8run_relational",
                        kind="STATUS",
                        document_json="{}",
                        **bad_scope,
                    )
                )
        assert _report_counts(repository)["report_artifacts"] == 0
    finally:
        repository.close()


def test_migration_never_backfills_fixture_report(tmp_path):
    from novelty_harness.domain.adjudication import FrozenAdjudication

    # A genuine legacy caller fixture exists independently of any repository manifest.
    from tests.fixtures.phase1 import fixture_provenance
    from tests.fixtures.phase8 import OBSERVED

    fixture = FrozenAdjudication(
        assessment_id="asm_fixture",
        overall_state="UNASSESSABLE",
        as_of=OBSERVED.date(),
        frozen_at=OBSERVED,
        provenance=fixture_provenance("report-migration"),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "fixture.db")
    try:
        _v8_topology(repository)
        (tmp_path / "adjudication.json").write_text(fixture.model_dump_json())
        with repository.engine.begin() as connection:
            connection.execute(text("UPDATE schema_version SET version=7"))
        assert ensure_schema(repository.engine) == 9
        assert _report_counts(repository) == dict.fromkeys(REPORT_TABLES, 0)
        with repository.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM phase7_frozen_manifests")
                ).scalar_one()
                == 0
            )
    finally:
        repository.close()


def test_begin_uses_one_transaction_and_preserves_frozen_authority(tmp_path):
    from novelty_harness.reporting.execution import ReportCompilationConfiguration
    from novelty_harness.reporting.models import ReportOptions
    from tests.fixtures.phase8 import make_report_case

    case = make_report_case(tmp_path)
    repo = case.repository
    try:
        before = _upstream_rows(repo)
        begins = []

        def observe(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.strip().upper().startswith("BEGIN"):
                begins.append(statement.strip().upper())

        event.listen(repo.engine, "before_cursor_execute", observe)
        try:
            record = repo.begin_report_compilation(
                case.bundle.scope.assessment_id,
                adjudication_id=case.frozen.adjudication_id,
                options=ReportOptions(),
                configuration=ReportCompilationConfiguration(),
                attempt_token="one-transaction",
            )
        finally:
            event.remove(repo.engine, "before_cursor_execute", observe)
        assert begins == ["BEGIN IMMEDIATE"]
        assert _upstream_rows(repo) == before
        artifacts = repo.load_report_artifacts(record.compilation_id)
        assert len(artifacts) == 1 and artifacts[0].document.next_state == "STARTED"
        assert _report_counts(repo) == {
            "report_compilations": 1,
            "report_artifacts": 1,
            "compiled_reports": 0,
            "report_dependencies": 0,
        }
    finally:
        repo.close()


@pytest.fixture(scope="module")
def acceptance_source(tmp_path_factory):
    from tests.fixtures.phase8 import make_report_case

    case = make_report_case(tmp_path_factory.mktemp("acceptance-source"))
    try:
        yield case
    finally:
        case.repository.close()


@pytest.fixture
def acceptance_case(acceptance_source, tmp_path):
    # SQLite backup makes each attack independent while preserving genuine
    # committed Phase 6/7 authority, not a deserialized frozen caller shape.
    import sqlite3
    from contextlib import closing
    from pathlib import Path

    from tests.fixtures.phase8 import ReportCase

    destination = tmp_path / "report-authority.db"
    repository = None
    try:
        with closing(sqlite3.connect(acceptance_source.repository.engine.url.database)) as source:
            with closing(sqlite3.connect(destination)) as target:
                source.backup(target)
        repository = SqlAlchemyEvidenceGraphRepository(Path(destination))
        frozen = repository.load_frozen_adjudication(
            acceptance_source.bundle.scope.assessment_id,
            adjudication_id=acceptance_source.frozen.adjudication_id,
        )
        bundle = repository.load_report_input_bundle(
            frozen.assessment_id, adjudication_id=frozen.adjudication_id
        )
        yield ReportCase(repository, frozen, bundle)
    finally:
        try:
            if repository is not None:
                repository.close()
        finally:
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(str(destination) + suffix).unlink(missing_ok=True)


class FailedReportWriter:
    @property
    def configuration(self):
        from novelty_harness.reporting.execution import ReportPortConfiguration

        return ReportPortConfiguration(
            mode="PORT_PROTOCOL",
            implementation=type(self).__module__ + "." + type(self).__qualname__,
        )

    async def write(self, context):
        raise RuntimeError("recorded unavailable report writer")


class FaithfulInputReportPort(FailedReportWriter):
    """Recorded public-text case; no claim of live semantic accuracy."""

    def __init__(self):
        self.template = None
        self.draft = None
        self.calls = []

    async def write(self, context):
        self.calls.append("write")
        assert context.question_id == 1
        assert self.template.draft.scope == context.scope
        first = self.template.draft.blocks[0].model_copy(
            update={"text": "The proposal separates relay control from status display."}
        )
        self.draft = self.template.draft.model_copy(
            update={"blocks": (first, *self.template.draft.blocks[1:])}
        )
        return self.draft

    async def repair(self, context):
        raise AssertionError("faithful input case must not need repair")

    async def extract(self, context):
        from novelty_harness.reporting.claims import ClaimExtractionProposal, TextSpan
        from novelty_harness.reporting.verification import section_extraction
        from novelty_harness.runtime.tracing.hashing import canonical_hash

        self.calls.append("extract")
        assert context.draft == self.draft
        prototype = section_extraction(self.template)
        blocks = {b.block_id: b for b in context.draft.blocks}
        claims = tuple(
            c.model_copy(
                update={
                    "block_text_digest": canonical_hash(blocks[c.block_id].text),
                    "spans": (TextSpan(start=0, end=len(blocks[c.block_id].text)),),
                    "normalized_assertion": blocks[c.block_id].text,
                }
            ).model_dump(mode="json")
            for c in prototype.claims
        )
        text = {c.claim_id: blocks[c.block_id].text for c in prototype.claims}
        payload = prototype.model_dump(mode="json")
        payload.update(
            draft_digest=canonical_hash(context.draft),
            claims=claims,
            basis_links=tuple(
                link.model_copy(update={"proposition": text[link.claim_id]}).model_dump(mode="json")
                for link in prototype.basis_links
            ),
            block_accounts=tuple(
                a.model_copy(
                    update={"block_text_digest": canonical_hash(blocks[a.block_id].text)}
                ).model_dump(mode="json")
                for a in prototype.block_accounts
            ),
        )
        return ClaimExtractionProposal.model_validate(payload)

    async def verify(self, context):
        from tests.unit.reporting.test_verification import scripted_batch

        self.calls.append("verify")
        assert context.draft == self.draft
        return scripted_batch(context)

    async def check_composition(self, context):
        from novelty_harness.reporting.verification import CompositionCheck

        self.calls.append("composition")
        assert context.drafts[0] == self.draft
        return CompositionCheck(
            scope=context.scope,
            compilation_id=context.compilation_id,
            narrative_digest=context.narrative_digest,
            claims_digest=context.claims_digest,
            permission_digest=context.permission_digest,
            disposition="SUPPORTED",
            implicated_block_ids=(),
            implicated_question_ids=(),
            indeterminate_scope=False,
            reason_codes=(),
            reason="Recorded faithful scope and limitation composition case",
        )


def _advance_report(case, compilation, state):
    from novelty_harness.evidence.graph.report_store import report_attempt_state
    from tests.unit.reporting.test_attempts import status_artifact

    previous = report_attempt_state(
        case.repository.load_report_artifacts(compilation.compilation_id)
    )
    artifact = status_artifact(
        compilation, previous, state, reason="Completed committed reporting stage"
    )
    case.repository.record_report_artifact(compilation.compilation_id, artifact)


def _build_report_candidate(
    case, *, token="candidate", failed=False, generative=False, repair=False
):
    import asyncio

    from novelty_harness.application.phase8_sections import (
        assure_report_composition,
        assure_report_section,
        invoke_report_operation,
    )
    from novelty_harness.ports.reporting import ReportPorts
    from novelty_harness.reporting.artifacts import (
        ReportArtifactKind,
        ReportAttemptState,
        make_report_artifact,
    )
    from novelty_harness.reporting.citations import build_citation_registry
    from novelty_harness.reporting.drafts import SectionDraft, build_section_context
    from novelty_harness.reporting.execution import (
        ReportCompilationConfiguration,
        approved_role_configuration,
    )
    from novelty_harness.reporting.fallback import FallbackRecord, render_fallback_section
    from novelty_harness.reporting.ir import build_report_ir
    from novelty_harness.reporting.models import (
        ReportGenerationLimits,
        ReportOptions,
        ReportProposalError,
        ReportSemanticRole,
    )
    from novelty_harness.reporting.plan import build_coverage_plan
    from tests.unit.reporting.test_ir import compiled_shape
    from tests.unit.reporting.test_repair import ScriptedSections

    port = (
        ScriptedSections()
        if repair
        else FaithfulInputReportPort()
        if generative
        else FailedReportWriter()
    )
    roles = (
        (
            ReportSemanticRole.WRITER,
            ReportSemanticRole.EXTRACTOR,
            ReportSemanticRole.VERIFIER,
            ReportSemanticRole.COMPOSITION,
        )
        if generative
        else (
            ReportSemanticRole.WRITER,
            ReportSemanticRole.EXTRACTOR,
            ReportSemanticRole.VERIFIER,
            ReportSemanticRole.REPAIR,
        )
        if repair
        else (ReportSemanticRole.WRITER,)
        if failed
        else ()
    )
    configuration = ReportCompilationConfiguration(
        roles=tuple(
            approved_role_configuration(case.bundle.scope, "pending", role, port.configuration)
            for role in roles
        )
    )
    compilation = case.repository.begin_report_compilation(
        case.bundle.scope.assessment_id,
        adjudication_id=case.frozen.adjudication_id,
        options=ReportOptions(
            compact_summary=True,
            limits=ReportGenerationLimits(
                max_context_chars=50000000,
                max_question_chars=4000000,
                max_blocks_per_question=2000,
                max_tokens=10000000000,
            ),
        ),
        configuration=configuration,
        attempt_token=token,
    )
    plan = build_coverage_plan(case.bundle, compilation)
    case.repository.record_report_artifact(
        compilation.compilation_id,
        make_report_artifact(
            compilation,
            ReportArtifactKind.PLAN,
            plan,
            method_version="p8-plan-firewall-v1",
        ),
    )
    _advance_report(case, compilation, ReportAttemptState.PLANNED)
    if failed:
        context = build_section_context(case.bundle, plan, question_id=1, compilation=compilation)
        with pytest.raises(ReportProposalError, match="provider operation failed"):
            asyncio.run(
                invoke_report_operation(
                    compilation,
                    case.repository,
                    port,
                    ReportSemanticRole.WRITER,
                    context,
                    SectionDraft,
                    lambda: port.write(context),
                )
            )
    sections = []
    for question in range(1, 10):
        section = render_fallback_section(case.bundle, compilation, question_id=question)
        if (generative and question == 1) or (repair and question == 2):
            if generative:
                port.template = section
            context = build_section_context(
                case.bundle, plan, question_id=question, compilation=compilation
            )
            assert not context.requires_fallback
            section = asyncio.run(
                assure_report_section(
                    compilation,
                    context,
                    bundle=case.bundle,
                    plan=plan,
                    ports=ReportPorts(writer=port, extractor=port, verifier=port),
                    repository=case.repository,
                )
            )
            assert set(section.block_origins.values()) == {
                "DETERMINISTIC_FALLBACK" if repair else "GENERATIVE_ACCEPTED"
            }
            if repair:
                assert sum(name == "repair" for name, _ in port.calls) == 1
        else:
            record = FallbackRecord(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                question_id=question,
                bundle_digest=case.bundle.bundle_digest,
                section=section,
            )
            case.repository.record_report_artifact(
                compilation.compilation_id,
                make_report_artifact(
                    compilation,
                    ReportArtifactKind.FALLBACK,
                    record,
                    method_version="p8-fallback-v1",
                ),
            )
        sections.append(section)
    _advance_report(case, compilation, ReportAttemptState.DRAFTED)
    if generative:
        sections = list(
            asyncio.run(
                assure_report_composition(
                    compilation,
                    tuple(sections),
                    bundle=case.bundle,
                    ports=ReportPorts(verifier=port),
                    repository=case.repository,
                )
            )
        )
        assert port.calls == ["write", "extract", "verify", "composition"]
    _advance_report(case, compilation, ReportAttemptState.VERIFIED)
    artifacts = case.repository.load_report_artifacts(compilation.compilation_id)
    citations = build_citation_registry(tuple(sections), case.bundle)
    ir = build_report_ir(case.bundle, compilation, tuple(sections), citations, artifacts)
    proposed = compiled_shape(ir, (compilation, sections, citations, artifacts))
    proposed = _rehash_report(
        proposed.model_copy(
            update={"approved_versions": ir.generation_provenance.approved_versions}
        )
    )
    return compilation, proposed, artifacts


# Native preacceptance snapshots avoid rebuilding identical scripted pipelines
# for each independent mutation. Accepted/corrupted state never enters this cache.
_candidate_snapshots = {}


def _report_candidate(case, *, token="candidate", failed=False, generative=False, repair=False):
    import sqlite3
    from pathlib import Path

    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_store import load_report_compilation_in_session
    from novelty_harness.reporting.ir import CompiledAssessmentReport

    key = (case.bundle.bundle_digest, token, failed, generative, repair)
    cached = _candidate_snapshots.get(key)
    database = Path(case.repository.engine.url.database)
    empty = all(count == 0 for count in _report_counts(case.repository).values())
    if cached is not None and empty:
        snapshot, compilation_id, serialized = cached
        # No open transaction is retained across the SQLite backup.
        case.repository.engine.dispose()
        with (
            closing(sqlite3.connect(snapshot)) as source,
            closing(sqlite3.connect(database)) as target,
        ):
            source.backup(target)
        artifacts = case.repository.load_report_artifacts(compilation_id)
        with Session(case.repository.engine) as session:
            session.execute(text("BEGIN"))
            compilation = load_report_compilation_in_session(session, compilation_id)
            session.commit()
        proposed = CompiledAssessmentReport.model_validate_json(serialized)
        return compilation, proposed, artifacts
    compilation, proposed, artifacts = _build_report_candidate(
        case, token=token, failed=failed, generative=generative, repair=repair
    )
    if empty:
        snapshot = database.with_name("preacceptance-" + compilation.compilation_id + ".db")
        with (
            closing(sqlite3.connect(database)) as source,
            closing(sqlite3.connect(snapshot)) as target,
        ):
            source.backup(target)
        _candidate_snapshots[key] = (
            snapshot,
            compilation.compilation_id,
            proposed.model_dump_json(),
        )
    return compilation, proposed, artifacts


def _rehash_report(report):
    from novelty_harness.reporting.ir import report_id

    return report.model_copy(update={"report_id": report_id(report)})


def _accepted_count(case, compilation):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import CompiledReportRow, ReportArtifactRow

    with Session(case.repository.engine) as session:
        reports = tuple(
            session.scalars(
                select(CompiledReportRow).where(
                    CompiledReportRow.compilation_id == compilation.compilation_id
                )
            )
        )
        statuses = tuple(
            session.scalars(
                select(ReportArtifactRow).where(
                    ReportArtifactRow.compilation_id == compilation.compilation_id,
                    ReportArtifactRow.kind == "STATUS",
                )
            )
        )
        return len(reports), sum('"next_state":"ACCEPTED"' in row.document_json for row in statuses)


def test_acceptance_revalidates_exact_text_execution_and_dependency_set(acceptance_case):
    from novelty_harness.reporting.repository import ReportAuthorityError

    case = acceptance_case
    assert hasattr(case.repository, "accept_compiled_report"), "atomic report acceptance is absent"
    compilation, proposed, artifacts = _report_candidate(case, failed=True)
    failed_ids = {
        a.artifact_id
        for a in artifacts
        if a.kind == "EXECUTION" and a.document.outcome == "PROVIDER_FAILURE"
    }
    assert failed_ids
    omitted = _rehash_report(
        proposed.model_copy(
            update={
                "dependencies": tuple(
                    d for d in proposed.dependencies if d.report_artifact_id not in failed_ids
                )
            }
        )
    )
    with pytest.raises(ReportAuthorityError):
        case.repository.accept_compiled_report(compilation.compilation_id, omitted)
    assert _accepted_count(case, compilation) == (0, 0)
    before = _upstream_rows(case.repository)
    assert (
        case.repository.accept_compiled_report(compilation.compilation_id, proposed)
        == proposed.report_id
    )
    assert _accepted_count(case, compilation) == (1, 1)
    assert _upstream_rows(case.repository) == before
    assert (
        case.repository.accept_compiled_report(compilation.compilation_id, proposed)
        == proposed.report_id
    )
    assert _accepted_count(case, compilation) == (1, 1)


def test_acceptance_persists_validated_snapshot_and_preserves_caller(acceptance_case):
    case = acceptance_case
    compilation, proposed, artifacts = _report_candidate(case)
    del artifacts
    canonical_id = proposed.report_id
    caller = proposed.model_copy(update={"report_id": " " + canonical_id + " "})
    caller_wire = caller.model_dump_json()
    before = _upstream_rows(case.repository)

    accepted_id = case.repository.accept_compiled_report(compilation.compilation_id, caller)
    assert accepted_id == canonical_id
    assert caller.model_dump_json() == caller_wire
    assert _accepted_count(case, compilation) == (1, 1)
    assert _upstream_rows(case.repository) == before
    del caller_wire
    loaded = case.repository.load_compiled_report(
        compilation.scope.assessment_id, report_id=accepted_id
    )
    assert loaded == proposed.model_copy(update={"accepted_at": loaded.accepted_at})
    del loaded
    assert (
        case.repository.accept_compiled_report(compilation.compilation_id, caller) == canonical_id
    )
    assert caller.report_id == " " + canonical_id + " "
    assert _accepted_count(case, compilation) == (1, 1)
    assert _upstream_rows(case.repository) == before


def test_caller_compiled_shape_or_ir_export_cannot_skip_acceptance(acceptance_case):
    from novelty_harness.reporting.repository import ReportAuthorityError

    compilation, proposed, _ = _report_candidate(acceptance_case)
    foreign = proposed.model_copy(
        update={"compilation_id": "caller-export-with-no-registered-attempt"}
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(
            foreign.compilation_id, _rehash_report(foreign)
        )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(
            compilation.compilation_id, proposed.model_dump(mode="json")
        )
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


def test_accepted_label_cannot_bypass_fallback_recompute(acceptance_case):
    from novelty_harness.reporting.repository import ReportAuthorityError

    compilation, proposed, _ = _report_candidate(acceptance_case)
    section = proposed.ir.sections[0]
    block = section.blocks[0]
    changed = block.model_copy(
        update={
            "draft_block": block.draft_block.model_copy(
                update={"text": "The entire idea is definitely novel."}
            )
        }
    )
    ir = proposed.ir.model_copy(
        update={
            "sections": (
                section.model_copy(update={"blocks": (changed, *section.blocks[1:])}),
                *proposed.ir.sections[1:],
            )
        }
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(
            compilation.compilation_id, _rehash_report(proposed.model_copy(update={"ir": ir}))
        )
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


def test_acceptance_failure_rolls_back_dependencies_and_status(acceptance_case):
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import ReportDependencyRow

    compilation, proposed, _ = _report_candidate(acceptance_case)

    def fail(session, _context, _instances):
        if any(isinstance(row, ReportDependencyRow) for row in session.new):
            raise RuntimeError("injected dependency insert failure")

    event.listen(Session, "before_flush", fail)
    try:
        with pytest.raises(RuntimeError, match="injected dependency"):
            acceptance_case.repository.accept_compiled_report(compilation.compilation_id, proposed)
    finally:
        event.remove(Session, "before_flush", fail)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)
    with acceptance_case.repository.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM report_dependencies")).scalar_one() == 0
        )


@pytest.mark.parametrize(
    "field", ["assessment_context_id", "phase6_snapshot_id", "adjudication_id"]
)
def test_acceptance_rejects_foreign_context_snapshot_or_compilation(acceptance_case, field):
    from novelty_harness.reporting.repository import ReportAuthorityError

    compilation, proposed, _ = _report_candidate(acceptance_case)
    changed = _rehash_report(
        proposed.model_copy(
            update={"scope": proposed.scope.model_copy(update={field: "foreign-native-locator"})}
        )
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, changed)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)


def test_real_generative_proof_is_required_and_can_accept(acceptance_case):
    from novelty_harness.reporting.repository import ReportAuthorityError

    compilation, proposed, _ = _report_candidate(acceptance_case, generative=True)
    assert all(b.origin == "GENERATIVE_ACCEPTED" for b in proposed.ir.sections[0].blocks)
    first = proposed.ir.sections[0]
    forged = first.model_copy(
        update={
            "blocks": tuple(b.model_copy(update={"verification_refs": ()}) for b in first.blocks)
        }
    )
    changed = _rehash_report(
        proposed.model_copy(
            update={
                "ir": proposed.ir.model_copy(
                    update={"sections": (forged, *proposed.ir.sections[1:])}
                )
            }
        )
    )
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, changed)
    assert (
        acceptance_case.repository.accept_compiled_report(compilation.compilation_id, proposed)
        == proposed.report_id
    )


def test_acceptance_owns_terminal_status_but_exact_receipt_replays(acceptance_case):
    from novelty_harness.evidence.graph.report_store import report_attempt_state
    from novelty_harness.reporting.artifacts import ReportAttemptState
    from novelty_harness.reporting.repository import ReportAuthorityError
    from tests.unit.reporting.test_attempts import status_artifact

    compilation, proposed, _ = _report_candidate(acceptance_case)
    repository = acceptance_case.repository
    previous = report_attempt_state(repository.load_report_artifacts(compilation.compilation_id))
    forged = status_artifact(
        compilation,
        previous,
        ReportAttemptState.ACCEPTED,
        reason=f"Accepted compiled report {proposed.report_id}",
    )
    with pytest.raises(ReportAuthorityError):
        repository.record_report_artifact(compilation.compilation_id, forged)
    assert _accepted_count(acceptance_case, compilation) == (0, 0)
    repository.accept_compiled_report(compilation.compilation_id, proposed)
    accepted = next(
        artifact
        for artifact in repository.load_report_artifacts(compilation.compilation_id)
        if artifact.kind == "STATUS" and artifact.document.next_state == ReportAttemptState.ACCEPTED
    )
    assert (
        repository.record_report_artifact(compilation.compilation_id, accepted)
        == accepted.artifact_id
    )
    assert _accepted_count(acceptance_case, compilation) == (1, 1)


def test_acceptance_retry_requires_its_terminal_receipt(acceptance_case):
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import ReportArtifactRow
    from novelty_harness.reporting.repository import ReportAuthorityError

    compilation, proposed, _ = _report_candidate(acceptance_case)
    repository = acceptance_case.repository
    repository.accept_compiled_report(compilation.compilation_id, proposed)
    accepted = next(
        a
        for a in repository.load_report_artifacts(compilation.compilation_id)
        if a.kind == "STATUS" and a.document.next_state == "ACCEPTED"
    )
    with Session(repository.engine) as session:
        session.execute(
            delete(ReportArtifactRow).where(ReportArtifactRow.artifact_id == accepted.artifact_id)
        )
        session.commit()
    with pytest.raises(ReportAuthorityError, match="terminal"):
        repository.accept_compiled_report(compilation.compilation_id, proposed)
    assert _accepted_count(acceptance_case, compilation) == (1, 0)


_accepted_snapshots = {}


def _accepted_report(case, *, failed=False, generative=False):
    """Clone only native, fully accepted repositories; every load still validates."""
    import sqlite3
    from pathlib import Path

    from novelty_harness.reporting.ir import CompiledAssessmentReport

    key = (case.bundle.bundle_digest, failed, generative)
    database = Path(case.repository.engine.url.database)
    cached = _accepted_snapshots.get(key)
    if cached is not None and all(n == 0 for n in _report_counts(case.repository).values()):
        snapshot, serialized = cached
        case.repository.engine.dispose()
        with (
            closing(sqlite3.connect(snapshot)) as source,
            closing(sqlite3.connect(database)) as target,
        ):
            source.backup(target)
        return CompiledAssessmentReport.model_validate_json(serialized)
    compilation, proposed, _ = _report_candidate(case, failed=failed, generative=generative)
    case.repository.accept_compiled_report(compilation.compilation_id, proposed)
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.report_models import CompiledReportRow

    with Session(case.repository.engine) as session:
        row = session.get(CompiledReportRow, proposed.report_id)
        accepted = CompiledAssessmentReport.model_validate_json(row.document_json)
    snapshot = database.with_name("accepted-" + accepted.report_id + ".db")
    with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(snapshot)) as target:
        source.backup(target)
    _accepted_snapshots[key] = snapshot, accepted.model_dump_json()
    return accepted


def test_reopen_exact_replay_and_terminal_artifact_rules(acceptance_case):
    from pathlib import Path

    from novelty_harness.reporting.repository import ReportAuthorityError

    report = _accepted_report(acceptance_case)
    path = Path(acceptance_case.repository.engine.url.database)
    reopened = SqlAlchemyEvidenceGraphRepository(path)
    try:
        loaded = reopened.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )
        assert loaded == report
        assert reopened.accept_compiled_report(report.compilation_id, loaded) == report.report_id
        artifact = reopened.load_report_artifacts(report.compilation_id)[0]
        assert (
            reopened.record_report_artifact(report.compilation_id, artifact) == artifact.artifact_id
        )
        with pytest.raises(ReportAuthorityError):
            reopened.load_compiled_report("asm_foreign", report_id=report.report_id)
        with pytest.raises(ReportAuthorityError):
            reopened.load_compiled_report(report.scope.assessment_id, report_id="p8report_missing")
    finally:
        reopened.close()


def test_report_load_uses_one_explicit_transaction(acceptance_case):
    report = _accepted_report(acceptance_case)
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.strip().upper().startswith("BEGIN"):
            statements.append(statement.strip().upper())

    event.listen(acceptance_case.repository.engine, "before_cursor_execute", observe)
    try:
        loaded = acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )
    finally:
        event.remove(acceptance_case.repository.engine, "before_cursor_execute", observe)
    assert loaded == report
    assert statements == ["BEGIN"]


@pytest.mark.parametrize("column", ["bundle_digest", "ir_digest", "context_id", "accepted_at"])
def test_report_load_rejects_manifest_column_corruption(acceptance_case, column):
    from novelty_harness.reporting.repository import ReportAuthorityError

    report = _accepted_report(acceptance_case)
    with acceptance_case.repository.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(text(f"UPDATE compiled_reports SET {column}='corrupt'"))
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_report_read_snapshot_survives_concurrent_revocation(acceptance_case):
    import sqlite3

    from novelty_harness.reporting.repository import ReportAuthorityError

    report = _accepted_report(acceptance_case)
    database = acceptance_case.repository.engine.url.database
    with acceptance_case.repository.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"
    revoked = []

    def revoke_after_manifest_read(_connection, _cursor, statement, _parameters, _context, _many):
        if not revoked and "FROM report_compilations" in statement:
            with sqlite3.connect(database) as writer:
                writer.execute(
                    "DELETE FROM phase6_graph_edge_memberships WHERE edge_id=?",
                    (acceptance_case.bundle.authorized_relations[0].edge.edge_id,),
                )
            revoked.append(True)

    event.listen(
        acceptance_case.repository.engine, "before_cursor_execute", revoke_after_manifest_read
    )
    try:
        loaded = acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )
    finally:
        event.remove(
            acceptance_case.repository.engine, "before_cursor_execute", revoke_after_manifest_read
        )
    assert revoked and loaded == report
    with pytest.raises(ReportAuthorityError):
        acceptance_case.repository.load_compiled_report(
            report.scope.assessment_id, report_id=report.report_id
        )


def test_pinned_method_validation_is_independent_of_default(monkeypatch):
    from novelty_harness.reporting import execution
    from tests.fixtures.phase8 import report_configuration

    configuration = report_configuration()
    configured = configuration.roles[0]
    execution.validate_method_registration(configured.method)
    monkeypatch.setattr(
        execution,
        "DEFAULT_SEMANTIC_METHODS",
        {**execution.DEFAULT_SEMANTIC_METHODS, configured.role: "p8-plan-v2"},
    )
    execution.validate_method_registration(configured.method)
    rebound = execution.bind_compilation_configuration(
        configuration, configured.scope, "p8run_replay"
    )
    assert rebound.roles[0].method_version == configured.method_version
    assert rebound.roles[0].instruction_hash == configured.instruction_hash
