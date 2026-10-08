"""Typed categorical Phase 7 gate findings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from pydantic import JsonValue

from novelty_harness.adjudication.counterfactual import (
    CounterfactualLocalization,
    validate_counterfactual,
)
from novelty_harness.adjudication.models import TargetRef, TargetScoped
from novelty_harness.adjudication.needs import (
    GateDExternalEvidenceBasis,
    InputClarificationNeed,
    ResearchGapRequest,
)
from novelty_harness.adjudication.packet import AdjudicationCasePacket
from novelty_harness.adjudication.roles import GateCState, GateDState
from novelty_harness.domain.enums import (
    EvidenceFamily,
    PrecedentState,
    ResearchDepth,
    SufficiencyState,
    SupportVerificationState,
)
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.evidence.graph.assessment_view import CommittedComparisonView
from novelty_harness.evidence.graph.models import GraphEdgeKind
from novelty_harness.research.adaptive.stopping import StopReason
from novelty_harness.research.coverage import CoverageState
from novelty_harness.research.models import FamilyApplicability
from novelty_harness.runtime.budgets.controller import BudgetController
from novelty_harness.runtime.tracing.hashing import canonical_hash

if TYPE_CHECKING:
    from novelty_harness.adjudication.judge import JudgeFinding

GateBPermission = Literal[
    "CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE",
    "MEANINGFUL_BOUNDED_POSITIVE_COMPARISON",
    "STRONG_POSITIVE_COVERAGE",
]


class GateFinding(TargetScoped):
    gate_id: str
    basis_ids: tuple[str, ...] = ()
    accepted_judge_finding_ids: tuple[str, ...] = ()
    limiting_factors: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    method_version: str = "phase7-gates-v2"
    provenance: str | None = None


class GateAFinding(GateFinding):
    contract_kind: Literal["phase7-gate-a-finding-v1"] = "phase7-gate-a-finding-v1"
    state: Literal["ASSESSABLE", "LIMITED", "INSUFFICIENT"]
    missing_fields: tuple[str, ...] = ()


class GateBFinding(GateFinding):
    contract_kind: Literal["phase7-gate-b-finding-v1"] = "phase7-gate-b-finding-v1"
    permissions: tuple[GateBPermission, ...] = ()


class GateCFinding(GateFinding):
    contract_kind: Literal["phase7-gate-c-finding-v1"] = "phase7-gate-c-finding-v1"
    state: GateCState
    comparison_ids: tuple[str, ...] = ()
    graph_relation_ids: tuple[str, ...] = ()
    source_version_ids: tuple[str, ...] = ()
    passage_ids: tuple[str, ...] = ()
    residual_delta: str | None = None


class GateDFinding(GateFinding):
    contract_kind: Literal["phase7-gate-d-finding-v1"] = "phase7-gate-d-finding-v1"
    state: GateDState
    differentiator: str | None = None
    nearest_comparison_ids: tuple[str, ...] = ()
    counterfactual_id: str | None = None


def evaluate_gate_a(
    packet: AdjudicationCasePacket, target: TargetRef
) -> tuple[GateAFinding, tuple[InputClarificationNeed, ...]]:
    """Determine claim-input comparison permission without dispatching research."""

    packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
    target = TargetRef.model_validate_json(target.model_dump_json())
    profile = next(
        (
            item
            for item in packet.target_profiles
            if item.target_id == target.id and item.target_kind == target.kind
        ),
        None,
    )
    if profile is None:
        raise ValueError("Gate A target is absent from the sealed packet")
    sufficiency = packet.manifest.sufficiency
    graph = packet.manifest.mcu_graph
    disagreements = graph.unresolved_disagreements if isinstance(graph, MCUGraph) else ()
    unresolved = " ".join((*packet.manifest.cir.unknowns, *disagreements)).casefold()
    missing: list[str] = []
    clarification: list[str] = []
    limits: list[str] = []
    if sufficiency.state == SufficiencyState.INSUFFICIENT:
        missing.append("phase2_sufficiency")
        limits.append("phase2_insufficient")
    elif sufficiency.state == SufficiencyState.EXPLORATORY:
        limits.append("phase2_exploratory")
    if profile.target_kind == "COMBINATION":
        if not profile.combination_relationships or "topology" in unresolved:
            missing.append("combination_topology")
            limits.append("unknown_combination_topology")
        if disagreements:
            missing.append("stable_decomposition")
            limits.append("unresolved_graph_decomposition")
    else:
        if profile.mechanism is None:
            if not profile.relationships or "mechanism" in unresolved:
                missing.append("mechanism")
                limits.append("unknown_material_mechanism")
            else:
                clarification.append("mechanism")
                limits.append("mechanism_unspecified")
        if "relationship direction" in unresolved and (
            target.id.casefold() in unresolved or profile.label.casefold() in unresolved
        ):
            missing.append("relationship_direction")
            limits.append("unresolved_relationship_direction")
        if disagreements and not missing:
            limits.append("unresolved_graph_decomposition")
    state: Literal["ASSESSABLE", "LIMITED", "INSUFFICIENT"] = (
        "INSUFFICIENT" if missing else "LIMITED" if limits else "ASSESSABLE"
    )
    missing_fields = tuple(dict.fromkeys((*missing, *clarification)))
    limiting_factors = tuple(dict.fromkeys(limits))
    basis_ids = (
        packet.manifest_id,
        str(packet.manifest.cir.idea_id),
        packet.manifest.cir.original_input_ref,
        profile.target_id,
    )
    gate_id = "p7gate_" + canonical_hash(
        cast(
            JsonValue,
            {
                "gate": "A",
                "case_id": packet.case_id,
                "target_id": target.id,
                "state": state,
                "missing_fields": missing_fields,
                "limiting_factors": limiting_factors,
                "method_version": "phase7-gates-v2",
            },
        )
    )
    finding = GateAFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        gate_id=gate_id,
        state=state,
        basis_ids=basis_ids,
        limiting_factors=limiting_factors,
        missing_fields=missing_fields,
        unresolved_questions=missing_fields,
        provenance="SEALED_PHASE2_INPUT_AND_TARGET_PROFILE",
    )
    if not missing_fields:
        return finding, ()
    need = InputClarificationNeed(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        need_id="p7need_"
        + canonical_hash(
            cast(
                JsonValue,
                {"case_id": packet.case_id, "target_id": target.id, "missing": missing_fields},
            )
        ),
        reason="The target claim lacks material input needed for comparison",
        missing_input_fields=missing_fields,
        material_gate="A",
        resolution_requirement="Clarify the named claim fields before adjudication",
        provenance="SEALED_PHASE2_INPUT_AND_TARGET_PROFILE",
    )
    return finding, (need,)


def evaluate_gate_b(packet: AdjudicationCasePacket, target: TargetRef) -> GateBFinding:
    """Intersect actual target evidence with sealed research coverage facts."""

    packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
    target = TargetRef.model_validate_json(target.model_dump_json())
    profile = next(
        (
            item
            for item in packet.target_profiles
            if item.target_id == target.id and item.target_kind == target.kind
        ),
        None,
    )
    if profile is None:
        raise ValueError("Gate B target is absent from the sealed packet")
    comparisons = tuple(
        item
        for item in packet.comparisons
        if item.comparison.comparison.chain.edge.mcu_id == target.id
    )
    assessed = tuple(
        item
        for item in packet.candidate_outcomes
        if item.target_id == target.id and item.decision == "ASSESSED"
    )
    unassessed = tuple(
        item
        for item in packet.candidate_outcomes
        if item.target_id == target.id and item.decision != "ASSESSED"
    )
    exclusions = tuple(
        item
        for item in (*packet.coverage.excluded_sources, *packet.coverage.excluded_versions)
        if item.target_id is None or item.target_id == target.id
    )
    eligible = tuple(
        item
        for item in comparisons
        if item.projection_status == "GRAPH_AUTHORIZED"
        and item.comparison.comparison.chain.verification.state
        in {SupportVerificationState.SUPPORTED, SupportVerificationState.PARTIALLY_SUPPORTED}
        and item.cited_passages
    )
    negative = tuple(
        item
        for item in eligible
        if (
            item.comparison.classification.relation == PrecedentState.DIRECT_PRECEDENT
            and item.comparison.classification.decisive
            and item.comparison.comparison.chain.verification.state
            == SupportVerificationState.SUPPORTED
        )
        or (
            item.comparison.classification.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT
            and item.comparison.comparison.chain.edge.chronology.state == "PREDATES_CUTOFF"
            and item.comparison.comparison.source_version_id is not None
            and bool(item.comparison.classification.covered_elements)
            and bool(
                item.comparison.classification.missing_elements
                or item.comparison.classification.missing_relationships
                or item.comparison.classification.configuration_gap
            )
            and any(
                relation.commit_id == item.commit_id
                and relation.classification_id == item.comparison.classification.classification_id
                and relation.edge.kind == GraphEdgeKind.STRONG_PARTIAL_PRECEDENT
                for relation in packet.authorized_relations
            )
        )
    )
    meaningful = tuple(
        item
        for item in eligible
        if item.comparison.classification.relation
        not in {
            PrecedentState.SUPERFICIAL_SIMILARITY,
            PrecedentState.UNASSESSABLE,
            PrecedentState.UNRESOLVED,
        }
    )
    permissions: list[GateBPermission] = []
    if negative:
        permissions.append("CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE")
    if meaningful and assessed:
        permissions.append("MEANINGFUL_BOUNDED_POSITIVE_COMPARISON")
    manifest = packet.manifest
    limits: list[str] = []
    plan = manifest.research_plan
    research = manifest.research_result
    if plan is None or research is None or manifest.coverage_policy is None:
        limits.append("historical_research_unknown")
    elif not plan.reviewed:
        limits.append("research_plan_unreviewed")
    if unassessed or exclusions:
        limits.append("unassessed_candidate")
    if packet.coverage.limitations:
        limits.append("phase6_coverage_limited")
    if manifest.stop_reason == "BUDGET_STOPPED" or (
        research is not None
        and any(stop.reason == StopReason.BUDGET_STOPPED for stop in research.stop_assessments)
    ):
        limits.append("budget_stopped")
    if manifest.stop_reason == "NO_NEW_YIELD":
        limits.append("no_new_yield_is_not_saturation")
    if (
        manifest.access_failures
        or manifest.stop_reason == "ACCESS_BLOCKED"
        or any(
            cell.state in {CoverageState.BLOCKED_NO_PROVIDER, CoverageState.PROVIDER_FAILURE}
            for cell in manifest.coverage_cells
            if cell.mcu_id in ({target.id} | set(profile.combination_members))
        )
    ):
        limits.append("provider_or_access_blocked")
    if manifest.remaining_gaps:
        limits.append("material_external_gap")
    if not meaningful:
        limits.append("no_relevant_assessed_comparison")
    if (
        plan is not None
        and research is not None
        and plan.reviewed
        and manifest.coverage_policy is not None
        and manifest.budget_limits is not None
        and manifest.budget_usage is not None
        and BudgetController().check(manifest.budget_usage, manifest.budget_limits).allowed
        and not limits
    ):
        research_targets = {target.id} | set(profile.combination_members)
        branches = tuple(
            item for item in plan.family_assessments if item.mcu_id in research_targets
        )
        branch_keys = {(item.mcu_id, item.evidence_family) for item in branches}
        expected_branch_keys = {
            (mcu_id, family) for mcu_id in research_targets for family in EvidenceFamily
        }
        applicable = tuple(
            item
            for item in branches
            if item.applicability
            in {FamilyApplicability.APPLICABLE, FamilyApplicability.POSSIBLY_APPLICABLE}
        )
        matrix = {
            (cell.screening.mcu_id, cell.screening.evidence_family): cell
            for cell in research.coverage_matrix
        }
        manifest_cells = {
            (cell.mcu_id, cell.evidence_family): cell for cell in manifest.coverage_cells
        }
        states = {(item.mcu_id, item.evidence_family): item for item in research.branch_states}
        policy = manifest.coverage_policy
        if (
            branch_keys == expected_branch_keys
            and applicable
            and all(
                branch.applicability != FamilyApplicability.UNRESOLVED and not branch.limitations
                for branch in branches
            )
            and not plan.limitations
            and not research.limitations
            and all(
                (cell := matrix.get((branch.mcu_id, branch.evidence_family))) is not None
                and cell.screening == manifest_cells.get((branch.mcu_id, branch.evidence_family))
                and cell.screening.state == CoverageState.SCREENED
                and len(cell.screening.planned_query_families)
                >= policy.by_family[branch.evidence_family].min_distinct_query_families
                and policy.by_family[branch.evidence_family].required_query_families
                <= cell.screening.planned_query_families
                and len(cell.screening.configured_providers)
                >= policy.by_family[branch.evidence_family].min_configured_providers
                and len(cell.screening.successful_providers)
                >= policy.by_family[branch.evidence_family].min_configured_providers
                and cell.screening.planned_query_families
                == frozenset(
                    query.query_family
                    for query in plan.intents
                    if (query.mcu_id, query.evidence_family)
                    == (branch.mcu_id, branch.evidence_family)
                )
                and cell.depth == ResearchDepth.SATURATED
                and cell.stop.reason == StopReason.SATURATED
                and (state := states.get((branch.mcu_id, branch.evidence_family))) is not None
                and not state.unresolved
                and not state.budget_stopped
                and not state.access_failures
                and not state.deferred_neighborhoods
                and not cell.screening.limitations
                for branch in applicable
            )
        ):
            permissions.append("STRONG_POSITIVE_COVERAGE")
        else:
            limits.append("coverage_not_converged")
    elif "historical_research_unknown" not in limits and "budget_stopped" not in limits:
        limits.append("strong_coverage_not_established")
    limiting_factors = tuple(dict.fromkeys(limits))
    basis_ids = tuple(
        dict.fromkeys(
            (
                packet.manifest_id,
                target.id,
                *(str(item.comparison.classification.classification_id) for item in eligible),
            )
        )
    )
    return GateBFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        gate_id="p7gate_"
        + canonical_hash(
            cast(
                JsonValue,
                {
                    "gate": "B",
                    "case_id": packet.case_id,
                    "target_id": target.id,
                    "permissions": permissions,
                    "limitations": limiting_factors,
                    "method_version": "phase7-gates-v2",
                },
            )
        ),
        permissions=tuple(permissions),
        basis_ids=basis_ids,
        limiting_factors=limiting_factors,
        unresolved_questions=manifest.remaining_gaps,
        provenance="SEALED_RESEARCH_AND_PHASE6_ASSESSMENT",
    )


def _authorized_gate_c_relations(
    packet: AdjudicationCasePacket, item: CommittedComparisonView
) -> tuple[str, ...]:
    """Return an exact graph join, or no usable relation for this chain."""

    classification = item.comparison.classification
    relations = tuple(
        relation
        for relation in packet.authorized_relations
        if relation.commit_id == item.commit_id
        and relation.classification_id == classification.classification_id
        and relation.verified_edge_id == item.comparison.comparison.chain.edge.edge_id
    )
    if item.projection_status != "GRAPH_AUTHORIZED" or {
        relation.edge.edge_id for relation in relations
    } != set(item.graph_edge_ids):
        return ()
    if any(
        relation.edge.verification is None
        or relation.edge.verification.support_state
        != item.comparison.comparison.chain.verification.state
        or relation.edge.verification.precedent_relation not in {None, classification.relation}
        for relation in relations
    ):
        return ()
    return tuple(sorted(relation.edge.edge_id for relation in relations))


def evaluate_gate_c(
    packet: AdjudicationCasePacket, target: TargetRef, judge: JudgeFinding | None
) -> GateCFinding:
    """Resolve one target from repository-derived Phase 6 chains without reclassification."""

    from novelty_harness.adjudication.judge import JudgeFinding

    packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
    target = TargetRef.model_validate_json(target.model_dump_json())
    if not any(
        profile.target_id == target.id and profile.target_kind == target.kind
        for profile in packet.target_profiles
    ):
        raise ValueError("Gate C target is absent from the sealed packet")
    comparisons = tuple(
        item for item in packet.comparisons if item.comparison.classification.mcu_id == target.id
    )
    if judge is not None:
        judge = JudgeFinding.model_validate_json(judge.model_dump_json())
        if (
            judge.assessment_id,
            judge.assessment_context_id,
            judge.phase6_snapshot_id,
            judge.target_id,
        ) != (
            packet.assessment_id,
            packet.assessment_context_id,
            packet.phase6_snapshot_id,
            target.id,
        ):
            raise ValueError("Gate C judge finding has foreign scope")
        phase6_ids = (
            {str(item.comparison.classification.classification_id) for item in comparisons}
            | {
                str(passage.passage.passage_id)
                for item in comparisons
                for passage in item.cited_passages
            }
            | {
                relation.edge.edge_id
                for relation in packet.authorized_relations
                if relation.classification_id
                in {item.comparison.classification.classification_id for item in comparisons}
            }
        )
        if not set(judge.phase6_basis_ids) <= phase6_ids:
            raise ValueError("Gate C judge cites absent Phase 6 evidence")

    eligible: list[tuple[CommittedComparisonView, tuple[str, ...]]] = []
    for item in comparisons:
        compared = item.comparison.comparison
        classification = item.comparison.classification
        relation_ids = _authorized_gate_c_relations(packet, item)
        if (
            relation_ids
            and compared.source_id == classification.source_id
            and compared.source_version_id is not None
            and compared.source_version_id == classification.source_version_id
            and compared.mcu_id == target.id
            and compared.chain.edge.chronology.state == "PREDATES_CUTOFF"
            and compared.chain.verification.state
            in {SupportVerificationState.SUPPORTED, SupportVerificationState.PARTIALLY_SUPPORTED}
            and compared.chain.verification.context_completeness == "COMPLETE"
            and item.cited_passages
            and all(
                passage.passage.source_id == compared.source_id
                and passage.passage.source_version_id == compared.source_version_id
                for passage in item.cited_passages
            )
        ):
            eligible.append((item, relation_ids))
    direct = tuple(
        (item, relation_ids)
        for item, relation_ids in eligible
        if item.comparison.classification.relation == PrecedentState.DIRECT_PRECEDENT
        and item.comparison.classification.decisive
        and item.comparison.comparison.chain.verification.state
        == SupportVerificationState.SUPPORTED
        and any(
            relation.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
            for relation in packet.authorized_relations
            if relation.edge.edge_id in relation_ids
        )
    )
    partial = tuple(
        (item, relation_ids)
        for item, relation_ids in eligible
        if item.comparison.classification.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT
        and (
            item.comparison.classification.missing_elements
            or item.comparison.classification.missing_relationships
            or item.comparison.classification.configuration_gap
        )
        and any(
            relation.edge.kind == GraphEdgeKind.STRONG_PARTIAL_PRECEDENT
            for relation in packet.authorized_relations
            if relation.edge.edge_id in relation_ids
        )
    )
    limits: list[str] = []
    chosen: tuple[CommittedComparisonView, tuple[str, ...]] | None = None
    residual_delta: str | None = None
    if direct:
        state: GateCState = "DIRECT_ESTABLISHED"
        chosen = min(
            direct,
            key=lambda pair: str(pair[0].comparison.classification.classification_id),
        )
    elif partial:
        state = "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA"
        chosen = min(
            partial,
            key=lambda pair: str(pair[0].comparison.classification.classification_id),
        )
        classification = chosen[0].comparison.classification
        residual_delta = "; ".join(
            (
                *classification.missing_elements,
                *classification.missing_relationships,
                *((classification.configuration_gap,) if classification.configuration_gap else ()),
            )
        )
    elif not comparisons:
        state = "UNASSESSABLE"
        limits.append("no_target_comparison")
    elif any(
        item.comparison.classification.relation == PrecedentState.UNASSESSABLE
        for item in comparisons
    ):
        state = "UNASSESSABLE"
        limits.append("phase6_unassessable_comparison")
    elif any(
        item.comparison.classification.relation
        in {
            PrecedentState.UNRESOLVED,
            PrecedentState.CONTRADICTORY_EVIDENCE,
        }
        for item in comparisons
    ):
        state = "DISPUTED"
        limits.append("phase6_unresolved_or_contradictory_comparison")
    else:
        state = "NO_DIRECT_IN_REVIEWED_SCOPE"
        limits.append("reviewed_scope_only")
    if judge is not None and judge.proposed_gate_c is not None:
        if judge.proposed_gate_c == "DIRECT_ESTABLISHED" and not direct:
            raise ValueError("Judge cannot establish direct precedent absent Phase 6 direct chain")
        if judge.proposed_gate_c == "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA" and not partial:
            raise ValueError("Judge cannot establish substantial reproduction absent Phase 6 chain")
        if judge.proposed_gate_c != state:
            state = "DISPUTED"
            chosen = None
            residual_delta = None
            limits.append("judge_scope_disagrees_with_phase6_chain")
    comparison_ids: tuple[str, ...] = ()
    graph_relation_ids: tuple[str, ...] = ()
    source_version_ids: tuple[str, ...] = ()
    passage_ids: tuple[str, ...] = ()
    if chosen is not None:
        item, graph_relation_ids = chosen
        comparison_ids = (str(item.comparison.classification.classification_id),)
        version_id = item.comparison.comparison.source_version_id
        source_version_ids = (str(version_id),) if version_id is not None else ()
        passage_ids = tuple(
            sorted(str(passage.passage.passage_id) for passage in item.cited_passages)
        )
    if state == "NO_DIRECT_IN_REVIEWED_SCOPE" and "reviewed_scope_only" not in limits:
        limits.append("reviewed_scope_only")
    limiting_factors = tuple(dict.fromkeys(limits))
    gate_id = "p7gate_" + canonical_hash(
        cast(
            JsonValue,
            {
                "gate": "C",
                "case_id": packet.case_id,
                "target_id": target.id,
                "state": state,
                "comparison_ids": comparison_ids,
                "graph_relation_ids": graph_relation_ids,
                "source_version_ids": source_version_ids,
                "passage_ids": passage_ids,
                "residual_delta": residual_delta,
                "limiting_factors": limiting_factors,
                "judge_finding_id": judge.finding_id if judge is not None else None,
                "method_version": "phase7-gates-v2",
            },
        )
    )
    return GateCFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        gate_id=gate_id,
        state=state,
        comparison_ids=comparison_ids,
        graph_relation_ids=graph_relation_ids,
        source_version_ids=source_version_ids,
        passage_ids=passage_ids,
        residual_delta=residual_delta,
        basis_ids=tuple((*comparison_ids, *graph_relation_ids, *passage_ids)),
        accepted_judge_finding_ids=(judge.finding_id,) if judge is not None else (),
        limiting_factors=limiting_factors,
        provenance="PHASE6_VERIFIED_CHAIN_AND_AUTHORIZED_GRAPH",
    )


def evaluate_gate_d(
    packet: AdjudicationCasePacket,
    target: TargetRef,
    judge: JudgeFinding | None,
    localization: CounterfactualLocalization | None,
) -> GateDFinding:
    """Localize the surviving claim difference without using value claims."""

    from novelty_harness.adjudication.judge import JudgeFinding

    packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
    target = TargetRef.model_validate_json(target.model_dump_json())
    gate_a, input_needs = evaluate_gate_a(packet, target)
    gate_c = evaluate_gate_c(packet, target, judge)
    limits: list[str] = []
    state: GateDState = "UNRESOLVED"
    nearest: tuple[str, ...] = ()
    counterfactual_id: str | None = None
    differentiator: str | None = None
    judge_accepted = False
    if gate_a.state == "INSUFFICIENT" or input_needs:
        limits.append("input_clarification_required")
    elif gate_c.state == "DIRECT_ESTABLISHED":
        state = "NOT_APPLICABLE_TO_DIRECT"
        nearest = gate_c.comparison_ids
    elif judge is None or localization is None:
        limits.append("contribution_not_localized")
    else:
        judge = JudgeFinding.model_validate_json(judge.model_dump_json())
        if (
            judge.assessment_id,
            judge.assessment_context_id,
            judge.phase6_snapshot_id,
            judge.target_id,
        ) != (
            packet.assessment_id,
            packet.assessment_context_id,
            packet.phase6_snapshot_id,
            target.id,
        ):
            raise ValueError("Gate D judge finding has foreign scope")
        localization = validate_counterfactual(packet, target, localization)
        if localization.nearest_comparison_id is not None:
            nearest = (localization.nearest_comparison_id,)
        counterfactual_id = localization.localization_id
        differentiator = localization.removed_element
        if judge.proposed_gate_d in {"SUBSTANTIVE", "NON_SUBSTANTIVE"}:
            if (
                localization.substantial_equivalence_after_removal is True
                and nearest
                and not localization.remaining_differences
                and localization.nearest_comparison_id in judge.phase6_basis_ids
            ):
                state = judge.proposed_gate_d
                judge_accepted = True
            else:
                limits.append("counterfactual_or_judge_basis_unresolved")
        elif judge.proposed_gate_d == "NOT_APPLICABLE_TO_DIRECT":
            raise ValueError(
                "Judge cannot declare direct applicability without a Phase 6 direct chain"
            )
        else:
            limits.append("judge_contribution_unresolved")
    if gate_c.state in {"UNASSESSABLE", "DISPUTED"} and state != "NOT_APPLICABLE_TO_DIRECT":
        state = "UNRESOLVED"
        limits.append("closest_phase6_comparison_unresolved")
    limiting_factors = tuple(dict.fromkeys(limits))
    gate_id = "p7gate_" + canonical_hash(
        cast(
            JsonValue,
            {
                "gate": "D",
                "case_id": packet.case_id,
                "target_id": target.id,
                "state": state,
                "nearest": nearest,
                "counterfactual_id": counterfactual_id,
                "differentiator": differentiator,
                "judge_id": judge.finding_id if judge is not None else None,
                "limiting_factors": limiting_factors,
                "method_version": "phase7-gates-v2",
            },
        )
    )
    return GateDFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        gate_id=gate_id,
        state=state,
        nearest_comparison_ids=nearest,
        counterfactual_id=counterfactual_id,
        differentiator=differentiator,
        basis_ids=tuple((*nearest, *((counterfactual_id,) if counterfactual_id else ()))),
        accepted_judge_finding_ids=(judge.finding_id,) if judge_accepted and judge else (),
        limiting_factors=limiting_factors,
        unresolved_questions=tuple(limits) if state == "UNRESOLVED" else (),
        provenance="SEALED_CLAIM_AND_PHASE6_LOCALIZED_DIFFERENCE",
    )


def gate_d_research_gap(
    packet: AdjudicationCasePacket, target: TargetRef, finding: GateDFinding
) -> ResearchGapRequest | None:
    """Name a missing historical reference only when Gate A is assessable."""

    packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
    finding = GateDFinding.model_validate_json(finding.model_dump_json())
    gate_a, input_needs = evaluate_gate_a(packet, target)
    if (
        gate_a.state == "INSUFFICIENT"
        or input_needs
        or finding.state != "UNRESOLVED"
        or finding.nearest_comparison_ids
        or finding.assessment_id != packet.assessment_id
        or finding.assessment_context_id != packet.assessment_context_id
        or finding.phase6_snapshot_id != packet.phase6_snapshot_id
        or finding.target_id != target.id
    ):
        return None
    excluded = next(
        (
            item
            for item in (*packet.coverage.excluded_sources, *packet.coverage.excluded_versions)
            if item.target_id in {None, target.id}
        ),
        None,
    )
    if excluded is None:
        return None
    reference = str(excluded.source_version_id or excluded.source_id)
    return ResearchGapRequest(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target.id,
        request_id="p7gap_"
        + canonical_hash(
            cast(JsonValue, {"case_id": packet.case_id, "gate": "D", "reference": reference})
        ),
        requesting_stage="ADJUDICATION",
        gap_type="ACCESS",
        reason="An excluded historical implementation remains unassessed",
        research_hypothesis="The excluded reference may clarify the surviving difference",
        material_gate="D",
        linked_comparison_ids=finding.nearest_comparison_ids,
        missing_prior_art_reference=reference,
        external_fact_basis=GateDExternalEvidenceBasis(
            assessment_id=packet.assessment_id,
            assessment_context_id=packet.assessment_context_id,
            phase6_snapshot_id=packet.phase6_snapshot_id,
            target_id=target.id,
            target_profile_digest=canonical_hash(
                next(p for p in packet.target_profiles if p.target_id == target.id)
            ),
            contribution=next(
                p.statement for p in packet.target_profiles if p.target_id == target.id
            ),
            source_id=str(excluded.source_id),
            source_version_id=str(excluded.source_version_id)
            if excluded.source_version_id
            else None,
            missing_external_fact_type="UNASSESSED_IMPLEMENTATION",
        ),
        priority="HIGH",
        stop_condition="Assess the named reference or record its access limitation",
        provenance="PHASE6_COVERAGE_EXCLUSION",
    )


def evaluate_gate_a_with_needs(
    packet: AdjudicationCasePacket,
    target: TargetRef,
    proposed_needs: tuple[InputClarificationNeed, ...],
) -> tuple[GateAFinding, tuple[InputClarificationNeed, ...]]:
    """Semantic claim ambiguity can only reduce the sealed input permission."""
    from novelty_harness.adjudication.needs import validate_input_clarification_need

    gate, deterministic = evaluate_gate_a(packet, target)
    all_needs = {n.need_id: n for n in deterministic}
    for need in proposed_needs:
        validate_input_clarification_need(need, packet)
        if need.target_id != target.id:
            raise ValueError("Input need differs from gate target")
        if need.need_id in all_needs and all_needs[need.need_id] != need:
            raise ValueError("Input need ID conflicts")
        all_needs[need.need_id] = need
    if proposed_needs:
        fields = tuple(
            sorted(
                {
                    *gate.missing_fields,
                    *(
                        f
                        for n in proposed_needs
                        for f in (*n.missing_input_fields, *n.unresolved_structure)
                    ),
                }
            )
        )
        gate = gate.model_copy(
            update={
                "gate_id": "p7gate_"
                + canonical_hash(
                    {
                        "sealed_gate": gate.gate_id,
                        "proposed_needs": [
                            n.model_dump(mode="json")
                            for n in sorted(proposed_needs, key=lambda n: n.need_id)
                        ],
                    }
                ),
                "state": "INSUFFICIENT",
                "missing_fields": fields,
                "unresolved_questions": fields,
                "limiting_factors": tuple(
                    sorted({*gate.limiting_factors, "role_or_judge_input_clarification_required"})
                ),
            }
        )
    return gate, tuple(all_needs.values())


def evaluate_gate_b_with_gaps(
    packet: AdjudicationCasePacket, target: TargetRef, gaps: tuple[ResearchGapRequest, ...]
) -> GateBFinding:
    gate = evaluate_gate_b(packet, target)
    if not gaps:
        return gate
    return gate.model_copy(
        update={
            "gate_id": "p7gate_"
            + canonical_hash(
                {
                    "sealed_gate": gate.gate_id,
                    "unresolved_requests": cast(JsonValue, sorted(g.request_id for g in gaps)),
                }
            ),
            "permissions": tuple(
                p
                for p in gate.permissions
                if p == "CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE"
            ),
            "limiting_factors": tuple(
                sorted({*gate.limiting_factors, "unresolved_proposed_research_gap"})
            ),
            "unresolved_questions": tuple(
                sorted({*gate.unresolved_questions, *(g.reason for g in gaps)})
            ),
        }
    )
