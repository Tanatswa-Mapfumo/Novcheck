"""Real repository-backed Phase 7 lifecycle tests, extended task by task."""

import asyncio
from typing import cast

import pytest
from sqlalchemy import event, text

from novelty_harness.adjudication.models import Phase7RunState
from novelty_harness.adjudication.needs import (
    GapDecision,
    InputClarificationNeed,
    ResearchContinuation,
    ResearchEscalationBudget,
    ResearchEscalationOutcome,
    ResearchGapRequest,
)
from novelty_harness.adjudication.packet import build_adjudication_case
from novelty_harness.adjudication.repository import Phase7AuthorityError
from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase
from novelty_harness.application.phase7_research import (
    Phase7ReviewedResearchAdapter,
    complete_research_escalation,
    dispatch_research_gap,
)
from novelty_harness.application.phase7_roles import (
    make_phase7_artifact,
    run_independent_first_passes,
)
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.domain.assessment import AssessmentRecord, AssessmentRequest
from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.mapping.dimensions import build_combination_comparison_profile
from novelty_harness.research.adaptive.pipeline import ResearchResult
from novelty_harness.research.coverage import CoverageCell, CoveragePolicy, CoverageState
from novelty_harness.research.models import (
    EvidenceFamilyAssessment,
    FamilyApplicability,
    ResearchPlan,
    SearchIntent,
    SearchPlanReview,
)
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.budgets.controller import BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.integration.test_phase6_evidence_pipeline import graph_database
from tests.unit.adjudication.test_roles import _committed_dispute_run, scope


def test_research_only_change_restarts_roles(tmp_path) -> None:
    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    target_id = next(item.target_id for item in packet.target_profiles if item.target_kind == "MCU")
    request = ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_zero_yield",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="One planned branch has not been screened",
        research_hypothesis="An external terminology branch may reveal a direct relation",
        evidence_families=(EvidenceFamily.SCHOLARLY,),
        material_gate="B",
        priority="HIGH",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    changed_usage = BudgetUsage(provider_calls=1)
    changed_cell = CoverageCell(
        mcu_id=target_id,
        evidence_family=EvidenceFamily.SCHOLARLY,
        state=CoverageState.DEGRADED,
        planned_query_families=frozenset(),
        configured_providers=("scripted-provider",),
        inspected_results=0,
        limitations=("Zero new yield",),
    )
    updated_manifest = context.manifest.model_copy(
        update={
            "budget_usage": changed_usage,
            "coverage_cells": (changed_cell,),
            "query_history": ("qry_zero_yield",),
            "providers_attempted": ("scripted-provider",),
            "stop_reason": "NO_NEW_YIELD",
        }
    )
    outcome = ResearchEscalationOutcome(
        request_id=request.request_id,
        assessment_id=packet.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        updated_snapshot_id=context.snapshot_id,
        updated_manifest=updated_manifest,
        attempted_query_ids=("qry_zero_yield",),
        providers_attempted=("scripted-provider",),
        coverage_cells=(changed_cell,),
        new_source_ids=(),
        budget_usage=changed_usage,
        stop_reason="NO_NEW_YIELD",
        cost=changed_usage,
    )

    class ZeroYieldPort:
        calls = 0

        async def execute(self, given_request, given_context):
            self.calls += 1
            assert given_request.model_copy(update={"dispatch_allowance": None}) == request
            assert given_request.dispatch_allowance.max_provider_calls == 3
            assert given_context == context
            return outcome

    port = ZeroYieldPort()
    budget = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=3),
        usage=BudgetUsage(),
        max_requests=2,
    )
    try:
        continuation = asyncio.run(
            dispatch_research_gap(run.run_id, request, packet, budget, port, repository)
        )
        assert isinstance(continuation, ResearchContinuation)
        assert continuation.restarted
        assert continuation.context.context_id != context.context_id
        assert continuation.context.snapshot_id == context.snapshot_id
        assert (
            repository.load_phase7_run(run.run_id).state
            == Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE
        )
        assert port.calls == 1
        successor_packet = build_adjudication_case(
            continuation.context,
            repository.load_phase6_assessment(
                packet.assessment_id, snapshot_id=continuation.context.snapshot_id
            ),
        )
        calls: list[str] = []
        for current_target in sorted(successor_packet.target_ids):

            class Prosecutor:
                async def propose(self, given):
                    calls.append("prosecutor")
                    return ProsecutionCase(
                        **scope(successor_packet, current_target),
                        case_id=f"p7prosecution_restart_{current_target}",
                        challenges=(),
                    )

            class Defender:
                async def propose(self, given):
                    calls.append("defender")
                    return DefenseCase(
                        **scope(successor_packet, current_target),
                        case_id=f"p7defense_restart_{current_target}",
                        points=(),
                    )

            asyncio.run(
                run_independent_first_passes(
                    continuation.run_id,
                    successor_packet,
                    Prosecutor(),
                    Defender(),
                    repository,
                )
            )
        assert len(calls) == 2 * len(successor_packet.target_ids)
        assert (
            repository.load_phase7_run(continuation.run_id).state
            == Phase7RunState.FIRST_PASSES_COMPLETE
        )
        assert all(
            item.assessment_context_id == continuation.context.context_id
            for item in repository.load_phase7_artifacts(continuation.run_id)
        )
    finally:
        repository.close()


def test_proven_true_noop_resumes_same_run(tmp_path) -> None:
    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    target_id = next(item.target_id for item in packet.target_profiles if item.target_kind == "MCU")
    request = ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_noop",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="Check whether the external branch is still available",
        research_hypothesis="The branch may be accessible",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    outcome = ResearchEscalationOutcome(
        request_id=request.request_id,
        assessment_id=packet.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        updated_snapshot_id=context.snapshot_id,
        updated_manifest=context.manifest,
        budget_usage=BudgetUsage(),
        cost=BudgetUsage(),
    )

    class NoOpPort:
        async def execute(self, given_request, given_context):
            return outcome

    try:
        continuation = asyncio.run(
            dispatch_research_gap(
                run.run_id,
                request,
                packet,
                ResearchEscalationBudget(
                    limits=BudgetLimits(max_provider_calls=1),
                    usage=BudgetUsage(),
                    max_requests=1,
                ),
                NoOpPort(),
                repository,
            )
        )
        assert isinstance(continuation, ResearchContinuation)
        assert not continuation.restarted
        assert continuation.run_id == run.run_id
        assert continuation.context == context
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.FIRST_PASSES_COMPLETE
        artifacts = repository.load_phase7_artifacts(run.run_id)
        assert sum(a.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"} for a in artifacts) == (
            2 * len(packet.target_ids)
        )
        assert sum(a.kind == "RESEARCH_GAP" for a in artifacts) == 1
        assert sum(a.kind == "RESEARCH_GAP_DISPOSITION" for a in artifacts) == 1
    finally:
        repository.close()


def test_gate_a_request_never_reaches_research_port(tmp_path) -> None:
    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    need = InputClarificationNeed(
        **scope(packet, next(iter(packet.target_ids))),
        need_id="p7need_topology",
        reason="Claimed topology is missing",
        missing_input_fields=("topology",),
        resolution_requirement="Clarify the claim structure",
    )

    class NeverSearch:
        calls = 0

        async def execute(self, request, context):
            self.calls += 1
            raise AssertionError("Gate A cannot dispatch external research")

    port = NeverSearch()
    try:
        decision = asyncio.run(
            dispatch_research_gap(
                run.run_id,
                need,
                packet,
                ResearchEscalationBudget(
                    limits=BudgetLimits(max_provider_calls=1),
                    usage=BudgetUsage(),
                    max_requests=1,
                ),
                port,
                repository,
            )
        )
        assert isinstance(decision, GapDecision)
        assert decision.status == "INPUT_RESOLUTION"
        assert port.calls == 0
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.FIRST_PASSES_COMPLETE
    finally:
        repository.close()


def test_provider_blocked_research_state_restarts_without_source(tmp_path) -> None:
    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    target_id = next(item.target_id for item in packet.target_profiles if item.target_kind == "MCU")
    request = ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_access_blocked",
        requesting_stage="FIRST_PASS",
        gap_type="ACCESS",
        reason="An external historical source remains inaccessible",
        research_hypothesis="Access may reveal the prior relationship",
        material_gate="C",
        stop_condition="CLOSE_ACCESS_GAP",
    )
    updated = context.manifest.model_copy(
        update={"access_failures": ("archive blocked",), "stop_reason": "ACCESS_BLOCKED"}
    )
    outcome = ResearchEscalationOutcome(
        request_id=request.request_id,
        assessment_id=packet.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        updated_snapshot_id=context.snapshot_id,
        updated_manifest=updated,
        access_failures=("archive blocked",),
        budget_usage=BudgetUsage(),
        stop_reason="ACCESS_BLOCKED",
        cost=BudgetUsage(),
    )

    class BlockedPort:
        async def execute(self, given_request, given_context):
            return outcome

    try:
        continuation = asyncio.run(
            dispatch_research_gap(
                run.run_id,
                request,
                packet,
                ResearchEscalationBudget(
                    limits=BudgetLimits(max_provider_calls=2), usage=BudgetUsage(), max_requests=1
                ),
                BlockedPort(),
                repository,
            )
        )
        assert isinstance(continuation, ResearchContinuation)
        assert continuation.restarted
        assert continuation.context.snapshot_id == context.snapshot_id
        assert continuation.context.context_id != context.context_id
        assert continuation.context.manifest.stop_reason == "ACCESS_BLOCKED"
    finally:
        repository.close()


def test_research_outcome_cannot_rewrite_cir(tmp_path) -> None:
    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    target_id = next(item.target_id for item in packet.target_profiles if item.target_kind == "MCU")
    request = ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_rewrite_input",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="Check an external branch",
        research_hypothesis="External source might clarify prior art",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    changed_cir = context.manifest.cir.model_copy(
        update={"original_input": "A different user claim inserted by research"}
    )
    outcome = ResearchEscalationOutcome(
        request_id=request.request_id,
        assessment_id=packet.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        updated_snapshot_id=context.snapshot_id,
        updated_manifest=context.manifest.model_copy(update={"cir": changed_cir}),
        budget_usage=BudgetUsage(),
        cost=BudgetUsage(),
    )

    class RewritePort:
        async def execute(self, given_request, given_context):
            return outcome

    try:
        with pytest.raises(Phase7AuthorityError, match="rewrite"):
            asyncio.run(
                dispatch_research_gap(
                    run.run_id,
                    request,
                    packet,
                    ResearchEscalationBudget(
                        limits=BudgetLimits(max_provider_calls=1),
                        usage=BudgetUsage(),
                        max_requests=1,
                    ),
                    RewritePort(),
                    repository,
                )
            )
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.FAILED
    finally:
        repository.close()


def test_research_successor_write_rolls_back_context_and_supersession(tmp_path) -> None:
    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    target_id = next(item.target_id for item in packet.target_profiles if item.target_kind == "MCU")
    request = ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_atomic_restart",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="External branch remains open",
        research_hypothesis="The branch may hold an earlier relationship",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    changed = context.manifest.model_copy(update={"stop_reason": "NO_NEW_YIELD"})
    outcome = ResearchEscalationOutcome(
        request_id=request.request_id,
        assessment_id=packet.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        updated_snapshot_id=context.snapshot_id,
        updated_manifest=changed,
        budget_usage=BudgetUsage(),
        stop_reason="NO_NEW_YIELD",
        cost=BudgetUsage(),
    )
    from novelty_harness.adjudication.needs import (
        GapEscalationPolicy,
        ResearchGapDisposition,
        remaining_research_allowance,
    )

    budget = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=1), usage=BudgetUsage(), max_requests=1
    )
    budget = ResearchEscalationBudget.model_validate_json(budget.model_dump_json())
    decision = GapEscalationPolicy().decide(request, context, budget, packet=packet)
    request = request.model_copy(
        update={"dispatch_allowance": remaining_research_allowance(context, budget)}
    )
    repository.record_phase7_artifact(
        run.run_id, make_phase7_artifact(run.run_id, "RESEARCH_GAP", request)
    )
    disposition = ResearchGapDisposition(
        **scope(packet, target_id),
        request_id=request.request_id,
        status=decision.status,
        reason=decision.reason,
        budget=budget,
    )
    repository.record_phase7_artifact(
        run.run_id, make_phase7_artifact(run.run_id, "RESEARCH_GAP_DISPOSITION", disposition)
    )
    repository.transition_phase7_run(
        run.run_id,
        expected_state=Phase7RunState.FIRST_PASSES_COMPLETE,
        next_state=Phase7RunState.ESCALATION_PENDING,
    )

    def reject_successor_run(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO phase7_runs"):
            raise RuntimeError("injected successor write failure")

    event.listen(repository.engine, "before_cursor_execute", reject_successor_run)
    try:
        with pytest.raises(RuntimeError, match="injected successor"):
            complete_research_escalation(run.run_id, outcome, repository)
    finally:
        event.remove(repository.engine, "before_cursor_execute", reject_successor_run)
    try:
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.ESCALATION_PENDING
        with repository.engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM phase7_assessment_contexts")) == 1
            assert connection.scalar(text("SELECT count(*) FROM phase7_runs")) == 1
            assert connection.scalar(text("SELECT count(*) FROM phase7_run_transitions")) == 3
    finally:
        repository.close()


def test_reviewed_research_adapter_refuses_unvalidated_phase3_history(tmp_path) -> None:
    packet, repository, _, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    target_id = next(item.target_id for item in packet.target_profiles if item.target_kind == "MCU")
    request = ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_no_reviewed_plan",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="Another source family may be relevant",
        research_hypothesis="A specific external branch might reveal a relation",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    calls: list[str] = []

    class NeverRunPhase4:
        async def execute(self, **kwargs):
            calls.append("phase4")
            raise AssertionError("Unvalidated Phase 3 history cannot dispatch Phase 4")

    assessment = AssessmentRecord(
        assessment_id=packet.assessment_id,
        request=AssessmentRequest(
            idea_id=context.manifest.cir.idea_id,
            input_text=context.manifest.cir.original_input,
            as_of=context.manifest.as_of,
        ),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    adapter = Phase7ReviewedResearchAdapter(
        assessment=assessment,
        phase4=cast(Phase4ResearchComponents, NeverRunPhase4()),
        phase5=None,
        phase6=None,
        writer=RunArtifactWriter(tmp_path),
        trace_sink=InMemoryTraceSink(),
        resolver=None,
        repository=repository,
    )
    try:
        with pytest.raises(Phase7AuthorityError, match="reviewed Phase 3"):
            asyncio.run(adapter.execute(request, context))
        assert calls == []
    finally:
        repository.close()


@pytest.mark.parametrize(
    "combination_target,prior_calls,real_phase4",
    ((False, 0, False), (False, 1, False), (True, 0, False), (True, 1, False), (False, 1, True)),
)
def test_reviewed_research_adapter_seals_zero_yield_phase4_result(
    tmp_path, combination_target: bool, prior_calls: int, real_phase4: bool
) -> None:
    packet, repository, _, _, _, _ = _committed_dispute_run(tmp_path)
    old_context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    graph = old_context.manifest.mcu_graph
    mcu_id = graph.mcus[0].mcu_id
    combination_id = graph.combinations[0].combination_id if combination_target else None
    target_id = (
        build_combination_comparison_profile(graph.combinations[0], graph.mcus).target_id
        if combination_target
        else mcu_id
    )
    draft = ResearchPlan(
        assessment_id=packet.assessment_id,
        as_of=old_context.manifest.as_of,
        mcu_ids=tuple(item.mcu_id for item in graph.mcus),
        combination_ids=tuple(item.combination_id for item in graph.combinations),
        family_assessments=(
            EvidenceFamilyAssessment(
                mcu_id=mcu_id,
                evidence_family=EvidenceFamily.SCHOLARLY,
                applicability=FamilyApplicability.APPLICABLE,
                rationale="Research branch remains relevant",
            ),
        ),
        intents=(
            SearchIntent(
                query_id="qry_phase7_reviewed",
                mcu_id=mcu_id,
                combination_id=combination_id,
                evidence_family=EvidenceFamily.SCHOLARLY,
                query_family=QueryFamily.DIRECT_CANONICAL,
                text="reviewed historical relationship",
                rationale="Test the identified branch",
                concepts=("relationship",),
            ),
        ),
    )
    if real_phase4:
        draft = draft.model_copy(
            update={
                "intents": (
                    *draft.intents,
                    draft.intents[0].model_copy(
                        update={
                            "query_id": "qry_phase7_second",
                            "text": "functional historical alternative",
                            "query_family": QueryFamily.FUNCTIONAL,
                        }
                    ),
                )
            }
        )
    plan = ResearchPlan.model_validate_json(
        draft.model_copy(
            update={
                "reviewed": True,
                "review_id": "review_phase7",
                "review": SearchPlanReview(
                    review_id="review_phase7",
                    plan_hash=draft.content_hash(),
                    status="PASS",
                    issues=(),
                    critic_prompt_version="test-review-v1",
                ),
            }
        ).model_dump_json()
    )
    policy = CoveragePolicy.standard()
    limits = BudgetLimits(max_provider_calls=2)
    context = repository.seal_phase7_context(
        packet.assessment_id,
        snapshot_id=old_context.snapshot_id,
        parent_context_id=old_context.context_id,
        manifest=old_context.manifest.model_copy(
            update={
                "research_plan": plan,
                "coverage_policy": policy,
                "budget_limits": limits,
                "budget_usage": BudgetUsage(provider_calls=prior_calls),
                "unknown_upstream_artifacts": ("phase4",),
            }
        ),
    )
    request = ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        target_id=target_id,
        request_id="p7gap_reviewed_zero_yield",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="Reviewed branch remains unsearched",
        research_hypothesis="Search may reveal an earlier relation",
        material_gate="B",
        evidence_families=(EvidenceFamily.SCHOLARLY,),
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    zero_result = ResearchResult(
        batches=(),
        fused_candidates=(),
        candidate_clusters=(),
        chronology={},
        temporal_assessments={},
        branch_states=(),
        stop_assessments=(),
        coverage_matrix=(),
        expansion_events=(),
        request_events=(),
        budget_usage=BudgetUsage(),
        limitations=("No source returned",),
    )

    class Phase4Stub:
        coverage_policy = policy
        budget_limits = limits
        calls = 0

        async def execute(self, **kwargs):
            self.calls += 1
            assert kwargs["plan"] == plan
            assert kwargs.get("budget_allowance", limits).max_provider_calls == 2 - prior_calls
            return zero_result

    phase4 = Phase4Stub()
    assessment = AssessmentRecord(
        assessment_id=packet.assessment_id,
        request=AssessmentRequest(
            idea_id=context.manifest.cir.idea_id,
            input_text=context.manifest.cir.original_input,
            as_of=context.manifest.as_of,
        ),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    adapter = Phase7ReviewedResearchAdapter(
        assessment=assessment,
        phase4=cast(Phase4ResearchComponents, phase4),
        phase5=None,
        phase6=None,
        writer=RunArtifactWriter(tmp_path),
        trace_sink=InMemoryTraceSink(),
        resolver=None,
        repository=repository,
    )
    try:
        if real_phase4:
            import httpx

            from tests.fixtures.phase4 import registry, stop_policy

            calls = []

            def empty_wire(query):
                calls.append(query)
                if query.url.host == "api.openalex.org":
                    return httpx.Response(
                        200, json={"meta": {"count": 0, "next_cursor": None}, "results": []}
                    )
                if query.url.host == "api.crossref.org":
                    return httpx.Response(
                        200,
                        json={
                            "status": "ok",
                            "message-type": "work-list",
                            "message-version": "1.0.0",
                            "message": {"items": [], "total-results": 0},
                        },
                    )
                if query.url.host == "api.github.com":
                    return httpx.Response(200, json={"items": [], "total_count": 0})
                return httpx.Response(200, json={"data": [], "total": 0, "offset": 0})

            async def execute_real():
                async with httpx.AsyncClient(transport=httpx.MockTransport(empty_wire)) as client:
                    providers, _ = registry(client)
                    adapter.phase4 = Phase4ResearchComponents(
                        providers, policy, limits, stop_policy()
                    )
                    return await adapter.execute(request, context)

            outcome = asyncio.run(execute_real())
            assert len(plan.intents) == 2
            assert len(calls) == 1
            assert outcome.cost.provider_calls == 1
            assert outcome.budget_usage.provider_calls == 2
        else:
            outcome = asyncio.run(adapter.execute(request, context))
            assert phase4.calls == 1
        assert outcome.updated_snapshot_id == context.snapshot_id
        assert outcome.new_source_ids == ()
        if not real_phase4:
            assert outcome.updated_manifest.research_result == zero_result
        assert outcome.stop_reason == ("BUDGET_STOPPED" if real_phase4 else "NO_NEW_YIELD")
        assert outcome.updated_manifest.content_digest() != context.manifest_digest
    finally:
        repository.close()


def _real_ports(packet, *, disputed=False):
    from novelty_harness.adjudication.roles import DefensePoint
    from novelty_harness.ports.adjudication import Phase7Ports
    from tests.unit.adjudication.test_judge import _scripted_judge
    from tests.unit.adjudication.test_roles import scope, valid_case

    primary = valid_case(packet)
    target_ids = sorted(packet.target_ids)

    class Role:
        def __init__(self, prosecution):
            self.prosecution = prosecution
            self.calls = []

        async def propose(self, packet):
            primary = valid_case(packet)
            target_id = target_ids[len(self.calls) % len(target_ids)]
            self.calls.append(packet)
            if self.prosecution:
                return (
                    primary
                    if target_id == primary.target_id
                    else ProsecutionCase(
                        **scope(packet, target_id),
                        case_id=f"p7pro_slice_{target_id}",
                        challenges=(),
                    )
                )
            return DefenseCase(
                **scope(packet, target_id),
                case_id=f"p7def_slice_{target_id}",
                points=(
                    DefensePoint(
                        **scope(packet, target_id),
                        defense_id="p7def_slice_point",
                        disposition="OBJECTION" if disputed else "CONCESSION",
                        thesis="The scoped precedent is conceded"
                        if not disputed
                        else "Scope differs",
                        comparison_ids=primary.challenges[0].comparison_ids,
                    ),
                )
                if target_id == primary.target_id
                else (),
            )

    class NoRebuttal:
        async def propose(self, packet, disputed_ids, other_case):
            from novelty_harness.adjudication.roles import RebuttalCase

            role = "DEFENDER" if isinstance(other_case, ProsecutionCase) else "PROSECUTOR"
            return RebuttalCase(
                **scope(packet, other_case.target_id),
                rebuttal_id=f"p7reb_slice_{role}",
                role=role,
                dispute_ids=disputed_ids,
                argument_ids=(other_case.challenges[0].argument_id,)
                if isinstance(other_case, ProsecutionCase)
                else (other_case.points[0].defense_id,),
                points=(),
            )

    return Phase7Ports(
        prosecutor=Role(True),
        defender=Role(False),
        prosecutor_rebuttal=NoRebuttal(),
        defender_rebuttal=NoRebuttal(),
        judge=_scripted_judge(packet, primary),
    )


def test_real_phase7_slice_freezes_repository_result(tmp_path) -> None:
    from novelty_harness.adjudication.frozen import FrozenAdjudication
    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_roles import build_packet

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        ports = _real_ports(packet)
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        assert isinstance(frozen, FrozenAdjudication)
        assert frozen == repository.load_frozen_adjudication(
            packet.assessment_id, adjudication_id=frozen.adjudication_id
        )
        assert set(f.target_id for f in frozen.target_findings) == packet.target_ids
        assert repository.load_phase7_run(frozen.run_id).state == Phase7RunState.FROZEN
        assert len(ports.prosecutor.calls) == len(packet.target_ids)
        assert len(ports.defender.calls) == len(packet.target_ids)
    finally:
        repository.close()


def test_clear_direct_reduced_path_skips_unneeded_steps(tmp_path) -> None:
    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_roles import build_packet

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        assert not frozen.rebuttal_ids
        assert frozen.judge_run_ids
        assert ports.judge.calls
        assert not frozen.research_gap_ids
    finally:
        repository.close()


def test_real_slice_reconciles_heterogeneous_pairs_without_vote(tmp_path) -> None:
    from dataclasses import replace

    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_judge import _scripted_judge
    from tests.unit.adjudication.test_roles import build_packet, valid_case

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet, disputed=True)
    alternate = _scripted_judge(
        packet,
        valid_case(packet),
        proposed_gate_c="NO_DIRECT_IN_REVIEWED_SCOPE",
        proposed_gate_d="SUBSTANTIVE",
    )
    alternate.model_config_id = "independent-alternate-v1"
    ports = replace(ports, alternate_judge=alternate)
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        target = next(
            f for f in frozen.target_findings if f.target_id == valid_case(packet).target_id
        )
        assert target.verdict.value == "UNASSESSABLE"
        assert len(ports.judge.calls) == len(alternate.calls) == 2
        assert len(frozen.judge_run_ids) == 4
        assert len(frozen.counterbalance_comparison_ids) == 2
        assert any("disagree" in limit.lower() for limit in frozen.limiting_factors)

    finally:
        repository.close()


def test_real_slice_preserves_role_case_limits(tmp_path) -> None:
    from dataclasses import replace

    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_roles import build_packet

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)
    inner = ports.prosecutor

    class LimitedProsecutor:
        async def propose(self, packet):
            return (await inner.propose(packet)).model_copy(
                update={"limitations": ("role_scope_limit",)}
            )

    ports = replace(ports, prosecutor=LimitedProsecutor())
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        assert "role_scope_limit" in frozen.limiting_factors
    finally:
        repository.close()


def test_real_phase7_requires_exact_configured_target_roles(tmp_path) -> None:
    from dataclasses import replace

    from novelty_harness.application.phase7 import run_phase7
    from novelty_harness.ports.adjudication import Phase7TargetRoles
    from tests.unit.adjudication.test_roles import build_packet

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)
    configured = {"absent_target": Phase7TargetRoles(ports.prosecutor, ports.defender)}
    ports = replace(ports, target_roles=configured)
    try:
        with pytest.raises(ValueError, match="target"):
            asyncio.run(
                run_phase7(
                    packet.assessment_id,
                    context_id=packet.assessment_context_id,
                    repository=repository,
                    ports=ports,
                )
            )
        assert not ports.prosecutor.calls
    finally:
        repository.close()


def _run_material_gap_case(tmp_path, outcome_kind) -> None:
    from dataclasses import replace

    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_roles import build_packet

    original = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    context = repository.load_phase7_context(
        original.assessment_id, context_id=original.assessment_context_id
    )
    context = repository.seal_phase7_context(
        original.assessment_id,
        snapshot_id=context.snapshot_id,
        manifest=context.manifest.model_copy(
            update={"remaining_gaps": ("Unscreened terminology branch",)}
        ),
    )
    packet = build_adjudication_case(
        context,
        repository.load_phase6_assessment(original.assessment_id, snapshot_id=context.snapshot_id),
    )
    ports = _real_ports(packet, disputed=True)

    class ZeroYield:
        calls = []

        async def execute(self, request, given):
            self.calls.append(request)
            if outcome_kind == "noop":
                return ResearchEscalationOutcome(
                    request_id=request.request_id,
                    assessment_id=given.assessment_id,
                    assessment_context_id=given.context_id,
                    phase6_snapshot_id=given.snapshot_id,
                    updated_snapshot_id=given.snapshot_id,
                    updated_manifest=given.manifest,
                    budget_usage=given.manifest.budget_usage or BudgetUsage(),
                    cost=BudgetUsage(),
                    remaining_gaps=given.manifest.remaining_gaps,
                )
            usage = BudgetUsage(provider_calls=1)
            coverage = (
                CoverageCell(
                    mcu_id=request.target_id,
                    evidence_family=EvidenceFamily.SCHOLARLY,
                    state=CoverageState.DEGRADED,
                    planned_query_families=frozenset(),
                    configured_providers=("scripted",),
                    inspected_results=0,
                    limitations=("zero_yield_review",),
                ),
            )
            updated = given.manifest.model_copy(
                update={
                    "budget_usage": usage,
                    "coverage_cells": coverage,
                    "query_history": ("qry_coordinator_zero",),
                    "providers_attempted": ("scripted",),
                    "remaining_gaps": (),
                    "stop_reason": "NO_NEW_YIELD",
                }
            )
            return ResearchEscalationOutcome(
                request_id=request.request_id,
                assessment_id=given.assessment_id,
                assessment_context_id=given.context_id,
                phase6_snapshot_id=given.snapshot_id,
                updated_snapshot_id=given.snapshot_id,
                updated_manifest=updated,
                attempted_query_ids=("qry_coordinator_zero",),
                providers_attempted=("scripted",),
                coverage_cells=coverage,
                budget_usage=usage,
                cost=usage,
                stop_reason="NO_NEW_YIELD",
            )

    class FreshJudge:
        model_config_id = ports.judge.model_config_id
        calls = []

        async def judge(self, packet, arguments, *, order, rubric_version):
            from tests.unit.adjudication.test_judge import _scripted_judge
            from tests.unit.adjudication.test_roles import valid_case

            self.calls.append(order)
            return await _scripted_judge(packet, valid_case(packet)).judge(
                packet, arguments, order=order, rubric_version=rubric_version
            )

    ports = replace(ports, judge=FreshJudge())
    escalation = ZeroYield()
    ports = replace(ports, research_escalation=escalation)
    if outcome_kind == "budget_spent":
        ports = replace(
            ports,
            research_budget=ResearchEscalationBudget(
                limits=BudgetLimits(max_provider_calls=1),
                usage=BudgetUsage(provider_calls=1),
                max_requests=1,
            ),
        )
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=context.context_id,
                repository=repository,
                ports=ports,
            )
        )
        assert len(escalation.calls) == (0 if outcome_kind == "budget_spent" else 1)
        if outcome_kind == "changed":
            assert frozen.assessment_context_id != context.context_id
            assert context.context_id in frozen.superseded_context_ids
            assert len(ports.prosecutor.calls) == len(packet.target_ids) * 2
            assert len(ports.defender.calls) == len(packet.target_ids) * 2
            assert ports.judge.calls == [("A", "B"), ("B", "A")]
            current = repository.load_phase7_context(
                packet.assessment_id, context_id=frozen.assessment_context_id
            )
            assert current.manifest.coverage_cells != context.manifest.coverage_cells
            assert current.manifest.budget_usage.provider_calls == 1
            with repository.engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT COUNT(*) FROM phase7_frozen_manifests")
                    ).scalar_one()
                    == 1
                )
                old_run_id = connection.execute(
                    text("SELECT run_id FROM phase7_runs WHERE context_id=:context"),
                    {"context": context.context_id},
                ).scalar_one()
            assert (
                repository.load_phase7_run(old_run_id).state
                == Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE
            )
            assert frozen.run_id != old_run_id
            for case in ports.prosecutor.calls[: len(packet.target_ids)]:
                assert case.assessment_context_id == context.context_id

        else:
            assert frozen.assessment_context_id == context.context_id
            assert not frozen.superseded_context_ids
            assert len(ports.prosecutor.calls) == len(packet.target_ids)
            assert len(ports.defender.calls) == len(packet.target_ids)
        assert ports.prosecutor.calls[-1].assessment_context_id == frozen.assessment_context_id
        assert (
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=frozen.adjudication_id
            )
            == frozen
        )
    finally:
        repository.close()


def test_phase8_boundary_rejects_caller_created_frozen_shape(tmp_path) -> None:
    from novelty_harness.reporting.minimal import summarize_frozen_phase7
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        with pytest.raises(Phase7AuthorityError):
            summarize_frozen_phase7(
                assessment_id=packet.assessment_id, adjudication_id=proposed, repository=repository
            )
        with pytest.raises(Phase7AuthorityError):
            summarize_frozen_phase7(
                assessment_id=packet.assessment_id,
                adjudication_id=proposed.adjudication_id,
                repository=repository,
            )
        adjudication_id = repository.freeze_phase7_adjudication(run.run_id, proposed)
        summary = summarize_frozen_phase7(
            assessment_id=packet.assessment_id,
            adjudication_id=adjudication_id,
            repository=repository,
        )
        assert summary.adjudication_id == adjudication_id
        assert summary.overall_verdict == proposed.overall_finding.verdict
        assert "Phase 8" in summary.markdown
        assert "Q1." not in summary.markdown
        assert not hasattr(summary, "report_id")
        assert not hasattr(summary, "compilation_id")
    finally:
        repository.close()


def test_fixture_adjudication_cannot_masquerade_as_real_phase7(tmp_path) -> None:
    from novelty_harness.reporting.minimal import summarize_frozen_phase7
    from tests.fixtures.phase1 import make_fixture
    from tests.unit.adjudication.test_roles import build_packet

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    fixture = make_fixture().adjudication
    try:
        with pytest.raises(Phase7AuthorityError):
            summarize_frozen_phase7(
                assessment_id=packet.assessment_id, adjudication_id=fixture, repository=repository
            )
    finally:
        repository.close()


@pytest.mark.parametrize("kind", ("DIRECT", "PARTIAL_NEGATIVE", "PARTIAL_POTENTIAL", "COMBINATION"))
def test_real_phase7_slice_supports_direct_partial_and_combination(tmp_path, kind) -> None:
    from dataclasses import replace

    from novelty_harness.adjudication.context import Phase7InputManifest
    from novelty_harness.adjudication.counterfactual import CounterfactualLocalization
    from novelty_harness.application.phase7 import run_phase7
    from novelty_harness.domain.mcu import MCUFeature
    from novelty_harness.evidence.graph.assessment_ledger import (
        Phase6AssessmentSnapshotRecord,
        Phase6CandidateLedgerRecord,
        Phase6CoverageLedger,
        Phase6TargetLedgerRecord,
        phase6_assessment_snapshot_id,
        phase6_candidate_record_id,
        phase6_target_record_id,
    )
    from novelty_harness.evidence.mapping.dimensions import build_mcu_comparison_profile
    from tests.adversarial.test_phase6_r15_assessment_authority import (
        NOW,
        _load_committed_matrix_case,
    )
    from tests.fixtures.phase1 import make_fixture
    from tests.unit.adjudication.test_judge import _scripted_judge
    from tests.unit.adjudication.test_roles import build_packet, valid_case

    if kind in {"DIRECT", "COMBINATION"}:
        packet = build_packet(tmp_path)
        repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
        ports = _real_ports(packet)
    else:
        repository, view, chain, classified = _load_committed_matrix_case(
            tmp_path, "STRONG_PARTIAL_PRECEDENT"
        )
        fixture = make_fixture()
        mcu = fixture.graph.mcus[0].model_copy(
            update={
                "mcu_id": "mcu_1",
                "features": (
                    *fixture.graph.mcus[0].features,
                    MCUFeature(feature_id="F3", concept="the load is remotely logged"),
                ),
            }
        )
        graph = fixture.graph.model_copy(update={"mcus": (mcu,), "combinations": ()})
        cir = fixture.idea.model_copy(
            update={
                "mcu_ids": (mcu.mcu_id,),
                "combination_ids": (),
                "context": fixture.idea.context.model_copy(update={"temporal_cutoff": view.as_of}),
            }
        )
        target = Phase6TargetLedgerRecord(
            snapshot_id="pending",
            assessment_id=view.assessment_id,
            profile=build_mcu_comparison_profile(mcu),
        )
        chain = view.committed_comparisons[0].comparison.comparison.chain
        classification = view.committed_comparisons[0].comparison.classification
        candidate = Phase6CandidateLedgerRecord(
            snapshot_id="pending",
            assessment_id=view.assessment_id,
            target_id=mcu.mcu_id,
            source_id=chain.source.source_id,
            source_version_id=chain.version.version_id,
            source_content_hash=chain.source.content_hash,
            version_content_hash=chain.version.content_hash,
            source_access_state=chain.source.access_state,
            version_access_state=chain.version.access_state,
            decision="ASSESSED",
            projection_intent="GRAPH_BACKED",
            commit_id=view.commit_ids[0],
            verified_edge_id=chain.edge.edge_id,
            classification_id=classification.classification_id,
        )
        snapshot = Phase6AssessmentSnapshotRecord(
            snapshot_id="pending",
            assessment_id=view.assessment_id,
            as_of=view.as_of,
            method_version="phase7-integration-fixture-v1",
            target_record_ids=(),
            candidate_record_ids=(),
            derived_record_ids=(),
            lineage_cluster_ids=(),
            audit_refs=(),
            max_sources_per_mcu=1,
            max_versions_per_source=1,
            max_expansions=0,
            window_chars=0,
            commit_ids=view.commit_ids,
            coverage=Phase6CoverageLedger(),
            completed_at=NOW,
        )
        snapshot_id = phase6_assessment_snapshot_id(
            snapshot, targets=(target,), candidates=(candidate,), derived=()
        )
        target = target.model_copy(update={"snapshot_id": snapshot_id})
        candidate = candidate.model_copy(update={"snapshot_id": snapshot_id})
        snapshot = snapshot.model_copy(
            update={
                "snapshot_id": snapshot_id,
                "target_record_ids": (phase6_target_record_id(target),),
                "candidate_record_ids": (phase6_candidate_record_id(candidate),),
            }
        )
        repository.record_phase6_assessment(
            snapshot, targets=(target,), candidates=(candidate,), derived=()
        )
        context = repository.seal_phase7_context(
            view.assessment_id,
            snapshot_id=snapshot_id,
            manifest=Phase7InputManifest(
                assessment_id=view.assessment_id,
                phase6_snapshot_id=snapshot_id,
                as_of=view.as_of,
                cir=cir,
                sufficiency=fixture.sufficiency,
                mcu_graph=graph,
                unknown_upstream_artifacts=("phase3", "phase4"),
            ),
        )
        packet = build_adjudication_case(
            context, repository.load_phase6_assessment(view.assessment_id, snapshot_id=snapshot_id)
        )
        ports = _real_ports(packet, disputed=True)
        inner = ports.prosecutor

        class PartialProsecution:
            async def propose(self, packet):
                case = await inner.propose(packet)
                return case.model_copy(
                    update={
                        "challenges": tuple(
                            c.model_copy(update={"effect": "PARTIAL_CHALLENGE"})
                            for c in case.challenges
                        )
                    }
                )

        localization = CounterfactualLocalization(
            **scope(packet, mcu.mcu_id),
            localization_id="p7counterfactual_slice",
            nearest_comparison_id=str(classification.classification_id),
            removed_element=classification.missing_elements[0],
            substantial_equivalence_after_removal=True,
            reason="Removing the claimed residual leaves the verified core",
        )
        judge = _scripted_judge(
            packet,
            valid_case(packet),
            proposed_gate_c="SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA",
            proposed_gate_d="NON_SUBSTANTIVE" if kind == "PARTIAL_NEGATIVE" else "SUBSTANTIVE",
            counterfactual=localization,
        )
        ports = replace(ports, prosecutor=PartialProsecution(), judge=judge)
    try:
        before = tuple(c.comparison.classification for c in packet.comparisons)
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        assert set(f.target_id for f in frozen.target_findings) == packet.target_ids
        if kind.startswith("PARTIAL"):
            expected = (
                "NOT_NOVEL_AT_CLAIMED_LEVEL" if kind == "PARTIAL_NEGATIVE" else "POTENTIALLY_NOVEL"
            )
            assert frozen.target_findings[0].verdict.value == expected
            assert len(ports.judge.calls) == 2
        elif kind == "DIRECT":
            assert any(
                f.verdict.value == "NOT_NOVEL_AT_CLAIMED_LEVEL" for f in frozen.target_findings
            )
        else:
            assert any(f.target_kind == "COMBINATION" for f in frozen.target_findings)
        loaded = repository.load_phase6_assessment(
            packet.assessment_id, snapshot_id=packet.phase6_snapshot_id
        )
        assert tuple(c.comparison.classification for c in loaded.committed_comparisons) == before
    finally:
        repository.close()


@pytest.mark.parametrize("outcome_kind", ("changed", "noop", "budget_spent"))
def test_positive_candidate_runs_material_gap_path(tmp_path, outcome_kind) -> None:
    _run_material_gap_case(tmp_path, outcome_kind)


@pytest.mark.parametrize("stage", ("FIRST_PASS", "ADJUDICATION"))
def test_semantic_input_need_freezes_clarification_without_research(tmp_path, stage) -> None:
    from dataclasses import replace

    from novelty_harness.adjudication.needs import InputClarificationNeed
    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_roles import build_packet, scope

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)
    need = InputClarificationNeed(
        **scope(packet, "mcu_control"),
        need_id="p7need_semantic_control",
        reason="Control meaning requires clarification",
        missing_input_fields=("control_mechanism",),
        resolution_requirement="Describe the control condition",
    )
    if stage == "FIRST_PASS":
        inner = ports.prosecutor

        class Role:
            async def propose(self, given):
                case = await inner.propose(given)
                return (
                    case.model_copy(
                        update={"input_needs": (need,), "input_need_ids": (need.need_id,)}
                    )
                    if case.target_id == need.target_id
                    else case
                )

        ports = replace(ports, prosecutor=Role())
    else:
        inner = ports.judge

        class Judge:
            model_config_id = inner.model_config_id

            async def judge(self, *args, **kwargs):
                finding = await inner.judge(*args, **kwargs)
                return finding.model_copy(
                    update={"input_needs": (need,), "input_need_ids": (need.need_id,)}
                )

        ports = replace(ports, judge=Judge())

    class Research:
        calls = 0

        async def execute(self, *args):
            self.calls += 1
            raise AssertionError("Input clarification reached research")

    research = Research()
    ports = replace(ports, research_escalation=research)
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        target = next(f for f in frozen.target_findings if f.target_id == need.target_id)
        assert target.verdict.value == "UNASSESSABLE"
        assert need.need_id in frozen.input_need_ids
        assert research.calls == 0
        assert (
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=frozen.adjudication_id
            )
            == frozen
        )
    finally:
        repository.close()


@pytest.mark.parametrize("stage", ("FIRST_PASS", "ADJUDICATION"))
@pytest.mark.parametrize("available", (False, True, "changed"))
def test_semantic_research_gap_is_retained_with_unavailable_disposition(
    tmp_path, stage, available
) -> None:
    from dataclasses import replace

    from novelty_harness.adjudication.needs import ResearchGapDisposition
    from novelty_harness.application.phase7 import run_phase7
    from tests.unit.adjudication.test_roles import build_packet, scope

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)
    base_prosecutor, base_defender = ports.prosecutor, ports.defender
    gap = ResearchGapRequest(
        **scope(packet, "mcu_control"),
        request_id="p7gap_semantic_history",
        requesting_stage=stage,
        gap_type="CHRONOLOGY",
        reason="A historical implementation detail remains unavailable",
        research_hypothesis="The missing publication may establish chronology",
        material_gate="C",
        stop_condition="Verify the date or retain the access limitation",
    )
    if stage == "FIRST_PASS":
        inner = ports.prosecutor

        class Role:
            async def propose(self, given):
                case = await inner.propose(given)
                return (
                    case.model_copy(
                        update={"research_gaps": (gap,), "research_gap_ids": (gap.request_id,)}
                    )
                    if case.target_id == gap.target_id
                    and given.assessment_context_id == packet.assessment_context_id
                    else case
                )

        ports = replace(ports, prosecutor=Role())
    else:
        inner = ports.judge

        class Judge:
            model_config_id = inner.model_config_id

            async def judge(self, *args, **kwargs):
                finding = await inner.judge(*args, **kwargs)
                given = args[0]
                finding = finding.model_copy(update=scope(given, finding.target_id))
                return (
                    finding.model_copy(
                        update={"research_gaps": (gap,), "research_gap_ids": (gap.request_id,)}
                    )
                    if given.assessment_context_id == packet.assessment_context_id
                    else finding
                )

        ports = replace(ports, judge=Judge())

    if stage == "FIRST_PASS" and available == "changed":
        inner_judge = ports.judge

        class SuccessorJudge:
            model_config_id = inner_judge.model_config_id

            async def judge(self, given, *args, **kwargs):
                finding = await inner_judge.judge(given, *args, **kwargs)
                return finding.model_copy(update=scope(given, finding.target_id))

        ports = replace(ports, judge=SuccessorJudge())

    class Research:
        calls = 0

        async def execute(self, request, context):
            self.calls += 1
            updated = context.manifest
            if available == "changed":
                updated = updated.model_copy(
                    update={
                        "query_history": (*updated.query_history, "qry_semantic_zero_yield"),
                        "stop_reason": "NO_NEW_YIELD",
                    }
                )
            return ResearchEscalationOutcome(
                request_id=request.request_id,
                assessment_id=context.assessment_id,
                assessment_context_id=context.context_id,
                phase6_snapshot_id=context.snapshot_id,
                updated_snapshot_id=context.snapshot_id,
                updated_manifest=updated,
                stop_reason=updated.stop_reason,
                budget_usage=context.manifest.budget_usage or BudgetUsage(),
                cost=BudgetUsage(),
            )

    research = Research()
    if available:
        ports = replace(ports, research_escalation=research)
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=ports,
            )
        )
        if available == "changed":
            assert frozen.assessment_context_id != packet.assessment_context_id
            assert len(base_prosecutor.calls) == len(packet.target_ids) * 2
            assert len(base_defender.calls) == len(packet.target_ids) * 2
        else:
            assert gap.request_id in frozen.research_gap_ids
        dispositions = tuple(
            ResearchGapDisposition.model_validate_json(a.document_json)
            for a in repository.load_phase7_artifacts(frozen.run_id)
            if a.kind == "RESEARCH_GAP_DISPOSITION"
        )
        assert len(dispositions) == (0 if available == "changed" else 1)
        if dispositions:
            assert dispositions[0].status == ("ACCEPT" if available else "UNAVAILABLE")
        assert research.calls == int(bool(available))
        assert (
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=frozen.adjudication_id
            )
            == frozen
        )
    finally:
        repository.close()


def test_agreed_substantive_partial_still_receives_neutral_adjudication(
    tmp_path, monkeypatch
) -> None:
    from dataclasses import replace

    from novelty_harness.application import phase7

    real_run = phase7.run_phase7

    async def reviewed(assessment_id, *, context_id, repository, ports):
        inner = ports.defender

        class Defender:
            async def propose(self, packet):
                case = await inner.propose(packet)
                return case.model_copy(
                    update={
                        "points": tuple(
                            p.model_copy(
                                update={
                                    "disposition": "CONCESSION",
                                    "thesis": (
                                        "The historical core is known; "
                                        "the claimed contribution still needs assessment"
                                    ),
                                }
                            )
                            for p in case.points
                        )
                    }
                )

        return await real_run(
            assessment_id,
            context_id=context_id,
            repository=repository,
            ports=replace(ports, defender=Defender()),
        )

    monkeypatch.setattr(phase7, "run_phase7", reviewed)
    test_real_phase7_slice_supports_direct_partial_and_combination(tmp_path, "PARTIAL_POTENTIAL")
