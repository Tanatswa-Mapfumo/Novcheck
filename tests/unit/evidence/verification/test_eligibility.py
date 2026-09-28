from datetime import UTC, date, datetime

import pytest

from novelty_harness.domain.enums import EvidenceTier, PrecedentState, SupportVerificationState
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DimensionMapping,
    EvidenceProposition,
    MappedStatement,
    PropositionCommitment,
    SourceMCUMapping,
)
from novelty_harness.evidence.normalization.models import SourceType
from novelty_harness.evidence.quality.assessment import assess_quality
from novelty_harness.evidence.quality.models import (
    AssessmentLevel,
    EvidenceQualitySignals,
)
from novelty_harness.evidence.verification.gates import (
    EdgeEligibilityError,
    assess_chronology,
    build_verified_evidence_edge,
)
from novelty_harness.evidence.verification.models import (
    CommitmentStateRecord,
    PassageSupportClaim,
    SupportVerification,
)
from tests.fixtures.phase5 import make_passage, make_source, make_version, phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 9, 28)
ORIGIN = phase5_provenance("eligibility-test")
COMMITMENTS = (
    PropositionCommitment(
        commitment_id="mech",
        dimension=ComparisonDimension.MECHANISM,
        text="threshold drives a relay coil",
    ),
    PropositionCommitment(
        commitment_id="outcome",
        dimension=ComparisonDimension.INTENDED_OUTCOME,
        text="the load switches without an operator",
    ),
)
CLAIM_PASSAGES = ("pass_1",)


def proposition() -> EvidenceProposition:
    return EvidenceProposition(
        proposition_id="prop_1",
        mcu_id="mcu_1",
        statement="A sensor controls a relay",
        commitments=COMMITMENTS,
        provenance=ORIGIN,
    )


def mapping() -> SourceMCUMapping:
    return SourceMCUMapping(
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        proposition_id="prop_1",
        dimensions=(
            DimensionMapping(
                dimension=ComparisonDimension.MECHANISM,
                matching=(
                    MappedStatement(
                        dimension=ComparisonDimension.MECHANISM,
                        statement="threshold drives a coil",
                        passage_ids=CLAIM_PASSAGES,
                    ),
                ),
            ),
        ),
        mapper_prompt_version="evidence-mapper-v1",
        mapper_rubric_version="mapping-rubric-v1",
        observed_at=NOW,
        provenance=ORIGIN,
    )


def verification(state: SupportVerificationState, *, relied=CLAIM_PASSAGES) -> SupportVerification:
    by_commitment = {
        SupportVerificationState.SUPPORTED: ("SUPPORTED", "SUPPORTED"),
        SupportVerificationState.NOT_SUPPORTED: ("NOT_SUPPORTED", "NOT_SUPPORTED"),
        SupportVerificationState.PARTIALLY_SUPPORTED: ("SUPPORTED", "NOT_SUPPORTED"),
        SupportVerificationState.CONTRADICTED: ("SUPPORTED", "CONTRADICTED"),
        SupportVerificationState.INSUFFICIENT_CONTEXT: ("SUPPORTED", "INSUFFICIENT"),
    }[state]
    records = tuple(
        CommitmentStateRecord(
            commitment_id=commitment.commitment_id,
            dimension=commitment.dimension,
            state=commitment_state,
            rationale=f"{commitment_state} rationale",
            passage_ids=relied,
        )
        for commitment, commitment_state in zip(COMMITMENTS, by_commitment, strict=True)
    )
    values: dict[str, object] = {
        "verification_id": "ver_1",
        "claim_id": "claim_1",
        "mapping_id": "map_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1_v1",
        "mcu_id": "mcu_1",
        "state": state,
        "commitment_states": records,
        "context_completeness": "COMPLETE",
        "context_expansions": 0,
        "verifier_prompt_version": "support-verifier-v1",
        "verifier_rubric_version": "support-rubric-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    if state == SupportVerificationState.SUPPORTED:
        values["supported_portions"] = tuple(item.text for item in COMMITMENTS)
    elif state == SupportVerificationState.PARTIALLY_SUPPORTED:
        values["supported_portions"] = (COMMITMENTS[0].text,)
        values["unsupported_portions"] = (COMMITMENTS[1].text,)
    elif state == SupportVerificationState.NOT_SUPPORTED:
        values["unsupported_portions"] = tuple(item.text for item in COMMITMENTS)
    elif state == SupportVerificationState.CONTRADICTED:
        values["contradictions"] = (f"{COMMITMENTS[1].text}: opposite stated",)
        values["supported_portions"] = (COMMITMENTS[0].text,)
    elif state == SupportVerificationState.INSUFFICIENT_CONTEXT:
        values["context_needed"] = ("the qualifier sentence",)
        values["supported_portions"] = (COMMITMENTS[0].text,)
    if relied:
        values["relied_on_passage_ids"] = relied
    return SupportVerification.model_validate(values)


def source(**overrides: object):
    return make_source("src_1", **overrides)


def bundle() -> SupportEvidenceBundle:
    claim = PassageSupportClaim(
        claim_id="claim_1",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        proposition_id="prop_1",
        proposition_statement=proposition().statement,
        commitments=COMMITMENTS,
        passage_ids=CLAIM_PASSAGES,
    )
    return SupportEvidenceBundle(
        claim=claim,
        passages=(
            make_passage(
                "src_1",
                text="A threshold drives a relay coil and switches a load without an operator.",
                passage_id="pass_1",
                source_version_id="srcv_1_v1",
            ),
        ),
    )


def build(state: SupportVerificationState, *, relation=None, source_overrides=None, quality=None):
    dates = (source_overrides or {}).get("dates", {"publication_date": date(2020, 1, 1)})
    published = dates.get("publication_date") if isinstance(dates, dict) else None
    return build_verified_evidence_edge(
        mapping=mapping(),
        verification=verification(state),
        proposition=proposition(),
        source=source(**(source_overrides or {})),
        bundle=bundle(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=published),
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id="asm_test",
        quality=quality,
        relation=relation,
    )


def test_supported_pre_cutoff_evidence_is_decisive_with_quality_attached() -> None:
    quality = assess_quality(source(), assessed_at=NOW)
    edge = build(SupportVerificationState.SUPPORTED, relation=None, quality=quality)
    assert edge.decisive and edge.eligibility.decisive
    assert edge.eligibility.reasons == ()
    assert edge.chronology.state == "PREDATES_CUTOFF"
    assert edge.quality_tier == quality.tier and edge.quality_assessment_id == "src_1"


def test_post_cutoff_evidence_cannot_be_decisive_or_direct_precedent() -> None:
    edge = build(
        SupportVerificationState.SUPPORTED,
        source_overrides={"dates": {"publication_date": date(2027, 1, 1)}},
    )
    assert not edge.decisive
    assert edge.chronology.state == "POST_CUTOFF"
    assert any("post-cutoff" in item for item in edge.eligibility.reasons)
    with pytest.raises(EdgeEligibilityError):
        build(
            SupportVerificationState.SUPPORTED,
            relation=PrecedentState.DIRECT_PRECEDENT,
            source_overrides={"dates": {"publication_date": date(2027, 1, 1)}},
        )


def test_uncertain_chronology_stays_uncertain_and_not_decisive() -> None:
    edge = build(SupportVerificationState.SUPPORTED, source_overrides={"dates": {}})
    assert edge.chronology.state == "UNCERTAIN"
    assert not edge.decisive
    assert any("uncertain" in item for item in edge.eligibility.reasons)


def test_cutoff_boundary_is_inclusive() -> None:
    source_record = source(dates={"publication_date": AS_OF})
    assessment = assess_chronology(source_record, as_of=AS_OF)
    assert assessment.state == "PREDATES_CUTOFF"


def test_unsupported_and_insufficient_evidence_cannot_create_decisive_edges() -> None:
    for state in (
        SupportVerificationState.NOT_SUPPORTED,
        SupportVerificationState.INSUFFICIENT_CONTEXT,
    ):
        edge = build(state)
        assert edge.support_state == state
        assert not edge.decisive
        assert any("Verification state" in item for item in edge.eligibility.reasons)
        with pytest.raises(EdgeEligibilityError):
            build(state, relation=PrecedentState.DIRECT_PRECEDENT)


def test_contradictions_remain_contradictions_and_cannot_be_direct() -> None:
    edge = build(
        SupportVerificationState.CONTRADICTED,
        relation=PrecedentState.CONTRADICTORY_EVIDENCE,
    )
    assert edge.support_state == SupportVerificationState.CONTRADICTED
    assert not edge.decisive
    with pytest.raises(EdgeEligibilityError):
        build(SupportVerificationState.CONTRADICTED, relation=PrecedentState.DIRECT_PRECEDENT)


def test_quality_cannot_alter_verification_state_or_decisiveness() -> None:
    high_quality = assess_quality(
        source(),
        assessed_at=NOW,
        signals=EvidenceQualitySignals(
            primary_artifact=True,
            technical_specificity=AssessmentLevel.HIGH,
            provenance_authenticity=AssessmentLevel.HIGH,
        ),
    )
    low_quality_source = source(
        source_type=SourceType.WEB, access_state="METADATA_ONLY", content_hash=None
    )
    low_quality = assess_quality(low_quality_source, assessed_at=NOW)
    high_edge = build(SupportVerificationState.SUPPORTED, quality=high_quality)
    low_edge = build_verified_evidence_edge(
        mapping=mapping(),
        verification=verification(SupportVerificationState.SUPPORTED),
        proposition=proposition(),
        source=low_quality_source,
        bundle=bundle(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        as_of=AS_OF,
        observed_at=NOW,
        quality=low_quality,
    )
    assert high_edge.support_state == low_edge.support_state
    assert high_edge.decisive == low_edge.decisive
    assert high_edge.quality_tier == EvidenceTier.A
    assert low_edge.quality_tier == EvidenceTier.D


def test_identity_disagreements_are_rejected() -> None:
    with pytest.raises(EdgeEligibilityError):
        build_verified_evidence_edge(
            mapping=mapping(),
            verification=verification(SupportVerificationState.SUPPORTED).model_copy(
                update={"mapping_id": "map_other"}
            ),
            proposition=proposition(),
            source=source(),
            bundle=bundle(),
            as_of=AS_OF,
            observed_at=NOW,
        )
    with pytest.raises(EdgeEligibilityError):
        build_verified_evidence_edge(
            mapping=mapping(),
            verification=verification(SupportVerificationState.SUPPORTED),
            proposition=proposition(),
            source=make_source("src_other"),
            bundle=bundle(),
            as_of=AS_OF,
            observed_at=NOW,
        )


def test_relied_on_passages_are_preferred_and_edge_ids_are_deterministic() -> None:
    expanded = ("pass_document", "pass_1")
    edge = build_verified_evidence_edge(
        mapping=mapping(),
        verification=verification(SupportVerificationState.SUPPORTED, relied=expanded),
        proposition=proposition(),
        source=source(),
        bundle=bundle(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        context_passages=(
            make_passage(
                "src_1",
                text="The full document confirms threshold control of the relay.",
                passage_id="pass_document",
                source_version_id="srcv_1_v1",
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
    )
    assert edge.passage_ids == expanded
    other = build(SupportVerificationState.SUPPORTED)
    assert edge.edge_id != other.edge_id
    repeat = build(SupportVerificationState.SUPPORTED)
    assert other.edge_id == repeat.edge_id
