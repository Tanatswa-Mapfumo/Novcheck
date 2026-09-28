"""Phase 6 support-verification contracts.

The blinded verification input contains only what the independent verifier is
allowed to see. Nothing here carries a novelty verdict, precedent proposal,
prosecutor/defender role, quality tier, retrieval rank, provider score, user
novelty claim or report wording.
"""

from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import EvidenceTier, PrecedentState, SupportVerificationState
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import (
    MappingId,
    MCUId,
    PassageId,
    PropositionId,
    SourceId,
    SourceVersionId,
    SupportClaimId,
    VerificationId,
)
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DirectedRelationship,
    MappingComparison,
    PropositionCommitment,
)
from novelty_harness.evidence.passages.models import PassageRecord

CommitmentState = Literal["SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "INSUFFICIENT"]
ChronologyState = Literal["PREDATES_CUTOFF", "POST_CUTOFF", "UNCERTAIN"]


class PassageSupportClaim(ContractModel):
    """A mapping turned into an exact-passage support question."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["passage-support-claim-v1"] = "passage-support-claim-v1"

    claim_id: SupportClaimId
    mapping_id: MappingId
    source_id: SourceId
    source_version_id: SourceVersionId | None
    mcu_id: MCUId
    proposition_id: PropositionId
    proposition_statement: NonBlankText
    commitments: tuple[PropositionCommitment, ...] = Field(min_length=1)
    claimed_dimensions: tuple[ComparisonDimension, ...] = ()
    relationship_claims: tuple[DirectedRelationship, ...] = ()
    passage_ids: tuple[PassageId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_commitments_and_passages(self) -> Self:
        identities = [commitment.commitment_id for commitment in self.commitments]
        if len(set(identities)) != len(identities):
            raise ValueError("Claim commitments must be unique")
        if len(set(self.passage_ids)) != len(self.passage_ids):
            raise ValueError("Claim passages must be unique")
        return self


class BlindedPassage(ContractModel):
    """Only the exact passage content the verifier may inspect."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["blinded-passage-v1"] = "blinded-passage-v1"

    passage_id: PassageId
    text: NonBlankText
    locator: NonBlankText


class BlindedVerificationInput(ContractModel):
    """The complete verifier input surface. Extra fields are rejected.

    Allowed: proposition, claimed commitments/dimension mapping, exact passage
    text/locator, minimal source/version identity for passage integrity.
    Forbidden: novelty verdict, proposed precedent class, prosecutor/defender
    role, quality tier, search rank, provider score, user novelty claim and
    report wording.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["blinded-verification-input-v1"] = "blinded-verification-input-v1"

    claim_id: SupportClaimId
    source_id: SourceId
    source_version_id: SourceVersionId | None
    proposition_statement: NonBlankText
    commitments: tuple[PropositionCommitment, ...] = Field(min_length=1)
    claimed_dimensions: tuple[ComparisonDimension, ...] = ()
    relationship_claims: tuple[DirectedRelationship, ...] = ()
    passages: tuple[BlindedPassage, ...] = Field(min_length=1)
    blinded: Literal[True] = True


class CommitmentStateRecord(ContractModel):
    """One commitment's deterministic record after verifier aggregation."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["commitment-state-v1"] = "commitment-state-v1"

    commitment_id: NonBlankText
    dimension: ComparisonDimension
    state: CommitmentState
    rationale: NonBlankText
    passage_ids: tuple[PassageId, ...] = ()


class SupportVerification(ContractModel):
    """Verified support state for one claim, with its unsupported remainder."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["support-verification-v1"] = "support-verification-v1"

    verification_id: VerificationId
    claim_id: SupportClaimId
    mapping_id: MappingId
    source_id: SourceId
    source_version_id: SourceVersionId | None
    mcu_id: MCUId
    state: SupportVerificationState
    commitment_states: tuple[CommitmentStateRecord, ...] = Field(min_length=1)
    supported_portions: tuple[NonBlankText, ...] = ()
    unsupported_portions: tuple[NonBlankText, ...] = ()
    contradictions: tuple[NonBlankText, ...] = ()
    context_needed: tuple[NonBlankText, ...] = ()
    relied_on_passage_ids: tuple[PassageId, ...] = ()
    context_expansions: int = Field(default=0, ge=0)
    verifier_prompt_version: NonBlankText
    verifier_rubric_version: NonBlankText
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def state_matches_payload(self) -> Self:
        states = {record.state for record in self.commitment_states}
        if self.state == SupportVerificationState.SUPPORTED:
            if states != {"SUPPORTED"}:
                raise ValueError("SUPPORTED requires every material commitment supported")
            if self.unsupported_portions or self.contradictions:
                raise ValueError("SUPPORTED cannot carry unsupported or contradictory portions")
        elif self.state == SupportVerificationState.PARTIALLY_SUPPORTED:
            if not self.unsupported_portions:
                raise ValueError("PARTIALLY_SUPPORTED must identify the unsupported remainder")
            if "SUPPORTED" not in states:
                raise ValueError("PARTIALLY_SUPPORTED requires at least one supported commitment")
        elif self.state == SupportVerificationState.NOT_SUPPORTED:
            if self.supported_portions:
                raise ValueError("NOT_SUPPORTED cannot claim supported portions")
        elif self.state == SupportVerificationState.CONTRADICTED:
            if not self.contradictions:
                raise ValueError("CONTRADICTED must record the contradiction")
        elif self.state == SupportVerificationState.INSUFFICIENT_CONTEXT:
            if not self.context_needed:
                raise ValueError("INSUFFICIENT_CONTEXT must state the context that is needed")
        return self


class ContextExpansion(ContractModel):
    """One bounded, same-source context window attempt."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["context-expansion-v1"] = "context-expansion-v1"

    origin_passage_id: PassageId
    source_id: SourceId
    source_version_id: SourceVersionId | None
    attempt: int = Field(ge=1)
    available: bool
    window_passage: PassageRecord | None = None
    blocked_reason: NonBlankText | None = None
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def availability_matches_payload(self) -> Self:
        if self.available:
            if self.window_passage is None:
                raise ValueError("Available expansion requires a window passage")
            if self.blocked_reason is not None:
                raise ValueError("Available expansion cannot be blocked")
            if self.window_passage.source_id != self.source_id:
                raise ValueError("Context expansion cannot cross sources")
            if self.window_passage.source_version_id != self.source_version_id:
                raise ValueError("Context expansion cannot cross source versions")
        elif self.window_passage is not None or self.blocked_reason is None:
            raise ValueError("Blocked expansion requires a reason and no window passage")
        return self


class ChronologyAssessment(ContractModel):
    """Deterministic public-disclosure chronology for one source."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["chronology-assessment-v1"] = "chronology-assessment-v1"

    as_of: date
    state: ChronologyState
    decisive_date_field: NonBlankText | None = None
    decisive_date: date | None = None
    rationale: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def state_matches_dates(self) -> Self:
        if self.state == "PREDATES_CUTOFF":
            if self.decisive_date is None or self.decisive_date > self.as_of:
                raise ValueError("PREDATES_CUTOFF requires an eligible public date")
        elif self.state == "POST_CUTOFF":
            if self.decisive_date is None or self.decisive_date <= self.as_of:
                raise ValueError("POST_CUTOFF requires a later public date")
        return self


class EdgeEligibility(ContractModel):
    """Decisiveness gate for one verified evidence edge."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["edge-eligibility-v1"] = "edge-eligibility-v1"

    decisive: bool
    chronology: ChronologyAssessment
    reasons: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def decisive_requires_chronology(self) -> Self:
        if self.decisive and self.chronology.state != "PREDATES_CUTOFF":
            raise ValueError("Decisive evidence requires a verified pre-cutoff public date")
        return self


class VerifiedEvidenceEdge(ContractModel):
    """Passage-grounded, independently verified and locally classified edge.

    This is the Phase 6 unit consumed by Phase 7 adjudication. It stores no
    final novelty verdict.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["verified-evidence-edge-v1"] = "verified-evidence-edge-v1"

    edge_id: NonBlankText
    source_id: SourceId
    source_version_id: SourceVersionId | None
    mcu_id: MCUId
    proposition_id: PropositionId
    proposition: NonBlankText
    mapping_id: MappingId
    verification_id: VerificationId
    passage_ids: tuple[PassageId, ...] = Field(min_length=1)
    comparison: MappingComparison
    support_state: SupportVerificationState
    decisive: bool
    chronology: ChronologyAssessment
    eligibility: EdgeEligibility
    relation: PrecedentState | None = None
    quality_tier: EvidenceTier | None = None
    quality_assessment_id: NonBlankText | None = None
    mapper_prompt_version: NonBlankText
    verifier_prompt_version: NonBlankText
    verifier_rubric_version: NonBlankText
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def eligibility_matches_state(self) -> Self:
        if self.decisive and self.support_state != SupportVerificationState.SUPPORTED:
            raise ValueError("Only fully SUPPORTED evidence can be decisive")
        if self.eligibility.decisive != self.decisive:
            raise ValueError("Edge eligibility must match the decisive flag")
        if self.eligibility.chronology != self.chronology:
            raise ValueError("Edge eligibility must carry the same chronology")
        if self.decisive and self.chronology.state != "PREDATES_CUTOFF":
            raise ValueError("Post-cutoff or uncertain evidence cannot be decisive")
        return self
