"""Gate A input needs and B/C/D external evidence requests."""

from typing import TYPE_CHECKING, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.adjudication.context import Phase7InputManifest, SealedAssessmentContext
from novelty_harness.adjudication.models import Phase7Artifact, Phase7Scoped, TargetScoped
from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.research.coverage import CoverageCell
from novelty_harness.runtime.budgets.controller import BudgetController, BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits

if TYPE_CHECKING:
    from novelty_harness.adjudication.packet import AdjudicationCasePacket


class InputClarificationNeed(TargetScoped):
    contract_kind: Literal["phase7-input-clarification-need-v1"] = (
        "phase7-input-clarification-need-v1"
    )
    need_id: str
    reason: str
    missing_input_fields: tuple[str, ...] = ()
    unresolved_structure: tuple[str, ...] = ()
    material_gate: Literal["A"] = "A"
    resolution_requirement: str
    provenance: str | None = None

    @model_validator(mode="after")
    def names_missing_input(self) -> Self:
        if not self.missing_input_fields and not self.unresolved_structure:
            raise ValueError("Input clarification must name missing input or structure")
        return self


class GateDExternalEvidenceBasis(TargetScoped):
    """A research justification, never an additional source of evidence authority."""

    contract_kind: Literal["phase7-gate-d-external-evidence-basis-v1"] = (
        "phase7-gate-d-external-evidence-basis-v1"
    )
    target_profile_digest: str
    contribution: str
    source_id: str
    source_version_id: str | None = None
    comparison_ids: tuple[str, ...] = ()
    missing_external_fact_type: Literal[
        "UNASSESSED_IMPLEMENTATION", "SOURCE_CHRONOLOGY", "SOURCE_CONTRADICTION"
    ]
    contradiction: str | None = None
    question: Literal["DOES_SOURCE_REPRODUCE_DEFINED_CONTRIBUTION"] = (
        "DOES_SOURCE_REPRODUCE_DEFINED_CONTRIBUTION"
    )
    significance_effect: Literal["SURVIVING_DIFFERENCE_MAY_CHANGE"] = (
        "SURVIVING_DIFFERENCE_MAY_CHANGE"
    )


class ResearchGapRequest(TargetScoped):
    contract_kind: Literal["phase7-research-gap-request-v3"] = "phase7-research-gap-request-v3"
    request_id: str
    dispatch_allowance: BudgetLimits | None = None
    requesting_stage: Literal["FIRST_PASS", "REBUTTAL", "ADJUDICATION"]
    gap_type: Literal[
        "TERMINOLOGY",
        "ADJACENT_DOMAIN",
        "PATENT_PRODUCT_SOFTWARE",
        "COMBINATION_RELATIONSHIP",
        "CHRONOLOGY",
        "ACCESS",
        "CONTRADICTORY_EVIDENCE",
        "COVERAGE",
    ]
    reason: str
    research_hypothesis: str
    evidence_families: tuple[EvidenceFamily, ...] = ()
    query_family_hints: tuple[str, ...] = ()
    retrieval_strategy_hints: tuple[str, ...] = ()
    material_gate: Literal["B", "C", "D"]
    linked_argument_ids: tuple[str, ...] = ()
    linked_comparison_ids: tuple[str, ...] = ()
    missing_prior_art_reference: str | None = None
    external_fact_basis: GateDExternalEvidenceBasis | None = None
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    stop_condition: str
    provenance: str | None = None

    @model_validator(mode="after")
    def evidence_dependent_d(self) -> Self:
        if self.material_gate == "D" and not self.missing_prior_art_reference:
            raise ValueError("Gate D research needs a missing prior-art reference")
        return self


def route_need(need: InputClarificationNeed | ResearchGapRequest) -> Literal["INPUT", "RESEARCH"]:
    """Keep target specification outside prior-art research dispatch."""

    if isinstance(need, InputClarificationNeed):
        InputClarificationNeed.model_validate_json(need.model_dump_json())
        return "INPUT"
    ResearchGapRequest.model_validate_json(need.model_dump_json())
    return "RESEARCH"


def validate_input_clarification_need(
    need: InputClarificationNeed, packet: "AdjudicationCasePacket"
) -> InputClarificationNeed:
    need = InputClarificationNeed.model_validate_json(need.model_dump_json())
    if (
        need.assessment_id != packet.assessment_id
        or need.assessment_context_id != packet.assessment_context_id
        or need.phase6_snapshot_id != packet.phase6_snapshot_id
        or need.target_id not in packet.target_ids
    ):
        raise ValueError("Input clarification scope differs from packet")
    return need


def validate_research_gap_request(
    request: ResearchGapRequest, packet: "AdjudicationCasePacket"
) -> ResearchGapRequest:
    request = ResearchGapRequest.model_validate_json(request.model_dump_json())
    if (
        request.assessment_id != packet.assessment_id
        or request.assessment_context_id != packet.assessment_context_id
        or request.phase6_snapshot_id != packet.phase6_snapshot_id
        or request.target_id not in packet.target_ids
    ):
        raise ValueError("Research gap scope differs from packet")
    known_comparisons = {
        str(item.comparison.classification.classification_id)
        for item in packet.comparisons
        if item.comparison.comparison.chain.edge.mcu_id == request.target_id
    }
    if len(set(request.linked_comparison_ids)) != len(request.linked_comparison_ids) or (
        set(request.linked_comparison_ids) - known_comparisons
    ):
        raise ValueError("Research gap comparison link is absent from packet target")
    if len(set(request.linked_argument_ids)) != len(request.linked_argument_ids):
        raise ValueError("Research gap argument links must be unique")
    if request.material_gate == "D":
        validate_gate_d_external_basis(request, packet)
    elif request.external_fact_basis is not None:
        raise ValueError("Gate D external basis cannot label another gate")
    return request


def validate_gate_d_external_basis(
    request: ResearchGapRequest, packet: "AdjudicationCasePacket"
) -> None:
    from novelty_harness.adjudication.gates import evaluate_gate_a
    from novelty_harness.adjudication.models import TargetRef
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    profile = next(p for p in packet.target_profiles if p.target_id == request.target_id)
    gate, needs = evaluate_gate_a(packet, TargetRef(kind=profile.target_kind, id=profile.target_id))
    if (
        gate.state == "INSUFFICIENT"
        or needs
        or gate.missing_fields
        or "unresolved_graph_decomposition" in gate.limiting_factors
    ):
        raise ValueError("Gate A does not permit a comparable Gate D target")
    basis = request.external_fact_basis
    if basis is None:
        raise ValueError("Gate D research requires a typed external fact basis")
    if (
        basis.assessment_id,
        basis.assessment_context_id,
        basis.phase6_snapshot_id,
        basis.target_id,
    ) != (
        request.assessment_id,
        request.assessment_context_id,
        request.phase6_snapshot_id,
        request.target_id,
    ):
        raise ValueError("Gate D external fact basis has foreign scope")
    if basis.target_profile_digest != canonical_hash(profile) or basis.contribution not in {
        profile.statement,
        profile.mechanism,
        *profile.features,
    }:
        raise ValueError("Gate D external fact basis does not bind a defined contribution")
    if (
        basis.comparison_ids != request.linked_comparison_ids
        or request.missing_prior_art_reference != (basis.source_version_id or basis.source_id)
    ):
        raise ValueError("Gate D external fact basis differs from request references")
    if basis.missing_external_fact_type == "UNASSESSED_IMPLEMENTATION":
        if (
            request.gap_type != "ACCESS"
            or not any(
                str(item.source_id) == basis.source_id
                and (str(item.source_version_id) if item.source_version_id else None)
                == basis.source_version_id
                and item.target_id in {None, request.target_id}
                for item in (*packet.coverage.excluded_sources, *packet.coverage.excluded_versions)
            )
            or basis.comparison_ids
        ):
            raise ValueError("Gate D external fact basis lacks an unassessed source in Phase 6")
    elif basis.missing_external_fact_type == "SOURCE_CONTRADICTION":
        if (
            request.gap_type != "CONTRADICTORY_EVIDENCE"
            or not basis.contradiction
            or not basis.comparison_ids
            or not all(
                any(
                    str(item.comparison.classification.classification_id) == comparison_id
                    and str(item.comparison.comparison.chain.source.source_id) == basis.source_id
                    and str(item.comparison.comparison.source_version_id) == basis.source_version_id
                    and basis.contradiction in item.comparison.classification.contradictions
                    for item in packet.comparisons
                )
                for comparison_id in basis.comparison_ids
            )
        ):
            raise ValueError("Gate D external fact basis lacks a verified source contradiction")
    elif (
        request.gap_type != "CHRONOLOGY"
        or not basis.comparison_ids
        or not all(
            any(
                str(item.comparison.classification.classification_id) == comparison_id
                and str(item.comparison.comparison.chain.source.source_id) == basis.source_id
                and str(item.comparison.comparison.source_version_id) == basis.source_version_id
                and item.comparison.comparison.chain.edge.chronology.state == "UNCERTAIN"
                for item in packet.comparisons
            )
            for comparison_id in basis.comparison_ids
        )
    ):
        raise ValueError("Gate D external fact basis lacks uncertain external chronology")


def gate_d_external_fact_bases(
    packet: "AdjudicationCasePacket",
) -> tuple[GateDExternalEvidenceBasis, ...]:
    """Display copyable justifications; proposals still undergo the same authority joins."""
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    result: list[GateDExternalEvidenceBasis] = []
    for profile in packet.target_profiles:
        scope = dict(
            assessment_id=packet.assessment_id,
            assessment_context_id=packet.assessment_context_id,
            phase6_snapshot_id=packet.phase6_snapshot_id,
            target_id=profile.target_id,
            target_profile_digest=canonical_hash(profile),
            contribution=profile.statement,
        )
        possible: list[GateDExternalEvidenceBasis] = []
        for excluded in (*packet.coverage.excluded_sources, *packet.coverage.excluded_versions):
            if excluded.target_id in {None, profile.target_id}:
                possible.append(
                    GateDExternalEvidenceBasis.model_validate(
                        {
                            **scope,
                            "source_id": str(excluded.source_id),
                            "source_version_id": str(excluded.source_version_id)
                            if excluded.source_version_id
                            else None,
                            "missing_external_fact_type": "UNASSESSED_IMPLEMENTATION",
                        }
                    )
                )
        for item in packet.comparisons:
            comparison = item.comparison.comparison
            classification = item.comparison.classification
            if classification.mcu_id != profile.target_id:
                continue
            bound = dict(
                source_id=str(comparison.source_id),
                source_version_id=comparison.source_version_id,
                comparison_ids=(str(classification.classification_id),),
            )
            if comparison.chain.edge.chronology.state == "UNCERTAIN":
                possible.append(
                    GateDExternalEvidenceBasis.model_validate(
                        {**scope, **bound, "missing_external_fact_type": "SOURCE_CHRONOLOGY"}
                    )
                )
            for contradiction in classification.contradictions:
                possible.append(
                    GateDExternalEvidenceBasis.model_validate(
                        {
                            **scope,
                            **bound,
                            "missing_external_fact_type": "SOURCE_CONTRADICTION",
                            "contradiction": contradiction,
                        }
                    )
                )
        for basis in possible:
            gap_type: Literal["ACCESS", "CHRONOLOGY", "CONTRADICTORY_EVIDENCE"] = (
                "ACCESS"
                if basis.missing_external_fact_type == "UNASSESSED_IMPLEMENTATION"
                else "CHRONOLOGY"
                if basis.missing_external_fact_type == "SOURCE_CHRONOLOGY"
                else "CONTRADICTORY_EVIDENCE"
            )
            request = ResearchGapRequest(
                assessment_id=packet.assessment_id,
                assessment_context_id=packet.assessment_context_id,
                phase6_snapshot_id=packet.phase6_snapshot_id,
                target_id=profile.target_id,
                request_id="display_only",
                requesting_stage="ADJUDICATION",
                gap_type=gap_type,
                material_gate="D",
                reason="Display a missing external fact",
                research_hypothesis="Resolve the source fact for the defined contribution",
                linked_comparison_ids=basis.comparison_ids,
                missing_prior_art_reference=basis.source_version_id or basis.source_id,
                external_fact_basis=basis,
                stop_condition="Resolve or retain the external limitation",
            )
            try:
                validate_research_gap_request(request, packet)
            except ValueError:
                continue
            result.append(basis)
    return tuple(result)


def classify_gap_origin(
    request: ResearchGapRequest, packet: "AdjudicationCasePacket"
) -> Literal["INPUT_MEANING_GAP", "EXTERNAL_EVIDENCE_GAP"]:
    # Scope/citation forgery must still raise; only unproved D meaning is redirected.
    if request.material_gate != "D":
        validate_research_gap_request(request, packet)
        return "EXTERNAL_EVIDENCE_GAP"
    request = ResearchGapRequest.model_validate_json(request.model_dump_json())
    if (request.assessment_id, request.assessment_context_id, request.phase6_snapshot_id) != (
        packet.assessment_id,
        packet.assessment_context_id,
        packet.phase6_snapshot_id,
    ) or request.target_id not in packet.target_ids:
        raise ValueError("Research gap scope differs from packet")
    try:
        validate_research_gap_request(request, packet)
    except ValueError:
        return "INPUT_MEANING_GAP"
    return "EXTERNAL_EVIDENCE_GAP"


def gap_input_clarification(request: ResearchGapRequest) -> InputClarificationNeed:
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    return InputClarificationNeed(
        assessment_id=request.assessment_id,
        assessment_context_id=request.assessment_context_id,
        phase6_snapshot_id=request.phase6_snapshot_id,
        target_id=request.target_id,
        need_id="p7need_" + canonical_hash(request),
        reason=request.reason,
        unresolved_structure=("defined_contribution_and_external_fact_basis",),
        resolution_requirement=(
            "Clarify the claimed contribution independently of prior art and identify "
            "the external fact affecting its significance"
        ),
        provenance="UNPROVED_GATE_D_EXTERNAL_FACT:" + request.request_id,
    )


def clarify_unproved_gate_d[Proposal: TargetScoped](
    proposal: Proposal, packet: "AdjudicationCasePacket"
) -> Proposal:
    """Conservatively project untrusted proposed D gaps into input needs before persistence."""
    gaps = getattr(proposal, "research_gaps", ())
    if tuple(g.request_id for g in gaps) != getattr(proposal, "research_gap_ids", ()):
        raise ValueError("Gap references differ from typed proposed content")
    invalid = tuple(g for g in gaps if classify_gap_origin(g, packet) == "INPUT_MEANING_GAP")
    if not invalid:
        return proposal
    needs = (*getattr(proposal, "input_needs", ()), *(gap_input_clarification(g) for g in invalid))
    kept = tuple(g for g in gaps if g not in invalid)
    return proposal.model_copy(
        update={
            "input_needs": needs,
            "input_need_ids": tuple(n.need_id for n in needs),
            "research_gaps": kept,
            "research_gap_ids": tuple(g.request_id for g in kept),
        }
    )


class ResearchEscalationBudget(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-research-escalation-budget-v1"] = (
        "phase7-research-escalation-budget-v1"
    )
    limits: BudgetLimits
    usage: BudgetUsage
    max_requests: int = Field(ge=0)
    issued_request_ids: tuple[str, ...] = ()
    accepted_request_ids: tuple[str, ...] = ()
    rejected_request_ids: tuple[str, ...] = ()
    provider_blocks: tuple[str, ...] = ()
    remaining_material_gaps: tuple[str, ...] = ()
    stop_reason: str | None = None


class GapDecision(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-gap-decision-v1"] = "phase7-gap-decision-v1"
    request_id: str
    status: Literal["ACCEPT", "INPUT_RESOLUTION", "DUPLICATE", "BUDGET_STOP", "NON_MATERIAL"]
    reason: str
    material_gate: Literal["A", "B", "C", "D"]


class ResearchEscalationOutcome(Phase7Scoped):
    contract_kind: Literal["phase7-research-escalation-outcome-v1"] = (
        "phase7-research-escalation-outcome-v1"
    )
    request_id: str
    updated_snapshot_id: str
    updated_manifest: Phase7InputManifest
    attempted_query_ids: tuple[str, ...] = ()
    providers_attempted: tuple[str, ...] = ()
    access_failures: tuple[str, ...] = ()
    coverage_cells: tuple[CoverageCell, ...] = ()
    remaining_gaps: tuple[str, ...] = ()
    new_source_ids: tuple[str, ...] = ()
    budget_usage: BudgetUsage
    stop_reason: str | None = None
    cost: BudgetUsage

    @model_validator(mode="after")
    def matches_updated_world_state(self) -> Self:
        if (
            self.updated_manifest.assessment_id != self.assessment_id
            or self.updated_manifest.phase6_snapshot_id != self.updated_snapshot_id
            or self.updated_manifest.budget_usage != self.budget_usage
            or self.updated_manifest.stop_reason != self.stop_reason
            or self.updated_manifest.providers_attempted != self.providers_attempted
            or self.updated_manifest.access_failures != self.access_failures
            or self.updated_manifest.coverage_cells != self.coverage_cells
            or self.updated_manifest.remaining_gaps != self.remaining_gaps
            or not set(self.attempted_query_ids) <= set(self.updated_manifest.query_history)
            or self.new_source_ids
            and self.updated_snapshot_id == self.phase6_snapshot_id
        ):
            raise ValueError("Research outcome differs from updated bound state")
        return self


class ResearchContinuation(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-research-continuation-v1"] = "phase7-research-continuation-v1"
    context: SealedAssessmentContext
    run_id: str
    restarted: bool


class GapEscalationPolicy:
    """Categorical permission for a typed missing-external-evidence request."""

    def decide(
        self,
        request: ResearchGapRequest,
        context: SealedAssessmentContext,
        budget: ResearchEscalationBudget,
        *,
        packet: "AdjudicationCasePacket | None" = None,
    ) -> GapDecision:
        request = ResearchGapRequest.model_validate_json(request.model_dump_json())
        budget = ResearchEscalationBudget.model_validate_json(budget.model_dump_json())
        if (
            request.assessment_id != context.assessment_id
            or request.assessment_context_id != context.context_id
            or request.phase6_snapshot_id != context.snapshot_id
        ):
            raise ValueError("Research request differs from sealed assessment context")
        if request.material_gate == "D":
            if (
                packet is None
                or packet.assessment_context_id != context.context_id
                or packet.manifest != context.manifest
                or classify_gap_origin(request, packet) == "INPUT_MEANING_GAP"
            ):
                return GapDecision(
                    request_id=request.request_id,
                    status="INPUT_RESOLUTION",
                    reason="Gate D lacks a comparable target and validated external fact basis",
                    material_gate="A",
                )
        sealed_limits = context.manifest.budget_limits
        sealed_usage = context.manifest.budget_usage
        sealed_budget_exhausted = (
            sealed_limits is not None
            and sealed_usage is not None
            and not BudgetController().check(sealed_usage, sealed_limits).allowed
        )
        if request.request_id in budget.issued_request_ids:
            status, reason = "DUPLICATE", "This exact research gap was already issued"
        elif (
            sealed_budget_exhausted
            or len(budget.issued_request_ids) >= budget.max_requests
            or not BudgetController().check(budget.usage, budget.limits).allowed
            or not BudgetController()
            .check(BudgetUsage(), remaining_research_allowance(context, budget))
            .allowed
        ):
            status, reason = "BUDGET_STOP", "Escalation budget is exhausted"
        elif request.material_gate == "D" and (
            not request.missing_prior_art_reference
            or request.gap_type not in {"ACCESS", "CHRONOLOGY", "CONTRADICTORY_EVIDENCE"}
        ):
            status, reason = "NON_MATERIAL", "Gate D gap lacks a specific external prior-art fact"
        elif not request.research_hypothesis or not request.stop_condition:
            status, reason = "NON_MATERIAL", "Gap lacks a testable external research question"
        else:
            status, reason = "ACCEPT", "External evidence could change the stated gate"
        return GapDecision(
            request_id=request.request_id,
            status=status,
            reason=reason,
            material_gate=request.material_gate,
        )


def validate_proposed_needs(
    proposal: TargetScoped,
    packet: "AdjudicationCasePacket",
    *,
    argument_ids: tuple[str, ...] | None = None,
) -> None:
    """Proposals carry complete typed content; dangling references confer no meaning."""
    needs = getattr(proposal, "input_needs", ())
    gaps = getattr(proposal, "research_gaps", ())
    if tuple(n.need_id for n in needs) != getattr(proposal, "input_need_ids", ()) or tuple(
        g.request_id for g in gaps
    ) != getattr(proposal, "research_gap_ids", ()):
        raise ValueError("Need/gap references must exactly match typed proposed content")
    if len({n.need_id for n in needs}) != len(needs) or len({g.request_id for g in gaps}) != len(
        gaps
    ):
        raise ValueError("Proposed need/gap IDs must be unique")
    if argument_ids is None:
        argument_ids = (
            tuple(a.argument_id for a in getattr(proposal, "challenges", ()))
            + tuple(
                p.defense_id for p in getattr(proposal, "points", ()) if hasattr(p, "defense_id")
            )
            + tuple(getattr(proposal, "argument_ids", ()))
        )
    for need in (*needs, *gaps):
        if need.target_id != proposal.target_id:
            raise ValueError("Proposed need/gap has foreign target")
        if isinstance(need, InputClarificationNeed):
            validate_input_clarification_need(need, packet)
        else:
            validate_research_gap_request(need, packet)
            if set(need.linked_argument_ids) - set(argument_ids):
                raise ValueError("Proposed research gap links absent role argument")


def remaining_research_allowance(
    context: SealedAssessmentContext, budget: ResearchEscalationBudget | None = None
) -> BudgetLimits:
    """Intersect cumulative caps and subtract already consumed resources before dispatch."""
    from novelty_harness.runtime.budgets.controller import DIMENSIONS

    sealed = context.manifest.budget_limits or BudgetLimits()
    prior = context.manifest.budget_usage or BudgetUsage()
    values: dict[str, int | float | None] = {}
    for dimension in DIMENSIONS:
        name = "max_" + dimension
        caps = [getattr(sealed, name)]
        if budget is not None:
            caps.append(getattr(budget.limits, name))
        bounded = [cap for cap in caps if cap is not None]
        used = max(getattr(prior, dimension), getattr(budget.usage, dimension) if budget else 0)
        values[name] = max(0, min(bounded) - used) if bounded else None
    return BudgetLimits.model_validate(values)


class ResearchGapDisposition(TargetScoped):
    contract_kind: Literal["phase7-research-gap-disposition-v1"] = (
        "phase7-research-gap-disposition-v1"
    )
    request_id: str
    status: Literal[
        "ACCEPT", "DUPLICATE", "BUDGET_STOP", "NON_MATERIAL", "UNAVAILABLE", "INPUT_RESOLUTION"
    ]
    reason: str
    budget: ResearchEscalationBudget | None = None


def artifact_proposed_needs(
    artifacts: tuple[Phase7Artifact, ...], target_id: str
) -> tuple[tuple[InputClarificationNeed, ...], tuple[ResearchGapRequest, ...]]:
    """Extract and join typed proposal content, including retained judge findings."""
    import json

    needs: dict[str, InputClarificationNeed] = {}
    gaps: dict[str, ResearchGapRequest] = {}
    for artifact in artifacts:
        if artifact.target_id != target_id or artifact.kind not in {
            "PROSECUTION_CASE",
            "DEFENSE_CASE",
            "REBUTTAL",
            "JUDGE_RUN",
        }:
            continue
        document = json.loads(artifact.document_json)
        if artifact.kind == "JUDGE_RUN":
            document = document["finding"]
        for raw in document.get("input_needs", ()):
            need = InputClarificationNeed.model_validate(raw)
            if need.need_id in needs and needs[need.need_id] != need:
                raise ValueError("Proposed input need ID conflicts")
            needs[need.need_id] = need
        for raw in document.get("research_gaps", ()):
            gap = ResearchGapRequest.model_validate(raw)
            if gap.request_id in gaps and gaps[gap.request_id] != gap:
                raise ValueError("Proposed research gap ID conflicts")
            gaps[gap.request_id] = gap
    return tuple(needs.values()), tuple(gaps.values())


def validate_research_disposition(
    request: ResearchGapRequest,
    disposition: ResearchGapDisposition,
    context: SealedAssessmentContext,
    packet: "AdjudicationCasePacket",
) -> None:
    validate_research_gap_request(request, packet)
    if (
        disposition.assessment_id,
        disposition.assessment_context_id,
        disposition.phase6_snapshot_id,
        disposition.target_id,
        disposition.request_id,
    ) != (
        request.assessment_id,
        request.assessment_context_id,
        request.phase6_snapshot_id,
        request.target_id,
        request.request_id,
    ):
        raise ValueError("Research disposition differs from request scope")
    if disposition.status == "UNAVAILABLE":
        if disposition.budget is not None or not disposition.reason:
            raise ValueError("Unavailable research disposition requires an explicit limitation")
        return
    if disposition.budget is None:
        raise ValueError("Research disposition lacks its cumulative budget policy")
    decision = GapEscalationPolicy().decide(request, context, disposition.budget, packet=packet)
    if (
        disposition.status != decision.status
        or disposition.reason != decision.reason
        or request.dispatch_allowance != remaining_research_allowance(context, disposition.budget)
    ):
        raise ValueError("Research disposition differs from deterministic dispatch permission")
