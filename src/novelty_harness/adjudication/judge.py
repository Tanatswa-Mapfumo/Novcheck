"""Neutral judge proposal and order-counterbalance records."""

from enum import StrEnum
from typing import Literal, Self, cast

from pydantic import ConfigDict, JsonValue, model_validator

from novelty_harness.adjudication.counterfactual import (
    CounterfactualLocalization,
    validate_counterfactual,
)
from novelty_harness.adjudication.frozen import TargetFinding
from novelty_harness.adjudication.gates import (
    GateAFinding,
    GateBFinding,
    GateCFinding,
    GateDFinding,
)
from novelty_harness.adjudication.models import TargetScoped
from novelty_harness.adjudication.needs import (
    InputClarificationNeed,
    ResearchGapRequest,
    validate_proposed_needs,
)
from novelty_harness.adjudication.packet import AdjudicationCasePacket
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.adjudication.roles import (
    DefenseCase,
    Dispute,
    DisputeResolutionCandidate,
    GateCState,
    GateDState,
    ProsecutionCase,
    RebuttalCase,
    RoleArgument,
    neutral_review_issues,
)
from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import VerdictState
from novelty_harness.runtime.tracing.hashing import canonical_hash


class JudgeStability(StrEnum):
    STABLE = "STABLE"
    MINOR_ORDER_VARIATION = "MINOR_ORDER_VARIATION"
    MATERIAL_ORDER_INSTABILITY = "MATERIAL_ORDER_INSTABILITY"


class JudgeFinding(TargetScoped):
    contract_kind: Literal["phase7-judge-finding-v2"] = "phase7-judge-finding-v2"
    finding_id: str
    accepted_challenge_ids: tuple[str, ...] = ()
    rejected_challenge_ids: tuple[str, ...] = ()
    uncertain_challenge_ids: tuple[str, ...] = ()
    phase6_basis_ids: tuple[str, ...] = ()
    proposed_gate_c: GateCState | None = None
    proposed_gate_d: GateDState | None = None
    reason: str
    limitations: tuple[str, ...] = ()
    input_need_ids: tuple[str, ...] = ()
    research_gap_ids: tuple[str, ...] = ()
    input_needs: tuple[InputClarificationNeed, ...] = ()
    research_gaps: tuple[ResearchGapRequest, ...] = ()
    counterfactual: CounterfactualLocalization | None = None


class JudgeProbeRegistration(TargetScoped):
    """Protocol provenance sealed before findings; it grants no semantic permission."""

    contract_kind: Literal["phase7-judge-probe-v1"] = "phase7-judge-probe-v1"
    registration_id: str
    dispute_id: str
    model_config_id: str
    probe_role: Literal["PRIMARY", "ALTERNATE"]


def judge_probe_id(run_id: str, probe: JudgeProbeRegistration) -> str:
    return "p7probe_" + canonical_hash(
        {
            "run_id": run_id,
            "probe": probe.model_dump(mode="json", exclude={"registration_id"}),
        }
    )


class CounterbalanceRun(TargetScoped):
    contract_kind: Literal["phase7-counterbalance-run-v1"] = "phase7-counterbalance-run-v1"
    run_id: str
    dispute_id: str
    packet_id: str
    argument_ids: tuple[str, str]
    order: tuple[Literal["A", "B"], Literal["A", "B"]]
    evidence_digest: str
    rubric_version: str
    model_config_id: str
    finding: JudgeFinding
    provenance: str | None = None

    @model_validator(mode="after")
    def valid_order_and_finding(self) -> Self:
        if set(self.order) != {"A", "B"}:
            raise ValueError("Judge argument order must contain A and B once")
        if (
            self.finding.assessment_id,
            self.finding.assessment_context_id,
            self.finding.phase6_snapshot_id,
            self.finding.target_id,
        ) != (
            self.assessment_id,
            self.assessment_context_id,
            self.phase6_snapshot_id,
            self.target_id,
        ):
            raise ValueError("Judge finding differs from run scope")
        return self


class NormalizedJudgeFinding(TargetScoped):
    contract_kind: Literal["phase7-normalized-judge-finding-v1"] = (
        "phase7-normalized-judge-finding-v1"
    )
    accepted_challenge_ids: tuple[str, ...] = ()
    decisive_phase6_ids: tuple[str, ...] = ()
    gate_c_effect: GateCState | None = None
    gate_d_effect: GateDState | None = None
    counterfactual_digest: str | None = None


class CounterbalanceComparison(TargetScoped):
    contract_kind: Literal["phase7-counterbalance-comparison-v1"] = (
        "phase7-counterbalance-comparison-v1"
    )
    comparison_id: str
    dispute_id: str
    packet_id: str
    argument_ids: tuple[str, str]
    evidence_digest: str
    rubric_version: str
    model_config_id: str
    first_run_id: str
    second_run_id: str
    first_finding: JudgeFinding
    second_finding: JudgeFinding
    stability: JudgeStability
    materially_disputed_dimensions: tuple[str, ...] = ()
    resolution_if_stable: NormalizedJudgeFinding | None = None


class JudgeResolution(TargetScoped):
    contract_kind: Literal["phase7-judge-resolution-v1"] = "phase7-judge-resolution-v1"
    resolution_id: str
    primary_comparison_id: str
    alternate_comparison_id: str | None = None
    resolved_semantics: NormalizedJudgeFinding | None = None
    permitted_ceiling: VerdictState | None = None
    unresolved_dimensions: tuple[str, ...] = ()
    limiting_factors: tuple[str, ...] = ()


class GateFacts(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-gate-facts-v1"] = "phase7-gate-facts-v1"
    gate_a: GateAFinding
    gate_b: GateBFinding
    undisputed_c: GateCFinding | None = None
    undisputed_d: GateDFinding | None = None
    robustness: RobustnessQualification
    domain: DomainQualification


class DisputeImpact(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-dispute-impact-v1"] = "phase7-dispute-impact-v1"
    level: Literal["HIGH_IMPACT", "LOW_IMPACT"]
    changed_dimensions: tuple[str, ...] = ()


def dispute_arguments(
    dispute: Dispute,
    prosecution: ProsecutionCase,
    defense: DefenseCase,
    *,
    rebuttals: tuple[RebuttalCase, ...] = (),
) -> tuple[RoleArgument, RoleArgument]:
    """Project the two committed positions into neutral argument contracts."""

    challenge = next(
        (item for item in prosecution.challenges if item.argument_id == dispute.argument_ids[0]),
        None,
    )
    if challenge is None:
        challenge = RoleArgument(
            assessment_id=prosecution.assessment_id,
            assessment_context_id=prosecution.assessment_context_id,
            phase6_snapshot_id=prosecution.phase6_snapshot_id,
            target_id=prosecution.target_id,
            argument_id=dispute.argument_ids[0],
            thesis=(
                "No material challenge in the independent first pass; assess the exact claim scope"
            ),
            effect="NO_MATERIAL_CHALLENGE",
        )
    point = next(
        (item for item in defense.points if item.defense_id == dispute.argument_ids[1]), None
    )
    if point is None:
        from novelty_harness.adjudication.roles import DefensePoint

        point = DefensePoint(
            assessment_id=defense.assessment_id,
            assessment_context_id=defense.assessment_context_id,
            phase6_snapshot_id=defense.phase6_snapshot_id,
            target_id=defense.target_id,
            defense_id=dispute.argument_ids[1],
            disposition="UNRESOLVED",
            thesis="No independently resolved contribution; assess the exact packet target",
        )
    other = RoleArgument(
        assessment_id=point.assessment_id,
        assessment_context_id=point.assessment_context_id,
        phase6_snapshot_id=point.phase6_snapshot_id,
        target_id=point.target_id,
        argument_id=point.defense_id,
        thesis=point.thesis,
        effect="UNRESOLVED_CHALLENGE"
        if point.disposition == "UNRESOLVED"
        else "NO_MATERIAL_CHALLENGE",
        comparison_ids=point.comparison_ids,
        graph_relation_ids=point.graph_relation_ids,
        source_ids=point.source_ids,
        source_version_ids=point.source_version_ids,
        passage_ids=point.passage_ids,
        missing_elements=point.differentiators,
        counterfactual=point.counterfactual,
        limitations=point.limitations,
    )
    projected: list[RoleArgument] = []
    for argument, role in ((challenge, "PROSECUTOR"), (other, "DEFENDER")):
        linked = tuple(
            item
            for item in rebuttals
            if item.role == role
            and argument.argument_id in item.argument_ids
            and item.target_id == dispute.target_id
        )
        updates: dict[str, object] = {
            "thesis": "\n".join(
                (argument.thesis, *(point for item in linked for point in item.points))
            ),
            "limitations": tuple(
                (*argument.limitations, *(limit for item in linked for limit in item.limitations))
            ),
        }
        for field in (
            "comparison_ids",
            "graph_relation_ids",
            "source_ids",
            "source_version_ids",
            "passage_ids",
        ):
            updates[field] = tuple(
                sorted(
                    {
                        *getattr(argument, field),
                        *(ref for item in linked for ref in getattr(item, field)),
                    }
                )
            )
        projected.append(RoleArgument.model_validate({**argument.model_dump(), **updates}))
    return projected[0], projected[1]


def validate_judge_finding(
    finding: JudgeFinding,
    packet: AdjudicationCasePacket,
    arguments: tuple[RoleArgument, ...],
) -> JudgeFinding:
    """Reject semantic proposals outside the displayed target and evidence."""

    if set(finding.__dict__) - set(JudgeFinding.model_fields):
        raise ValueError("Judge proposal contains forbidden authority fields")
    finding = JudgeFinding.model_validate_json(finding.model_dump_json())
    target_ids = {item.target_id for item in arguments}
    if len(target_ids) != 1 or (
        finding.assessment_id != packet.assessment_id
        or finding.assessment_context_id != packet.assessment_context_id
        or finding.phase6_snapshot_id != packet.phase6_snapshot_id
        or finding.target_id not in target_ids
        or finding.target_id not in packet.target_ids
    ):
        raise ValueError("Judge proposal scope differs from packet arguments")
    groups = (
        finding.accepted_challenge_ids,
        finding.rejected_challenge_ids,
        finding.uncertain_challenge_ids,
    )
    classified_ids = tuple(item for group in groups for item in group)
    if len(classified_ids) != len(set(classified_ids)) or set(classified_ids) - {
        item.argument_id for item in arguments
    }:
        raise ValueError("Judge proposal cites an absent or contradictory argument")
    comparisons = tuple(
        item
        for item in packet.comparisons
        if item.comparison.classification.mcu_id == finding.target_id
    )
    comparison_ids = {str(item.comparison.classification.classification_id) for item in comparisons}
    basis_ids = (
        comparison_ids
        | {str(p.passage.passage_id) for item in comparisons for p in item.cited_passages}
        | {
            r.edge.edge_id
            for r in packet.authorized_relations
            if str(r.classification_id) in comparison_ids
        }
    )
    if set(finding.phase6_basis_ids) - basis_ids:
        raise ValueError("Judge proposal cites Phase 6 ID absent from target packet")
    if finding.counterfactual is not None:
        from novelty_harness.adjudication.models import TargetRef

        profile = next(p for p in packet.target_profiles if p.target_id == finding.target_id)
        localization = validate_counterfactual(
            packet,
            TargetRef(kind=profile.target_kind, id=finding.target_id),
            finding.counterfactual,
        )
        if localization.nearest_comparison_id not in finding.phase6_basis_ids:
            raise ValueError("Judge counterfactual lacks its decisive nearest comparison")
    validate_proposed_needs(finding, packet, argument_ids=tuple(a.argument_id for a in arguments))
    if finding.proposed_gate_c is not None:
        from novelty_harness.adjudication.gates import evaluate_gate_c
        from novelty_harness.adjudication.models import TargetRef

        profile = next(p for p in packet.target_profiles if p.target_id == finding.target_id)
        evaluate_gate_c(packet, TargetRef(kind=profile.target_kind, id=finding.target_id), finding)
    return finding


def _hypothetical_gate_c(
    candidate: DisputeResolutionCandidate,
    packet: AdjudicationCasePacket,
    baseline: GateCFinding | None,
) -> GateCFinding | None:
    state = candidate.gate_c_candidate
    if state is None:
        return baseline
    comparison_by_id = {
        str(item.comparison.classification.classification_id): item
        for item in packet.comparisons
        if item.comparison.classification.mcu_id == candidate.target_id
    }
    if not set(candidate.basis_phase6_ids) <= set(comparison_by_id):
        raise ValueError("Dispute candidate cites foreign Phase 6 comparison")
    cited = tuple(candidate.basis_phase6_ids)
    relation_ids = tuple(
        sorted(
            {
                relation.edge.edge_id
                for relation in packet.authorized_relations
                if str(relation.classification_id) in cited
            }
        )
    )
    passage_ids = tuple(
        sorted(
            {
                str(passage.passage.passage_id)
                for comparison_id in cited
                for passage in comparison_by_id[comparison_id].cited_passages
            }
        )
    )
    residual = None
    if state == "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA":
        residuals = tuple(
            difference
            for comparison_id in cited
            for classification in (comparison_by_id[comparison_id].comparison.classification,)
            for difference in (
                *classification.missing_elements,
                *classification.missing_relationships,
                *((classification.configuration_gap,) if classification.configuration_gap else ()),
            )
        )
        if not residuals:
            raise ValueError("Substantial candidate has no Phase 6 residual difference")
        residual = "; ".join(residuals)
    return GateCFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=candidate.target_id,
        gate_id="p7gate_"
        + canonical_hash({"candidate_id": candidate.candidate_id, "gate": "C", "state": state}),
        state=state,
        comparison_ids=cited,
        graph_relation_ids=relation_ids,
        passage_ids=passage_ids,
        residual_delta=residual,
        basis_ids=tuple((*cited, *relation_ids, *passage_ids)),
        provenance="PRE_JUDGE_HYPOTHETICAL_NOT_EVIDENCE",
    )


def _hypothetical_gate_d(
    candidate: DisputeResolutionCandidate,
    packet: AdjudicationCasePacket,
    baseline: GateDFinding | None,
) -> GateDFinding | None:
    state = candidate.gate_d_candidate
    if state is None:
        return baseline
    if not set(candidate.basis_phase6_ids) <= {
        str(item.comparison.classification.classification_id)
        for item in packet.comparisons
        if item.comparison.classification.mcu_id == candidate.target_id
    }:
        raise ValueError("Dispute candidate cites foreign Phase 6 comparison")
    return GateDFinding(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=candidate.target_id,
        gate_id="p7gate_"
        + canonical_hash({"candidate_id": candidate.candidate_id, "gate": "D", "state": state}),
        state=state,
        nearest_comparison_ids=candidate.basis_phase6_ids,
        basis_ids=candidate.basis_phase6_ids,
        provenance="PRE_JUDGE_HYPOTHETICAL_NOT_EVIDENCE",
    )


def classify_dispute_impact(
    dispute: Dispute,
    packet: AdjudicationCasePacket,
    gate_facts: GateFacts,
    *,
    prosecution: ProsecutionCase,
    defense: DefenseCase,
    rebuttals: tuple[RebuttalCase, ...] = (),
) -> DisputeImpact:
    """Compare both validated semantic alternatives before any judge call."""

    from novelty_harness.adjudication.policy import VerdictPermissionPolicy

    packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
    dispute = Dispute.model_validate_json(dispute.model_dump_json())
    gate_facts = GateFacts.model_validate_json(gate_facts.model_dump_json())
    expected = neutral_review_issues(prosecution, defense, packet, rebuttals=rebuttals)
    if dispute not in expected:
        raise ValueError("Supplied dispute omits or replaces a validated resolution candidate")
    scope = (
        packet.assessment_id,
        packet.assessment_context_id,
        packet.phase6_snapshot_id,
        dispute.target_id,
    )
    for artifact in (
        gate_facts.gate_a,
        gate_facts.gate_b,
        gate_facts.robustness,
        gate_facts.domain,
        gate_facts.undisputed_c,
        gate_facts.undisputed_d,
    ):
        if (
            artifact is not None
            and (
                artifact.assessment_id,
                artifact.assessment_context_id,
                artifact.phase6_snapshot_id,
                artifact.target_id,
            )
            != scope
        ):
            raise ValueError("Impact gate facts have foreign dispute scope")
    if dispute.resolution_space_unbounded:
        return DisputeImpact(
            level="HIGH_IMPACT", changed_dimensions=("unbounded_resolution_space",)
        )
    candidates = dispute.candidates
    if len(candidates) != 2:
        raise ValueError("Impact requires the complete validated candidate pair")
    changed: list[str] = []
    if candidates[0].gate_c_candidate != candidates[1].gate_c_candidate:
        changed.append("gate_c")
    if candidates[0].gate_d_candidate != candidates[1].gate_d_candidate:
        changed.append("gate_d")
    hypotheticals: list[TargetFinding] = []
    for candidate in candidates:
        try:
            gate_c = _hypothetical_gate_c(candidate, packet, gate_facts.undisputed_c)
            gate_d = _hypothetical_gate_d(candidate, packet, gate_facts.undisputed_d)
            if gate_c is None or gate_d is None:
                changed.append("missing_undisputed_baseline")
                break
            outcome = VerdictPermissionPolicy().evaluate(
                packet=packet,
                gate_a=gate_facts.gate_a,
                gate_b=gate_facts.gate_b,
                gate_c=gate_c,
                gate_d=gate_d,
                stability=JudgeStability.STABLE,
                robustness=gate_facts.robustness,
                domain=gate_facts.domain,
            )
        except ValueError:
            changed.append("unsafe_hypothetical")
            break
        hypotheticals.append(outcome)
    if len(hypotheticals) == 2:
        first, second = hypotheticals
        if first.verdict != second.verdict:
            changed.append("target_verdict")
        if (first.verdict == VerdictState.UNASSESSABLE) != (
            second.verdict == VerdictState.UNASSESSABLE
        ):
            changed.append("assessability")
        if first.language_permission != second.language_permission:
            changed.append("maximum_language_class")
        if (first.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL) != (
            second.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
        ):
            changed.append("claim_specific_negative_permission")
        positive = {VerdictState.POTENTIALLY_NOVEL, VerdictState.STRONG_EVIDENCE_OF_NOVELTY}
        if (first.verdict in positive) != (second.verdict in positive):
            changed.append("potentially_novel_permission")
    dimensions = tuple(dict.fromkeys(changed))
    return DisputeImpact(
        level="HIGH_IMPACT" if dimensions else "LOW_IMPACT",
        changed_dimensions=dimensions,
    )


def normalize_judge_finding(finding: JudgeFinding) -> NormalizedJudgeFinding:
    finding = JudgeFinding.model_validate_json(finding.model_dump_json())
    return NormalizedJudgeFinding(
        assessment_id=finding.assessment_id,
        assessment_context_id=finding.assessment_context_id,
        phase6_snapshot_id=finding.phase6_snapshot_id,
        target_id=finding.target_id,
        accepted_challenge_ids=tuple(sorted(set(finding.accepted_challenge_ids))),
        decisive_phase6_ids=tuple(sorted(set(finding.phase6_basis_ids))),
        gate_c_effect=finding.proposed_gate_c,
        gate_d_effect=finding.proposed_gate_d,
        counterfactual_digest=(
            canonical_hash(
                cast(
                    JsonValue,
                    {
                        **finding.counterfactual.model_dump(
                            mode="json", exclude={"localization_id", "reason", "limiting_factors"}
                        ),
                        "remaining_differences": sorted(
                            set(finding.counterfactual.remaining_differences)
                        ),
                    },
                )
            )
            if finding.counterfactual is not None
            else None
        ),
    )


def _material_dimensions(
    first: NormalizedJudgeFinding, second: NormalizedJudgeFinding
) -> tuple[str, ...]:
    fields = {
        "accepted_challenge_ids": "accepted_challenge_ids",
        "decisive_phase6_ids": "decisive_phase6_ids",
        "gate_c_effect": "gate_c",
        "gate_d_effect": "gate_d",
        "counterfactual_digest": "counterfactual",
    }
    return tuple(
        label for field, label in fields.items() if getattr(first, field) != getattr(second, field)
    )


def compare_counterbalance(
    first: CounterbalanceRun, second: CounterbalanceRun
) -> CounterbalanceComparison:
    """Retain the full pair, separating semantic conflict from wording variation."""

    first = CounterbalanceRun.model_validate_json(first.model_dump_json())
    second = CounterbalanceRun.model_validate_json(second.model_dump_json())
    shared = (
        "assessment_id",
        "assessment_context_id",
        "phase6_snapshot_id",
        "target_id",
        "dispute_id",
        "packet_id",
        "argument_ids",
        "evidence_digest",
        "rubric_version",
        "model_config_id",
    )
    if any(getattr(first, field) != getattr(second, field) for field in shared):
        raise ValueError(
            "Counterbalance pair differs in scope, packet, arguments, evidence, rubric or model"
        )
    if first.run_id == second.run_id or first.order != tuple(reversed(second.order)):
        raise ValueError("Counterbalance needs two distinct runs in reversed orders")
    if len(set(first.argument_ids)) != 2 or not first.model_config_id.strip():
        raise ValueError("Counterbalance needs distinct arguments and an explicit configuration")
    normalized_first = normalize_judge_finding(first.finding)
    normalized_second = normalize_judge_finding(second.finding)
    dimensions = _material_dimensions(normalized_first, normalized_second)
    if dimensions:
        stability = JudgeStability.MATERIAL_ORDER_INSTABILITY
    elif first.finding.model_dump(exclude={"finding_id"}) == second.finding.model_dump(
        exclude={"finding_id"}
    ):
        stability = JudgeStability.STABLE
    else:
        stability = JudgeStability.MINOR_ORDER_VARIATION
    comparison = CounterbalanceComparison(
        assessment_id=first.assessment_id,
        assessment_context_id=first.assessment_context_id,
        phase6_snapshot_id=first.phase6_snapshot_id,
        target_id=first.target_id,
        comparison_id="pending",
        dispute_id=first.dispute_id,
        packet_id=first.packet_id,
        argument_ids=first.argument_ids,
        evidence_digest=first.evidence_digest,
        rubric_version=first.rubric_version,
        model_config_id=first.model_config_id,
        first_run_id=first.run_id,
        second_run_id=second.run_id,
        first_finding=first.finding,
        second_finding=second.finding,
        stability=stability,
        materially_disputed_dimensions=dimensions,
        resolution_if_stable=None if dimensions else normalized_first,
    )
    return comparison.model_copy(
        update={
            "comparison_id": "p7judgecmp_"
            + canonical_hash(comparison.model_dump(mode="json", exclude={"comparison_id"}))
        }
    )


def _validate_comparison(comparison: object) -> CounterbalanceComparison:
    if not isinstance(comparison, CounterbalanceComparison):
        raise ValueError("Judge reconciliation requires a full counterbalance comparison pair")
    comparison = CounterbalanceComparison.model_validate_json(comparison.model_dump_json())
    shared = dict(
        assessment_id=comparison.assessment_id,
        assessment_context_id=comparison.assessment_context_id,
        phase6_snapshot_id=comparison.phase6_snapshot_id,
        target_id=comparison.target_id,
        dispute_id=comparison.dispute_id,
        packet_id=comparison.packet_id,
        argument_ids=comparison.argument_ids,
        evidence_digest=comparison.evidence_digest,
        rubric_version=comparison.rubric_version,
        model_config_id=comparison.model_config_id,
    )
    first = CounterbalanceRun.model_validate(
        {
            **shared,
            "run_id": comparison.first_run_id,
            "order": ("A", "B"),
            "finding": comparison.first_finding,
        }
    )
    second = CounterbalanceRun.model_validate(
        {
            **shared,
            "run_id": comparison.second_run_id,
            "order": ("B", "A"),
            "finding": comparison.second_finding,
        }
    )
    if compare_counterbalance(first, second) != comparison:
        raise ValueError(
            "Comparison stability, normalized resolution or identity differs from actual findings"
        )
    return comparison


def resolve_judge_comparisons(
    primary: CounterbalanceComparison,
    alternate: CounterbalanceComparison | None,
) -> JudgeResolution:
    """Reconcile independent semantic probes; no finding is counted as a vote."""

    primary = _validate_comparison(primary)
    if alternate is not None:
        alternate = _validate_comparison(alternate)
        shared = (
            "assessment_id",
            "assessment_context_id",
            "phase6_snapshot_id",
            "target_id",
            "dispute_id",
            "packet_id",
            "argument_ids",
            "evidence_digest",
            "rubric_version",
        )
        if any(getattr(primary, field) != getattr(alternate, field) for field in shared):
            raise ValueError("Alternate comparison differs from the primary sealed dispute")
        if primary.model_config_id == alternate.model_config_id:
            raise ValueError("Heterogeneous comparison requires a different configured model")
        if set((primary.first_run_id, primary.second_run_id)) & set(
            (alternate.first_run_id, alternate.second_run_id)
        ):
            raise ValueError("Alternate comparison reuses a primary judge run")
    primary_semantics = primary.resolution_if_stable
    alternate_semantics = alternate.resolution_if_stable if alternate else None
    resolved = primary_semantics
    dimensions = primary.materially_disputed_dimensions
    limitations: tuple[str, ...] = ()
    if alternate is None:
        if primary_semantics is None:
            limitations = ("Primary judge has unresolved material order instability",)
    elif alternate_semantics is None:
        resolved = None
        dimensions = tuple(sorted(set((*dimensions, *alternate.materially_disputed_dimensions))))
        limitations = ("Invoked alternate judge has unresolved material order instability",)
    elif primary_semantics is None:
        resolved = alternate_semantics
        dimensions = ()
        limitations = (
            "Stable alternate resolved semantics; primary material order instability retained",
        )
    else:
        dimensions = _material_dimensions(primary_semantics, alternate_semantics)
        if dimensions:
            resolved = None
            limitations = (
                "Internally stable models materially disagree; "
                "no majority or preferred-provider rule",
            )
    ceiling: VerdictState | None = None
    if resolved is None:
        # A ceiling limits future permission; it never establishes a verdict.
        findings = (
            primary.first_finding,
            primary.second_finding,
            *((alternate.first_finding, alternate.second_finding) if alternate else ()),
        )
        positive_states = {
            "NO_DIRECT_IN_REVIEWED_SCOPE",
            "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA",
        }
        ceiling = (
            VerdictState.POTENTIALLY_NOVEL
            if all(
                finding.proposed_gate_c in positive_states
                and finding.proposed_gate_d == "SUBSTANTIVE"
                for finding in findings
            )
            else VerdictState.UNASSESSABLE
        )
    resolution = JudgeResolution(
        assessment_id=primary.assessment_id,
        assessment_context_id=primary.assessment_context_id,
        phase6_snapshot_id=primary.phase6_snapshot_id,
        target_id=primary.target_id,
        resolution_id="pending",
        primary_comparison_id=primary.comparison_id,
        alternate_comparison_id=alternate.comparison_id if alternate else None,
        resolved_semantics=resolved,
        permitted_ceiling=ceiling,
        unresolved_dimensions=dimensions,
        limiting_factors=limitations,
    )
    return resolution.model_copy(
        update={
            "resolution_id": "p7judgeres_"
            + canonical_hash(resolution.model_dump(mode="json", exclude={"resolution_id"}))
        }
    )
