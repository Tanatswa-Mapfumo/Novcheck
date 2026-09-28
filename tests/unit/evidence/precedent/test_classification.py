from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DimensionMapping,
    DirectedRelationship,
    EvidenceProposition,
    MappedStatement,
    PropositionCommitment,
    SourceMCUMapping,
)
from novelty_harness.evidence.precedent.gates import (
    ClassificationFacts,
    classify_precedent,
)
from novelty_harness.evidence.verification.models import (
    CommitmentStateRecord,
    PassageSupportClaim,
    SupportVerification,
)
from tests.fixtures.phase5 import phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("classification-test")
RELATIONSHIP = DirectedRelationship(subject="sensor", relation="controls", object="relay")


def commitment(
    commitment_id: str,
    dimension: ComparisonDimension,
    *,
    text: str | None = None,
    relationship: DirectedRelationship | None = None,
) -> PropositionCommitment:
    values: dict[str, object] = {
        "commitment_id": commitment_id,
        "dimension": dimension,
        "text": text or f"{dimension.value} commitment",
    }
    if relationship is not None:
        values["relationship"] = relationship
    return PropositionCommitment.model_validate(values)


def proposition(*commitments: PropositionCommitment) -> EvidenceProposition:
    return EvidenceProposition(
        proposition_id="prop_1",
        mcu_id="mcu_1",
        statement="A sensor controls a relay",
        commitments=commitments,
        provenance=ORIGIN,
    )


def statement(dimension: ComparisonDimension) -> MappedStatement:
    return MappedStatement(
        dimension=dimension,
        statement=f"mapped {dimension.value}",
        passage_ids=("pass_1",),
        relationship=(
            RELATIONSHIP
            if dimension in {ComparisonDimension.RELATIONSHIPS, ComparisonDimension.CONTROL_FLOW}
            else None
        ),
    )


def mapping_for(
    *,
    matching: Sequence[ComparisonDimension] = (),
    missing: Sequence[ComparisonDimension] = (),
    conflicting: Sequence[ComparisonDimension] = (),
    source_id: str = "src_1",
    proposition_id: str = "prop_1",
    mcu_id: str = "mcu_1",
    mapping_id: str = "map_1",
) -> SourceMCUMapping:
    grouped: dict[ComparisonDimension, dict[str, list[object]]] = {}
    for dimension in matching:
        grouped.setdefault(dimension, {"matching": [], "missing": [], "conflicting": []})[
            "matching"
        ].append(statement(dimension))
    for dimension in missing:
        grouped.setdefault(dimension, {"matching": [], "missing": [], "conflicting": []})[
            "missing"
        ].append(f"no {dimension.value} stated")
    for dimension in conflicting:
        grouped.setdefault(dimension, {"matching": [], "missing": [], "conflicting": []})[
            "conflicting"
        ].append(statement(dimension))
    if not grouped:
        grouped[ComparisonDimension.MECHANISM] = {
            "matching": [],
            "missing": ["nothing mapped"],
            "conflicting": [],
        }
    dimensions = [
        DimensionMapping(
            dimension=dimension,
            matching=tuple(values["matching"]),  # type: ignore[arg-type]
            missing=tuple(values["missing"]),  # type: ignore[arg-type]
            conflicting=tuple(values["conflicting"]),  # type: ignore[arg-type]
        )
        for dimension, values in grouped.items()
    ]
    return SourceMCUMapping(
        mapping_id=mapping_id,
        source_id=source_id,
        source_version_id="srcv_1_v1",
        mcu_id=mcu_id,
        proposition_id=proposition_id,
        dimensions=tuple(dimensions),
        mapper_prompt_version="evidence-mapper-v1",
        mapper_rubric_version="mapping-rubric-v1",
        observed_at=NOW,
        provenance=ORIGIN,
    )


def verification_for(
    target: EvidenceProposition,
    states: Mapping[str, str],
    *,
    relied: Sequence[str] = ("pass_1",),
    source_id: str = "src_1",
    mapping_id: str = "map_1",
) -> SupportVerification:
    records = tuple(
        CommitmentStateRecord(
            commitment_id=item.commitment_id,
            dimension=item.dimension,
            state=states[item.commitment_id],  # type: ignore[arg-type]
            rationale=f"{states[item.commitment_id]} rationale",
            passage_ids=tuple(relied),
        )
        for item in target.commitments
    )
    values: dict[str, object] = {
        "verification_id": "ver_1",
        "claim_id": "claim_1",
        "mapping_id": mapping_id,
        "source_id": source_id,
        "source_version_id": "srcv_1_v1",
        "mcu_id": target.mcu_id,
        "commitment_states": records,
        "context_completeness": "COMPLETE",
        "relied_on_passage_ids": tuple(relied),
        "verifier_prompt_version": "support-verifier-v1",
        "verifier_rubric_version": "support-rubric-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values["supported_portions"] = tuple(
        item.text for item in target.commitments if states[item.commitment_id] == "SUPPORTED"
    )
    values["unsupported_portions"] = tuple(
        item.text for item in target.commitments if states[item.commitment_id] == "NOT_SUPPORTED"
    )
    values["contradictions"] = tuple(
        item.text for item in target.commitments if states[item.commitment_id] == "CONTRADICTED"
    )
    values["context_needed"] = tuple(
        f"more context for {item.commitment_id}"
        for item in target.commitments
        if states[item.commitment_id] == "INSUFFICIENT"
    )
    if "CONTRADICTED" in states.values():
        values["state"] = SupportVerificationState.CONTRADICTED
    elif "INSUFFICIENT" in states.values():
        values["state"] = SupportVerificationState.INSUFFICIENT_CONTEXT
    elif all(state == "SUPPORTED" for state in states.values()):
        values["state"] = SupportVerificationState.SUPPORTED
    elif not values["supported_portions"]:
        values["state"] = SupportVerificationState.NOT_SUPPORTED
    else:
        values["state"] = SupportVerificationState.PARTIALLY_SUPPORTED
    return SupportVerification.model_validate(values)


def claim_for(
    target: EvidenceProposition,
    mapped: SourceMCUMapping,
    verified: SupportVerification,
) -> PassageSupportClaim:
    return PassageSupportClaim(
        claim_id=verified.claim_id,
        mapping_id=mapped.mapping_id,
        source_id=mapped.source_id,
        source_version_id=mapped.source_version_id,
        mcu_id=target.mcu_id,
        proposition_id=target.proposition_id,
        proposition_statement=target.statement,
        commitments=target.commitments,
        passage_ids=("pass_1",),
    )


def classification_facts(**values: object) -> ClassificationFacts:
    target = values.get("proposition")
    mapped = values.get("mapping")
    verified = values.get("verification")
    if (
        "claim" not in values
        and isinstance(target, EvidenceProposition)
        and isinstance(mapped, SourceMCUMapping)
        and isinstance(verified, SupportVerification)
    ):
        values["claim"] = claim_for(target, mapped, verified)
    return ClassificationFacts.model_validate(values)


def facts_for(
    target: EvidenceProposition,
    *,
    states: Mapping[str, str],
    matching: Sequence[ComparisonDimension] = (),
    missing: Sequence[ComparisonDimension] = (),
    conflicting: Sequence[ComparisonDimension] = (),
    decisive: bool = False,
    chronology: str = "UNCERTAIN",
    selection_failure: str | None = None,
    source_id: str = "src_1",
) -> ClassificationFacts:
    if selection_failure is not None:
        return ClassificationFacts(
            proposition=target,
            source_id=source_id,
            source_version_id="srcv_1_v1",
            decisive=decisive,
            chronology_state=chronology,  # type: ignore[arg-type]
            selection_failure=selection_failure,
        )
    mapped = mapping_for(
        matching=matching,
        missing=missing,
        conflicting=conflicting,
        source_id=source_id,
        proposition_id=target.proposition_id,
        mcu_id=target.mcu_id,
    )
    verified = verification_for(target, states, source_id=source_id)
    return classification_facts(
        proposition=target,
        source_id=source_id,
        source_version_id="srcv_1_v1",
        mapping=mapped,
        verification=verified,
        claim=claim_for(target, mapped, verified),
        decisive=decisive,
        chronology_state=chronology,  # type: ignore[arg-type]
    )


def basic_commitments() -> tuple[PropositionCommitment, ...]:
    return (
        commitment("mech", ComparisonDimension.MECHANISM, text="threshold drives a coil"),
        commitment("feat", ComparisonDimension.FEATURES, text="sensor"),
        commitment(
            "rel",
            ComparisonDimension.RELATIONSHIPS,
            text="sensor controls relay",
            relationship=RELATIONSHIP,
        ),
    )


def test_all_material_commitments_with_relationships_are_direct_single_source() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED", "feat": "SUPPORTED", "rel": "SUPPORTED"},
            matching=(
                ComparisonDimension.MECHANISM,
                ComparisonDimension.FEATURES,
                ComparisonDimension.RELATIONSHIPS,
            ),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.DIRECT_PRECEDENT
    assert classification.decisive and classification.single_source
    assert classification.covered_relationships == ("sensor controls relay",)
    assert classification.missing_elements == () and classification.missing_relationships == ()


def test_relationship_gap_defeats_direct_despite_feature_overlap() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED", "feat": "SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(
                ComparisonDimension.MECHANISM,
                ComparisonDimension.FEATURES,
                ComparisonDimension.RELATIONSHIPS,
            ),
            conflicting=(ComparisonDimension.CONTROL_FLOW,),
            decisive=False,
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    assert classification.configuration_gap
    assert not classification.decisive


def test_most_aspects_with_one_material_gap_is_strong_partial() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED", "feat": "SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.MECHANISM, ComparisonDimension.FEATURES),
            missing=(ComparisonDimension.RELATIONSHIPS,),
        ),
        clock=lambda: NOW,
    )
    # Relationship/configuration is unsupported while ingredients are present.
    assert classification.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    target2 = proposition(
        commitment("mech", ComparisonDimension.MECHANISM, text="threshold drives a coil"),
        commitment("feat", ComparisonDimension.FEATURES, text="sensor"),
        commitment("feat2", ComparisonDimension.FEATURES, text="relay"),
        commitment("constraint", ComparisonDimension.CONSTRAINTS, text="must run offline"),
    )
    classification2 = classify_precedent(
        facts_for(
            target2,
            states={
                "mech": "SUPPORTED",
                "feat": "SUPPORTED",
                "feat2": "SUPPORTED",
                "constraint": "NOT_SUPPORTED",
            },
            matching=(
                ComparisonDimension.MECHANISM,
                ComparisonDimension.FEATURES,
                ComparisonDimension.CONSTRAINTS,
            ),
            missing=(ComparisonDimension.CONSTRAINTS,),
        ),
        clock=lambda: NOW,
    )
    assert classification2.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT
    assert classification2.missing_elements == ("must run offline",)


def test_functional_match_with_missing_mechanism_is_analogous_not_direct() -> None:
    # F09: analogy requires an independently verified functional commitment,
    # not merely a mapper-proposed PURPOSE match.
    target = proposition(
        commitment("mech", ComparisonDimension.MECHANISM, text="threshold drives a coil"),
        commitment("feat", ComparisonDimension.FEATURES, text="sensor"),
        commitment("outcome", ComparisonDimension.INTENDED_OUTCOME, text="avoid manual switching"),
        commitment(
            "rel",
            ComparisonDimension.RELATIONSHIPS,
            text="sensor controls relay",
            relationship=RELATIONSHIP,
        ),
    )
    classification = classify_precedent(
        facts_for(
            target,
            states={
                "mech": "NOT_SUPPORTED",
                "feat": "SUPPORTED",
                "outcome": "SUPPORTED",
                "rel": "NOT_SUPPORTED",
            },
            matching=(ComparisonDimension.PURPOSE, ComparisonDimension.FEATURES),
            missing=(ComparisonDimension.MECHANISM, ComparisonDimension.RELATIONSHIPS),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.ANALOGOUS_PRECEDENT
    assert classification.functional_similarity == (ComparisonDimension.INTENDED_OUTCOME,)
    assert not classification.decisive


def test_mapper_only_surface_overlap_cannot_change_unverified_precedent() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={
                "mech": "NOT_SUPPORTED",
                "feat": "NOT_SUPPORTED",
                "rel": "NOT_SUPPORTED",
            },
            matching=(ComparisonDimension.ARCHITECTURE,),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED
    assert not classification.decisive
    without_mapper_match = classify_precedent(
        facts_for(
            target,
            states={"mech": "NOT_SUPPORTED", "feat": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"},
            missing=(ComparisonDimension.ARCHITECTURE,),
        ),
        clock=lambda: NOW,
    )
    assert without_mapper_match.relation == classification.relation


def test_no_local_match_never_claims_global_absence() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={
                "mech": "NOT_SUPPORTED",
                "feat": "NOT_SUPPORTED",
                "rel": "NOT_SUPPORTED",
            },
            missing=(ComparisonDimension.MECHANISM,),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED
    assert classification.scope == "LOCAL_SOURCE_MCU"
    assert classification.global_absence_claim_permitted is False


def test_contradiction_is_classified_as_contradictory_evidence() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "CONTRADICTED", "feat": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"},
            conflicting=(ComparisonDimension.MECHANISM,),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.CONTRADICTORY_EVIDENCE
    assert classification.contradictions


def test_exhausted_insufficient_context_is_unresolved() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED", "feat": "INSUFFICIENT", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.MECHANISM,),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.UNRESOLVED
    assert classification.unresolved


def test_full_match_that_is_not_temporally_eligible_is_not_direct() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED", "feat": "SUPPORTED", "rel": "SUPPORTED"},
            matching=(
                ComparisonDimension.MECHANISM,
                ComparisonDimension.FEATURES,
                ComparisonDimension.RELATIONSHIPS,
            ),
            decisive=False,
            chronology="POST_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.UNRESOLVED
    assert not classification.decisive
    assert any("POST_CUTOFF" in item for item in classification.unresolved)


def test_missing_mapping_or_grounded_passage_is_unassessable() -> None:
    target = proposition(*basic_commitments())
    classification = classify_precedent(
        facts_for(
            target,
            states={},
            selection_failure="Mapping cites no exact passage for any dimension",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.UNASSESSABLE
    assert classification.unassessable_reason is not None
