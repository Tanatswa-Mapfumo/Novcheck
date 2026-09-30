"""Deterministic identity and citation joins for a Phase 6 evidence chain."""

from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.mapping.models import EvidenceProposition, SourceMCUMapping
from novelty_harness.evidence.normalization.models import SourceRecord, SourceVersionRecord
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.verification.models import (
    ChronologyAssessment,
    CommitmentStateRecord,
    ContextCompletenessState,
    SupportVerification,
    VerifiedEvidenceEdge,
)


class SemanticIntegrityError(ValueError):
    """Artifacts are individually shaped but do not describe one comparison."""


class VerifiedEvidenceChain(ContractModel):
    """The immutable claim, verifier and passage proof behind one verified edge."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["verified-evidence-chain-v1"] = "verified-evidence-chain-v1"

    assessment_id: AssessmentId
    source: SourceRecord
    version: SourceVersionRecord | None
    proposition: EvidenceProposition
    mapping: SourceMCUMapping
    bundle: SupportEvidenceBundle
    verification: SupportVerification
    context_passages: tuple[PassageRecord, ...] = ()
    edge: VerifiedEvidenceEdge


class VerifiedComparison(ContractModel):
    """Validated chain comparison; persisted content authority is checked on upsert."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["verified-comparison-v1"] = "verified-comparison-v1"
    chain: VerifiedEvidenceChain
    assessment_id: AssessmentId
    source_id: str
    source_version_id: str | None
    mcu_id: str
    proposition_id: str
    mapping_id: str
    claim_id: str
    verification_id: str
    passage_ids: tuple[str, ...]
    chronology: ChronologyAssessment
    context_completeness: ContextCompletenessState
    verified_semantic_facts: tuple[CommitmentStateRecord, ...]

    @model_validator(mode="after")
    def authoritative_chain(self) -> "VerifiedComparison":
        from novelty_harness.evidence.verification.gates import validate_verified_chain

        cited = validate_verified_chain(self.chain)
        chain = self.chain
        expected = (
            chain.assessment_id,
            chain.source.source_id,
            chain.version.version_id if chain.version else None,
            chain.proposition.mcu_id,
            chain.proposition.proposition_id,
            chain.mapping.mapping_id,
            chain.bundle.claim.claim_id,
            chain.verification.verification_id,
            tuple(passage.passage_id for passage in cited),
            chain.edge.chronology,
            chain.verification.context_completeness,
            chain.verification.commitment_states,
        )
        actual = (
            self.assessment_id,
            self.source_id,
            self.source_version_id,
            self.mcu_id,
            self.proposition_id,
            self.mapping_id,
            self.claim_id,
            self.verification_id,
            self.passage_ids,
            self.chronology,
            self.context_completeness,
            self.verified_semantic_facts,
        )
        if actual != expected:
            raise SemanticIntegrityError("Verified comparison identities differ from its chain")
        return self


def verified_comparison(chain: VerifiedEvidenceChain) -> VerifiedComparison:
    """Produce the only classification-ready artifact from a resolved chain."""

    return VerifiedComparison(
        chain=chain,
        assessment_id=chain.assessment_id,
        source_id=chain.source.source_id,
        source_version_id=chain.version.version_id if chain.version else None,
        mcu_id=chain.proposition.mcu_id,
        proposition_id=chain.proposition.proposition_id,
        mapping_id=chain.mapping.mapping_id,
        claim_id=chain.bundle.claim.claim_id,
        verification_id=chain.verification.verification_id,
        passage_ids=chain.edge.passage_ids,
        chronology=chain.edge.chronology,
        context_completeness=chain.verification.context_completeness,
        verified_semantic_facts=chain.verification.commitment_states,
    )


def canonical_verifier_citations(verification: SupportVerification) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            passage_id
            for record in verification.commitment_states
            for passage_id in record.passage_ids
        )
    )


def validate_semantic_chain(
    *,
    source: SourceRecord,
    version: SourceVersionRecord | None,
    proposition: EvidenceProposition,
    mapping: SourceMCUMapping,
    bundle: SupportEvidenceBundle,
    verification: SupportVerification,
    context_passages: Sequence[PassageRecord] = (),
) -> tuple[PassageRecord, ...]:
    """Resolve every verification citation to an exact same-version passage."""

    source = SourceRecord.model_validate(source.model_dump(mode="json"))
    version = (
        SourceVersionRecord.model_validate(version.model_dump(mode="json"))
        if version is not None
        else None
    )
    proposition = EvidenceProposition.model_validate(proposition.model_dump(mode="json"))
    mapping = SourceMCUMapping.model_validate(mapping.model_dump(mode="json"))
    bundle = SupportEvidenceBundle.model_validate(bundle.model_dump(mode="json"))
    verification = SupportVerification.model_validate(verification.model_dump(mode="json"))
    claim = bundle.claim
    source_id = source.source_id
    version_id = version.version_id if version is not None else None
    if version is not None and version.source_id != source_id:
        raise SemanticIntegrityError("Cited source version owner does not match source")
    if version_id != mapping.source_version_id or version_id != verification.source_version_id:
        raise SemanticIntegrityError("Cited source version does not match mapping/verification")
    if (
        mapping.source_id != source_id
        or verification.source_id != source_id
        or claim.source_id != source_id
    ):
        raise SemanticIntegrityError("Source identity differs across evidence artifacts")
    if (
        mapping.mcu_id != proposition.mcu_id
        or verification.mcu_id != proposition.mcu_id
        or claim.mcu_id != proposition.mcu_id
    ):
        raise SemanticIntegrityError("MCU identity differs across evidence artifacts")
    if (
        mapping.proposition_id != proposition.proposition_id
        or claim.proposition_id != proposition.proposition_id
    ):
        raise SemanticIntegrityError("Claim proposition identity differs from mapping")
    if (
        claim.proposition_statement != proposition.statement
        or claim.commitments != proposition.commitments
    ):
        raise SemanticIntegrityError("Claim does not carry the exact proposition commitments")
    if claim.mapping_id != mapping.mapping_id or verification.mapping_id != mapping.mapping_id:
        raise SemanticIntegrityError("Mapping identity differs across evidence artifacts")
    if claim.claim_id != verification.claim_id:
        raise SemanticIntegrityError("Verification belongs to another support claim")
    if claim.source_version_id != version_id:
        raise SemanticIntegrityError("Claim belongs to another source version")

    expected = {item.commitment_id: item for item in proposition.commitments}
    if set(verification.material_commitment_ids) != set(expected):
        raise SemanticIntegrityError("Verification material commitments differ from claim")
    judged = {item.commitment_id: item for item in verification.commitment_states}
    if len(judged) != len(verification.commitment_states) or set(judged) != set(expected):
        raise SemanticIntegrityError("Verification does not judge every exact claim commitment")
    if any(record.dimension != expected[identity].dimension for identity, record in judged.items()):
        raise SemanticIntegrityError("Verification commitment dimension differs from claim")

    canonical = canonical_verifier_citations(verification)
    if verification.relied_on_passage_ids != canonical:
        raise SemanticIntegrityError("relied_on_passage_ids differ from commitment citations")
    for record in verification.commitment_states:
        if (
            record.state in {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED"}
            and not record.passage_ids
        ):
            raise SemanticIntegrityError("Support-bearing judgment lacks verifier-cited passages")

    if tuple(item.passage_id for item in bundle.passages) != claim.passage_ids:
        raise SemanticIntegrityError("Claim passage identities differ from bundle")
    if not set(mapping.mapped_passage_ids()) <= set(claim.passage_ids):
        raise SemanticIntegrityError("Mapping cites a passage outside its support claim")
    available: dict[str, PassageRecord] = {}
    for passage in (*bundle.passages, *context_passages):
        passage = PassageRecord.model_validate(passage.model_dump(mode="json"))
        if passage.passage_id in available and available[passage.passage_id] != passage:
            raise SemanticIntegrityError("One passage ID has conflicting contents")
        if passage.source_id != source_id or passage.source_version_id != version_id:
            raise SemanticIntegrityError("Cited passage belongs to another source/version")
        if passage.content_hash != text_hash(passage.text):
            raise SemanticIntegrityError("Cited passage content hash does not match text")
        attestation = passage.attestation
        if attestation is None:
            raise SemanticIntegrityError(
                "Cited passage lacks immutable source-content provenance attestation"
            )
        authoritative_digest = version.content_hash if version is not None else source.content_hash
        if (
            authoritative_digest is None
            or attestation.parent_content_digest != authoritative_digest
        ):
            raise SemanticIntegrityError(
                "Cited passage parent digest conflicts with source/version hash"
            )
        if (
            attestation.parent.source_id != source_id
            or attestation.parent.source_version_id != version_id
        ):
            raise SemanticIntegrityError(
                "Cited passage provenance belongs to another source/version"
            )
        available[passage.passage_id] = passage
    missing = set(canonical) - set(available)
    if missing:
        raise SemanticIntegrityError(f"Verifier cited unavailable passages: {sorted(missing)}")
    return tuple(available[identity] for identity in canonical)
