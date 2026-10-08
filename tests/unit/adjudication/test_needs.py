import pytest
from pydantic import ValidationError

from novelty_harness.adjudication.context import SealedAssessmentContext
from novelty_harness.adjudication.needs import (
    GapEscalationPolicy,
    InputClarificationNeed,
    ResearchEscalationBudget,
    ResearchGapRequest,
    route_need,
    validate_research_gap_request,
)
from novelty_harness.runtime.budgets.controller import BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits
from tests.unit.adjudication.test_roles import build_packet

SCOPE = {
    "assessment_id": "asm_need",
    "assessment_context_id": "p7ctx_need",
    "phase6_snapshot_id": "p6snap_need",
    "target_id": "mcu_need",
}


def test_gate_a_need_never_routes_research() -> None:
    need = InputClarificationNeed(
        **SCOPE,
        need_id="p7need_mechanism",
        reason="Mechanism unspecified",
        missing_input_fields=("mechanism",),
        resolution_requirement="Clarify the claim",
    )
    assert route_need(need) == "INPUT"
    with pytest.raises(ValidationError):
        ResearchGapRequest(
            **SCOPE,
            request_id="p7gap_wrong",
            requesting_stage="FIRST_PASS",
            gap_type="COVERAGE",
            reason="Mechanism unspecified",
            research_hypothesis="Search might reveal what user meant",
            material_gate="A",
            stop_condition="TEST_COVERAGE_BRANCH",
        )


def test_gate_d_gap_requires_external_prior_art() -> None:
    values = {
        **SCOPE,
        "request_id": "p7gap_d",
        "requesting_stage": "ADJUDICATION",
        "gap_type": "ACCESS",
        "reason": "Closest historical implementation unavailable",
        "research_hypothesis": "An archived implementation may show the relation",
        "material_gate": "D",
        "stop_condition": "CLOSE_ACCESS_GAP",
    }
    with pytest.raises(ValidationError):
        ResearchGapRequest.model_validate(values)
    request = ResearchGapRequest.model_validate(
        {**values, "missing_prior_art_reference": "srcv_historical"}
    )
    assert route_need(request) == "RESEARCH"


def test_input_specification_cannot_disguise_itself_as_gate_d_research() -> None:
    with pytest.raises(ValidationError):
        ResearchGapRequest(
            **SCOPE,
            request_id="p7gap_disguised",
            requesting_stage="ADJUDICATION",
            gap_type="INPUT_SPECIFICATION",
            reason="The user's mechanism is missing",
            research_hypothesis="Search might reveal what the user meant",
            material_gate="D",
            missing_prior_art_reference="srcv_claimed",
            stop_condition="ASSESS_RELATIONSHIP_IN_PRIOR_ART",
        )


def test_gap_linked_comparison_must_belong_to_packet(tmp_path) -> None:
    packet = build_packet(tmp_path)
    request = ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=packet.target_profiles[0].target_id,
        request_id="p7gap_foreign_link",
        requesting_stage="FIRST_PASS",
        gap_type="CHRONOLOGY",
        reason="An external date is missing",
        research_hypothesis="A dated source version may clarify chronology",
        material_gate="C",
        linked_comparison_ids=("cls_foreign",),
        stop_condition="RESOLVE_CHRONOLOGY",
    )
    with pytest.raises(ValueError, match="comparison"):
        validate_research_gap_request(request, packet)


def test_gap_policy_deduplicates_and_respects_budget(tmp_path) -> None:
    packet = build_packet(tmp_path)
    context = SealedAssessmentContext(
        context_id=packet.assessment_context_id,
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id=packet.manifest_id,
        manifest_digest=packet.manifest_digest,
        manifest=packet.manifest,
    )
    request = ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=packet.target_profiles[0].target_id,
        request_id="p7gap_budget",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="Coverage branch remains material",
        research_hypothesis="A missing external branch may contain the configuration",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    policy = GapEscalationPolicy()
    available = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=2),
        usage=BudgetUsage(),
        max_requests=1,
    )
    assert policy.decide(request, context, available).status == "ACCEPT"
    assert (
        policy.decide(
            request,
            context,
            available.model_copy(update={"issued_request_ids": (request.request_id,)}),
        ).status
        == "DUPLICATE"
    )
    assert (
        policy.decide(
            request,
            context,
            available.model_copy(update={"usage": BudgetUsage(provider_calls=2)}),
        ).status
        == "BUDGET_STOP"
    )
    assert (
        policy.decide(
            request,
            context,
            available.model_copy(update={"max_requests": 0}),
        ).status
        == "BUDGET_STOP"
    )


def test_gate_d_gap_requires_material_external_fact_for_escalation(tmp_path) -> None:
    packet = build_packet(tmp_path)
    context = SealedAssessmentContext(
        context_id=packet.assessment_context_id,
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id=packet.manifest_id,
        manifest_digest=packet.manifest_digest,
        manifest=packet.manifest,
    )
    request = ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=packet.target_profiles[0].target_id,
        request_id="p7gap_d_coverage",
        requesting_stage="ADJUDICATION",
        gap_type="COVERAGE",
        reason="A source may clarify the closest historical delta",
        research_hypothesis="Search the archive for the missing source",
        material_gate="D",
        missing_prior_art_reference="srcv_missing",
        stop_condition="CLOSE_ACCESS_GAP",
    )
    budget = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=1), usage=BudgetUsage(), max_requests=1
    )
    assert GapEscalationPolicy().decide(request, context, budget).status == "INPUT_RESOLUTION"
    assert (
        GapEscalationPolicy()
        .decide(request.model_copy(update={"gap_type": "ACCESS"}), context, budget, packet=packet)
        .status
        == "INPUT_RESOLUTION"
    )


def test_gap_policy_cannot_expand_sealed_budget_with_caller_limits(tmp_path) -> None:
    packet = build_packet(tmp_path)
    context = SealedAssessmentContext(
        context_id=packet.assessment_context_id,
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id=packet.manifest_id,
        manifest_digest=packet.manifest_digest,
        manifest=packet.manifest,
    )
    bounded_manifest = context.manifest.model_copy(
        update={
            "budget_limits": BudgetLimits(max_provider_calls=1),
            "budget_usage": BudgetUsage(provider_calls=1),
        }
    )
    bounded_context = context.model_copy(update={"manifest": bounded_manifest})
    request = ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=packet.target_profiles[0].target_id,
        request_id="p7gap_no_budget_override",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="One external branch remains open",
        research_hypothesis="The branch might contain a direct relation",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    caller_budget = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=100),
        usage=BudgetUsage(),
        max_requests=100,
    )
    assert (
        GapEscalationPolicy().decide(request, bounded_context, caller_budget).status
        == "BUDGET_STOP"
    )


def test_gap_policy_intersects_tighter_cap_with_sealed_usage(tmp_path) -> None:
    packet = build_packet(tmp_path)
    context = SealedAssessmentContext(
        context_id=packet.assessment_context_id,
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id=packet.manifest_id,
        manifest_digest=packet.manifest_digest,
        manifest=packet.manifest,
    )
    bounded_manifest = context.manifest.model_copy(
        update={
            "budget_limits": BudgetLimits(max_provider_calls=10),
            "budget_usage": BudgetUsage(provider_calls=1),
        }
    )
    bounded_context = context.model_copy(update={"manifest": bounded_manifest})
    request = ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=packet.target_profiles[0].target_id,
        request_id="p7gap_no_budget_override",
        requesting_stage="FIRST_PASS",
        gap_type="COVERAGE",
        reason="One external branch remains open",
        research_hypothesis="The branch might contain a direct relation",
        material_gate="B",
        stop_condition="TEST_COVERAGE_BRANCH",
    )
    caller_budget = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=1),
        usage=BudgetUsage(),
        max_requests=100,
    )
    assert (
        GapEscalationPolicy().decide(request, bounded_context, caller_budget).status
        == "BUDGET_STOP"
    )


def test_remaining_allowance_intersects_all_cumulative_dimensions(tmp_path) -> None:
    from novelty_harness.adjudication.needs import remaining_research_allowance
    from novelty_harness.runtime.budgets.controller import DIMENSIONS

    packet = build_packet(tmp_path)
    context = SealedAssessmentContext(
        context_id=packet.assessment_context_id,
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id=packet.manifest_id,
        manifest_digest=packet.manifest_digest,
        manifest=packet.manifest,
    )
    context = context.model_copy(
        update={
            "manifest": packet.manifest.model_copy(
                update={
                    "budget_limits": BudgetLimits.model_validate(
                        {"max_" + d: 10 for d in DIMENSIONS}
                    ),
                    "budget_usage": BudgetUsage.model_validate({d: 3 for d in DIMENSIONS}),
                }
            )
        }
    )
    budget = ResearchEscalationBudget(
        limits=BudgetLimits.model_validate({"max_" + d: 5 for d in DIMENSIONS}),
        usage=BudgetUsage.model_validate({d: 2 for d in DIMENSIONS}),
        max_requests=1,
    )
    allowance = remaining_research_allowance(context, budget)
    assert all(getattr(allowance, "max_" + d) == 2 for d in DIMENSIONS)
