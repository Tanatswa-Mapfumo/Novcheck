"""Deterministic Phase 7 gate checks over a sealed case packet."""

import pytest

from novelty_harness.adjudication.context import SealedAssessmentContext
from novelty_harness.adjudication.counterfactual import (
    CounterfactualLocalization,
    validate_counterfactual,
)
from novelty_harness.adjudication.gates import (
    evaluate_gate_a,
    evaluate_gate_b,
    evaluate_gate_c,
    evaluate_gate_d,
    gate_d_research_gap,
)
from novelty_harness.adjudication.judge import JudgeFinding
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.adjudication.needs import InputClarificationNeed, route_need
from novelty_harness.adjudication.packet import AdjudicationCasePacket, build_adjudication_case
from novelty_harness.domain.enums import (
    EvidenceFamily,
    PrecedentState,
    ResearchDepth,
    SufficiencyState,
    ValueMaturity,
)
from novelty_harness.domain.mcu import MCUFeature
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.mapping.dimensions import build_mcu_comparison_profile
from novelty_harness.research.adaptive.models import BranchState
from novelty_harness.research.adaptive.pipeline import AdaptiveCoverageCell, ResearchResult
from novelty_harness.research.adaptive.stopping import StopAssessment, StopReason
from novelty_harness.research.coverage import CoverageCell, CoveragePolicy, CoverageState
from novelty_harness.research.models import (
    EvidenceFamilyAssessment,
    FamilyApplicability,
    ResearchPlan,
    SearchIntent,
    SearchPlanReview,
)
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.runtime.budgets.controller import BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.hashing import canonical_hash
from tests.adversarial.test_phase6_r15_assessment_authority import _load_committed_matrix_case
from tests.integration.test_phase6_evidence_pipeline import graph_database
from tests.unit.adjudication.test_roles import build_packet


@pytest.fixture(scope="module")
def packet(tmp_path_factory) -> AdjudicationCasePacket:
    return build_packet(tmp_path_factory.mktemp("phase7-gate-a"))


def _target(packet: AdjudicationCasePacket, *, kind: str) -> TargetRef:
    profile = next(item for item in packet.target_profiles if item.target_kind == kind)
    return TargetRef(kind=kind, id=str(profile.target_id))


def _reseal(
    packet: AdjudicationCasePacket,
    tmp_path,
    *,
    sufficiency=None,
    graph=None,
    **manifest_updates,
):
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        manifest = packet.manifest.model_copy(
            update={
                "sufficiency": sufficiency or packet.manifest.sufficiency,
                "mcu_graph": graph or packet.manifest.mcu_graph,
                **manifest_updates,
            }
        )
        context = repository.seal_phase7_context(
            packet.assessment_id,
            snapshot_id=packet.phase6_snapshot_id,
            manifest=manifest,
            parent_context_id=packet.assessment_context_id,
        )
        return build_adjudication_case(
            context,
            repository.load_phase6_assessment(
                packet.assessment_id, snapshot_id=context.snapshot_id
            ),
        )
    finally:
        repository.close()


def test_gate_a_unknown_topology_never_dispatches(packet: AdjudicationCasePacket) -> None:
    finding, needs = evaluate_gate_a(packet, _target(packet, kind="COMBINATION"))
    assert finding.state == "INSUFFICIENT"
    assert "combination_topology" in finding.missing_fields
    assert len(needs) == 1
    assert isinstance(needs[0], InputClarificationNeed)
    assert needs[0].material_gate == "A"
    assert route_need(needs[0]) == "INPUT"


def test_gate_a_missing_mechanism_is_unassessable(packet: AdjudicationCasePacket) -> None:
    target = TargetRef(kind="MCU", id="mcu_status")
    finding, needs = evaluate_gate_a(packet, target)
    assert finding.state == "INSUFFICIENT"
    assert "mechanism" in finding.missing_fields
    assert needs[0].missing_input_fields == ("mechanism",)


def test_gate_a_exploratory_is_limited(tmp_path) -> None:
    packet = build_packet(tmp_path)
    exploratory = packet.manifest.sufficiency.model_copy(
        update={"state": SufficiencyState.EXPLORATORY}
    )
    successor = _reseal(packet, tmp_path, sufficiency=exploratory)
    finding, _ = evaluate_gate_a(successor, TargetRef(kind="MCU", id="mcu_control"))
    assert finding.state == "LIMITED"
    assert "phase2_exploratory" in finding.limiting_factors


def test_gate_a_phase2_insufficient_cannot_upgrade(tmp_path) -> None:
    packet = build_packet(tmp_path)
    insufficient = packet.manifest.sufficiency.model_copy(
        update={"state": SufficiencyState.INSUFFICIENT}
    )
    successor = _reseal(packet, tmp_path, sufficiency=insufficient)
    finding, needs = evaluate_gate_a(successor, TargetRef(kind="MCU", id="mcu_control"))
    assert finding.state == "INSUFFICIENT"
    assert "phase2_insufficient" in finding.limiting_factors
    assert needs


def test_gate_a_unresolved_relationship_direction_is_input_need(tmp_path) -> None:
    packet = build_packet(tmp_path)
    disputed_graph = packet.manifest.mcu_graph.model_copy(
        update={"unresolved_disagreements": ("mcu_control relationship direction unresolved",)}
    )
    successor = _reseal(packet, tmp_path, graph=disputed_graph)
    finding, needs = evaluate_gate_a(successor, TargetRef(kind="MCU", id="mcu_control"))
    assert finding.state == "INSUFFICIENT"
    assert "relationship_direction" in finding.missing_fields
    assert needs[0].material_gate == "A"


def test_gate_a_unstable_combination_decomposition_needs_clarification(tmp_path) -> None:
    packet = build_packet(tmp_path)
    disputed_graph = packet.manifest.mcu_graph.model_copy(
        update={"unresolved_disagreements": ("C1 decomposition unstable",)}
    )
    successor = _reseal(packet, tmp_path, graph=disputed_graph)
    finding, needs = evaluate_gate_a(successor, _target(successor, kind="COMBINATION"))
    assert finding.state == "INSUFFICIENT"
    assert "stable_decomposition" in finding.missing_fields
    assert route_need(needs[0]) == "INPUT"


def test_gate_a_limited_relationship_still_requests_missing_mechanism(
    packet: AdjudicationCasePacket,
) -> None:
    graph = packet.manifest.mcu_graph
    mcus = tuple(
        mcu.model_copy(update={"mechanism": None}) if mcu.mcu_id == "mcu_control" else mcu
        for mcu in graph.mcus
    )
    manifest = packet.manifest.model_copy(
        update={"mcu_graph": graph.model_copy(update={"mcus": mcus})}
    )
    view = packet.phase6_view.model_copy(
        update={
            "targets": tuple(
                build_mcu_comparison_profile(mcus[0]) if item.target_id == "mcu_control" else item
                for item in packet.target_profiles
            )
        }
    )
    context = SealedAssessmentContext(
        context_id="p7ctx_fixture_limited_mechanism",
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=canonical_hash(view),
        manifest_id="p7manifest_" + manifest.content_digest(),
        manifest_digest=manifest.content_digest(),
        manifest=manifest,
    )
    local_packet = build_adjudication_case(context, view)
    finding, needs = evaluate_gate_a(local_packet, TargetRef(kind="MCU", id="mcu_control"))
    assert finding.state == "LIMITED"
    assert needs[0].missing_input_fields == ("mechanism",)
    gate_d = evaluate_gate_d(local_packet, TargetRef(kind="MCU", id="mcu_control"), None, None)
    assert gate_d.state == "UNRESOLVED"
    assert (
        gate_d_research_gap(local_packet, TargetRef(kind="MCU", id="mcu_control"), gate_d) is None
    )


def test_gate_b_direct_negative_needs_no_global_saturation(packet: AdjudicationCasePacket) -> None:
    finding = evaluate_gate_b(packet, TargetRef(kind="MCU", id="mcu_control"))
    assert "CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE" in finding.permissions
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions
    assert "historical_research_unknown" in finding.limiting_factors


def test_gate_b_budget_stop_is_not_saturation(tmp_path) -> None:
    packet = build_packet(tmp_path)
    changed = _reseal(
        packet,
        tmp_path,
        budget_usage=BudgetUsage(provider_calls=1),
        stop_reason="BUDGET_STOPPED",
        query_history=("qry_budget_stop",),
    )
    finding = evaluate_gate_b(changed, TargetRef(kind="MCU", id="mcu_control"))
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions
    assert "budget_stopped" in finding.limiting_factors
    assert "CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE" in finding.permissions


def test_gate_b_no_new_yield_is_not_saturation(tmp_path) -> None:
    packet = build_packet(tmp_path)
    changed = _reseal(
        packet,
        tmp_path,
        budget_usage=BudgetUsage(provider_calls=1),
        stop_reason="NO_NEW_YIELD",
        query_history=("qry_zero_yield",),
    )
    prior = evaluate_gate_b(packet, TargetRef(kind="MCU", id="mcu_control"))
    finding = evaluate_gate_b(changed, TargetRef(kind="MCU", id="mcu_control"))
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions
    assert "no_new_yield_is_not_saturation" in finding.limiting_factors
    assert finding.gate_id != prior.gate_id


def test_gate_b_unassessed_source_limits_positive_permission(
    packet: AdjudicationCasePacket,
) -> None:
    finding = evaluate_gate_b(packet, TargetRef(kind="MCU", id="mcu_control"))
    assert "unassessed_candidate" in finding.limiting_factors
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions


def test_gate_b_provider_blocked_never_means_no_prior_art(tmp_path) -> None:
    packet = build_packet(tmp_path)
    blocked = CoverageCell(
        mcu_id="mcu_control",
        evidence_family=EvidenceFamily.SCHOLARLY,
        state=CoverageState.PROVIDER_FAILURE,
        planned_query_families=frozenset(),
        configured_providers=("blocked-provider",),
        limitations=("Provider unavailable",),
    )
    changed = _reseal(
        packet,
        tmp_path,
        coverage_cells=(blocked,),
        providers_attempted=("blocked-provider",),
        access_failures=("provider unavailable",),
        stop_reason="ACCESS_BLOCKED",
    )
    finding = evaluate_gate_b(changed, TargetRef(kind="MCU", id="mcu_control"))
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions
    assert "provider_or_access_blocked" in finding.limiting_factors
    assert "CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE" in finding.permissions


def _gate_b_saturated_packet(
    packet: AdjudicationCasePacket, *, complete_families: bool, screened_to_policy: bool = True
) -> AdjudicationCasePacket:
    target_id = "mcu_control"
    family = EvidenceFamily.SCHOLARLY
    draft = ResearchPlan(
        assessment_id=packet.assessment_id,
        as_of=packet.as_of,
        mcu_ids=tuple(mcu.mcu_id for mcu in packet.manifest.mcu_graph.mcus),
        family_assessments=(
            EvidenceFamilyAssessment(
                mcu_id=target_id,
                evidence_family=family,
                applicability=FamilyApplicability.APPLICABLE,
                rationale="Historical scholarship is relevant",
            ),
            *(
                EvidenceFamilyAssessment(
                    mcu_id=target_id,
                    evidence_family=other,
                    applicability=FamilyApplicability.NOT_APPLICABLE,
                    rationale="This family has no applicable material in the fixture",
                    exclusion_reason="Explicitly excluded by the reviewed fixture plan",
                )
                for other in EvidenceFamily
                if complete_families and other != family
            ),
        ),
        intents=(
            SearchIntent(
                query_id="qry_gate_b_direct",
                mcu_id=target_id,
                evidence_family=family,
                query_family=QueryFamily.DIRECT_CANONICAL,
                text="direct historical mechanism",
                rationale="Find the historical mechanism",
                concepts=("mechanism",),
            ),
            SearchIntent(
                query_id="qry_gate_b_mechanism",
                mcu_id=target_id,
                evidence_family=family,
                query_family=QueryFamily.MECHANISM,
                text="historical control relationship",
                rationale="Find the historical relationship",
                concepts=("relationship",),
            ),
        ),
    )
    plan = draft.model_copy(
        update={
            "reviewed": True,
            "review_id": "review_incomplete_family_fixture",
            "review": SearchPlanReview(
                review_id="review_incomplete_family_fixture",
                plan_hash=draft.content_hash(),
                status="PASS",
                issues=(),
                critic_prompt_version="test-review-v1",
            ),
        }
    )
    cell = CoverageCell(
        mcu_id=target_id,
        evidence_family=family,
        state=CoverageState.SCREENED,
        planned_query_families=(
            frozenset({QueryFamily.DIRECT_CANONICAL, QueryFamily.MECHANISM})
            if screened_to_policy
            else frozenset()
        ),
        configured_providers=("fixture-provider",),
        successful_providers=("fixture-provider",) if screened_to_policy else (),
    )
    stop = StopAssessment(
        reason=StopReason.SATURATED,
        signals={
            "budget_blocked": False,
            "provider_diversity": True,
            "mechanism_diversity": True,
            "diminishing_yield": True,
            "stable_top_clusters": True,
            "overlap": True,
            "major_candidates_explored": True,
            "coverage_floor": True,
            "citation_convergence": True,
        },
    )
    result = ResearchResult(
        batches=(),
        fused_candidates=(),
        candidate_clusters=(),
        chronology={},
        temporal_assessments={},
        branch_states=(
            BranchState(
                mcu_id=target_id,
                evidence_family=family,
                depth=ResearchDepth.SATURATED,
                unresolved=False,
            ),
        ),
        stop_assessments=(stop,),
        coverage_matrix=(
            AdaptiveCoverageCell(
                screening=cell,
                depth=ResearchDepth.SATURATED,
                stop=stop,
                strategies=frozenset(),
                rounds=2,
            ),
        ),
        expansion_events=(),
        request_events=(),
        budget_usage=BudgetUsage(),
        limitations=(),
    )
    manifest = packet.manifest.model_copy(
        update={
            "research_plan": plan,
            "research_result": result,
            "coverage_policy": CoveragePolicy.standard(),
            "budget_limits": BudgetLimits(max_provider_calls=2),
            "budget_usage": BudgetUsage(),
            "coverage_cells": (cell,),
            "unknown_upstream_artifacts": (),
        }
    )
    view = packet.phase6_view.model_copy(
        update={
            "candidate_outcomes": tuple(
                item for item in packet.candidate_outcomes if item.decision == "ASSESSED"
            ),
            "coverage": packet.coverage.model_copy(
                update={"excluded_sources": (), "excluded_versions": (), "limitations": ()}
            ),
        }
    )
    context = SealedAssessmentContext(
        context_id=(
            "p7ctx_fixture_complete_family" if complete_families else "p7ctx_fixture_omitted_family"
        ),
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=canonical_hash(view),
        manifest_id="p7manifest_" + manifest.content_digest(),
        manifest_digest=manifest.content_digest(),
        manifest=manifest,
    )
    return build_adjudication_case(context, view)


def test_gate_b_omitted_family_cannot_establish_strong_coverage(
    packet: AdjudicationCasePacket,
) -> None:
    local_packet = _gate_b_saturated_packet(packet, complete_families=False)
    finding = evaluate_gate_b(local_packet, TargetRef(kind="MCU", id="mcu_control"))
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions
    assert "coverage_not_converged" in finding.limiting_factors


def test_gate_b_explicit_family_exclusions_allow_complete_coverage(
    packet: AdjudicationCasePacket,
) -> None:
    local_packet = _gate_b_saturated_packet(packet, complete_families=True)
    finding = evaluate_gate_b(local_packet, TargetRef(kind="MCU", id="mcu_control"))
    assert "STRONG_POSITIVE_COVERAGE" in finding.permissions


def test_gate_b_screened_label_below_approved_policy_floor_is_not_strong(
    packet: AdjudicationCasePacket,
) -> None:
    local_packet = _gate_b_saturated_packet(
        packet, complete_families=True, screened_to_policy=False
    )
    finding = evaluate_gate_b(local_packet, TargetRef(kind="MCU", id="mcu_control"))
    assert "STRONG_POSITIVE_COVERAGE" not in finding.permissions


def _packet_from_view(packet: AdjudicationCasePacket, view, label: str) -> AdjudicationCasePacket:
    context = SealedAssessmentContext(
        context_id="p7ctx_fixture_gate_c_" + label,
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=canonical_hash(view),
        manifest_id=packet.manifest_id,
        manifest_digest=packet.manifest_digest,
        manifest=packet.manifest,
    )
    return build_adjudication_case(context, view)


def _packet_with_comparisons(
    packet: AdjudicationCasePacket, *, kept_relations: frozenset[PrecedentState]
) -> AdjudicationCasePacket:
    comparisons = tuple(
        item
        for item in packet.comparisons
        if item.comparison.classification.relation in kept_relations
    )
    identities = {
        (item.commit_id, str(item.comparison.classification.classification_id))
        for item in comparisons
    }
    view = packet.phase6_view.model_copy(
        update={
            "committed_comparisons": comparisons,
            "authorized_graph_relations": tuple(
                item
                for item in packet.authorized_relations
                if (item.commit_id, str(item.classification_id)) in identities
            ),
        }
    )
    return _packet_from_view(packet, view, canonical_hash(sorted(kept_relations)))


def test_gate_c_direct_requires_authorized_single_source(packet: AdjudicationCasePacket) -> None:
    target = TargetRef(kind="MCU", id="mcu_control")
    before = tuple(item.comparison for item in packet.comparisons)
    finding = evaluate_gate_c(packet, target, None)
    assert finding.state == "DIRECT_ESTABLISHED"
    assert len(finding.comparison_ids) == 1
    chosen = next(
        item
        for item in packet.comparisons
        if str(item.comparison.classification.classification_id) == finding.comparison_ids[0]
    )
    assert chosen.projection_status == "GRAPH_AUTHORIZED"
    assert chosen.comparison.classification.relation == PrecedentState.DIRECT_PRECEDENT
    assert chosen.comparison.comparison.chain.edge.chronology.state == "PREDATES_CUTOFF"
    assert set(finding.graph_relation_ids) <= set(chosen.graph_edge_ids)
    assert set(finding.passage_ids) == {
        str(item.passage.passage_id) for item in chosen.cited_passages
    }
    assert tuple(item.comparison for item in packet.comparisons) == before


def test_gate_c_uncertain_chronology_not_direct(packet: AdjudicationCasePacket) -> None:
    uncertain = _packet_with_comparisons(
        packet, kept_relations=frozenset({PrecedentState.UNRESOLVED})
    )
    finding = evaluate_gate_c(uncertain, TargetRef(kind="MCU", id="mcu_control"), None)
    assert finding.state in {"DISPUTED", "UNASSESSABLE"}
    assert finding.state != "DIRECT_ESTABLISHED"


def test_gate_c_no_target_comparison_is_unassessable(packet: AdjudicationCasePacket) -> None:
    no_direct = _packet_with_comparisons(packet, kept_relations=frozenset())
    finding = evaluate_gate_c(no_direct, TargetRef(kind="MCU", id="mcu_control"), None)
    assert finding.state == "UNASSESSABLE"


def _matrix_packet(tmp_path, case: str) -> AdjudicationCasePacket:
    repository, view, _, _ = _load_committed_matrix_case(tmp_path, case)
    try:
        baseline = build_packet(tmp_path / "baseline")
        mcu = baseline.manifest.mcu_graph.mcus[0].model_copy(
            update={
                "mcu_id": "mcu_1",
                "features": (
                    *baseline.manifest.mcu_graph.mcus[0].features,
                    MCUFeature(feature_id="F3", concept="the load is remotely logged"),
                ),
            }
        )
        graph = baseline.manifest.mcu_graph.model_copy(update={"mcus": (mcu,), "combinations": ()})
        cir = baseline.manifest.cir.model_copy(
            update={
                "context": baseline.manifest.cir.context.model_copy(
                    update={"temporal_cutoff": view.as_of}
                )
            }
        )
        manifest = baseline.manifest.model_copy(
            update={
                "assessment_id": view.assessment_id,
                "phase6_snapshot_id": view.snapshot_id,
                "as_of": view.as_of,
                "cir": cir,
                "mcu_graph": graph,
            }
        )
        context = SealedAssessmentContext(
            context_id="p7ctx_fixture_matrix_" + case,
            assessment_id=view.assessment_id,
            snapshot_id=view.snapshot_id,
            phase6_view_digest=canonical_hash(view),
            manifest_id="p7manifest_" + manifest.content_digest(),
            manifest_digest=manifest.content_digest(),
            manifest=manifest,
        )
        # Pure gate fixture: give the matrix target an explicit claimed mechanism
        # and feature so Gate A can evaluate the localized Phase 6 residual.
        fixture_view = view.model_copy(update={"targets": (build_mcu_comparison_profile(mcu),)})
        context = context.model_copy(update={"phase6_view_digest": canonical_hash(fixture_view)})
        return build_adjudication_case(context, fixture_view)
    finally:
        repository.close()


def test_gate_c_local_no_direct_stays_local(tmp_path) -> None:
    packet = _matrix_packet(tmp_path, "NO_MATCH")
    finding = evaluate_gate_c(packet, TargetRef(kind="MCU", id="mcu_1"), None)
    assert finding.state == "NO_DIRECT_IN_REVIEWED_SCOPE"
    assert "reviewed_scope_only" in finding.limiting_factors
    assert packet.comparisons[0].comparison.classification.relation == (
        PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED
    )


def test_gate_c_partials_across_sources_never_stitch(
    packet: AdjudicationCasePacket, tmp_path
) -> None:
    packet = _matrix_packet(tmp_path, "STRONG_PARTIAL_PRECEDENT")
    finding = evaluate_gate_c(packet, TargetRef(kind="MCU", id="mcu_1"), None)
    assert finding.state == "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA"
    assert finding.state != "DIRECT_ESTABLISHED"
    assert finding.residual_delta == "the load is remotely logged"
    assert packet.comparisons[0].comparison.classification.relation == (
        PrecedentState.STRONG_PARTIAL_PRECEDENT
    )


def test_gate_c_incomplete_graph_projections_from_two_sources_do_not_stitch(
    packet: AdjudicationCasePacket,
) -> None:
    direct = tuple(
        item
        for item in packet.comparisons
        if item.comparison.classification.mcu_id == "mcu_control"
        and item.comparison.classification.relation == PrecedentState.DIRECT_PRECEDENT
    )
    assert len({item.comparison.comparison.source_id for item in direct}) == 2
    support_edges = tuple(
        relation
        for relation in packet.authorized_relations
        if relation.classification_id
        in {item.comparison.classification.classification_id for item in direct}
        and relation.edge.kind == "SUPPORTS"
    )
    assert len(support_edges) == 2
    incomplete = tuple(
        item.model_copy(
            update={
                "graph_edge_ids": tuple(
                    relation.edge.edge_id
                    for relation in support_edges
                    if relation.classification_id
                    == item.comparison.classification.classification_id
                )
            }
        )
        for item in direct
    )
    view = packet.phase6_view.model_copy(
        update={
            "committed_comparisons": incomplete,
            "authorized_graph_relations": support_edges,
        }
    )
    local_packet = _packet_from_view(packet, view, "two_incomplete_source_projections")
    finding = evaluate_gate_c(local_packet, TargetRef(kind="MCU", id="mcu_control"), None)
    assert finding.state != "DIRECT_ESTABLISHED"


def test_gate_c_judge_cannot_invent_phase6_direct(packet: AdjudicationCasePacket) -> None:
    no_direct = _packet_with_comparisons(packet, kept_relations=frozenset())
    judge = JudgeFinding(
        assessment_id=no_direct.assessment_id,
        assessment_context_id=no_direct.assessment_context_id,
        phase6_snapshot_id=no_direct.phase6_snapshot_id,
        target_id="mcu_control",
        finding_id="p7judge_claim_direct",
        proposed_gate_c="DIRECT_ESTABLISHED",
        reason="A judge claims a direct precedent",
    )
    with pytest.raises(ValueError, match="Phase 6|direct"):
        evaluate_gate_c(no_direct, TargetRef(kind="MCU", id="mcu_control"), judge)


def test_gate_c_forged_graph_relation_cannot_establish_direct(
    packet: AdjudicationCasePacket,
) -> None:
    original = next(
        item
        for item in packet.comparisons
        if item.comparison.classification.mcu_id == "mcu_control"
        and item.comparison.classification.relation == PrecedentState.DIRECT_PRECEDENT
    )
    forged = original.model_copy(
        update={"graph_edge_ids": (*original.graph_edge_ids, "gedge_fabricated")}
    )
    view = packet.phase6_view.model_copy(
        update={
            "committed_comparisons": (forged,),
            "authorized_graph_relations": tuple(
                relation
                for relation in packet.authorized_relations
                if relation.classification_id
                == original.comparison.classification.classification_id
            ),
        }
    )
    local_packet = _packet_from_view(packet, view, "forged_graph_relation")
    finding = evaluate_gate_c(local_packet, TargetRef(kind="MCU", id="mcu_control"), None)
    assert finding.state != "DIRECT_ESTABLISHED"


def _partial_gate_d_inputs(tmp_path, proposed_state: str):
    packet = _matrix_packet(tmp_path, "STRONG_PARTIAL_PRECEDENT")
    classification = packet.comparisons[0].comparison.classification
    target = TargetRef(kind="MCU", id="mcu_1")
    judge = JudgeFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        finding_id="p7judge_gate_d_" + proposed_state,
        phase6_basis_ids=(str(classification.classification_id),),
        proposed_gate_d=proposed_state,
        reason="The missing feature is assessed in the claimed causal scope",
    )
    localization = CounterfactualLocalization(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        localization_id="p7counterfactual_" + proposed_state,
        nearest_comparison_id=str(classification.classification_id),
        removed_element=classification.missing_elements[0],
        substantial_equivalence_after_removal=True,
        reason="Removing the missing feature leaves the verified historical core",
    )
    return packet, target, judge, localization


def test_gate_d_terminology_only_is_non_substantive(tmp_path) -> None:
    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "NON_SUBSTANTIVE")
    finding = evaluate_gate_d(packet, target, judge, localization)
    assert finding.state == "NON_SUBSTANTIVE"
    assert finding.nearest_comparison_ids == (localization.nearest_comparison_id,)


def test_gate_d_causal_or_topology_change_can_be_substantive(tmp_path) -> None:
    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "SUBSTANTIVE")
    finding = evaluate_gate_d(packet, target, judge, localization)
    assert finding.state == "SUBSTANTIVE"
    assert finding.counterfactual_id == localization.localization_id
    assert packet.comparisons[0].comparison.classification.relation == (
        PrecedentState.STRONG_PARTIAL_PRECEDENT
    )


def test_gate_d_missing_user_meaning_is_input_need(packet: AdjudicationCasePacket) -> None:
    target = TargetRef(kind="MCU", id="mcu_status")
    gate_a, needs = evaluate_gate_a(packet, target)
    assert gate_a.state == "INSUFFICIENT"
    finding = evaluate_gate_d(packet, target, None, None)
    assert finding.state == "UNRESOLVED"
    assert "input_clarification_required" in finding.limiting_factors
    assert needs[0].material_gate == "A"


def test_gate_d_missing_closest_source_can_request_research(
    packet: AdjudicationCasePacket,
) -> None:
    no_comparison = _packet_with_comparisons(packet, kept_relations=frozenset())
    target = TargetRef(kind="MCU", id="mcu_control")
    finding = evaluate_gate_d(no_comparison, target, None, None)
    gap = gate_d_research_gap(no_comparison, target, finding)
    assert finding.state == "UNRESOLVED"
    assert gap is not None
    assert gap.material_gate == "D"
    assert gap.missing_prior_art_reference


def test_gate_d_counterfactual_rejects_foreign_context(tmp_path) -> None:
    packet, target, _, localization = _partial_gate_d_inputs(tmp_path, "SUBSTANTIVE")
    foreign = localization.model_copy(update={"assessment_context_id": "p7ctx_foreign"})
    with pytest.raises(ValueError, match="scope"):
        validate_counterfactual(packet, target, foreign)


def test_gate_d_direct_precedent_has_no_residual_localization(
    packet: AdjudicationCasePacket,
) -> None:
    target = TargetRef(kind="MCU", id="mcu_control")
    finding = evaluate_gate_d(packet, target, None, None)
    assert finding.state == "NOT_APPLICABLE_TO_DIRECT"
    assert finding.nearest_comparison_ids
    assert gate_d_research_gap(packet, target, finding) is None


def test_gate_d_counterfactual_rejects_invented_difference(tmp_path) -> None:
    packet, target, _, localization = _partial_gate_d_inputs(tmp_path, "SUBSTANTIVE")
    invented = localization.model_copy(update={"removed_element": "invented mechanism"})
    with pytest.raises(ValueError, match="localized Phase 6 difference"):
        validate_counterfactual(packet, target, invented)


def test_gate_d_unsupported_value_claim_cannot_change_novelty(tmp_path) -> None:
    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "NON_SUBSTANTIVE")
    before = evaluate_gate_d(packet, target, judge, localization)
    high_value_claim = packet.manifest.cir.model_copy(
        update={
            "claimed_advantages": tuple(
                item.model_copy(update={"maturity": ValueMaturity.DEMONSTRATED})
                for item in packet.manifest.cir.claimed_advantages
            )
        }
    )
    manifest = packet.manifest.model_copy(update={"cir": high_value_claim})
    context = SealedAssessmentContext(
        context_id="p7ctx_fixture_high_value",
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id="p7manifest_" + manifest.content_digest(),
        manifest_digest=manifest.content_digest(),
        manifest=manifest,
    )
    changed_packet = build_adjudication_case(context, packet.phase6_view)
    changed_judge = judge.model_copy(update={"assessment_context_id": context.context_id})
    changed_localization = localization.model_copy(
        update={"assessment_context_id": context.context_id}
    )
    after = evaluate_gate_d(changed_packet, target, changed_judge, changed_localization)
    assert before.state == after.state == "NON_SUBSTANTIVE"
