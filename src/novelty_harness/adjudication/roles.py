"""Untrusted role proposals and bounded dispute records."""

from typing import TYPE_CHECKING, Literal, Self

from pydantic import model_validator

from novelty_harness.adjudication.models import TargetScoped
from novelty_harness.adjudication.needs import (
    InputClarificationNeed,
    ResearchGapRequest,
    validate_proposed_needs,
)
from novelty_harness.adjudication.prompts import DEFENDER_PROMPT_VERSION, PROSECUTOR_PROMPT_VERSION
from novelty_harness.runtime.tracing.hashing import canonical_hash

if TYPE_CHECKING:
    from novelty_harness.adjudication.packet import AdjudicationCasePacket

ChallengeEffect = Literal[
    "DIRECT_CHALLENGE",
    "PARTIAL_CHALLENGE",
    "COMPONENT_CHALLENGE",
    "ANALOGY_CHALLENGE",
    "NO_MATERIAL_CHALLENGE",
    "UNRESOLVED_CHALLENGE",
]
GateCState = Literal[
    "DIRECT_ESTABLISHED",
    "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA",
    "NO_DIRECT_IN_REVIEWED_SCOPE",
    "DISPUTED",
    "UNASSESSABLE",
]
GateDState = Literal["SUBSTANTIVE", "NON_SUBSTANTIVE", "UNRESOLVED", "NOT_APPLICABLE_TO_DIRECT"]


class RoleArgument(TargetScoped):
    contract_kind: Literal["phase7-role-argument-v1"] = "phase7-role-argument-v1"
    argument_id: str
    thesis: str
    effect: ChallengeEffect
    comparison_ids: tuple[str, ...] = ()
    graph_relation_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    source_version_ids: tuple[str, ...] = ()
    passage_ids: tuple[str, ...] = ()
    matched_elements: tuple[str, ...] = ()
    matched_relationships: tuple[str, ...] = ()
    missing_elements: tuple[str, ...] = ()
    material_conflicts: tuple[str, ...] = ()
    chronology_analysis: str | None = None
    coverage_relevance: str | None = None
    counterfactual: str | None = None
    limitations: tuple[str, ...] = ()


class ProsecutionCase(TargetScoped):
    contract_kind: Literal["phase7-prosecution-case-v2"] = "phase7-prosecution-case-v2"
    case_id: str
    challenges: tuple[RoleArgument, ...]
    input_need_ids: tuple[str, ...] = ()
    research_gap_ids: tuple[str, ...] = ()
    input_needs: tuple[InputClarificationNeed, ...] = ()
    research_gaps: tuple[ResearchGapRequest, ...] = ()
    limitations: tuple[str, ...] = ()
    prompt_version: str = "p7-prosecutor-v2"
    model_provenance: str | None = None

    @model_validator(mode="after")
    def valid_challenges(self) -> Self:
        if len({item.argument_id for item in self.challenges}) != len(self.challenges):
            raise ValueError("Challenge IDs must be unique")
        for item in self.challenges:
            if (
                item.assessment_id,
                item.assessment_context_id,
                item.phase6_snapshot_id,
                item.target_id,
            ) != (
                self.assessment_id,
                self.assessment_context_id,
                self.phase6_snapshot_id,
                self.target_id,
            ):
                raise ValueError("Challenge scope differs from prosecution case")
        return self


class DefensePoint(TargetScoped):
    contract_kind: Literal["phase7-defense-point-v1"] = "phase7-defense-point-v1"
    defense_id: str
    disposition: Literal["CONCESSION", "OBJECTION", "UNRESOLVED"]
    thesis: str
    comparison_ids: tuple[str, ...] = ()
    graph_relation_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    source_version_ids: tuple[str, ...] = ()
    passage_ids: tuple[str, ...] = ()
    differentiators: tuple[str, ...] = ()
    counterfactual: str | None = None
    limitations: tuple[str, ...] = ()


class DefenseCase(TargetScoped):
    contract_kind: Literal["phase7-defense-case-v2"] = "phase7-defense-case-v2"
    case_id: str
    points: tuple[DefensePoint, ...]
    input_need_ids: tuple[str, ...] = ()
    research_gap_ids: tuple[str, ...] = ()
    input_needs: tuple[InputClarificationNeed, ...] = ()
    research_gaps: tuple[ResearchGapRequest, ...] = ()
    limitations: tuple[str, ...] = ()
    prompt_version: str = "p7-defender-v2"
    model_provenance: str | None = None

    @model_validator(mode="after")
    def valid_points(self) -> Self:
        if len({item.defense_id for item in self.points}) != len(self.points):
            raise ValueError("Defense IDs must be unique")
        for item in self.points:
            if (
                item.assessment_id,
                item.assessment_context_id,
                item.phase6_snapshot_id,
                item.target_id,
            ) != (
                self.assessment_id,
                self.assessment_context_id,
                self.phase6_snapshot_id,
                self.target_id,
            ):
                raise ValueError("Defense point scope differs from defense case")
        return self


class RebuttalCase(TargetScoped):
    contract_kind: Literal["phase7-rebuttal-case-v2"] = "phase7-rebuttal-case-v2"
    rebuttal_id: str
    role: Literal["PROSECUTOR", "DEFENDER"]
    dispute_ids: tuple[str, ...]
    argument_ids: tuple[str, ...]
    comparison_ids: tuple[str, ...] = ()
    graph_relation_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    source_version_ids: tuple[str, ...] = ()
    passage_ids: tuple[str, ...] = ()
    points: tuple[str, ...] = ()
    input_need_ids: tuple[str, ...] = ()
    research_gap_ids: tuple[str, ...] = ()
    input_needs: tuple[InputClarificationNeed, ...] = ()
    research_gaps: tuple[ResearchGapRequest, ...] = ()
    limitations: tuple[str, ...] = ()


class DisputeResolutionCandidate(TargetScoped):
    contract_kind: Literal["phase7-dispute-resolution-candidate-v1"] = (
        "phase7-dispute-resolution-candidate-v1"
    )
    candidate_id: str
    dispute_id: str
    gate_c_candidate: GateCState | None = None
    gate_d_candidate: GateDState | None = None
    basis_argument_ids: tuple[str, ...]
    basis_phase6_ids: tuple[str, ...] = ()
    bounded: Literal[True]
    reason: str


class Dispute(TargetScoped):
    contract_kind: Literal["phase7-dispute-v2"] = "phase7-dispute-v2"
    dispute_id: str
    argument_ids: tuple[str, ...]
    disputed_effect: str
    candidates: tuple[DisputeResolutionCandidate, ...] = ()
    resolution_space_unbounded: bool = False
    scope_review: bool = False

    @model_validator(mode="after")
    def valid_resolution_space(self) -> Self:
        if self.resolution_space_unbounded:
            if self.candidates:
                raise ValueError("Unbounded dispute cannot assert a candidate pair")
            return self
        if len(self.candidates) != 2:
            raise ValueError("Bounded dispute needs exactly two candidates")
        if self.candidates[0].candidate_id == self.candidates[1].candidate_id:
            raise ValueError("Dispute candidates must be distinct")
        for item in self.candidates:
            if (
                item.dispute_id,
                item.assessment_id,
                item.assessment_context_id,
                item.phase6_snapshot_id,
                item.target_id,
            ) != (
                self.dispute_id,
                self.assessment_id,
                self.assessment_context_id,
                self.phase6_snapshot_id,
                self.target_id,
            ):
                raise ValueError("Candidate scope differs from dispute")
        return self


def _validate_scope(item: TargetScoped, packet: "AdjudicationCasePacket") -> None:
    if (
        item.assessment_id != packet.assessment_id
        or item.assessment_context_id != packet.assessment_context_id
        or item.phase6_snapshot_id != packet.phase6_snapshot_id
        or item.target_id not in packet.target_ids
    ):
        raise ValueError("Role proposal scope differs from the case packet")


def _validate_citations(
    packet: "AdjudicationCasePacket",
    target_id: str,
    *,
    comparison_ids: tuple[str, ...],
    graph_relation_ids: tuple[str, ...] = (),
    source_ids: tuple[str, ...] = (),
    source_version_ids: tuple[str, ...] = (),
    passage_ids: tuple[str, ...] = (),
) -> None:
    if any(
        len(set(ids)) != len(ids)
        for ids in (
            comparison_ids,
            graph_relation_ids,
            source_ids,
            source_version_ids,
            passage_ids,
        )
    ):
        raise ValueError("Role citation IDs must be unique")
    comparisons = {
        str(item.comparison.classification.classification_id): item
        for item in packet.comparisons
        if item.comparison.comparison.chain.edge.mcu_id == target_id
    }
    if not set(comparison_ids) <= set(comparisons):
        raise ValueError("Role comparison ID is absent from the packet target")
    if not comparison_ids and any(
        (
            graph_relation_ids,
            source_ids,
            source_version_ids,
            passage_ids,
        )
    ):
        raise ValueError("Role citation requires a packet comparison ID")
    selected = tuple(comparisons[identity] for identity in comparison_ids)
    allowed_sources = {str(item.comparison.comparison.chain.source.source_id) for item in selected}
    allowed_versions = {
        str(item.comparison.comparison.chain.version.version_id)
        for item in selected
        if item.comparison.comparison.chain.version is not None
    }
    allowed_passages = {
        str(passage.passage.passage_id) for item in selected for passage in item.cited_passages
    }
    allowed_relations = {
        str(relation.edge.edge_id)
        for relation in packet.authorized_relations
        if str(relation.classification_id) in comparison_ids
        and any(
            relation.verified_edge_id == item.comparison.comparison.chain.edge.edge_id
            for item in selected
        )
    }
    if set(source_ids) - allowed_sources:
        raise ValueError("Role source ID is absent from its packet comparison")
    if set(source_version_ids) - allowed_versions:
        raise ValueError("Role source version ID is absent from its packet comparison")
    if set(passage_ids) - allowed_passages:
        raise ValueError("Role passage ID is absent from its packet comparison")
    if set(graph_relation_ids) - allowed_relations:
        raise ValueError("Role graph relation ID is absent from authorized packet relations")


def validate_prosecution_case(
    case: ProsecutionCase, packet: "AdjudicationCasePacket"
) -> ProsecutionCase:
    case = ProsecutionCase.model_validate_json(case.model_dump_json())
    _validate_scope(case, packet)
    if case.prompt_version != PROSECUTOR_PROMPT_VERSION:
        raise ValueError("Prosecution prompt version is stale")
    validate_proposed_needs(case, packet)
    for argument in case.challenges:
        _validate_scope(argument, packet)
        if argument.effect == "DIRECT_CHALLENGE" and len(argument.comparison_ids) > 1:
            raise ValueError("One direct challenge cannot stitch multiple comparisons")
        _validate_citations(
            packet,
            argument.target_id,
            comparison_ids=argument.comparison_ids,
            graph_relation_ids=argument.graph_relation_ids,
            source_ids=argument.source_ids,
            source_version_ids=argument.source_version_ids,
            passage_ids=argument.passage_ids,
        )
    return case


def validate_defense_case(case: DefenseCase, packet: "AdjudicationCasePacket") -> DefenseCase:
    case = DefenseCase.model_validate_json(case.model_dump_json())
    _validate_scope(case, packet)
    if case.prompt_version != DEFENDER_PROMPT_VERSION:
        raise ValueError("Defense prompt version is stale")
    validate_proposed_needs(case, packet)
    for point in case.points:
        _validate_scope(point, packet)
        _validate_citations(
            packet,
            point.target_id,
            comparison_ids=point.comparison_ids,
            graph_relation_ids=point.graph_relation_ids,
            source_ids=point.source_ids,
            source_version_ids=point.source_version_ids,
            passage_ids=point.passage_ids,
        )
    return case


def validate_rebuttal_case(case: RebuttalCase, packet: "AdjudicationCasePacket") -> RebuttalCase:
    case = RebuttalCase.model_validate_json(case.model_dump_json())
    _validate_scope(case, packet)
    validate_proposed_needs(case, packet)
    if not case.dispute_ids or not case.argument_ids:
        raise ValueError("Rebuttal must name a dispute and an argument")
    if len(set(case.dispute_ids)) != len(case.dispute_ids) or len(set(case.argument_ids)) != len(
        case.argument_ids
    ):
        raise ValueError("Rebuttal links must be unique")
    _validate_citations(
        packet,
        case.target_id,
        comparison_ids=case.comparison_ids,
        graph_relation_ids=case.graph_relation_ids,
        source_ids=case.source_ids,
        source_version_ids=case.source_version_ids,
        passage_ids=case.passage_ids,
    )
    return case


def material_disputes(
    prosecution: ProsecutionCase,
    defense: DefenseCase,
    packet: "AdjudicationCasePacket",
    *,
    rebuttals: tuple[RebuttalCase, ...] = (),
) -> tuple[Dispute, ...]:
    """Derive material alternatives from validated, independent role positions."""

    prosecution = validate_prosecution_case(prosecution, packet)
    defense = validate_defense_case(defense, packet)
    if prosecution.target_id != defense.target_id:
        raise ValueError("First-pass roles address different targets")
    base: list[Dispute] = []
    c_state_by_effect: dict[ChallengeEffect, GateCState] = {
        "DIRECT_CHALLENGE": "DIRECT_ESTABLISHED",
        "PARTIAL_CHALLENGE": "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA",
        "COMPONENT_CHALLENGE": "NO_DIRECT_IN_REVIEWED_SCOPE",
        "ANALOGY_CHALLENGE": "NO_DIRECT_IN_REVIEWED_SCOPE",
        "NO_MATERIAL_CHALLENGE": "NO_DIRECT_IN_REVIEWED_SCOPE",
        "UNRESOLVED_CHALLENGE": "DISPUTED",
    }
    for challenge in prosecution.challenges:
        if challenge.effect == "NO_MATERIAL_CHALLENGE":
            continue
        for point in defense.points:
            if (
                point.disposition == "CONCESSION"
                and not point.differentiators
                and not point.counterfactual
            ):
                continue
            shared_basis = bool(set(challenge.comparison_ids) & set(point.comparison_ids))
            dispute_id = "p7dispute_" + canonical_hash(
                {
                    "packet_id": packet.case_id,
                    "challenge_id": challenge.argument_id,
                    "defense_id": point.defense_id,
                }
            )
            defense_state: GateCState = (
                "DISPUTED" if point.disposition == "UNRESOLVED" else "NO_DIRECT_IN_REVIEWED_SCOPE"
            )
            prosecution_state = c_state_by_effect[challenge.effect]
            direct_basis = any(
                str(item.comparison.classification.classification_id) in challenge.comparison_ids
                and item.comparison.classification.relation.value == "DIRECT_PRECEDENT"
                and any(
                    relation.classification_id == item.comparison.classification.classification_id
                    for relation in packet.authorized_relations
                )
                for item in packet.comparisons
            )
            unbounded = (
                not shared_basis
                or prosecution_state == defense_state
                or prosecution_state == "DIRECT_ESTABLISHED"
                and not direct_basis
                or challenge.counterfactual != point.counterfactual
                and (challenge.counterfactual is not None or point.counterfactual is not None)
            )
            candidates: tuple[DisputeResolutionCandidate, ...] = ()
            if not unbounded:
                candidates = (
                    DisputeResolutionCandidate(
                        assessment_id=packet.assessment_id,
                        assessment_context_id=packet.assessment_context_id,
                        phase6_snapshot_id=packet.phase6_snapshot_id,
                        target_id=challenge.target_id,
                        dispute_id=dispute_id,
                        candidate_id="p7candidate_"
                        + canonical_hash({"dispute_id": dispute_id, "role": "PROSECUTOR"}),
                        gate_c_candidate=prosecution_state,
                        basis_argument_ids=(challenge.argument_id,),
                        basis_phase6_ids=challenge.comparison_ids,
                        bounded=True,
                        reason=challenge.thesis,
                    ),
                    DisputeResolutionCandidate(
                        assessment_id=packet.assessment_id,
                        assessment_context_id=packet.assessment_context_id,
                        phase6_snapshot_id=packet.phase6_snapshot_id,
                        target_id=challenge.target_id,
                        dispute_id=dispute_id,
                        candidate_id="p7candidate_"
                        + canonical_hash({"dispute_id": dispute_id, "role": "DEFENDER"}),
                        gate_c_candidate=defense_state,
                        basis_argument_ids=(point.defense_id,),
                        basis_phase6_ids=point.comparison_ids,
                        bounded=True,
                        reason=point.thesis,
                    ),
                )
            base.append(
                Dispute(
                    dispute_id=dispute_id,
                    assessment_id=packet.assessment_id,
                    assessment_context_id=packet.assessment_context_id,
                    phase6_snapshot_id=packet.phase6_snapshot_id,
                    target_id=challenge.target_id,
                    argument_ids=(challenge.argument_id, point.defense_id),
                    disputed_effect=challenge.effect,
                    candidates=candidates,
                    resolution_space_unbounded=unbounded,
                )
            )
    if not rebuttals:
        return tuple(base)
    known_ids = {item.dispute_id for item in base}
    known_arguments = {argument.argument_id for argument in prosecution.challenges} | {
        point.defense_id for point in defense.points
    }
    validated_rebuttals = tuple(validate_rebuttal_case(item, packet) for item in rebuttals)
    for rebuttal in validated_rebuttals:
        if (
            rebuttal.target_id != prosecution.target_id
            or set(rebuttal.dispute_ids) - known_ids
            or set(rebuttal.argument_ids) - known_arguments
        ):
            raise ValueError("Rebuttal links differ from validated dispute arguments")
    updated: list[Dispute] = []
    for dispute in base:
        relevant = tuple(
            item for item in validated_rebuttals if dispute.dispute_id in item.dispute_ids
        )
        if relevant and any(item.points for item in relevant):
            # Rebuttal prose has no typed Gate C/D state. Preserve its possible
            # semantic expansion rather than silently trimming the resolution set.
            updated.append(
                dispute.model_copy(
                    update={
                        "dispute_id": "p7dispute_"
                        + canonical_hash(
                            {
                                "base_dispute_id": dispute.dispute_id,
                                "rebuttal_ids": [item.rebuttal_id for item in relevant],
                            }
                        ),
                        "candidates": (),
                        "resolution_space_unbounded": True,
                    }
                )
            )
        else:
            updated.append(dispute)
    return tuple(updated)


def neutral_review_issues(
    prosecution: ProsecutionCase,
    defense: DefenseCase,
    packet: "AdjudicationCasePacket",
    *,
    rebuttals: tuple[RebuttalCase, ...] = (),
) -> tuple[Dispute, ...]:
    """Retain neutral target adjudication even when both independent roles agree."""
    material = material_disputes(prosecution, defense, packet, rebuttals=rebuttals)
    if material:
        return material
    from novelty_harness.adjudication.gates import evaluate_gate_a
    from novelty_harness.adjudication.models import TargetRef

    profile = next(p for p in packet.target_profiles if p.target_id == prosecution.target_id)
    gate, needs = evaluate_gate_a(packet, TargetRef(kind=profile.target_kind, id=profile.target_id))
    if gate.state == "INSUFFICIENT" or needs:
        return ()
    argument_ids = (
        prosecution.challenges[0].argument_id
        if prosecution.challenges
        else "p7position_" + canonical_hash(prosecution),
        defense.points[0].defense_id if defense.points else "p7position_" + canonical_hash(defense),
    )
    return (
        Dispute(
            assessment_id=packet.assessment_id,
            assessment_context_id=packet.assessment_context_id,
            phase6_snapshot_id=packet.phase6_snapshot_id,
            target_id=profile.target_id,
            dispute_id="p7dispute_"
            + canonical_hash(
                {
                    "case": packet.case_id,
                    "target": profile.target_id,
                    "arguments": list(argument_ids),
                    "purpose": "NEUTRAL_SCOPE_REVIEW",
                }
            ),
            argument_ids=argument_ids,
            disputed_effect="NEUTRAL_SCOPE_REVIEW",
            scope_review=True,
            resolution_space_unbounded=True,
        ),
    )
