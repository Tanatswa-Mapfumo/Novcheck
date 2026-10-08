"""Real report compilation, bounded invocation and durable replay without Internet."""

import asyncio
from collections import Counter

import pytest

from novelty_harness.ports.reporting import ReportPorts
from novelty_harness.reporting.artifacts import ReportArtifactKind, ReportStatusEvent
from novelty_harness.reporting.execution import ReportPortConfiguration, ReportSamplingSettings
from novelty_harness.reporting.models import ReportGenerationLimits, ReportLens, ReportOptions
from novelty_harness.reporting.repository import ReportAuthorityError
from tests.fixtures.phase8 import make_report_scenario
from tests.unit.evidence.graph.test_report_store import FaithfulInputReportPort
from tests.unit.evidence.graph.test_report_store import acceptance_case as _acceptance_case
from tests.unit.evidence.graph.test_report_store import acceptance_source as _acceptance_source

acceptance_case = _acceptance_case
acceptance_source = _acceptance_source


def generous_options(**changes):
    return ReportOptions(
        compact_summary=True,
        limits=ReportGenerationLimits(
            max_context_chars=50000000,
            max_question_chars=4000000,
            max_blocks_per_question=2000,
            max_tokens=100000000000,
        ),
        **changes,
    )


class RecordedCompilerPort(FaithfulInputReportPort):
    """Scripted faithful meanings, not a qualification of live model quality."""

    def __init__(self, *, failures=(), model="recorded-compiler"):
        super().__init__()
        self.failures = set(failures)
        self.model = model
        self.templates = {}
        self.drafts = {}
        self.plan_proposal = None

    @property
    def configuration(self):
        return ReportPortConfiguration(
            mode="PORT_PROTOCOL",
            implementation=type(self).__module__ + "." + type(self).__qualname__,
            model=self.model,
            sampling=ReportSamplingSettings(max_output_tokens=4000000),
        )

    def prepare(self, bundle, compilation):
        from novelty_harness.reporting.fallback import render_fallback_section
        from novelty_harness.reporting.plan import ReportPlanProposal, build_coverage_plan

        self.templates = {
            q: render_fallback_section(bundle, compilation, question_id=q) for q in range(1, 10)
        }
        plan = build_coverage_plan(bundle, compilation)
        q2 = plan.questions[1]
        first = q2.subsections[0].model_copy(
            update={"heading": "Closest mechanism", "purpose": "Explain its retained scope"}
        )
        second = first.model_copy(
            update={
                "subsection_id": "q2-configuration",
                "heading": "Configuration and residual",
                "parent_id": first.subsection_id,
                "depth": 2,
            }
        )
        questions = list(plan.questions)
        questions[1] = q2.model_copy(update={"subsections": (first, second)})
        self.plan_proposal = ReportPlanProposal(
            scope=compilation.scope,
            compilation_id=compilation.compilation_id,
            bundle_digest=bundle.bundle_digest,
            questions=tuple(questions),
        )

    def operation(self, role, question=None):
        self.calls.append((role, question))
        if role in self.failures or (role, question) in self.failures:
            raise RuntimeError("recorded unavailable report operation")

    async def plan(self, context, options):
        self.operation("plan")
        assert self.plan_proposal.scope == context.scope
        return self.plan_proposal

    async def write(self, context):
        self.operation("write", context.question_id)
        template = self.templates[context.question_id]
        # A prose writer uses plain descriptions rather than raw metadata labels.
        blocks = tuple(
            b.model_copy(update={"text": b.text.replace("metadata:", "metadata —")})
            for b in template.draft.blocks
        )
        if context.question_id == 1:
            blocks = (
                blocks[0].model_copy(
                    update={"text": "The proposal separates relay control from status display."}
                ),
                *blocks[1:],
            )
        draft = template.draft.model_copy(update={"blocks": blocks})
        self.drafts[context.question_id] = draft
        return draft

    async def extract(self, context):
        from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
        from novelty_harness.reporting.claims import ClaimExtractionProposal
        from novelty_harness.reporting.models import ReportClaimCategory

        self.operation("extract", context.draft.question_id)
        self.template = self.templates[context.draft.question_id]
        self.draft = self.drafts[context.draft.question_id]
        result = await super().extract(context)
        self.calls.pop()  # The shared recorded helper also notes the same operation.
        payload = result.model_dump(mode="json")
        labels = set(CANONICAL_QUESTIONS)
        nonmaterial = {c.claim_id for c in result.claims if c.normalized_assertion in labels}
        payload["claims"] = tuple(
            c.model_copy(
                update={"category": ReportClaimCategory.UNCERTAINTY_CLAIM}
                if c.normalized_assertion.startswith("No authoritative value assessment")
                else {}
            ).model_dump(mode="json")
            for c in result.claims
            if c.claim_id not in nonmaterial
        )
        payload["basis_links"] = tuple(
            link.model_dump(mode="json")
            for link in result.basis_links
            if link.claim_id not in nonmaterial
        )
        payload["block_accounts"] = tuple(
            a.model_copy(
                update={
                    "claim_ids": tuple(c for c in a.claim_ids if c not in nonmaterial),
                    "non_material_reason": "Canonical question label contains no assertion"
                    if set(a.claim_ids) <= nonmaterial
                    else a.non_material_reason,
                }
            ).model_dump(mode="json")
            for a in result.block_accounts
        )
        return ClaimExtractionProposal.model_validate(payload)

    async def verify(self, context):
        self.operation("verify", context.draft.question_id)
        self.draft = self.drafts[context.draft.question_id]
        result = await super().verify(context)
        self.calls.pop()
        return result

    async def check_composition(self, context):
        self.operation("composition")
        self.draft = context.drafts[0]
        result = await super().check_composition(context)
        self.calls.pop()
        return result


class SimulatedCrash(BaseException):
    pass


class ObservedRepository:
    """Observe actual transactions outside ports; never manufacture report authority."""

    def __init__(self, case, *, port=None, crash_after=None):
        self.inner = case.repository
        self.bundle = case.bundle
        self.port = port
        self.crash_after = crash_after
        self.loaded = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def begin_report_compilation(self, *args, **kwargs):
        compilation = self.inner.begin_report_compilation(*args, **kwargs)
        if self.port is not None:
            self.port.prepare(self.bundle, compilation)
        return compilation

    def record_report_artifact(self, compilation_id, artifact):
        result = self.inner.record_report_artifact(compilation_id, artifact)
        if (artifact.kind, artifact.question_id) == self.crash_after:
            self.crash_after = None
            raise SimulatedCrash("process stopped after committed section proof")
        return result

    def load_compiled_report(self, assessment_id, *, report_id):
        result = self.inner.load_compiled_report(assessment_id, report_id=report_id)
        self.loaded.append(result.report_id)
        return result


def compile_report(
    case, *, token="coordinator", port=None, ports=None, options=None, repository=None
):
    from novelty_harness.application.phase8 import compile_assessment_report

    if port is not None and ports is None:
        ports = ReportPorts(planner=port, writer=port, extractor=port, verifier=port)
    repository = repository or ObservedRepository(case, port=port)
    return asyncio.run(
        compile_assessment_report(
            case.bundle.scope.assessment_id,
            adjudication_id=case.frozen.adjudication_id,
            repository=repository,
            ports=ports,
            options=options or ReportOptions(compact_summary=True),
            attempt_token=token,
        )
    )


def upstream_rows(case):
    with case.repository.engine.connect() as connection:
        names = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).scalars()
        return {
            name: tuple(
                sorted(connection.exec_driver_sql(f'SELECT * FROM "{name}"').fetchall(), key=repr)
            )
            for name in names
            if name.startswith(("phase6_", "phase7_"))
        }


def assert_complete(case, report):
    assert tuple(s.question_id for s in report.ir.sections) == tuple(range(1, 10))
    assert report.scope == case.bundle.scope
    assert report.ir.target_findings == case.frozen.target_findings
    assert report.ir.overall_finding == case.frozen.overall_finding
    assert {s.obligation_id for s in report.ir.coverage_satisfaction} == {
        o.obligation_id for o in case.bundle.coverage_obligations
    }
    assert report.ir.citation_registry.citations
    assert any(v.kind == "NO_VALUE_ASSESSMENT" for v in report.ir.value_availability)
    assert report.ir.uncertainty_summary
    assert (
        case.repository.load_compiled_report(report.scope.assessment_id, report_id=report.report_id)
        == report
    )


def test_all_semantic_ports_unavailable_produces_full_report(acceptance_case):
    before = upstream_rows(acceptance_case)
    repository = ObservedRepository(acceptance_case)
    report = compile_report(acceptance_case, repository=repository)
    assert_complete(acceptance_case, report)
    assert repository.loaded == [report.report_id]
    assert all(b.origin == "DETERMINISTIC_FALLBACK" for s in report.ir.sections for b in s.blocks)
    assert not report.execution_refs
    assert upstream_rows(acceptance_case) == before


def test_generative_planner_writer_synthesis_survives_full_pipeline(acceptance_case):
    port = RecordedCompilerPort()
    report = compile_report(acceptance_case, port=port, options=generous_options())
    assert_complete(acceptance_case, report)
    assert all(b.origin == "GENERATIVE_ACCEPTED" for s in report.ir.sections for b in s.blocks)
    assert (
        report.ir.sections[1].question_plan.subsections[1].heading == "Configuration and residual"
    )
    assert (
        report.ir.sections[0].blocks[0].draft_block.text
        == "The proposal separates relay control from status display."
    )
    assert Counter(role for role, _ in port.calls) == {
        "plan": 1,
        "write": 9,
        "extract": 9,
        "verify": 9,
        "composition": 1,
    }


@pytest.mark.parametrize(
    "scenario", ["DIRECT", "PARTIAL_NEGATIVE", "POTENTIAL", "MIXED", "UNASSESSABLE"]
)
def test_direct_partial_potential_mixed_and_unassessable_compile(tmp_path, scenario):
    case = make_report_scenario(tmp_path, scenario)
    try:
        before = upstream_rows(case)
        report = compile_report(case)
        assert_complete(case, report)
        assert upstream_rows(case) == before
    finally:
        case.repository.close()


def test_all_configured_providers_fail_to_complete_fallback(acceptance_case):
    port = RecordedCompilerPort(failures={"plan", "write", "extract", "verify", "composition"})
    report = compile_report(acceptance_case, port=port, options=generous_options())
    assert_complete(acceptance_case, report)
    assert all(b.origin == "DETERMINISTIC_FALLBACK" for s in report.ir.sections for b in s.blocks)
    artifacts = acceptance_case.repository.load_report_artifacts(report.compilation_id)
    executions = [a.document for a in artifacts if a.kind == ReportArtifactKind.EXECUTION]
    assert executions and all(e.outcome == "PROVIDER_FAILURE" for e in executions)


def test_retry_replays_committed_sections_without_calls(acceptance_case):
    port = RecordedCompilerPort()
    repository = ObservedRepository(
        acceptance_case, port=port, crash_after=(ReportArtifactKind.VERIFICATION, 1)
    )
    with pytest.raises(SimulatedCrash):
        compile_report(
            acceptance_case, port=port, options=generous_options(), repository=repository
        )
    report = compile_report(
        acceptance_case, port=port, options=generous_options(), repository=repository
    )
    assert_complete(acceptance_case, report)
    for role in ("write", "extract", "verify"):
        assert port.calls.count((role, 1)) == 1
    assert all(b.origin == "GENERATIVE_ACCEPTED" for b in report.ir.sections[0].blocks)


@pytest.mark.parametrize("lens", list(ReportLens))
def test_new_model_lens_or_attempt_changes_report_not_adjudication(acceptance_case, lens):
    before = upstream_rows(acceptance_case)
    first = RecordedCompilerPort(model="model-a")
    second = RecordedCompilerPort(model="model-b")
    zero = ReportGenerationLimits(max_calls=0)
    a = compile_report(acceptance_case, port=first, token="a", options=ReportOptions(limits=zero))
    b = compile_report(
        acceptance_case, port=second, token="b", options=ReportOptions(lens=lens, limits=zero)
    )
    c = compile_report(
        acceptance_case, port=second, token="c", options=ReportOptions(lens=lens, limits=zero)
    )
    assert len({a.report_id, b.report_id, c.report_id}) == 3
    assert a.ir.generation_provenance.configuration != b.ir.generation_provenance.configuration
    for report in (a, b, c):
        assert report.ir.target_findings == acceptance_case.frozen.target_findings
        assert report.ir.source_dependency_manifest == acceptance_case.bundle.dependency_manifest
    assert upstream_rows(acceptance_case) == before
    assert not first.calls and not second.calls


@pytest.mark.parametrize(
    "limit",
    [dict(max_calls=0), dict(max_tokens=0), dict(max_cost_usd=0), dict(max_context_chars=0)],
)
def test_operational_limits_fallback_without_omission(acceptance_case, limit):
    port = RecordedCompilerPort()
    report = compile_report(
        acceptance_case, port=port, options=ReportOptions(limits=ReportGenerationLimits(**limit))
    )
    assert_complete(acceptance_case, report)
    assert not port.calls
    assert all(b.origin == "DETERMINISTIC_FALLBACK" for s in report.ir.sections for b in s.blocks)


def test_partial_outage_affects_only_unverified_content(acceptance_case):
    port = RecordedCompilerPort(failures={("write", 3)})
    report = compile_report(acceptance_case, port=port, options=generous_options())
    assert_complete(acceptance_case, report)
    for section in report.ir.sections:
        expected = "DETERMINISTIC_FALLBACK" if section.question_id == 3 else "GENERATIVE_ACCEPTED"
        assert {b.origin for b in section.blocks} == {expected}
    assert port.calls.count(("composition", None)) == 1


def test_limited_input_missing_meaning_cannot_gain_positive_report(tmp_path):
    case = make_report_scenario(tmp_path, "LIMITED")
    try:
        report = compile_report(case)
        assert_complete(case, report)
        target = next(f for f in report.ir.target_findings if f.target_id == "mcu_control")
        assert target.verdict.value == "UNASSESSABLE"
        assert case.bundle.input_needs
        assert any(i.upstream_kind == "INPUT_NEED" for i in report.ir.uncertainty_summary)
    finally:
        case.repository.close()


@pytest.mark.parametrize("stop", ["BUDGET_STOPPED", "PROVIDER_BLOCKED", "NO_NEW_YIELD"])
def test_budget_provider_no_yield_remain_distinct(tmp_path, stop):
    case = make_report_scenario(tmp_path, stop)
    try:
        report = compile_report(case)
        assert_complete(case, report)
        assert any(i.state == stop for i in report.ir.uncertainty_summary)
        assert not any(i.state == "SATURATED" for i in report.ir.uncertainty_summary)
        assert case.bundle.research_state.budget_usage.provider_calls == 7
    finally:
        case.repository.close()


def test_replay_after_acceptance_does_not_regenerate(acceptance_case):
    port = RecordedCompilerPort()
    report = compile_report(acceptance_case, port=port, options=generous_options())
    calls = list(port.calls)
    replay = compile_report(acceptance_case, port=port, options=generous_options())
    assert replay == report
    assert port.calls == calls
    statuses = [
        a.document
        for a in acceptance_case.repository.load_report_artifacts(report.compilation_id)
        if isinstance(a.document, ReportStatusEvent)
    ]
    assert Counter(s.next_state.value for s in statuses) == {
        "STARTED": 1,
        "PLANNED": 1,
        "DRAFTED": 1,
        "VERIFIED": 1,
        "ACCEPTED": 1,
    }


def test_zero_yield_successor_requires_its_own_report_scope(tmp_path):
    case = make_report_scenario(tmp_path, "ZERO_YIELD_SUCCESSOR")
    try:
        report = compile_report(case)
        assert_complete(case, report)
        assert case.frozen.superseded_context_ids
        assert report.scope.assessment_context_id not in case.frozen.superseded_context_ids
        assert any(i.historical for i in report.ir.uncertainty_summary)
        from novelty_harness.application.phase8 import compile_assessment_report

        with pytest.raises(ReportAuthorityError):
            asyncio.run(
                compile_assessment_report(
                    report.scope.assessment_id,
                    adjudication_id="absent-old-adjudication",
                    repository=case.repository,
                    options=ReportOptions(),
                )
            )
    finally:
        case.repository.close()


def test_direct_negative_retains_single_source_and_scoped_wording(tmp_path):
    case = make_report_scenario(tmp_path, "DIRECT")
    try:
        report = compile_report(case)
        assert any(
            f.verdict.value == "NOT_NOVEL_AT_CLAIMED_LEVEL" for f in report.ir.target_findings
        )
        assert all(
            w.target is not None and w.claim_scope
            for w in report.ir.supported_and_qualified_wording
        )
        assert (
            report.ir.citation_registry
            == case.repository.load_compiled_report(
                report.scope.assessment_id, report_id=report.report_id
            ).ir.citation_registry
        )
    finally:
        case.repository.close()


def test_potential_candidate_remains_scoped_without_value_upgrade(tmp_path):
    case = make_report_scenario(tmp_path, "POTENTIAL")
    try:
        report = compile_report(case)
        assert report.ir.target_findings[0].verdict.value == "POTENTIALLY_NOVEL"
        assert not any(
            v.kind == "AUTHORITATIVE_VALUE_FINDING" for v in report.ir.value_availability
        )
        assert report.ir.target_findings == case.frozen.target_findings
    finally:
        case.repository.close()


@pytest.mark.parametrize("cap", [dict(max_tokens=1), dict(max_cost_usd=1)])
def test_invocation_checks_budget_before_dispatch(acceptance_case, cap):
    from novelty_harness.application.phase8 import _configuration
    from novelty_harness.application.phase8_sections import invoke_report_operation
    from novelty_harness.reporting.drafts import SectionDraft, build_section_context
    from novelty_harness.reporting.models import ReportProposalError, ReportSemanticRole
    from novelty_harness.reporting.plan import build_coverage_plan

    port = RecordedCompilerPort(failures={"write"})
    limits = generous_options().limits.model_copy(update=cap)
    compilation = acceptance_case.repository.begin_report_compilation(
        acceptance_case.bundle.scope.assessment_id,
        adjudication_id=acceptance_case.frozen.adjudication_id,
        options=ReportOptions(limits=limits),
        configuration=_configuration(acceptance_case.bundle, ReportPorts(writer=port)),
        attempt_token="dispatch-budget",
    )
    context = build_section_context(
        acceptance_case.bundle,
        build_coverage_plan(acceptance_case.bundle, compilation),
        question_id=1,
        compilation=compilation,
    )
    with pytest.raises(ReportProposalError, match="budget"):
        asyncio.run(
            invoke_report_operation(
                compilation,
                acceptance_case.repository,
                port,
                ReportSemanticRole.WRITER,
                context,
                SectionDraft,
                lambda: port.write(context),
            )
        )
    assert not port.calls
    assert not any(
        a.kind == ReportArtifactKind.EXECUTION
        for a in acceptance_case.repository.load_report_artifacts(compilation.compilation_id)
    )


def test_schema_recovery_reserves_remaining_call_budget(acceptance_case):
    from novelty_harness.application.phase8 import _configuration
    from novelty_harness.application.phase8_model_adapter import ReportModelAdapter
    from novelty_harness.application.phase8_sections import invoke_report_operation
    from novelty_harness.ports.models import LLMCallConfig
    from novelty_harness.reporting.drafts import SectionDraft, build_section_context
    from novelty_harness.reporting.models import ReportProposalError, ReportSemanticRole
    from novelty_harness.reporting.plan import build_coverage_plan
    from novelty_harness.runtime.semantic.structured import SemanticRunner
    from tests.unit.reporting.test_execution import RecordedReportProvider

    provider = RecordedReportProvider()
    provider.payloads["SectionDraft"] = {"invalid": True}
    adapter = ReportModelAdapter(SemanticRunner(provider, LLMCallConfig(model="recorded-model")))
    compilation = acceptance_case.repository.begin_report_compilation(
        acceptance_case.bundle.scope.assessment_id,
        adjudication_id=acceptance_case.frozen.adjudication_id,
        options=generous_options().model_copy(
            update={"limits": generous_options().limits.model_copy(update={"max_calls": 1})}
        ),
        configuration=_configuration(acceptance_case.bundle, ReportPorts(writer=adapter)),
        attempt_token="recovery-budget",
    )
    context = build_section_context(
        acceptance_case.bundle,
        build_coverage_plan(acceptance_case.bundle, compilation),
        question_id=1,
        compilation=compilation,
    )
    with pytest.raises(ReportProposalError, match="budget"):
        asyncio.run(
            invoke_report_operation(
                compilation,
                acceptance_case.repository,
                adapter,
                ReportSemanticRole.WRITER,
                context,
                SectionDraft,
                lambda: adapter.write(context),
            )
        )
    assert not provider.calls


def test_unknown_usage_remains_unknown_and_cumulative_budget_stops_calls(acceptance_case):
    from novelty_harness.application.phase8 import _configuration
    from novelty_harness.application.phase8_sections import invoke_report_operation
    from novelty_harness.reporting.drafts import SectionDraft, build_section_context
    from novelty_harness.reporting.models import ReportProposalError, ReportSemanticRole
    from novelty_harness.reporting.plan import build_coverage_plan

    port = RecordedCompilerPort(failures={"write"})
    compilation = acceptance_case.repository.begin_report_compilation(
        acceptance_case.bundle.scope.assessment_id,
        adjudication_id=acceptance_case.frozen.adjudication_id,
        options=generous_options().model_copy(
            update={
                "limits": generous_options().limits.model_copy(update={"max_tokens": 200000000})
            }
        ),
        configuration=_configuration(acceptance_case.bundle, ReportPorts(writer=port)),
        attempt_token="unknown-usage-budget",
    )
    context = build_section_context(
        acceptance_case.bundle,
        build_coverage_plan(acceptance_case.bundle, compilation),
        question_id=1,
        compilation=compilation,
    )

    async def invoke():
        return await invoke_report_operation(
            compilation,
            acceptance_case.repository,
            port,
            ReportSemanticRole.WRITER,
            context,
            SectionDraft,
            lambda: port.write(context),
        )

    with pytest.raises(ReportProposalError, match="provider operation failed"):
        asyncio.run(invoke())
    with pytest.raises(ReportProposalError, match="budget"):
        asyncio.run(invoke())
    assert port.calls == [("write", 1)]
    records = [
        a.document
        for a in acceptance_case.repository.load_report_artifacts(compilation.compilation_id)
        if a.kind == ReportArtifactKind.EXECUTION
    ]
    assert len(records) == 1
    assert records[0].observations.tokens is None
    assert records[0].observations.cost_usd is None


@pytest.mark.parametrize("stage", [ReportArtifactKind.DRAFT, ReportArtifactKind.EXTRACTION])
def test_retry_reuses_each_committed_section_operation(acceptance_case, stage):
    port = RecordedCompilerPort()
    repository = ObservedRepository(acceptance_case, port=port, crash_after=(stage, 1))
    with pytest.raises(SimulatedCrash):
        compile_report(
            acceptance_case, port=port, options=generous_options(), repository=repository
        )
    repository.crash_after = (ReportArtifactKind.VERIFICATION, 1)
    with pytest.raises(SimulatedCrash):
        compile_report(
            acceptance_case, port=port, options=generous_options(), repository=repository
        )
    assert port.calls.count(("write", 1)) == 1
    assert port.calls.count(("extract", 1)) == 1
    assert port.calls.count(("verify", 1)) == 1


@pytest.mark.parametrize("failed", [False, True])
def test_retry_reuses_committed_planner_proposal(acceptance_case, failed):
    port = RecordedCompilerPort(failures={"plan"} if failed else ())
    repository = ObservedRepository(
        acceptance_case,
        port=port,
        crash_after=(
            ReportArtifactKind.EXECUTION if failed else ReportArtifactKind.PLAN_PROPOSAL,
            None,
        ),
    )
    with pytest.raises(SimulatedCrash):
        compile_report(
            acceptance_case, port=port, options=generous_options(), repository=repository
        )
    repository.crash_after = (ReportArtifactKind.DRAFT, 1)
    with pytest.raises(SimulatedCrash):
        compile_report(
            acceptance_case, port=port, options=generous_options(), repository=repository
        )
    assert port.calls.count(("plan", None)) == 1
    assert port.calls.count(("write", 1)) == 1
