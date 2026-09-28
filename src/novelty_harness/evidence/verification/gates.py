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
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.mapping.models import EvidenceProposition, SourceMCUMapping
from novelty_harness.evidence.normalization.models import SourceRecord, SourceVersionRecord
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.quality.models import EvidenceQualityAssessment
from novelty_harness.evidence.verification.integrity import (
    SemanticIntegrityError,
    VerifiedEvidenceChain,
    validate_semantic_chain,
)
from novelty_harness.evidence.verification.models import (
    BlindedPassage,
    BlindedVerificationInput,
    ChronologyAssessment,
    CitedDisclosure,
    CommitmentStateRecord,
    EdgeEligibility,
    SupportVerification,
    VerifiedEvidenceEdge,
    derive_support_state,
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
        if judgment.state in EVIDENTIAL_JUDGMENT_STATES and not judgment.passage_ids:
            raise VerificationValidationError(
                f"Evidential judgment for {judgment.commitment_id} must cite at least "
                "one supplied passage"
            )


def aggregate_verification(
    *,
    bundle: SupportEvidenceBundle,
    blinded: BlindedVerificationInput,
    proposal: VerifierProposal,
    clock: Callable[[], datetime] = utc_now,
) -> SupportVerification:
    """Deterministically aggregate commitment judgments into one state."""

    claim = bundle.claim
    if (
        blinded.claim_id != claim.claim_id
        or blinded.source_id != claim.source_id
        or blinded.source_version_id != claim.source_version_id
        or tuple(passage.passage_id for passage in blinded.passages) != claim.passage_ids
    ):
        raise VerificationValidationError("Blinded input does not match the support claim")
    validate_judgments(blinded, proposal)
    commitment_text = {commitment.commitment_id: commitment for commitment in blinded.commitments}
    records = tuple(
        CommitmentStateRecord(
            commitment_id=judgment.commitment_id,
            dimension=commitment_text[judgment.commitment_id].dimension,
            state=judgment.state,
            rationale=judgment.rationale,
            passage_ids=judgment.passage_ids,
            supported_subset=judgment.supported_subset,
            unsupported_remainder=judgment.unsupported_remainder,
        )
        for judgment in sorted(proposal.judgments, key=lambda item: item.commitment_id)
    )

    contradictions = tuple(
        f"{commitment_text[judgment.commitment_id].text}: {judgment.rationale}"
        for judgment in proposal.judgments
        if judgment.state == "CONTRADICTED"
    )
    supported = tuple(
        portion
        for judgment in proposal.judgments
        if judgment.state in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
        for portion in (
            (commitment_text[judgment.commitment_id].text,)
            if judgment.state == "SUPPORTED"
            else (
                f"{commitment_text[judgment.commitment_id].text} "
                f"(supported subset: {judgment.supported_subset})",
            )
        )
    )
    unsupported = tuple(
        portion
        for judgment in proposal.judgments
        if judgment.state in {"NOT_SUPPORTED", "PARTIALLY_SUPPORTED"}
        for portion in (
            (commitment_text[judgment.commitment_id].text,)
            if judgment.state == "NOT_SUPPORTED"
            else (
                f"{commitment_text[judgment.commitment_id].text} "
                f"(unsupported remainder: {judgment.unsupported_remainder})",
            )
        )
    )
    context_needed = tuple(proposal.context_needed) or tuple(
        f"More context needed for: {commitment_text[judgment.commitment_id].text}"
        for judgment in proposal.judgments
        if judgment.state == "INSUFFICIENT"
    )

    state = derive_support_state(records)

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


#: Judgment states that assert something about the evidence and therefore
#: require at least one cited passage (F05).
EVIDENTIAL_JUDGMENT_STATES = frozenset({"SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED"})


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


def assess_cited_disclosure(
    source: SourceRecord,
    *,
    as_of: date,
    version: SourceVersionRecord | None = None,
) -> CitedDisclosure:
    """Bind chronology to an owned cited disclosure and source-wide first date.

    A cited version's public disclosure governs that version alone. Parent or
    sibling source dates cannot make a revision earlier or erase an eligible
    preprint. A contradictory first-public assertion stays uncertain.
    """

    if version is not None and version.source_id != source.source_id:
        raise EdgeEligibilityError("Cited version owner does not match source")
    candidates = [
        (getattr(source.dates, field), field)
        for field in PUBLIC_DISCLOSURE_FIELDS
        if getattr(source.dates, field) is not None
    ]
    if version is not None:
        public_date, field = version.published_date, "version_published_date"
    elif candidates:
        public_date, field = min(candidates)
    else:
        public_date, field = None, None
    first_public = source.dates.first_public_version
    conflict = first_public is not None and public_date is not None and public_date < first_public
    if conflict:
        chronology = ChronologyAssessment(
            as_of=as_of,
            state="UNCERTAIN",
            rationale=(
                "Cited disclosure predates conflicting source-wide first-public-version metadata",
            ),
        )
    elif public_date is None:
        chronology = ChronologyAssessment(
            as_of=as_of,
            state="UNCERTAIN",
            decisive_date_field=field,
            rationale=("Cited disclosure has no complete public date",),
        )
    else:
        state: Literal["PREDATES_CUTOFF", "POST_CUTOFF"] = (
            "PREDATES_CUTOFF" if public_date <= as_of else "POST_CUTOFF"
        )
        chronology = ChronologyAssessment(
            as_of=as_of,
            state=state,
            decisive_date_field=field,
            decisive_date=public_date,
            rationale=(
                f"Cited public disclosure is {field}={public_date.isoformat()}",
                "Post-cutoff evidence cannot negate historical novelty"
                if state == "POST_CUTOFF"
                else "Cited disclosure is at or before the assessment cutoff",
            ),
        )
    return CitedDisclosure(
        source_id=source.source_id,
        source_version_id=version.version_id if version is not None else None,
        as_of=as_of,
        cited_public_date=public_date,
        source_first_public_version=first_public,
        chronology=chronology,
    )


def assess_chronology(
    source: SourceRecord,
    *,
    as_of: date,
    version: SourceVersionRecord | None = None,
) -> ChronologyAssessment:
    """Compatibility view of the authoritative cited disclosure."""

    return assess_cited_disclosure(source, as_of=as_of, version=version).chronology


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
    bundle: SupportEvidenceBundle,
    as_of: date,
    observed_at: datetime,
    assessment_id: AssessmentId | None = None,
    version: SourceVersionRecord | None = None,
    context_passages: tuple[PassageRecord, ...] = (),
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
        or mapping.proposition_id != proposition.proposition_id
    ):
        raise EdgeEligibilityError("Verification, mapping and source identities must agree")
    if mapping.source_version_id != verification.source_version_id:
        raise EdgeEligibilityError("Verification and mapping versions must agree")
    if mapping.source_version_id is not None and version is None:
        raise EdgeEligibilityError("Cited source version object is required")
    if mapping.source_version_id is None and version is not None:
        raise EdgeEligibilityError("Unversioned evidence cannot cite a version object")
    if version is not None and version.version_id != verification.source_version_id:
        raise EdgeEligibilityError("Cited version does not match the verified version")
    if version is not None and version.source_id != source.source_id:
        raise EdgeEligibilityError("Cited version owner does not match the source")
    try:
        validate_semantic_chain(
            source=source,
            version=version,
            proposition=proposition,
            mapping=mapping,
            bundle=bundle,
            verification=verification,
            context_passages=context_passages,
        )
    except SemanticIntegrityError as error:
        raise EdgeEligibilityError(str(error)) from error
    if quality is not None and quality.source_id != source.source_id:
        raise EdgeEligibilityError("Quality assessment belongs to another source")

    disclosure = assess_cited_disclosure(source, as_of=as_of, version=version)
    chronology = disclosure.chronology
    decisive = (
        verification.state == SupportVerificationState.SUPPORTED
        and chronology.state == "PREDATES_CUTOFF"
        and verification.context_completeness == "COMPLETE"
    )
    reasons: list[str] = []
    if verification.state != SupportVerificationState.SUPPORTED:
        reasons.append(f"Verification state is {verification.state.value}")
    if verification.context_completeness != "COMPLETE":
        reasons.append(
            f"Verification context is {verification.context_completeness} and cannot be decisive"
        )
    if chronology.state == "POST_CUTOFF":
        reasons.append("Source is post-cutoff and cannot be decisive precedent")
    elif chronology.state == "UNCERTAIN":
        reasons.append("Source chronology is uncertain and cannot be decisive")
    if relation is not None:
        check_relation_eligible(relation, verification, decisive=decisive)

    support_bearing = verification.state in {
        SupportVerificationState.SUPPORTED,
        SupportVerificationState.PARTIALLY_SUPPORTED,
        SupportVerificationState.CONTRADICTED,
    }
    if support_bearing:
        passage_ids = verification.relied_on_passage_ids
        if not passage_ids:
            raise EdgeEligibilityError(
                "Support-bearing evidence must use verifier-cited passages only"
            )
    else:
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
            "claim_id": bundle.claim.claim_id,
            "claim_digest": canonical_hash(bundle.claim),
            "assessment_id": assessment_id or bundle.claim.claim_id,
            "passage_ids": list(passage_ids),
            "relation": relation.value if relation else None,
            "as_of": as_of.isoformat(),
            "chronology_state": chronology.state,
            "disclosure": disclosure.model_dump(mode="json"),
            "context_completeness": verification.context_completeness,
            "chronology_date": chronology.decisive_date.isoformat()
            if chronology.decisive_date is not None
            else None,
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
        claim_id=bundle.claim.claim_id,
        claim_digest=canonical_hash(bundle.claim),
        assessment_id=assessment_id,
        verification_id=verification.verification_id,
        passage_ids=passage_ids,
        comparison=mapping.aggregate_comparison(),
        support_state=verification.state,
        decisive=decisive,
        disclosure=disclosure,
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


def validate_verified_chain(chain: VerifiedEvidenceChain) -> tuple[PassageRecord, ...]:
    """Reconstruct eligibility from persisted inputs, rejecting self-declared edges."""

    cited = validate_semantic_chain(
        source=chain.source,
        version=chain.version,
        proposition=chain.proposition,
        mapping=chain.mapping,
        bundle=chain.bundle,
        verification=chain.verification,
        context_passages=chain.context_passages,
    )
    if chain.edge.assessment_id != chain.assessment_id:
        raise SemanticIntegrityError("Verified edge belongs to another assessment")
    rebuilt = build_verified_evidence_edge(
        mapping=chain.mapping,
        verification=chain.verification,
        proposition=chain.proposition,
        source=chain.source,
        bundle=chain.bundle,
        version=chain.version,
        context_passages=chain.context_passages,
        assessment_id=chain.assessment_id,
        as_of=chain.edge.chronology.as_of,
        observed_at=chain.edge.observed_at,
        relation=chain.edge.relation,
    )
    for field in (
        "edge_id",
        "source_id",
        "source_version_id",
        "mcu_id",
        "proposition_id",
        "proposition",
        "mapping_id",
        "claim_id",
        "claim_digest",
        "verification_id",
        "passage_ids",
        "comparison",
        "support_state",
        "decisive",
        "disclosure",
        "chronology",
        "eligibility",
        "relation",
        "mapper_prompt_version",
        "verifier_prompt_version",
        "verifier_rubric_version",
    ):
        if getattr(chain.edge, field) != getattr(rebuilt, field):
            raise SemanticIntegrityError(f"Verified edge {field} differs from resolved chain")
    return cited
