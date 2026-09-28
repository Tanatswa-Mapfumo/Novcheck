"""Deterministic support-verification gates.

The verifier proposal is untrusted: every commitment must be judged exactly
once, every cited passage must exist in the blinded input, and the overall
state is aggregated deterministically. The LLM cannot declare SUPPORTED while
skipping commitments, invent passages, or average a contradiction away.
"""

from collections.abc import Callable
from datetime import datetime

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.verification.models import (
    BlindedPassage,
    BlindedVerificationInput,
    CommitmentStateRecord,
    SupportVerification,
)
from novelty_harness.evidence.verification.prompts import (
    VERIFIER_PROMPT_VERSION,
    VERIFIER_RUBRIC_VERSION,
    VerifierProposal,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

VERIFICATION_COMPONENT_PROVENANCE = "independent_support_verifier"


class VerificationValidationError(ValueError):
    """The untrusted verifier proposal violated deterministic rules."""


class PassageIntegrityError(ValueError):
    """Stored passage content no longer matches its recorded hash/structure."""


def check_passage_integrity(bundle: SupportEvidenceBundle) -> None:
    """Re-validate exact content before any judgment is trusted."""

    claim = bundle.claim
    if tuple(passage.passage_id for passage in bundle.passages) != claim.passage_ids:
        raise PassageIntegrityError("Bundle passages do not match the claim citations")
    seen: set[str] = set()
    for passage in bundle.passages:
        if passage.passage_id in seen:
            raise PassageIntegrityError("Duplicate passages in a support bundle")
        seen.add(passage.passage_id)
        if passage.source_id != claim.source_id:
            raise PassageIntegrityError("Support claim cites another source")
        if passage.source_version_id != claim.source_version_id:
            raise PassageIntegrityError("Support claim cites another source version")
        if passage.content_hash != text_hash(passage.text):
            raise PassageIntegrityError("Passage content hash does not match its text")
        if not passage.text.strip():
            raise PassageIntegrityError("Passage text is blank")


def build_blinded_input(bundle: SupportEvidenceBundle) -> BlindedVerificationInput:
    """Build the only input surface the verifier may see."""

    claim = bundle.claim
    return BlindedVerificationInput(
        claim_id=claim.claim_id,
        source_id=claim.source_id,
        source_version_id=claim.source_version_id,
        proposition_statement=claim.proposition_statement,
        commitments=claim.commitments,
        claimed_dimensions=claim.claimed_dimensions,
        relationship_claims=claim.relationship_claims,
        passages=tuple(
            BlindedPassage(
                passage_id=passage.passage_id,
                text=passage.text,
                locator=passage.locator.kind.value,
            )
            for passage in bundle.passages
        ),
    )


def validate_judgments(blinded: BlindedVerificationInput, proposal: VerifierProposal) -> None:
    expected = {commitment.commitment_id for commitment in blinded.commitments}
    judged = {judgment.commitment_id for judgment in proposal.judgments}
    if judged != expected:
        missing = sorted(expected - judged)
        unknown = sorted(judged - expected)
        raise VerificationValidationError(
            f"Verifier must judge every material commitment exactly once; "
            f"missing={missing} unknown={unknown}"
        )
    known_passages = {passage.passage_id for passage in blinded.passages}
    for judgment in proposal.judgments:
        invented = sorted(set(judgment.passage_ids) - known_passages)
        if invented:
            raise VerificationValidationError(
                f"Verifier cited passages that were not supplied: {invented}"
            )


def aggregate_verification(
    *,
    bundle: SupportEvidenceBundle,
    blinded: BlindedVerificationInput,
    proposal: VerifierProposal,
    clock: Callable[[], datetime] = utc_now,
) -> SupportVerification:
    """Deterministically aggregate commitment judgments into one state."""

    validate_judgments(blinded, proposal)
    commitment_text = {commitment.commitment_id: commitment for commitment in blinded.commitments}
    states = {judgment.commitment_id: judgment.state for judgment in proposal.judgments}
    records = tuple(
        CommitmentStateRecord(
            commitment_id=judgment.commitment_id,
            dimension=commitment_text[judgment.commitment_id].dimension,
            state=judgment.state,
            rationale=judgment.rationale,
            passage_ids=judgment.passage_ids,
        )
        for judgment in sorted(proposal.judgments, key=lambda item: item.commitment_id)
    )

    contradictions = tuple(
        f"{commitment_text[judgment.commitment_id].text}: {judgment.rationale}"
        for judgment in proposal.judgments
        if judgment.state == "CONTRADICTED"
    )
    supported = tuple(
        commitment_text[judgment.commitment_id].text
        for judgment in proposal.judgments
        if judgment.state == "SUPPORTED"
    )
    unsupported = tuple(
        commitment_text[judgment.commitment_id].text
        for judgment in proposal.judgments
        if judgment.state == "NOT_SUPPORTED"
    )
    context_needed = tuple(proposal.context_needed) or tuple(
        f"More context needed for: {commitment_text[judgment.commitment_id].text}"
        for judgment in proposal.judgments
        if judgment.state == "INSUFFICIENT"
    )

    if contradictions:
        state = SupportVerificationState.CONTRADICTED
    elif "INSUFFICIENT" in states.values():
        state = SupportVerificationState.INSUFFICIENT_CONTEXT
    elif all(item == "SUPPORTED" for item in states.values()):
        state = SupportVerificationState.SUPPORTED
    elif not supported:
        state = SupportVerificationState.NOT_SUPPORTED
    else:
        state = SupportVerificationState.PARTIALLY_SUPPORTED

    relied_on = tuple(
        dict.fromkeys(
            passage_id for judgment in proposal.judgments for passage_id in judgment.passage_ids
        )
    )
    identity = canonical_hash(
        {
            "claim_id": blinded.claim_id,
            "state": state.value,
            "commitments": [record.model_dump(mode="json") for record in records],
            "context_needed": list(context_needed),
            "relied_on_passage_ids": list(relied_on),
            "prompt_version": VERIFIER_PROMPT_VERSION,
            "rubric_version": VERIFIER_RUBRIC_VERSION,
        }
    )
    return SupportVerification(
        verification_id="ver_" + identity,
        claim_id=blinded.claim_id,
        mapping_id=bundle.claim.mapping_id,
        source_id=blinded.source_id,
        source_version_id=blinded.source_version_id,
        mcu_id=bundle.claim.mcu_id,
        state=state,
        commitment_states=records,
        supported_portions=supported,
        unsupported_portions=unsupported,
        contradictions=contradictions,
        context_needed=context_needed,
        relied_on_passage_ids=relied_on,
        context_expansions=0,
        verifier_prompt_version=VERIFIER_PROMPT_VERSION,
        verifier_rubric_version=VERIFIER_RUBRIC_VERSION,
        observed_at=clock(),
        provenance=ArtifactProvenance(
            kind="implemented",
            component=VERIFICATION_COMPONENT_PROVENANCE,
            detail="Blinded commitment-level entailment verification; no precedent or quality.",
        ),
    )


def contradiction_blocks_stage(
    verification: SupportVerification,
    *,
    integrity_failure: bool = False,
) -> bool:
    """Contradictions are final unless a passage-integrity failure was detected."""

    return verification.state == SupportVerificationState.CONTRADICTED and not integrity_failure


def relation_requires_verified_support(relation: PrecedentState) -> bool:
    """Phase 6 gate: precedent states that require fully supported evidence."""

    return relation in {
        PrecedentState.DIRECT_PRECEDENT,
        PrecedentState.STRONG_PARTIAL_PRECEDENT,
        PrecedentState.COMPONENT_PRECEDENT_ONLY,
    }


__all__ = [
    "PassageIntegrityError",
    "VERIFICATION_COMPONENT_PROVENANCE",
    "VerificationValidationError",
    "aggregate_verification",
    "build_blinded_input",
    "check_passage_integrity",
    "contradiction_blocks_stage",
    "relation_requires_verified_support",
    "validate_judgments",
]
