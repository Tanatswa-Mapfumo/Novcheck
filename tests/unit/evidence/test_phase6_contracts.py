from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from novelty_harness.domain.enums import EvidenceTier, PrecedentState, SupportVerificationState
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DimensionMapping,
    DirectedRelationship,
    EvidenceProposition,
    MappedStatement,
    MappingComparison,
    PropositionCommitment,
    SourceMCUMapping,
)
from novelty_harness.evidence.precedent.models import (
    CounterfactualDiagnostic,
    PatentScreeningDateRecord,
    PatentScreeningResult,
    PrecedentClassification,
)
from novelty_harness.evidence.verification.models import (
    BlindedPassage,
    BlindedVerificationInput,
    ChronologyAssessment,
    CommitmentStateRecord,
    ContextExpansion,
    EdgeEligibility,
    PassageSupportClaim,
    SupportVerification,
    VerifiedEvidenceEdge,
)
from tests.fixtures.phase5 import phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("phase6-contract-test")
RELATION = DirectedRelationship(subject="sensor", relation="controls", object="relay")


def commitment(
    commitment_id: str = "mech",
    dimension: ComparisonDimension = ComparisonDimension.MECHANISM,
    *,
    text: str = "Sensor controls relay",
    relationship: DirectedRelationship | None = None,
) -> PropositionCommitment:
    values: dict[str, object] = {
        "commitment_id": commitment_id,
        "dimension": dimension,
        "text": text,
    }
    if relationship is not None:
        values["relationship"] = relationship
    return PropositionCommitment.model_validate(values)


def proposition(**overrides: object) -> EvidenceProposition:
    values: dict[str, object] = {
        "proposition_id": "prop_1",
        "mcu_id": "mcu_1",
        "statement": "A sensor controls a relay",
        "commitments": (
            commitment(),
            commitment("rel:0", ComparisonDimension.RELATIONSHIPS, relationship=RELATION),
        ),
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return EvidenceProposition.model_validate(values)


def mapping(**overrides: object) -> SourceMCUMapping:
    values: dict[str, object] = {
        "mapping_id": "map_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1",
        "mcu_id": "mcu_1",
        "proposition_id": "prop_1",
        "dimensions": (
            DimensionMapping(
                dimension=ComparisonDimension.MECHANISM,
                matching=(
                    MappedStatement(
                        dimension=ComparisonDimension.MECHANISM,
                        statement="Sensor controls relay",
                        passage_ids=("pass_1",),
                    ),
                ),
            ),
            DimensionMapping(
                dimension=ComparisonDimension.RELATIONSHIPS,
                matching=(
                    MappedStatement(
                        dimension=ComparisonDimension.RELATIONSHIPS,
                        statement="sensor controls relay",
                        passage_ids=("pass_1",),
                        relationship=RELATION,
                    ),
                ),
                conflicting=(
                    MappedStatement(
                        dimension=ComparisonDimension.RELATIONSHIPS,
                        statement="relay controls sensor",
                        passage_ids=("pass_2",),
                        relationship=DirectedRelationship(
                            subject="relay", relation="controls", object="sensor"
                        ),
                    ),
                ),
            ),
            DimensionMapping(
                dimension=ComparisonDimension.CONTEXT,
                missing=("deployment context",),
            ),
        ),
        "mapper_prompt_version": "evidence-mapper-v1",
        "mapper_rubric_version": "mapping-rubric-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return SourceMCUMapping.model_validate(values)


def claim(**overrides: object) -> PassageSupportClaim:
    values: dict[str, object] = {
        "claim_id": "claim_1",
        "mapping_id": "map_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1",
        "mcu_id": "mcu_1",
        "proposition_id": "prop_1",
        "proposition_statement": "A sensor controls a relay",
        "commitments": proposition().commitments,
        "claimed_dimensions": (ComparisonDimension.MECHANISM,),
        "relationship_claims": (RELATION,),
        "passage_ids": ("pass_1",),
    }
    values.update(overrides)
    return PassageSupportClaim.model_validate(values)


def verification(**overrides: object) -> SupportVerification:
    values: dict[str, object] = {
        "verification_id": "ver_1",
        "claim_id": "claim_1",
        "mapping_id": "map_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1",
        "mcu_id": "mcu_1",
        "state": SupportVerificationState.SUPPORTED,
        "commitment_states": (
            CommitmentStateRecord(
                commitment_id="mech",
                dimension=ComparisonDimension.MECHANISM,
                state="SUPPORTED",
                rationale="Passage states the relationship",
                passage_ids=("pass_1",),
            ),
        ),
        "supported_portions": ("Sensor controls relay",),
        "verifier_prompt_version": "support-verifier-v1",
        "verifier_rubric_version": "support-rubric-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return SupportVerification.model_validate(values)


def chronology(state: str = "PREDATES_CUTOFF") -> ChronologyAssessment:
    values: dict[str, object] = {"as_of": date(2026, 9, 28), "state": state}
    if state == "PREDATES_CUTOFF":
        values.update(
            {"decisive_date": date(2024, 1, 1), "decisive_date_field": "publication_date"}
        )
    elif state == "POST_CUTOFF":
        values.update(
            {"decisive_date": date(2027, 1, 1), "decisive_date_field": "publication_date"}
        )
    return ChronologyAssessment.model_validate(values)


def test_comparison_dimensions_are_exactly_the_spec_set() -> None:
    assert {dimension.value for dimension in ComparisonDimension} == {
        "PURPOSE",
        "PROBLEM",
        "TARGET",
        "MECHANISM",
        "ARCHITECTURE",
        "FEATURES",
        "RELATIONSHIPS",
        "CONTROL_FLOW",
        "CONTEXT",
        "INTENDED_OUTCOME",
        "CONSTRAINTS",
        "EVALUATION_TARGET",
    }


def test_relationship_dimensions_require_a_directed_relationship() -> None:
    with pytest.raises(ValidationError):
        commitment("rel", ComparisonDimension.RELATIONSHIPS, text="controls")
    with pytest.raises(ValidationError):
        MappedStatement(
            dimension=ComparisonDimension.CONTROL_FLOW,
            statement="flow",
            passage_ids=("pass_1",),
        )
    ok = MappedStatement(
        dimension=ComparisonDimension.CONTROL_FLOW,
        statement="flow",
        passage_ids=("pass_1",),
        relationship=RELATION,
    )
    assert ok.relationship is not None


def test_proposition_and_mapping_round_trip_and_require_passages() -> None:
    prop = proposition()
    assert EvidenceProposition.model_validate(prop.model_dump(mode="json")) == prop
    with pytest.raises(ValidationError):
        proposition(commitments=())
    with pytest.raises(ValidationError):
        proposition(commitments=(commitment(), commitment()))

    mapped = mapping()
    assert SourceMCUMapping.model_validate(mapped.model_dump(mode="json")) == mapped
    assert mapped.mapped_passage_ids() == ("pass_1", "pass_2")
    with pytest.raises(ValidationError):
        MappedStatement(dimension=ComparisonDimension.MECHANISM, statement="x", passage_ids=())
    with pytest.raises(ValidationError):
        DimensionMapping(dimension=ComparisonDimension.MECHANISM)
    with pytest.raises(ValidationError):
        mapping(dimensions=(mapping().dimensions[0], mapping().dimensions[0]))


def test_aggregate_comparison_keeps_matches_misses_and_conflicts_separate() -> None:
    comparison = mapping().aggregate_comparison()
    assert isinstance(comparison, MappingComparison)
    assert comparison.matching_relationships == ("sensor controls relay",)
    assert comparison.conflicting_elements == ("RELATIONSHIPS: relay controls sensor",)
    assert comparison.missing_elements == ("CONTEXT: deployment context",)
    assert "PURPOSE" not in " ".join(comparison.matching_elements)


def test_blinded_verification_input_rejects_forbidden_fields() -> None:
    allowed = BlindedVerificationInput(
        claim_id="claim_1",
        source_id="src_1",
        source_version_id="srcv_1",
        proposition_statement="A sensor controls a relay",
        commitments=proposition().commitments,
        claimed_dimensions=(ComparisonDimension.MECHANISM,),
        relationship_claims=(RELATION,),
        passages=(
            BlindedPassage(
                passage_id="pass_1", text="Exact passage text", locator="RESOLVED_CONTENT"
            ),
        ),
    )
    assert BlindedVerificationInput.model_validate(allowed.model_dump(mode="json")) == allowed
    forbidden = (
        "novelty_verdict",
        "verdict",
        "precedent_class",
        "relation_type",
        "prosecutor",
        "defender",
        "quality_tier",
        "evidence_quality",
        "search_rank",
        "provider_score",
        "relevance",
        "user_novelty_claim",
        "report_wording",
    )
    payload = allowed.model_dump(mode="json")
    for field in forbidden:
        with pytest.raises(ValidationError):
            BlindedVerificationInput.model_validate({**payload, field: "x"})


def test_support_verification_states_match_their_payloads() -> None:
    supported = verification()
    assert SupportVerification.model_validate(supported.model_dump(mode="json")) == supported
    record = CommitmentStateRecord(
        commitment_id="mech",
        dimension=ComparisonDimension.MECHANISM,
        state="NOT_SUPPORTED",
        rationale="Passage is about another domain",
    )
    with pytest.raises(ValidationError):
        verification(state=SupportVerificationState.NOT_SUPPORTED, supported_portions=("x",))
    with pytest.raises(ValidationError):
        verification(
            state=SupportVerificationState.PARTIALLY_SUPPORTED,
            commitment_states=(record,),
            supported_portions=("something",),
        )
    partial = verification(
        state=SupportVerificationState.PARTIALLY_SUPPORTED,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="mech",
                dimension=ComparisonDimension.MECHANISM,
                state="SUPPORTED",
                rationale="supported",
            ),
            record,
        ),
        supported_portions=("mechanism",),
        unsupported_portions=("context",),
    )
    assert partial.unsupported_portions == ("context",)
    with pytest.raises(ValidationError):
        verification(
            state=SupportVerificationState.CONTRADICTED,
            commitment_states=(
                CommitmentStateRecord(
                    commitment_id="mech",
                    dimension=ComparisonDimension.MECHANISM,
                    state="CONTRADICTED",
                    rationale="opposite direction",
                ),
            ),
        )
    insufficient = verification(
        state=SupportVerificationState.INSUFFICIENT_CONTEXT,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="mech",
                dimension=ComparisonDimension.MECHANISM,
                state="INSUFFICIENT",
                rationale="qualifier missing",
            ),
        ),
        context_needed=("following sentence",),
    )
    assert insufficient.context_needed == ("following sentence",)


def test_context_expansion_availability_is_consistent() -> None:
    blocked = ContextExpansion(
        origin_passage_id="pass_1",
        source_id="src_1",
        source_version_id="srcv_1",
        attempt=1,
        available=False,
        blocked_reason="No wider same-source window is stored",
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert ContextExpansion.model_validate(blocked.model_dump(mode="json")) == blocked
    with pytest.raises(ValidationError):
        ContextExpansion.model_validate(
            {**blocked.model_dump(), "available": True, "window_passage_id": None}
        )


def test_chronology_and_eligibility_gates() -> None:
    assert chronology().state == "PREDATES_CUTOFF"
    with pytest.raises(ValidationError):
        ChronologyAssessment(as_of=date(2026, 9, 28), state="PREDATES_CUTOFF")
    eligible = EdgeEligibility(decisive=True, chronology=chronology())
    assert eligible.decisive
    with pytest.raises(ValidationError):
        EdgeEligibility(decisive=True, chronology=chronology("POST_CUTOFF"))
    uncertain = EdgeEligibility(decisive=False, chronology=chronology("UNCERTAIN"))
    assert not uncertain.decisive


def test_verified_edge_cannot_be_decisive_without_full_support_or_pre_cutoff_chronology() -> None:
    values: dict[str, object] = {
        "edge_id": "edge_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1",
        "mcu_id": "mcu_1",
        "proposition_id": "prop_1",
        "proposition": "A sensor controls a relay",
        "mapping_id": "map_1",
        "verification_id": "ver_1",
        "passage_ids": ("pass_1",),
        "comparison": mapping().aggregate_comparison(),
        "support_state": SupportVerificationState.SUPPORTED,
        "decisive": True,
        "chronology": chronology(),
        "eligibility": EdgeEligibility(decisive=True, chronology=chronology()),
        "relation": PrecedentState.DIRECT_PRECEDENT,
        "quality_tier": EvidenceTier.A,
        "mapper_prompt_version": "evidence-mapper-v1",
        "verifier_prompt_version": "support-verifier-v1",
        "verifier_rubric_version": "support-rubric-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    edge = VerifiedEvidenceEdge.model_validate(values)
    assert VerifiedEvidenceEdge.model_validate(edge.model_dump(mode="json")) == edge
    with pytest.raises(ValidationError):
        VerifiedEvidenceEdge.model_validate(
            {**values, "support_state": SupportVerificationState.PARTIALLY_SUPPORTED}
        )
    with pytest.raises(ValidationError):
        VerifiedEvidenceEdge.model_validate({**values, "chronology": chronology("POST_CUTOFF")})


def classification(**overrides: object) -> PrecedentClassification:
    values: dict[str, object] = {
        "classification_id": "cls_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1",
        "mcu_id": "mcu_1",
        "mapping_id": "map_1",
        "verification_id": "ver_1",
        "relation": PrecedentState.DIRECT_PRECEDENT,
        "decisive": True,
        "basis": ("Single source covers all material elements and relationships",),
        "covered_elements": ("sensor",),
        "covered_relationships": ("sensor controls relay",),
        "classifier_version": "precedent-classifier-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return PrecedentClassification.model_validate(values)


def test_precedent_classification_is_local_only_and_relation_consistent() -> None:
    direct = classification()
    assert direct.scope == "LOCAL_SOURCE_MCU"
    assert direct.global_absence_claim_permitted is False
    assert PrecedentClassification.model_validate(direct.model_dump(mode="json")) == direct
    with pytest.raises(ValidationError):
        classification(global_absence_claim_permitted=True)
    with pytest.raises(ValidationError):
        classification(missing_elements=("relay",))
    with pytest.raises(ValidationError):
        classification(relation=PrecedentState.STRONG_PARTIAL_PRECEDENT, decisive=False)
    partial = classification(
        relation=PrecedentState.STRONG_PARTIAL_PRECEDENT,
        decisive=False,
        missing_elements=("relay",),
    )
    assert partial.missing_elements == ("relay",)
    component = classification(
        relation=PrecedentState.COMPONENT_PRECEDENT_ONLY,
        decisive=False,
        covered_elements=("sensor", "relay"),
        missing_relationships=("sensor controls relay",),
        configuration_gap="Claimed configuration not identified",
    )
    assert component.configuration_gap is not None
    with pytest.raises(ValidationError):
        classification(
            relation=PrecedentState.COMPONENT_PRECEDENT_ONLY,
            decisive=False,
            configuration_gap=None,
        )
    analogous = classification(
        relation=PrecedentState.ANALOGOUS_PRECEDENT,
        decisive=False,
        functional_similarity=(ComparisonDimension.PURPOSE,),
        missing_relationships=("sensor controls relay",),
    )
    assert analogous.functional_similarity == (ComparisonDimension.PURPOSE,)
    with pytest.raises(ValidationError):
        classification(relation=PrecedentState.ANALOGOUS_PRECEDENT, decisive=False)
    contradictory = classification(
        relation=PrecedentState.CONTRADICTORY_EVIDENCE,
        decisive=False,
        contradictions=("Passage states relay controls sensor",),
    )
    assert contradictory.contradictions
    with pytest.raises(ValidationError):
        classification(relation=PrecedentState.CONTRADICTORY_EVIDENCE, decisive=False)
    unresolved = classification(
        relation=PrecedentState.UNRESOLVED,
        decisive=False,
        unresolved=("Qualifier context unavailable",),
    )
    assert unresolved.unresolved
    unassessable = classification(
        relation=PrecedentState.UNASSESSABLE,
        decisive=False,
        unassessable_reason="Mechanism withheld",
    )
    assert unassessable.unassessable_reason is not None
    absent = classification(relation=PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED, decisive=False)
    assert absent.scope == "LOCAL_SOURCE_MCU"
    with pytest.raises(ValidationError):
        classification(
            relation=PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
            decisive=False,
            unassessable_reason="wrong payload",
        )


def test_counterfactual_diagnostic_is_explicitly_diagnostic() -> None:
    diagnostic = CounterfactualDiagnostic(
        removed_element="adaptive scheduling",
        remaining_distinction="Feedback loop",
        becomes_substantially_equivalent=False,
        basis=("Removing the scheduler leaves a different control path",),
    )
    assert diagnostic.diagnostic_only is True
    with pytest.raises(ValidationError):
        CounterfactualDiagnostic.model_validate(
            {**diagnostic.model_dump(mode="json"), "diagnostic_only": False}
        )


def test_patent_screening_preserves_the_one_reference_distinction() -> None:
    single = PatentScreeningResult(
        screening_id="psr_1",
        mcu_id="mcu_1",
        mode="SINGLE_REFERENCE_ANTICIPATION_LIKE",
        single_reference_id="src_patent_a",
        reference_source_ids=("src_patent_a",),
        covered_elements=("sensor", "relay"),
        covered_relationships=("sensor controls relay",),
        dates=(
            PatentScreeningDateRecord(
                source_id="src_patent_a",
                priority_date=date(2018, 1, 1),
                publication_date=date(2020, 1, 1),
            ),
        ),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert single.disclaimer == "patent-screening-not-legal-advice-v1"
    multi = PatentScreeningResult(
        screening_id="psr_2",
        mcu_id="mcu_1",
        mode="MULTI_REFERENCE_COMBINATION_LIKE",
        reference_source_ids=("src_patent_a", "src_patent_b"),
        missing_elements=("relay",),
        limitations=("Two references each cover part of the configuration",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert multi.single_reference_id is None
    with pytest.raises(ValidationError):
        PatentScreeningResult.model_validate(
            {
                **multi.model_dump(mode="json"),
                "mode": "SINGLE_REFERENCE_ANTICIPATION_LIKE",
                "single_reference_id": "src_patent_a",
            }
        )
    with pytest.raises(ValidationError):
        PatentScreeningResult.model_validate(
            {**single.model_dump(mode="json"), "missing_elements": ("relay",)}
        )
