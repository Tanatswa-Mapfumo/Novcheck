"""Explicit real slice integration and repository-loaded exports; no live network."""

import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from novelty_harness.application.evidence_phase6 import Phase6EvidenceComponents
from novelty_harness.application.research import Phase3ResearchComponents
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.intake.pipeline import UnderstandingComponents
from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.research.critique import SearchPlanCritic
from novelty_harness.research.planning import SearchStrategist
from novelty_harness.research.revision import SearchPlanReviser
from novelty_harness.research.screening import ScreeningExecutor
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses
from tests.fixtures.phase3 import applicability_response, planning_response
from tests.fixtures.phase4 import registry, stop_policy, wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.fixtures.phase6 import (
    StubLLMProvider,
    map_evidence_response,
)
from tests.fixtures.phase8 import ReportCase
from tests.integration.test_phase5_slice_with_phase6_evidence import (
    CombinationReconciler,
    ExpandedPhase5EvidenceComponents,
    verify_expanded_response,
)
from tests.integration.test_phase8_compiler import compile_report, upstream_rows
from tests.unit.evidence.graph.test_report_store import acceptance_source as _acceptance_source
from tests.unit.research.test_search_critique import critic_response

acceptance_source = _acceptance_source


@pytest.fixture(scope="module")
def exported_source(acceptance_source):
    # Compile once; every mutation/export test receives a private SQLite copy.
    report = compile_report(acceptance_source, token="exports-baseline")
    return acceptance_source, report


@pytest.fixture
def exported_case(exported_source, tmp_path):
    source, report = exported_source
    destination = tmp_path / "accepted-copy.sqlite"
    repository = None
    try:
        with closing(sqlite3.connect(source.repository.engine.url.database)) as origin:
            with closing(sqlite3.connect(destination)) as target:
                origin.backup(target)
        repository = SqlAlchemyEvidenceGraphRepository(destination)
        frozen = repository.load_frozen_adjudication(
            source.frozen.assessment_id, adjudication_id=source.frozen.adjudication_id
        )
        bundle = repository.load_report_input_bundle(
            frozen.assessment_id, adjudication_id=frozen.adjudication_id
        )
        yield ReportCase(repository, frozen, bundle), report
    finally:
        try:
            if repository is not None:
                repository.close()
        finally:
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(str(destination) + suffix).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_real_slice_compiles_loaded_report_and_preserves_summary_only_branch(
    tmp_path, monkeypatch
):
    from novelty_harness.application.models import ReportCompilationRequest
    from novelty_harness.application.vertical_slice import (
        Phase7VerticalSliceResult,
        Phase8VerticalSliceResult,
    )
    from novelty_harness.reporting.models import ReportGenerationLimits, ReportOptions

    summary_only, _ = await _run_real_slice(tmp_path / "summary")
    assert type(summary_only) is Phase7VerticalSliceResult
    assert summary_only.summary.overall_verdict == summary_only.adjudication.overall_finding.verdict
    # The compatibility assertions are complete; release this independent run
    # before constructing the full-report branch on the 8 GB development Mac.
    del summary_only
    from novelty_harness.adjudication.models import Phase7RunState
    from novelty_harness.application import vertical_slice

    original_compile = vertical_slice.compile_assessment_report
    observed = []

    async def observe_compile(assessment_id, **kwargs):
        repository = kwargs["repository"]
        bundle = repository.load_report_input_bundle(
            assessment_id, adjudication_id=kwargs["adjudication_id"]
        )
        frozen = bundle.frozen_adjudication
        assert repository.load_phase7_run(frozen.run_id).state == Phase7RunState.FROZEN
        case = ReportCase(repository, frozen, bundle)
        before = upstream_rows(case)
        scope, run_id, adjudication_id = bundle.scope, frozen.run_id, frozen.adjudication_id
        del bundle, frozen, case
        report = await original_compile(assessment_id, **kwargs)
        reloaded = repository.load_report_input_bundle(
            assessment_id, adjudication_id=adjudication_id
        )
        assert (
            upstream_rows(ReportCase(repository, reloaded.frozen_adjudication, reloaded)) == before
        )
        assert report.scope == scope
        assert report.compilation_id != run_id
        observed.append((adjudication_id, report.compilation_id, kwargs["attempt_token"]))
        return report

    monkeypatch.setattr(vertical_slice, "compile_assessment_report", observe_compile)
    full, sink = await _run_real_slice(
        tmp_path / "full",
        ReportCompilationRequest(
            ReportOptions(limits=ReportGenerationLimits(max_calls=0)),
            attempt_token="task22-full-report",
        ),
    )
    assert observed == [
        (full.adjudication.adjudication_id, full.report.compilation_id, "task22-full-report")
    ]
    assert type(full) is Phase8VerticalSliceResult
    assert full.report.scope.adjudication_id == full.adjudication.adjudication_id
    assert full.report.ir.target_findings == full.adjudication.target_findings
    assert full.summary.overall_verdict == full.adjudication.overall_finding.verdict
    repository = SqlAlchemyEvidenceGraphRepository(full.run_dir / "phase5/evidence_graph.sqlite3")
    try:
        with repository.engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT attempt_token,adjudication_id FROM report_compilations "
                "WHERE compilation_id=?",
                (full.report.compilation_id,),
            ).one() == ("task22-full-report", full.adjudication.adjudication_id)
        assert (
            repository.load_compiled_report(
                full.record.assessment_id, report_id=full.report.report_id
            )
            == full.report
        )
        assert (
            repository.load_frozen_adjudication(
                full.record.assessment_id, adjudication_id=full.adjudication.adjudication_id
            )
            == full.adjudication
        )
    finally:
        repository.close()
    exported = full.run_dir / "reports" / full.report.report_id
    assert json.loads((exported / "report.json").read_text())["report_id"] == full.report.report_id
    assert (exported / "report.yaml").exists() and (exported / "report.md").exists()
    assert any(event.stage.value == "REPORTED" for event in sink.events)


@pytest.mark.parametrize("failure", ["generation", "export"])
@pytest.mark.asyncio
async def test_report_generation_or_export_failure_does_not_rewrite_adjudication(
    tmp_path, monkeypatch, failure
):
    from novelty_harness.application.models import ReportCompilationRequest
    from novelty_harness.reporting.models import ReportOptions

    observed = {}

    def preserve_upstream(assessment_id, repository, adjudication_id):
        bundle = repository.load_report_input_bundle(assessment_id, adjudication_id=adjudication_id)
        case = ReportCase(repository, bundle.frozen_adjudication, bundle)
        observed["frozen"] = case.frozen
        observed["rows"] = upstream_rows(case)

    async def broken_compile(assessment_id, **kwargs):
        preserve_upstream(assessment_id, kwargs["repository"], kwargs["adjudication_id"])
        raise RuntimeError("recorded report generation failure")

    def broken_export(assessment_id, **kwargs):
        loaded = kwargs["repository"].load_compiled_report(
            assessment_id, report_id=kwargs["report_id"]
        )
        preserve_upstream(assessment_id, kwargs["repository"], loaded.scope.adjudication_id)
        raise OSError("recorded export failure")

    monkeypatch.setattr(
        "novelty_harness.application.vertical_slice.compile_assessment_report"
        if failure == "generation"
        else "novelty_harness.application.vertical_slice.export_compiled_report",
        broken_compile if failure == "generation" else broken_export,
    )
    with pytest.raises(RuntimeError, match="Phase 8"):
        await _run_real_slice(tmp_path, ReportCompilationRequest(ReportOptions()))
    database = next(tmp_path.rglob("evidence_graph.sqlite3"))
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        with closing(sqlite3.connect(database)) as conn:
            aid, fid = conn.execute(
                "SELECT assessment_id,adjudication_id FROM phase7_frozen_manifests"
            ).fetchone()
        frozen = repository.load_frozen_adjudication(aid, adjudication_id=fid)
        assert frozen == observed["frozen"]
        bundle = repository.load_report_input_bundle(aid, adjudication_id=fid)
        assert upstream_rows(ReportCase(repository, frozen, bundle)) == observed["rows"]
        assert (database.parents[1] / "report.md").exists()
        assert "Phase 8" in (database.parents[1] / "report.md").read_text()
    finally:
        repository.close()


def test_export_retry_uses_accepted_report_without_semantic_calls(
    exported_case, tmp_path, monkeypatch
):
    from novelty_harness.application.phase8_exports import export_compiled_report

    case, report = exported_case
    before = upstream_rows(case)
    writer = RunArtifactWriter(tmp_path / "exports")
    semantic_calls = []

    def forbidden_semantic_call(*args, **kwargs):
        semantic_calls.append((args, kwargs))
        raise AssertionError("Export retry must not compile or dispatch semantic work")

    for name in (
        "novelty_harness.application.phase8.compile_assessment_report",
        "novelty_harness.application.phase8.invoke_report_operation",
        "novelty_harness.application.phase8_sections.invoke_report_operation",
        "novelty_harness.runtime.semantic.structured.SemanticRunner.run",
    ):
        monkeypatch.setattr(name, forbidden_semantic_call)

    class FailingWriter(RunArtifactWriter):
        def write_text(self, assessment_id, relative_name, text):
            if relative_name.endswith("/report.yaml"):
                raise OSError("recorded disk failure after JSON publication")
            return super().write_text(assessment_id, relative_name, text)

    with pytest.raises(OSError):
        export_compiled_report(
            case.frozen.assessment_id,
            report_id=report.report_id,
            repository=case.repository,
            artifact_writer=FailingWriter(tmp_path / "failed"),
        )
    partial = tmp_path / "failed" / case.frozen.assessment_id / "reports" / report.report_id
    assert json.loads((partial / "report.json").read_text())["report_id"] == report.report_id
    assert not (partial / "report.yaml").exists()
    assert not (partial / "report.md").exists()
    assert (
        case.repository.load_compiled_report(case.frozen.assessment_id, report_id=report.report_id)
        == report
    )
    first = export_compiled_report(
        case.frozen.assessment_id,
        report_id=report.report_id,
        repository=case.repository,
        artifact_writer=writer,
    )
    second = export_compiled_report(
        case.frozen.assessment_id,
        report_id=report.report_id,
        repository=case.repository,
        artifact_writer=writer,
    )
    assert first == second and len(first) == 3
    assert json.loads(first[0].read_text())["report_id"] == report.report_id
    assert upstream_rows(case) == before
    assert semantic_calls == []


def test_full_report_operation_can_run_after_completed_phase7_lifecycle(tmp_path):
    from novelty_harness.application.phase8_exports import export_compiled_report
    from novelty_harness.domain.enums import AssessmentStatus

    result, _ = asyncio.run(_run_real_slice(tmp_path / "completed"))
    assert result.record.status == AssessmentStatus.COMPLETED
    lifecycle_path = result.run_dir / "assessment_record.json"
    lifecycle_before = lifecycle_path.read_bytes()
    repository = SqlAlchemyEvidenceGraphRepository(result.run_dir / "phase5/evidence_graph.sqlite3")
    try:
        bundle = repository.load_report_input_bundle(
            result.record.assessment_id, adjudication_id=result.adjudication.adjudication_id
        )
        case = ReportCase(repository, result.adjudication, bundle)
        before = upstream_rows(case)
        report = compile_report(case, token="standalone-after-phase7")
        paths = export_compiled_report(
            case.frozen.assessment_id,
            report_id=report.report_id,
            repository=repository,
            artifact_writer=RunArtifactWriter(tmp_path / "completed"),
        )
        assert all(path.exists() for path in paths)
        assert upstream_rows(case) == before
        assert lifecycle_path.read_bytes() == lifecycle_before
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_fixture_report_cannot_masquerade_as_real_report(tmp_path):
    from novelty_harness.application.models import ReportCompilationRequest
    from novelty_harness.reporting.models import ReportOptions

    fixture = make_fixture()
    with pytest.raises(ValueError, match="real Phase 7"):
        await run_vertical_slice(
            request=fixture.request,
            components=fixture.components,
            search_provider=fixture.search_provider,
            content_resolver=fixture.content_resolver,
            trace_sink=InMemoryTraceSink(),
            artifact_writer=RunArtifactWriter(tmp_path),
            phase8=ReportCompilationRequest(ReportOptions()),
        )


def test_corrupt_authority_prevents_any_report_export(exported_case, exported_source, tmp_path):
    from novelty_harness.application.phase8_exports import export_compiled_report
    from novelty_harness.reporting.repository import ReportAuthorityError

    case, report = exported_case
    source, baseline_report = exported_source
    source_before = upstream_rows(source)
    assert (
        source.repository.load_compiled_report(
            source.frozen.assessment_id, report_id=baseline_report.report_id
        )
        == baseline_report
    )
    with case.repository.engine.begin() as connection:
        result = connection.exec_driver_sql(
            "UPDATE phase7_artifacts SET document_json = '{}' WHERE kind = 'GATE_C'"
        )
        assert result.rowcount > 0
    root = tmp_path / "refused"
    with pytest.raises(ReportAuthorityError):
        export_compiled_report(
            case.frozen.assessment_id,
            report_id=report.report_id,
            repository=case.repository,
            artifact_writer=RunArtifactWriter(root),
        )
    assert not root.exists()
    assert upstream_rows(source) == source_before
    assert (
        source.repository.load_frozen_adjudication(
            source.frozen.assessment_id, adjudication_id=source.frozen.adjudication_id
        )
        == source.frozen
    )
    assert (
        source.repository.load_compiled_report(
            source.frozen.assessment_id, report_id=baseline_report.report_id
        )
        == baseline_report
    )


def test_two_reports_keep_separate_export_paths(exported_case, tmp_path):
    from novelty_harness.application.phase8_exports import export_compiled_report

    case, first = exported_case
    second = compile_report(case, token="another-export")
    writer = RunArtifactWriter(tmp_path / "exports")
    a = export_compiled_report(
        case.frozen.assessment_id,
        report_id=first.report_id,
        repository=case.repository,
        artifact_writer=writer,
    )
    before = [p.read_bytes() for p in a]
    b = export_compiled_report(
        case.frozen.assessment_id,
        report_id=second.report_id,
        repository=case.repository,
        artifact_writer=writer,
    )
    assert set(a).isdisjoint(b)
    assert [p.read_bytes() for p in a] == before


async def _run_real_slice(tmp_path, phase8=None):
    f = make_fixture()
    understanding = UnderstandingComponents(
        SemanticRunner(RecordedLLM(understanding_responses())), clock=f.clock
    )
    runner = SemanticRunner(
        RecordedLLM(
            {
                "assess_families": applicability_response(),
                "plan_research": planning_response(),
                "criticize_search": critic_response(),
            }
        )
    )
    from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase
    from novelty_harness.ports.adjudication import Phase7Ports
    from tests.unit.adjudication.test_roles import scope

    class Roles:
        def __init__(self, prosecution):
            self.prosecution = prosecution
            self.calls = 0

        async def propose(self, packet):
            target_id = sorted(packet.target_ids)[self.calls % len(packet.target_ids)]
            self.calls += 1
            if self.prosecution:
                return ProsecutionCase(
                    **scope(packet, target_id), case_id=f"p7pro_vertical_{target_id}", challenges=()
                )
            return DefenseCase(
                **scope(packet, target_id), case_id=f"p7def_vertical_{target_id}", points=()
            )

    class Unused:
        model_config_id = "unused"

        async def propose(self, *args):
            raise AssertionError("No disputed arguments")

    class NeutralJudge:
        model_config_id = "neutral-vertical-v2"

        def __init__(self):
            self.calls = []

        async def judge(self, packet, arguments, *, order, rubric_version):
            from novelty_harness.adjudication.gates import evaluate_gate_c, evaluate_gate_d
            from novelty_harness.adjudication.judge import JudgeFinding
            from novelty_harness.adjudication.models import TargetRef

            self.calls.append((arguments[0].target_id, order))
            profile = next(
                p for p in packet.target_profiles if p.target_id == arguments[0].target_id
            )
            target = TargetRef(kind=profile.target_kind, id=profile.target_id)
            gate_c = evaluate_gate_c(packet, target, None)
            gate_d = evaluate_gate_d(packet, target, None, None)
            return JudgeFinding(
                **scope(packet, arguments[0].target_id),
                finding_id="p7judge_vertical_scope_" + arguments[0].target_id,
                phase6_basis_ids=gate_c.comparison_ids,
                proposed_gate_c=gate_c.state,
                proposed_gate_d=gate_d.state,
                reason=(
                    "The packet supports these scoped states; "
                    "unresolved contribution stays unresolved"
                ),
            )

    judge = NeutralJudge()
    phase7 = Phase7Ports(Roles(True), Roles(False), Unused(), Unused(), judge)
    components = replace(
        f.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=CombinationReconciler(understanding),
    )
    sink = InMemoryTraceSink()
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        from novelty_harness.domain.enums import EvidenceFamily
        from novelty_harness.providers.registry import ProviderRegistry

        available, _ = registry(client, clock=f.clock)
        provider = available.providers_for(EvidenceFamily.SCHOLARLY)[0]
        # A single recorded provider keeps this branch test small. Missing
        # evidence families remain explicitly unsearched in native authority.
        providers = ProviderRegistry()
        providers.register(provider.provider, provider.descriptor, compiler=provider.compiler)
        policy = CoveragePolicy.standard()
        research = Phase3ResearchComponents(
            EvidenceFamilyApplicabilityAssessor(runner),
            SearchStrategist(runner),
            SearchPlanCritic(runner),
            SearchPlanReviser(runner),
            ScreeningExecutor(providers, policy),
        )
        adaptive = Phase4ResearchComponents(
            providers, policy, BudgetLimits(max_deep_search_rounds=1), stop_policy()
        )
        result = await run_vertical_slice(
            request=f.request,
            components=components,
            search_provider=f.search_provider,
            content_resolver=SyntheticContentResolver(),
            trace_sink=sink,
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=f.clock,
            research=research,
            adaptive_research=adaptive,
            evidence=ExpandedPhase5EvidenceComponents(),
            phase6=Phase6EvidenceComponents(
                SemanticRunner(
                    StubLLMProvider(
                        {
                            "map_evidence": map_evidence_response,
                            "verify_support": verify_expanded_response,
                        }
                    )
                ),
                max_sources_per_mcu=1,
                max_expansions=0,
            ),
            phase7=phase7,
            phase8=phase8,
        )
    return result, sink


def test_report_request_is_immutable_and_refuses_export_seed():
    from dataclasses import FrozenInstanceError

    from novelty_harness.application.models import ReportCompilationRequest
    from novelty_harness.reporting.models import ReportOptions

    request = ReportCompilationRequest(ReportOptions())
    with pytest.raises(FrozenInstanceError):
        request.attempt_token = "modified"
    with pytest.raises(ValueError, match="ReportOptions"):
        ReportCompilationRequest(make_fixture().adjudication)
