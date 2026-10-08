"""Typed external-evidence escalation and context-bound continuation."""

from novelty_harness.adjudication.context import SealedAssessmentContext
from novelty_harness.adjudication.models import Phase7RunState
from novelty_harness.adjudication.needs import (
    GapDecision,
    GapEscalationPolicy,
    InputClarificationNeed,
    ResearchContinuation,
    ResearchEscalationBudget,
    ResearchEscalationOutcome,
    ResearchGapDisposition,
    ResearchGapRequest,
    classify_gap_origin,
    gap_input_clarification,
    remaining_research_allowance,
    route_need,
    validate_research_gap_request,
)
from novelty_harness.adjudication.packet import AdjudicationCasePacket, build_adjudication_case
from novelty_harness.adjudication.repository import (
    Phase7AdjudicationRepository,
    Phase7AuthorityError,
)
from novelty_harness.application.evidence_phase5 import Phase5EvidenceComponents
from novelty_harness.application.evidence_phase6 import GRAPH_REF, Phase6EvidenceComponents
from novelty_harness.application.phase7_roles import make_phase7_artifact
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.mapping.dimensions import build_combination_comparison_profile
from novelty_harness.ports.adjudication import ResearchEscalationPort
from novelty_harness.ports.content import ContentResolver
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.budgets.controller import DIMENSIONS, BudgetUsage
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.sinks import TraceSink


class Phase7ReviewedResearchAdapter:
    """Run a sealed, reviewed Phase 3 plan through the existing Phase 4–6 services."""

    def __init__(
        self,
        *,
        assessment: AssessmentRecord,
        phase4: Phase4ResearchComponents,
        phase5: Phase5EvidenceComponents | None,
        phase6: Phase6EvidenceComponents | None,
        writer: RunArtifactWriter,
        trace_sink: TraceSink,
        resolver: ContentResolver | None,
        repository: SqlAlchemyEvidenceGraphRepository,
    ) -> None:
        self.assessment = assessment
        self.phase4 = phase4
        self.phase5 = phase5
        self.phase6 = phase6
        self.writer = writer
        self.trace_sink = trace_sink
        self.resolver = resolver
        self.repository = repository

    async def execute(
        self, request: ResearchGapRequest, context: SealedAssessmentContext
    ) -> ResearchEscalationOutcome:
        """Return typed changed state; repository completion decides restart versus true no-op."""

        request = ResearchGapRequest.model_validate_json(request.model_dump_json())
        loaded_context = self.repository.load_phase7_context(
            context.assessment_id, context_id=context.context_id
        )
        if loaded_context != context:
            raise Phase7AuthorityError("Escalation context differs from repository state")
        manifest = context.manifest
        if (
            request.assessment_id != context.assessment_id
            or request.assessment_context_id != context.context_id
            or request.phase6_snapshot_id != context.snapshot_id
            or self.assessment.assessment_id != context.assessment_id
            or self.assessment.request.as_of != manifest.as_of
        ):
            raise Phase7AuthorityError(
                "Escalation request or assessment differs from sealed context"
            )
        plan = manifest.research_plan
        if plan is None or not plan.reviewed or plan.review is None:
            raise Phase7AuthorityError(
                "Escalation requires a repository-validated reviewed Phase 3 plan"
            )
        if manifest.coverage_policy is None or manifest.budget_limits is None:
            raise Phase7AuthorityError(
                "Escalation requires sealed coverage policy and budget limits"
            )
        if (
            self.phase4.coverage_policy != manifest.coverage_policy
            or self.phase4.budget_limits != manifest.budget_limits
        ):
            raise Phase7AuthorityError("Phase 4 configuration differs from sealed policy")
        graph = manifest.mcu_graph
        target = next((item for item in graph.mcus if item.mcu_id == request.target_id), None)
        combination = next(
            (
                item
                for item in graph.combinations
                if build_combination_comparison_profile(item, graph.mcus).target_id
                == request.target_id
            ),
            None,
        )
        if target is None and combination is None:
            raise Phase7AuthorityError("Research gap target is absent from the sealed graph")
        if target is not None:
            relevant_ids = {target.mcu_id}
        elif combination is not None:
            relevant_ids = set(combination.member_ids)
        else:
            raise Phase7AuthorityError("Research gap target is absent from the sealed graph")
        relevant = tuple(
            intent
            for intent in plan.intents
            if intent.mcu_id in relevant_ids
            and (combination is None or intent.combination_id == combination.combination_id)
            and (
                not request.evidence_families or intent.evidence_family in request.evidence_families
            )
        )
        if not relevant:
            raise Phase7AuthorityError("Reviewed Phase 3 plan lacks a query for the requested gap")
        allowance = remaining_research_allowance(context)
        if request.dispatch_allowance is not None:
            allowance = type(allowance).model_validate(
                {
                    name: min(a, b) if a is not None and b is not None else a if b is None else b
                    for name in type(allowance).model_fields
                    if name.startswith("max_")
                    for a, b in [
                        (getattr(allowance, name), getattr(request.dispatch_allowance, name))
                    ]
                }
            )
        research = await self.phase4.execute(
            assessment=self.assessment,
            mcus=graph.mcus,
            plan=plan,
            budget_allowance=allowance,
            trace_sink=self.trace_sink,
            writer=self.writer,
        )
        research = type(research).model_validate_json(research.model_dump_json())
        old_view = self.repository.load_phase6_assessment(
            context.assessment_id, snapshot_id=context.snapshot_id
        )
        snapshot_id = context.snapshot_id
        new_source_ids: tuple[str, ...] = ()
        if research.fused_candidates:
            if self.phase5 is None or self.phase6 is None:
                raise Phase7AuthorityError(
                    "New candidates require Phase 5 and Phase 6 verification"
                )
            expected_database = self.writer.assessment_dir(context.assessment_id) / GRAPH_REF
            if self.repository.engine.url.database != str(expected_database):
                raise Phase7AuthorityError(
                    "Phase 5/6 escalation must use the current evidence repository"
                )
            evidence = await self.phase5.execute(
                assessment=self.assessment,
                research=research,
                resolver=self.resolver,
                writer=self.writer,
                trace_sink=self.trace_sink,
            )
            if evidence.sources:
                verified = await self.phase6.execute(
                    assessment=self.assessment,
                    evidence=evidence,
                    mcus=graph.mcus,
                    combinations=graph.combinations,
                    as_of=manifest.as_of,
                    writer=self.writer,
                    trace_sink=self.trace_sink,
                )
                snapshot_id = verified.snapshot_id
                updated_view = self.repository.load_phase6_assessment(
                    context.assessment_id, snapshot_id=snapshot_id
                )
                if not set(old_view.commit_ids) <= set(updated_view.commit_ids):
                    raise Phase7AuthorityError(
                        "Phase 6 successor omitted committed earlier evidence"
                    )
                previously_verified = {
                    str(item.comparison.comparison.chain.source.source_id)
                    for item in old_view.committed_comparisons
                }
                if snapshot_id != context.snapshot_id:
                    new_source_ids = tuple(
                        sorted(
                            str(source.source_id)
                            for source in evidence.sources
                            if str(source.source_id) not in previously_verified
                        )
                    )
        attempted_query_ids = tuple(
            dict.fromkeys(str(event.compiled_query.query_id) for event in research.request_events)
        )
        providers = tuple(
            dict.fromkeys(event.compiled_query.provider_name for event in research.request_events)
        )
        access_failures = tuple(
            dict.fromkeys(
                failure for branch in research.branch_states for failure in branch.access_failures
            )
        )
        coverage_cells = tuple(cell.screening for cell in research.coverage_matrix)
        remaining_gaps = tuple(
            dict.fromkeys(gap for stop in research.stop_assessments for gap in stop.unresolved_gaps)
        )
        reasons = {stop.reason.value for stop in research.stop_assessments}
        stop_reason = (
            "BUDGET_STOPPED"
            if "BUDGET_STOPPED" in reasons
            else "ACCESS_BLOCKED"
            if "ACCESS_BLOCKED" in reasons
            else "SATURATED"
            if reasons == {"SATURATED"}
            else "NO_NEW_YIELD"
            if not new_source_ids
            else None
        )
        prior_usage = manifest.budget_usage or BudgetUsage()
        cumulative = BudgetUsage.model_validate(
            {
                name: getattr(prior_usage, name) + getattr(research.budget_usage, name)
                for name in DIMENSIONS
            }
        )
        updated_manifest = manifest.model_copy(
            update={
                "phase6_snapshot_id": snapshot_id,
                "research_result": research,
                "budget_usage": cumulative,
                "coverage_cells": coverage_cells,
                "query_history": manifest.query_history + attempted_query_ids,
                "providers_attempted": manifest.providers_attempted + providers,
                "access_failures": manifest.access_failures + access_failures,
                "remaining_gaps": remaining_gaps,
                "stop_reason": stop_reason,
                "unknown_upstream_artifacts": tuple(
                    name for name in manifest.unknown_upstream_artifacts if name != "phase4"
                ),
                "upstream_artifact_digests": {
                    **manifest.upstream_artifact_digests,
                    "research_result": canonical_hash(research),
                },
            }
        )
        return ResearchEscalationOutcome(
            request_id=request.request_id,
            assessment_id=context.assessment_id,
            assessment_context_id=context.context_id,
            phase6_snapshot_id=context.snapshot_id,
            updated_snapshot_id=snapshot_id,
            updated_manifest=updated_manifest,
            attempted_query_ids=attempted_query_ids,
            providers_attempted=updated_manifest.providers_attempted,
            access_failures=updated_manifest.access_failures,
            coverage_cells=coverage_cells,
            remaining_gaps=remaining_gaps,
            new_source_ids=new_source_ids,
            budget_usage=cumulative,
            stop_reason=stop_reason,
            cost=research.budget_usage,
        )


def complete_research_escalation(
    run_id: str,
    outcome: ResearchEscalationOutcome,
    repository: Phase7AdjudicationRepository,
) -> ResearchContinuation:
    """Apply one completed outcome in the repository's atomic successor transaction."""

    return repository.complete_phase7_research(run_id, outcome)


async def dispatch_research_gap(
    run_id: str,
    need: InputClarificationNeed | ResearchGapRequest,
    packet: AdjudicationCasePacket,
    budget: ResearchEscalationBudget,
    port: ResearchEscalationPort,
    repository: Phase7AdjudicationRepository,
) -> GapDecision | ResearchContinuation:
    """Route only accepted external gaps through the reviewed research port."""

    if isinstance(need, InputClarificationNeed):
        route_need(need)
        return GapDecision(
            request_id=need.need_id,
            status="INPUT_RESOLUTION",
            reason="Claim input requires clarification before prior-art research",
            material_gate="A",
        )
    route_need(need)
    if classify_gap_origin(need, packet) == "INPUT_MEANING_GAP":
        clarification = gap_input_clarification(need)
        return GapDecision(
            request_id=need.request_id,
            status="INPUT_RESOLUTION",
            reason=clarification.resolution_requirement,
            material_gate="A",
        )
    request = validate_research_gap_request(need, packet)
    budget = ResearchEscalationBudget.model_validate_json(budget.model_dump_json())
    run = repository.load_phase7_run(run_id)
    context = repository.load_phase7_context(
        run.assessment_id, context_id=run.assessment_context_id
    )
    authoritative_packet = build_adjudication_case(
        context,
        repository.load_phase6_assessment(run.assessment_id, snapshot_id=run.phase6_snapshot_id),
    )
    if (
        run.case_id != packet.case_id
        or canonical_hash(packet) != canonical_hash(authoritative_packet)
        or run.state not in {Phase7RunState.FIRST_PASSES_COMPLETE, Phase7RunState.JUDGING}
    ):
        raise Phase7AuthorityError("Research gap is not bound to completed first passes")
    decision = GapEscalationPolicy().decide(request, context, budget, packet=authoritative_packet)
    request = request.model_copy(
        update={"dispatch_allowance": remaining_research_allowance(context, budget)}
    )
    repository.record_phase7_artifact(run_id, make_phase7_artifact(run_id, "RESEARCH_GAP", request))
    disposition = ResearchGapDisposition(
        assessment_id=request.assessment_id,
        assessment_context_id=request.assessment_context_id,
        phase6_snapshot_id=request.phase6_snapshot_id,
        target_id=request.target_id,
        request_id=request.request_id,
        status=decision.status,
        reason=decision.reason,
        budget=budget,
    )
    repository.record_phase7_artifact(
        run_id, make_phase7_artifact(run_id, "RESEARCH_GAP_DISPOSITION", disposition)
    )
    if decision.status != "ACCEPT":
        return decision
    repository.transition_phase7_run(
        run_id,
        expected_state=run.state,
        next_state=Phase7RunState.ESCALATION_PENDING,
    )
    try:
        outcome = await port.execute(request, context)
        outcome = ResearchEscalationOutcome.model_validate_json(outcome.model_dump_json())
        if (
            outcome.request_id != request.request_id
            or outcome.assessment_id != request.assessment_id
            or outcome.assessment_context_id != request.assessment_context_id
            or outcome.phase6_snapshot_id != request.phase6_snapshot_id
        ):
            raise Phase7AuthorityError("Research outcome differs from accepted request")
        allowance = request.dispatch_allowance
        if allowance is not None and any(
            getattr(allowance, "max_" + dimension) is not None
            and getattr(outcome.cost, dimension) > getattr(allowance, "max_" + dimension)
            for dimension in DIMENSIONS
        ):
            raise Phase7AuthorityError("Research outcome exceeded its reserved allowance")
        return complete_research_escalation(run_id, outcome, repository)
    except Exception:
        if repository.load_phase7_run(run_id).state == Phase7RunState.ESCALATION_PENDING:
            repository.transition_phase7_run(
                run_id,
                expected_state=Phase7RunState.ESCALATION_PENDING,
                next_state=Phase7RunState.FAILED,
            )
        raise
