"""Deterministic MCU comparison profiles and proposition commitments.

Profiles preserve mechanism, relationships and control flow separately, add
nothing that the MCU did not state, and record unknown dimensions explicitly.
Combination profiles keep member and relationship structure so that a source
can never be credited with a claimed configuration it does not contain.
"""

from collections.abc import Sequence
from typing import Literal, Self

from pydantic import ConfigDict, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DirectedRelationship,
    EvidenceProposition,
    PropositionCommitment,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

#: Conservative control-flow/process verb lexicon. A relationship is treated as
#: control flow only when its verb matches this documented set; unusual
#: terminology remains a material RELATIONSHIPS commitment rather than being
#: dropped.
CONTROL_FLOW_VERBS = frozenset(
    {
        "activate",
        "activates",
        "allocate",
        "allocates",
        "approve",
        "approves",
        "authorize",
        "authorizes",
        "block",
        "blocks",
        "control",
        "controls",
        "deactivate",
        "deactivates",
        "dispatch",
        "dispatches",
        "escalate",
        "escalates",
        "gate",
        "gates",
        "orchestrate",
        "orchestrates",
        "permit",
        "permits",
        "redirect",
        "redirects",
        "route",
        "routes",
        "schedule",
        "schedules",
        "sequence",
        "sequences",
        "trigger",
        "triggers",
    }
)


class MemberContribution(ContractModel):
    """Retained member structure inside a combination profile."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["mcu-member-contribution-v1"] = "mcu-member-contribution-v1"

    mcu_id: MCUId
    label: NonBlankText
    statement: NonBlankText
    mechanism: NonBlankText | None = None
    features: tuple[NonBlankText, ...] = ()
    relationships: tuple[DirectedRelationship, ...] = ()
    control_flow: tuple[DirectedRelationship, ...] = ()


class MCUComparisonProfile(ContractModel):
    """Structural view of an MCU (or combination) for mapping and comparison."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["mcu-comparison-profile-v1"] = "mcu-comparison-profile-v1"

    target_id: MCUId
    target_kind: Literal["MCU", "COMBINATION"] = "MCU"
    combination_id: NonBlankText | None = None
    label: NonBlankText
    statement: NonBlankText
    purpose: NonBlankText | None = None
    object_or_target: NonBlankText | None = None
    mechanism: NonBlankText | None = None
    features: tuple[NonBlankText, ...] = ()
    relationships: tuple[DirectedRelationship, ...] = ()
    control_flow: tuple[DirectedRelationship, ...] = ()
    context: NonBlankText | None = None
    intended_effect: NonBlankText | None = None
    combination_members: tuple[MCUId, ...] = ()
    combination_relationships: tuple[DirectedRelationship, ...] = ()
    member_contributions: tuple[MemberContribution, ...] = ()
    unknown_dimensions: tuple[ComparisonDimension, ...] = ()

    @model_validator(mode="after")
    def consistent_kind(self) -> Self:
        if self.target_kind == "COMBINATION" and (
            self.combination_id is None or not self.combination_members
        ):
            raise ValueError("Combination profiles require an id and members")
        if self.target_kind == "MCU" and self.combination_id is not None:
            raise ValueError("Plain MCU profiles cannot carry a combination id")
        if not set(self.control_flow) <= set(self.relationships):
            raise ValueError("Control flow must be a subset of stated relationships")
        if self.target_kind == "COMBINATION" and {
            contribution.mcu_id for contribution in self.member_contributions
        } != set(self.combination_members):
            raise ValueError("Combination member contributions must cover every member")
        return self


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = " ".join(value.split())
    return stripped or None


def _relationship(value: object) -> DirectedRelationship:
    return DirectedRelationship.model_validate(value)


def _control_flow(
    relationships: Sequence[DirectedRelationship],
) -> tuple[DirectedRelationship, ...]:
    return tuple(
        relationship
        for relationship in relationships
        if relationship.relation.casefold() in CONTROL_FLOW_VERBS
    )


def build_mcu_comparison_profile(mcu: MCU) -> MCUComparisonProfile:
    """Build a structural profile without inventing absent dimensions."""

    unknown: list[ComparisonDimension] = []
    mechanism = _clean(mcu.mechanism)
    purpose = _clean(mcu.purpose)
    target = _clean(mcu.object_or_target)
    context = _clean(mcu.context)
    intended_effect = _clean(mcu.intended_effect)
    features = tuple(dict.fromkeys(" ".join(feature.concept.split()) for feature in mcu.features))
    relationships = tuple(_relationship(item.model_dump()) for item in mcu.relationships)
    if mechanism is None:
        unknown.append(ComparisonDimension.MECHANISM)
    if purpose is None:
        unknown.append(ComparisonDimension.PURPOSE)
    if target is None:
        unknown.append(ComparisonDimension.TARGET)
    if context is None:
        unknown.append(ComparisonDimension.CONTEXT)
    if intended_effect is None:
        unknown.append(ComparisonDimension.INTENDED_OUTCOME)
    if not features:
        unknown.append(ComparisonDimension.FEATURES)
    if not relationships:
        unknown.extend((ComparisonDimension.RELATIONSHIPS, ComparisonDimension.CONTROL_FLOW))
    return MCUComparisonProfile(
        target_id=mcu.mcu_id,
        target_kind="MCU",
        label=mcu.label,
        statement=" ".join(mcu.statement.split()),
        purpose=purpose,
        object_or_target=target,
        mechanism=mechanism,
        features=features,
        relationships=relationships,
        control_flow=_control_flow(relationships),
        context=context,
        intended_effect=intended_effect,
        unknown_dimensions=tuple(dict.fromkeys(unknown)),
    )


def build_combination_comparison_profile(
    combination: MCUCombination, members: Sequence[MCU]
) -> MCUComparisonProfile:
    """Build a combination profile retaining member and configuration structure."""

    by_id = {member.mcu_id: member for member in members}
    missing = [identity for identity in combination.member_ids if identity not in by_id]
    if missing:
        raise ValueError(f"Combination members are missing from the graph: {missing}")
    relationships = tuple(_relationship(item.model_dump()) for item in combination.relationships)
    contributions: list[MemberContribution] = []
    for identity in combination.member_ids:
        member = by_id[identity]
        member_relationships = tuple(
            _relationship(item.model_dump()) for item in member.relationships
        )
        contributions.append(
            MemberContribution(
                mcu_id=member.mcu_id,
                label=member.label,
                statement=" ".join(member.statement.split()),
                mechanism=_clean(member.mechanism),
                features=tuple(
                    dict.fromkeys(" ".join(feature.concept.split()) for feature in member.features)
                ),
                relationships=member_relationships,
                control_flow=_control_flow(member_relationships),
            )
        )
    target_id: MCUId = "mcu_comb_" + canonical_hash(combination.combination_id)[:24]
    return MCUComparisonProfile(
        target_id=target_id,
        target_kind="COMBINATION",
        combination_id=combination.combination_id,
        label=combination.label,
        statement=" ".join(combination.statement.split()),
        relationships=relationships,
        control_flow=_control_flow(relationships),
        combination_members=tuple(combination.member_ids),
        combination_relationships=relationships,
        member_contributions=tuple(contributions),
        unknown_dimensions=(() if relationships else (ComparisonDimension.CONTROL_FLOW,)),
    )


def build_proposition(profile: MCUComparisonProfile) -> EvidenceProposition:
    """Turn a profile into verifiable material commitments.

    Only explicitly stated fields become commitments. A profile with no
    structured fields falls back to its own statement as the single commitment
    rather than inventing mechanism detail.
    """

    commitments: list[PropositionCommitment] = []
    if profile.mechanism is not None:
        commitments.append(
            PropositionCommitment(
                commitment_id="mech",
                dimension=ComparisonDimension.MECHANISM,
                text=profile.mechanism,
            )
        )
    if profile.purpose is not None:
        commitments.append(
            PropositionCommitment(
                commitment_id="purpose",
                dimension=ComparisonDimension.PURPOSE,
                text=profile.purpose,
            )
        )
    if profile.object_or_target is not None:
        commitments.append(
            PropositionCommitment(
                commitment_id="target",
                dimension=ComparisonDimension.TARGET,
                text=profile.object_or_target,
            )
        )
    if profile.context is not None:
        commitments.append(
            PropositionCommitment(
                commitment_id="context",
                dimension=ComparisonDimension.CONTEXT,
                text=profile.context,
            )
        )
    if profile.intended_effect is not None:
        commitments.append(
            PropositionCommitment(
                commitment_id="outcome",
                dimension=ComparisonDimension.INTENDED_OUTCOME,
                text=profile.intended_effect,
            )
        )
    for index, feature in enumerate(profile.features):
        commitments.append(
            PropositionCommitment(
                commitment_id=f"feat:{index}",
                dimension=ComparisonDimension.FEATURES,
                text=feature,
            )
        )
    control_ids = {relationship.describe() for relationship in profile.control_flow}
    for index, relationship in enumerate(profile.relationships):
        dimension = (
            ComparisonDimension.CONTROL_FLOW
            if relationship.describe() in control_ids
            else ComparisonDimension.RELATIONSHIPS
        )
        commitments.append(
            PropositionCommitment(
                commitment_id=f"rel:{index}",
                dimension=dimension,
                text=relationship.describe(),
                relationship=relationship,
            )
        )
    if profile.target_kind == "COMBINATION":
        commitments.append(
            PropositionCommitment(
                commitment_id="cfg",
                dimension=ComparisonDimension.ARCHITECTURE,
                text=profile.statement,
            )
        )
        for contribution in profile.member_contributions:
            member_detail = contribution.mechanism or contribution.statement
            commitments.append(
                PropositionCommitment(
                    commitment_id=f"member:{contribution.mcu_id}",
                    dimension=ComparisonDimension.ARCHITECTURE,
                    text=f"{contribution.label}: {member_detail}",
                )
            )
            for index, feature in enumerate(contribution.features):
                commitments.append(
                    PropositionCommitment(
                        commitment_id=f"member:{contribution.mcu_id}:feat:{index}",
                        dimension=ComparisonDimension.FEATURES,
                        text=feature,
                    )
                )
            member_control = {relationship.describe() for relationship in contribution.control_flow}
            for index, relationship in enumerate(contribution.relationships):
                dimension = (
                    ComparisonDimension.CONTROL_FLOW
                    if relationship.describe() in member_control
                    else ComparisonDimension.RELATIONSHIPS
                )
                commitments.append(
                    PropositionCommitment(
                        commitment_id=f"member:{contribution.mcu_id}:rel:{index}",
                        dimension=dimension,
                        text=relationship.describe(),
                        relationship=relationship,
                    )
                )
        combination_control = {relationship.describe() for relationship in profile.control_flow}
        for index, relationship in enumerate(profile.combination_relationships):
            dimension = (
                ComparisonDimension.CONTROL_FLOW
                if relationship.describe() in combination_control
                else ComparisonDimension.RELATIONSHIPS
            )
            commitments.append(
                PropositionCommitment(
                    commitment_id=f"crel:{index}",
                    dimension=dimension,
                    text=relationship.describe(),
                    relationship=relationship,
                )
            )
    if not commitments:
        commitments.append(
            PropositionCommitment(
                commitment_id="statement",
                dimension=ComparisonDimension.INTENDED_OUTCOME,
                text=profile.statement,
            )
        )
    payload: JsonValue = {
        "mcu_id": str(profile.target_id),
        "statement": profile.statement,
        "commitments": [item.model_dump(mode="json") for item in commitments],
    }
    return EvidenceProposition(
        proposition_id="prop_" + canonical_hash(payload),
        mcu_id=profile.target_id,
        statement=profile.statement,
        commitments=tuple(commitments),
        unknown_dimensions=profile.unknown_dimensions,
        provenance=_profile_provenance(profile),
    )


def _profile_provenance(profile: MCUComparisonProfile) -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="implemented",
        component="mcu_comparison_profile",
        detail=f"Deterministic profile for {profile.target_kind.lower()} {profile.target_id}",
    )
