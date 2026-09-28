"""Deterministic support-verification gates.

The verifier proposal is untrusted: every commitment must be judged exactly
once, every cited passage must exist in the blinded input, and the overall
state is aggregated deterministically. The LLM cannot declare SUPPORTED while
skipping commitments, invent passages, or average a contradiction away.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Literal

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import (
    PrecedentState,
    SupportVerificationState,
)
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.mapping.models import EvidenceProposition, SourceMCUMapping
from novelty_harness.evidence.normalization.models import SourceRecord
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.quality.models import EvidenceQualityAssessment
from novelty_harness.evidence.verification.models import (
    BlindedPassage,
    BlindedVerificationInput,
    ChronologyAssessment,
    CommitmentStateRecord,
    EdgeEligibility,
    SupportVerification,
    VerifiedEvidenceEdge,
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


#: Precedent relations that require decisive, fully supported evidence.
SUPPORT_REQUIRING_RELATIONS = frozenset({PrecedentState.DIRECT_PRECEDENT})

#: Precedent relations that require at least verified partial support.
PARTIAL_SUPPORT_RELATIONS = frozenset(
    {
        PrecedentState.DIRECT_PRECEDENT,
        PrecedentState.STRONG_PARTIAL_PRECEDENT,
        PrecedentState.COMPONENT_PRECEDENT_ONLY,
        PrecedentState.ANALOGOUS_PRECEDENT,
    }
)


class EdgeEligibilityError(ValueError):
    """A verified edge violated chronology, support or identity eligibility."""


#: Public-disclosure date fields; creation/priority dates never establish
#: disclosure (ADR-020) so they cannot make a source pre-cutoff.
PUBLIC_DISCLOSURE_FIELDS = (
    "publication_date",
    "first_public_version",
    "first_release_date",
    "patent_publication_date",
    "product_launch_date",
    "archive_capture_date",
)


def assess_chronology(source: SourceRecord, *, as_of: date) -> ChronologyAssessment:
    """Compute the public-disclosure chronology gate for one source."""

    candidates = [
        (getattr(source.dates, field), field)
        for field in PUBLIC_DISCLOSURE_FIELDS
        if getattr(source.dates, field) is not None
    ]
    if not candidates:
        return ChronologyAssessment(
            as_of=as_of,
            state="UNCERTAIN",
            rationale=("No complete public-disclosure date; chronology stays uncertain",),
        )
    decisive_date, field = min(candidates)
    state: Literal["PREDATES_CUTOFF", "POST_CUTOFF"] = (
        "PREDATES_CUTOFF" if decisive_date <= as_of else "POST_CUTOFF"
    )
    rationale = (
        f"Earliest public disclosure is {field}={decisive_date.isoformat()}",
        "Post-cutoff evidence cannot negate historical novelty"
        if state == "POST_CUTOFF"
        else "Earliest public disclosure is at or before the assessment cutoff",
    )
    return ChronologyAssessment(
        as_of=as_of,
        state=state,
        decisive_date_field=field,
        decisive_date=decisive_date,
        rationale=rationale,
    )


def check_relation_eligible(
    relation: PrecedentState,
    verification: SupportVerification,
    *,
    decisive: bool,
) -> None:
    """Reject precedent relations that the verification state cannot support."""

    if relation in SUPPORT_REQUIRING_RELATIONS and not decisive:
        raise EdgeEligibilityError(
            f"{relation.value} requires fully supported, pre-cutoff evidence"
        )
    if (
        relation in PARTIAL_SUPPORT_RELATIONS
        and verification.state == SupportVerificationState.CONTRADICTED
    ):
        raise EdgeEligibilityError(f"{relation.value} cannot be assigned to contradicted evidence")
    if (
        relation == PrecedentState.CONTRADICTORY_EVIDENCE
        and verification.state != SupportVerificationState.CONTRADICTED
    ):
        raise EdgeEligibilityError("CONTRADICTORY_EVIDENCE requires a verified contradiction")


def build_verified_evidence_edge(
    *,
    mapping: SourceMCUMapping,
    verification: SupportVerification,
    proposition: EvidenceProposition,
    source: SourceRecord,
    as_of: date,
    observed_at: datetime,
    quality: EvidenceQualityAssessment | None = None,
    relation: PrecedentState | None = None,
    provenance: ArtifactProvenance | None = None,
) -> VerifiedEvidenceEdge:
    """Attach chronology and quality to a verification without changing it."""

    if (
        verification.mapping_id != mapping.mapping_id
        or verification.source_id != mapping.source_id
        or verification.source_id != source.source_id
        or verification.mcu_id != proposition.mcu_id
        or mapping.mcu_id != proposition.mcu_id
    ):
        raise EdgeEligibilityError("Verification, mapping and source identities must agree")
    if mapping.source_version_id != verification.source_version_id:
        raise EdgeEligibilityError("Verification and mapping versions must agree")
    if quality is not None and quality.source_id != source.source_id:
        raise EdgeEligibilityError("Quality assessment belongs to another source")

    chronology = assess_chronology(source, as_of=as_of)
    decisive = (
        verification.state == SupportVerificationState.SUPPORTED
        and chronology.state == "PREDATES_CUTOFF"
    )
    reasons: list[str] = []
    if verification.state != SupportVerificationState.SUPPORTED:
        reasons.append(f"Verification state is {verification.state.value}")
    if chronology.state == "POST_CUTOFF":
        reasons.append("Source is post-cutoff and cannot be decisive precedent")
    elif chronology.state == "UNCERTAIN":
        reasons.append("Source chronology is uncertain and cannot be decisive")
    if relation is not None:
        check_relation_eligible(relation, verification, decisive=decisive)

    passage_ids = verification.relied_on_passage_ids or mapping.mapped_passage_ids()
    if not passage_ids:
        raise EdgeEligibilityError("A verified edge requires at least one exact passage")

    edge_id = "edge_" + canonical_hash(
        {
            "source_id": source.source_id,
            "source_version_id": verification.source_version_id,
            "mcu_id": proposition.mcu_id,
            "mapping_id": mapping.mapping_id,
            "verification_id": verification.verification_id,
            "passage_ids": list(passage_ids),
            "relation": relation.value if relation else None,
        }
    )
    return VerifiedEvidenceEdge(
        edge_id=edge_id,
        source_id=source.source_id,
        source_version_id=verification.source_version_id,
        mcu_id=proposition.mcu_id,
        proposition_id=proposition.proposition_id,
        proposition=proposition.statement,
        mapping_id=mapping.mapping_id,
        verification_id=verification.verification_id,
        passage_ids=passage_ids,
        comparison=mapping.aggregate_comparison(),
        support_state=verification.state,
        decisive=decisive,
        chronology=chronology,
        eligibility=EdgeEligibility(
            decisive=decisive, chronology=chronology, reasons=tuple(reasons)
        ),
        relation=relation,
        quality_tier=quality.tier if quality else None,
        quality_assessment_id=None if quality is None else quality.source_id,
        mapper_prompt_version=mapping.mapper_prompt_version,
        verifier_prompt_version=verification.verifier_prompt_version,
        verifier_rubric_version=verification.verifier_rubric_version,
        observed_at=observed_at,
        provenance=provenance
        or ArtifactProvenance(
            kind="implemented",
            component="verified_edge_eligibility",
            detail="Chronology and quality attached without altering verification state.",
        ),
    )
