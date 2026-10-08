"""Compile a report from exact repository locators, then return authoritative readback."""

from datetime import UTC, datetime
from typing import cast

from novelty_harness.application.phase8_execution import actual_port_configuration
from novelty_harness.application.phase8_sections import (
    assure_report_composition,
    assure_report_section,
    invoke_report_operation,
    record_section_artifact,
)
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.ports.reporting import ReportPorts
from novelty_harness.reporting.artifacts import (
    ReportArtifact,
    ReportArtifactKind,
    ReportAttemptState,
    ReportCompilationRecord,
    ReportStatusEvent,
    report_status_event_id,
)
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.citations import build_citation_registry
from novelty_harness.reporting.drafts import build_section_context
from novelty_harness.reporting.execution import (
    ReportCompilationConfiguration,
    ReportExecutionRecord,
    approved_role_configuration,
)
from novelty_harness.reporting.ir import CompiledAssessmentReport, build_report_ir, report_id
from novelty_harness.reporting.models import (
    QuestionId,
    ReportOptions,
    ReportSemanticRole,
)
from novelty_harness.reporting.plan import (
    ReportPlan,
    ReportPlanProposal,
    build_coverage_plan,
    build_planner_context,
    validate_report_plan,
)
from novelty_harness.reporting.repository import ReportAuthorityError, ReportRepository
from novelty_harness.runtime.tracing.hashing import canonical_json


def _state(artifacts: tuple[ReportArtifact, ...]) -> ReportStatusEvent:
    events = tuple(a.document for a in artifacts if isinstance(a.document, ReportStatusEvent))
    successors = {e.predecessor_id for e in events if e.predecessor_id is not None}
    terminal = tuple(e for e in events if e.event_id not in successors)
    if len(terminal) != 1:
        raise ReportAuthorityError("compilation has no unique current status")
    return terminal[0]


def _advance(
    compilation: ReportCompilationRecord,
    repository: ReportRepository,
    state: ReportAttemptState,
) -> None:
    previous = _state(repository.load_report_artifacts(compilation.compilation_id))
    event = ReportStatusEvent(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        event_id="pending",
        predecessor_id=previous.event_id,
        expected_state=previous.next_state,
        next_state=state,
        reason="Completed committed reporting stage",
        observed_at=datetime.now(UTC),
    )
    event = event.model_copy(update={"event_id": report_status_event_id(event)})
    record_section_artifact(
        compilation, repository, ReportArtifactKind.STATUS, event, "p8-bundle-v1"
    )


def _configuration(bundle: ReportInputBundle, ports: ReportPorts) -> ReportCompilationConfiguration:
    selected = {
        ReportSemanticRole.PLANNER: ports.planner,
        ReportSemanticRole.WRITER: ports.writer,
        ReportSemanticRole.EXTRACTOR: ports.extractor,
        ReportSemanticRole.VERIFIER: ports.verifier,
        ReportSemanticRole.COMPOSITION: ports.verifier,
        ReportSemanticRole.REPAIR: ports.writer,
    }
    return ReportCompilationConfiguration(
        roles=tuple(
            approved_role_configuration(
                bundle.scope, "pending", role, actual_port_configuration(port)
            )
            for role, port in selected.items()
        )
    )


async def _plan(
    compilation: ReportCompilationRecord,
    bundle: ReportInputBundle,
    ports: ReportPorts,
    repository: ReportRepository,
) -> ReportPlan:
    artifacts = repository.load_report_artifacts(compilation.compilation_id)
    plans = tuple(a.document for a in artifacts if isinstance(a.document, ReportPlan))
    if len(plans) > 1:
        raise ReportAuthorityError("compilation has multiple committed plans")
    if plans:
        return plans[0]
    plan = build_coverage_plan(bundle, compilation)
    proposals = tuple(a.document for a in artifacts if isinstance(a.document, ReportPlanProposal))
    if len(proposals) > 1:
        raise ReportAuthorityError("compilation has multiple committed planner proposals")
    if proposals:
        try:
            plan = validate_report_plan(proposals[0], bundle, compilation.options)
        except ValueError:
            pass
    planner = ports.planner
    limits = compilation.options.limits
    dispatched = any(
        isinstance(a.document, ReportExecutionRecord)
        and a.document.role == ReportSemanticRole.PLANNER
        for a in artifacts
    )
    if (
        not proposals
        and not dispatched
        and planner is not None
        and limits.max_calls
        and limits.max_tokens
        and limits.max_cost_usd != 0
    ):
        context = build_planner_context(bundle, compilation)
        if len(canonical_json(context)) <= limits.max_context_chars:
            try:
                proposal, execution_ref = await invoke_report_operation(
                    compilation,
                    repository,
                    planner,
                    ReportSemanticRole.PLANNER,
                    context,
                    ReportPlanProposal,
                    lambda: planner.plan(context, compilation.options),
                )
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.PLAN_PROPOSAL,
                    proposal,
                    "p8-plan-v1",
                    execution_ref=execution_ref,
                )
                plan = validate_report_plan(proposal, bundle, compilation.options)
            except ReportAuthorityError:
                raise
            except (ValueError, RuntimeError):
                pass
    record_section_artifact(
        compilation, repository, ReportArtifactKind.PLAN, plan, "p8-plan-firewall-v1"
    )
    return plan


async def compile_assessment_report(
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
    repository: ReportRepository,
    ports: ReportPorts | None = None,
    options: ReportOptions,
    attempt_token: str | None = None,
) -> CompiledAssessmentReport:
    """A separate presentation attempt never reopens evidence or adjudication."""
    selected = ports or ReportPorts()
    bundle = repository.load_report_input_bundle(assessment_id, adjudication_id=adjudication_id)
    compilation = repository.begin_report_compilation(
        assessment_id,
        adjudication_id=adjudication_id,
        options=options,
        configuration=_configuration(bundle, selected),
        attempt_token=attempt_token,
    )
    current = _state(repository.load_report_artifacts(compilation.compilation_id))
    if current.next_state == ReportAttemptState.ACCEPTED:
        prefix = "Accepted compiled report "
        if not current.reason.startswith(prefix):
            raise ReportAuthorityError("accepted compilation has no exact report locator")
        return repository.load_compiled_report(
            assessment_id, report_id=current.reason[len(prefix) :]
        )
    if current.next_state == ReportAttemptState.FAILED:
        raise ReportAuthorityError("failed compilation requires a new attempt token")
    for role in compilation.configuration.roles:
        if role.port.mode != "NOT_CONFIGURED":
            record_section_artifact(
                compilation,
                repository,
                ReportArtifactKind.METHOD,
                role.method,
                role.method_version,
            )
            record_section_artifact(
                compilation,
                repository,
                ReportArtifactKind.CONFIGURATION,
                role,
                role.method_version,
            )
    plan = await _plan(compilation, bundle, selected, repository)
    if current.next_state == ReportAttemptState.STARTED:
        _advance(compilation, repository, ReportAttemptState.PLANNED)
    limits = options.limits
    generation = (
        selected
        if limits.max_calls and limits.max_tokens and limits.max_cost_usd != 0
        else ReportPorts()
    )
    sections = tuple(
        [
            await assure_report_section(
                compilation,
                build_section_context(
                    bundle, plan, question_id=cast(QuestionId, question), compilation=compilation
                ),
                bundle=bundle,
                plan=plan,
                ports=generation,
                repository=repository,
            )
            for question in range(1, 10)
        ]
    )
    if (
        _state(repository.load_report_artifacts(compilation.compilation_id)).next_state
        == ReportAttemptState.PLANNED
    ):
        _advance(compilation, repository, ReportAttemptState.DRAFTED)
    sections = await assure_report_composition(
        compilation, sections, bundle=bundle, ports=generation, repository=repository
    )
    current = _state(repository.load_report_artifacts(compilation.compilation_id))
    if current.next_state == ReportAttemptState.DRAFTED:
        _advance(compilation, repository, ReportAttemptState.VERIFIED)
    artifacts = repository.load_report_artifacts(compilation.compilation_id)
    citations = build_citation_registry(sections, bundle)
    ir = build_report_ir(bundle, compilation, sections, citations, artifacts)
    provenance = ir.generation_provenance
    proposed = CompiledAssessmentReport(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        report_id="pending",
        ir=ir,
        dependencies=(*ir.source_dependency_manifest, *ir.report_artifact_dependencies),
        approved_versions=provenance.approved_versions,
        configuration_refs=provenance.configuration_refs,
        execution_refs=provenance.execution_refs,
        accepted_at=datetime.now(UTC),
    )
    proposed = proposed.model_copy(update={"report_id": report_id(proposed)})
    accepted_id = repository.accept_compiled_report(compilation.compilation_id, proposed)
    return repository.load_compiled_report(assessment_id, report_id=accepted_id)
