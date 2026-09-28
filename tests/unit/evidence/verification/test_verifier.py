import json
from datetime import UTC, datetime

import pytest

from novelty_harness.domain.enums import SupportVerificationState
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DirectedRelationship,
    PropositionCommitment,
)
from novelty_harness.evidence.verification.gates import (
    PassageIntegrityError,
    VerificationValidationError,
    check_passage_integrity,
)
from novelty_harness.evidence.verification.prompts import (
    VERIFIER_PROMPT_VERSION,
    VerifierProposal,
)
from novelty_harness.evidence.verification.verifier import (
    VERIFIER_TASK,
    IndependentSupportVerifier,
)
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase5 import make_passage, phase5_provenance
from tests.fixtures.phase6 import StubLLMProvider

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("verifier-test")
VERSION = "srcv_1_v1"

MECHANISM = PropositionCommitment(
    commitment_id="mech",
    dimension=ComparisonDimension.MECHANISM,
    text="threshold drives a relay coil",
)
OUTCOME = PropositionCommitment(
    commitment_id="outcome",
    dimension=ComparisonDimension.INTENDED_OUTCOME,
    text="the load switches without an operator",
)
RELATIONSHIP = DirectedRelationship(subject="sensor", relation="controls", object="relay")


def bundle(text: str = "A threshold drives a relay coil and the load switches."):
    from novelty_harness.evidence.verification.models import PassageSupportClaim

    passage = make_passage("src_1", text=text, passage_id="pass_1", source_version_id=VERSION)
    claim = PassageSupportClaim(
        claim_id="claim_1",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id=VERSION,
        mcu_id="mcu_1",
        proposition_id="prop_1",
        proposition_statement="A sensor controls a relay",
        commitments=(MECHANISM, OUTCOME),
        claimed_dimensions=(ComparisonDimension.MECHANISM, ComparisonDimension.INTENDED_OUTCOME),
        relationship_claims=(RELATIONSHIP,),
        passage_ids=("pass_1",),
    )
    return SupportEvidenceBundle(claim=claim, passages=(passage,))


def proposal_data(
    *states: tuple[str, str],
    context_needed: tuple[str, ...] = (),
    passage_id: str = "pass_1",
) -> dict[str, object]:
    return {
        "prompt_version": VERIFIER_PROMPT_VERSION,
        "judgments": [
            {
                "commitment_id": commitment_id,
                "state": state,
                "rationale": f"judgment for {commitment_id}",
                "passage_ids": [passage_id],
            }
            for commitment_id, state in states
        ],
        "context_needed": list(context_needed),
    }


def verifier(data: dict[str, object]) -> IndependentSupportVerifier:
    return IndependentSupportVerifier(SemanticRunner(StubLLMProvider({VERIFIER_TASK: data})))


async def test_supported_requires_every_material_commitment() -> None:
    verification = await verifier(
        proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))
    ).verify(bundle(), clock=lambda: NOW)
    assert verification.state == SupportVerificationState.SUPPORTED
    assert verification.supported_portions == (MECHANISM.text, OUTCOME.text)
    assert verification.unsupported_portions == ()
    assert verification.relied_on_passage_ids == ("pass_1",)
    assert verification.verifier_prompt_version == "support-verifier-v1"
    assert verification.verifier_rubric_version == "support-rubric-v1"


async def test_partial_support_identifies_the_unsupported_remainder() -> None:
    verification = await verifier(
        proposal_data(("mech", "SUPPORTED"), ("outcome", "NOT_SUPPORTED"))
    ).verify(bundle(), clock=lambda: NOW)
    assert verification.state == SupportVerificationState.PARTIALLY_SUPPORTED
    assert verification.unsupported_portions == (OUTCOME.text,)
    assert verification.supported_portions == (MECHANISM.text,)


async def test_contradiction_dominates_and_remains_contradiction() -> None:
    verification = await verifier(
        proposal_data(("mech", "SUPPORTED"), ("outcome", "CONTRADICTED"))
    ).verify(bundle(), clock=lambda: NOW)
    assert verification.state == SupportVerificationState.CONTRADICTED
    assert any(OUTCOME.text in item for item in verification.contradictions)


async def test_insufficient_evidence_abstains_with_context_needed() -> None:
    verification = await verifier(
        proposal_data(
            ("mech", "SUPPORTED"),
            ("outcome", "INSUFFICIENT"),
            context_needed=("the sentence after the claim",),
        )
    ).verify(bundle(), clock=lambda: NOW)
    assert verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert verification.context_needed == ("the sentence after the claim",)
    derived = await verifier(
        proposal_data(("mech", "SUPPORTED"), ("outcome", "INSUFFICIENT"))
    ).verify(bundle(), clock=lambda: NOW)
    assert derived.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert derived.context_needed


async def test_nothing_supported_is_not_supported() -> None:
    verification = await verifier(
        proposal_data(("mech", "NOT_SUPPORTED"), ("outcome", "NOT_SUPPORTED"))
    ).verify(bundle(), clock=lambda: NOW)
    assert verification.state == SupportVerificationState.NOT_SUPPORTED
    assert verification.supported_portions == ()


async def test_invented_passages_are_rejected() -> None:
    data = proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))
    data["judgments"][0]["passage_ids"] = ["pass_invented"]  # type: ignore[index]
    with pytest.raises(VerificationValidationError):
        await verifier(data).verify(bundle(), clock=lambda: NOW)


async def test_missing_or_unknown_commitments_are_rejected() -> None:
    with pytest.raises(VerificationValidationError):
        await verifier(proposal_data(("mech", "SUPPORTED"))).verify(bundle(), clock=lambda: NOW)
    with pytest.raises(VerificationValidationError):
        await verifier(
            proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"), ("extra", "SUPPORTED"))
        ).verify(bundle(), clock=lambda: NOW)


async def test_verifier_context_is_only_the_blinded_input() -> None:
    provider = StubLLMProvider(
        {VERIFIER_TASK: proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))}
    )
    await IndependentSupportVerifier(SemanticRunner(provider)).verify(bundle(), clock=lambda: NOW)
    task, context = provider.calls[0]
    assert task == VERIFIER_TASK
    assert [block.label for block in context] == ["system_instruction", "verification_input"]
    payload = json.loads(context[1].text)
    assert set(payload) == {
        "schema_version",
        "contract_kind",
        "claim_id",
        "source_id",
        "source_version_id",
        "proposition_statement",
        "commitments",
        "claimed_dimensions",
        "relationship_claims",
        "passages",
        "blinded",
    }
    rendered = json.dumps(payload).casefold()
    for forbidden in (
        "quality",
        "tier",
        "rank",
        "provider_score",
        "novelty",
        "verdict",
        "precedent",
        "prosecutor",
        "defender",
        "report",
    ):
        assert forbidden not in rendered


async def test_tampered_passage_content_is_an_integrity_failure() -> None:
    original = bundle()
    passage = original.passages[0]
    tampered = type(passage).model_construct(
        **{**passage.model_dump(mode="python"), "content_hash": "0" * 64}
    )
    corrupted = SupportEvidenceBundle.model_construct(
        claim=original.claim, passages=(tampered,), limitations=()
    )
    with pytest.raises(PassageIntegrityError):
        check_passage_integrity(corrupted)
    with pytest.raises(PassageIntegrityError):
        await verifier(proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))).verify(
            corrupted, clock=lambda: NOW
        )


async def test_verification_identity_is_deterministic() -> None:
    data = proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))
    first = await verifier(data).verify(bundle(), clock=lambda: NOW)
    second = await verifier(data).verify(bundle(), clock=lambda: NOW)
    assert first.verification_id == second.verification_id
    assert first.verification_id.startswith("ver_")
    assert isinstance(VerifierProposal.model_validate(data), VerifierProposal)


def test_verification_contract_has_no_verdict_quality_or_rank_fields() -> None:
    import inspect

    from novelty_harness.evidence.verification.models import SupportVerification

    forbidden = {
        "verdict",
        "novelty",
        "quality_tier",
        "rank",
        "provider_score",
        "precedent",
        "prosecutor",
        "defender",
    }
    assert not set(SupportVerification.model_fields) & forbidden
    parameters = set(inspect.signature(IndependentSupportVerifier.verify).parameters)
    assert parameters == {"self", "bundle", "clock"}
