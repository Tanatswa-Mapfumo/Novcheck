"""Structured contribution localization without editing the claim or evidence."""

from typing import TYPE_CHECKING, Literal

from novelty_harness.adjudication.models import TargetRef, TargetScoped

if TYPE_CHECKING:
    from novelty_harness.adjudication.packet import AdjudicationCasePacket


class CounterfactualLocalization(TargetScoped):
    contract_kind: Literal["phase7-counterfactual-localization-v2"] = (
        "phase7-counterfactual-localization-v2"
    )
    localization_id: str
    nearest_comparison_id: str | None
    removed_element: str
    remaining_differences: tuple[str, ...] = ()
    substantial_equivalence_after_removal: bool | None = None
    reason: str
    limiting_factors: tuple[str, ...] = ()


def validate_counterfactual(
    packet: "AdjudicationCasePacket", target: TargetRef, proposal: CounterfactualLocalization
) -> CounterfactualLocalization:
    """Require an exact target and a comparison-localized claimed difference."""

    proposal = CounterfactualLocalization.model_validate_json(proposal.model_dump_json())
    if (
        proposal.assessment_id,
        proposal.assessment_context_id,
        proposal.phase6_snapshot_id,
        proposal.target_id,
    ) != (
        packet.assessment_id,
        packet.assessment_context_id,
        packet.phase6_snapshot_id,
        target.id,
    ):
        raise ValueError("Counterfactual scope differs from case packet")
    profile = next(
        (
            item
            for item in packet.target_profiles
            if item.target_id == target.id and item.target_kind == target.kind
        ),
        None,
    )
    if profile is None:
        raise ValueError("Counterfactual target is absent from packet")
    comparisons = {
        str(item.comparison.classification.classification_id): item
        for item in packet.comparisons
        if item.comparison.classification.mcu_id == target.id
    }
    if proposal.nearest_comparison_id is None:
        if comparisons or proposal.substantial_equivalence_after_removal is not None:
            raise ValueError("Counterfactual equivalence needs a nearest Phase 6 comparison")
        return proposal
    nearest = comparisons.get(proposal.nearest_comparison_id)
    if nearest is None:
        raise ValueError("Counterfactual nearest comparison is absent from target packet")
    classification = nearest.comparison.classification
    packet_differences = {
        *classification.missing_elements,
        *classification.missing_relationships,
        *((classification.configuration_gap,) if classification.configuration_gap else ()),
    }
    if proposal.removed_element not in packet_differences:
        raise ValueError("Counterfactual removed element is not a localized Phase 6 difference")
    if set(proposal.remaining_differences) != packet_differences - {proposal.removed_element}:
        raise ValueError("Counterfactual must completely account for remaining Phase 6 differences")
    return proposal
