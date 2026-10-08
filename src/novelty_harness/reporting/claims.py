"""Independent extraction proposals with exact public text accounting."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from novelty_harness.adjudication.frozen import OverallFinding, TargetFinding
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.reporting.bundle import LanguageEnvelope
from novelty_harness.reporting.drafts import SectionAuthority, SectionContext, SectionDraft
from novelty_harness.reporting.models import (
    AuthorityRef,
    Digest,
    NonBlank,
    QuestionId,
    ReportClaimCategory,
    ReportContract,
    ReportProposalError,
    ReportScoped,
    validate_authority_refs,
)
from novelty_harness.reporting.obligations import CoverageObligation
from novelty_harness.reporting.uncertainty import UncertaintyItem
from novelty_harness.runtime.tracing.hashing import canonical_hash


class ClaimUse(StrEnum):
    ASSERTION = "ASSERTION"
    ATTRIBUTED_INPUT_CLAIM = "ATTRIBUTED_INPUT_CLAIM"
    RECOMMENDATION = "RECOMMENDATION"
    DISALLOWED_WORDING_EXAMPLE = "DISALLOWED_WORDING_EXAMPLE"


class TextSpan(ReportContract):
    """Half-open offsets in Unicode code points of the actual stored block."""

    contract_kind: Literal["phase8-text-span-v1"] = "phase8-text-span-v1"
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def nonempty(self) -> "TextSpan":
        if self.end <= self.start:
            raise ValueError("claim span must be nonempty")
        return self


class ClaimTarget(ReportContract):
    contract_kind: Literal["phase8-claim-target-v1"] = "phase8-claim-target-v1"
    target: TargetRef
    claim_scope: NonBlank


class ReportClaim(ReportScoped):
    contract_kind: Literal["phase8-report-claim-v1"] = "phase8-report-claim-v1"
    claim_id: NonBlank
    block_id: NonBlank
    block_text_digest: Digest
    spans: tuple[TextSpan, ...] = Field(min_length=1)
    normalized_assertion: NonBlank
    category: ReportClaimCategory
    use: ClaimUse
    target_scopes: tuple[ClaimTarget, ...] = ()
    basis_candidates: tuple[AuthorityRef, ...] = ()
    citation_candidates: tuple[AuthorityRef, ...] = ()
    required_qualification_refs: tuple[AuthorityRef, ...] = ()


class ClaimBasisLink(ReportScoped):
    contract_kind: Literal["phase8-claim-basis-link-v1"] = "phase8-claim-basis-link-v1"
    claim_id: NonBlank
    authority_ref: AuthorityRef
    proposition: NonBlank
    use: ClaimUse


class BlockClaimAccount(ReportContract):
    contract_kind: Literal["phase8-block-claim-account-v1"] = "phase8-block-claim-account-v1"
    block_id: NonBlank
    block_text_digest: Digest
    claim_ids: tuple[NonBlank, ...]
    non_material_reason: NonBlank | None = None


class ClaimExtractionProposal(ReportScoped):
    contract_kind: Literal["phase8-claim-extraction-proposal-v1"] = (
        "phase8-claim-extraction-proposal-v1"
    )
    question_id: QuestionId
    draft_digest: Digest
    claims: tuple[ReportClaim, ...]
    basis_links: tuple[ClaimBasisLink, ...]
    block_accounts: tuple[BlockClaimAccount, ...]

    @model_validator(mode="after")
    def canonical_claim_addresses(self) -> "ClaimExtractionProposal":
        """Normalize local output labels before the runtime hashes validated output.

        This assigns addresses only; it changes no proposed meaning or basis and
        creates no completeness/support result. Raw response hashes retain labels.
        """
        labels = [c.claim_id for c in self.claims]
        if len(set(labels)) != len(labels):
            raise ValueError("duplicate extraction claim label")
        addresses = {c.claim_id: report_claim_id(c) for c in self.claims}
        if len(set(addresses.values())) != len(addresses):
            raise ValueError("duplicate semantic extraction claim")
        if any(link.claim_id not in addresses for link in self.basis_links) or any(
            identifier not in addresses for a in self.block_accounts for identifier in a.claim_ids
        ):
            raise ValueError("extraction links or accounts reference an unknown claim")
        object.__setattr__(
            self,
            "claims",
            tuple(c.model_copy(update={"claim_id": addresses[c.claim_id]}) for c in self.claims),
        )
        object.__setattr__(
            self,
            "basis_links",
            tuple(
                link.model_copy(update={"claim_id": addresses[link.claim_id]})
                for link in self.basis_links
            ),
        )
        object.__setattr__(
            self,
            "block_accounts",
            tuple(
                account.model_copy(
                    update={"claim_ids": tuple(addresses[c] for c in account.claim_ids)}
                )
                for account in self.block_accounts
            ),
        )
        return self


class ClaimExtractionContext(ReportScoped):
    contract_kind: Literal["phase8-claim-extraction-context-v1"] = (
        "phase8-claim-extraction-context-v1"
    )
    question_id: QuestionId
    draft: SectionDraft
    draft_digest: Digest
    authority: SectionAuthority
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    language_envelopes: tuple[LanguageEnvelope, ...]
    coverage_obligations: tuple[CoverageObligation, ...]
    uncertainty: tuple[UncertaintyItem, ...]
    eligible_basis_refs: tuple[AuthorityRef, ...]
    eligible_citation_refs: tuple[AuthorityRef, ...]
    allowed_categories: tuple[ReportClaimCategory, ...] = tuple(ReportClaimCategory)


def report_claim_id(claim: ReportClaim) -> str:
    return "p8claim_" + canonical_hash(claim.model_dump(mode="json", exclude={"claim_id"}))


def build_claim_extraction_context(
    draft: SectionDraft, context: SectionContext
) -> ClaimExtractionContext:
    draft = SectionDraft.model_validate(draft.model_dump(mode="json"))
    if (draft.scope, draft.compilation_id, draft.question_id) != (
        context.scope,
        context.compilation_id,
        context.question_id,
    ):
        raise ReportProposalError("extraction draft belongs to another section context")
    return ClaimExtractionContext(
        scope=draft.scope,
        compilation_id=draft.compilation_id,
        question_id=draft.question_id,
        draft=draft,
        draft_digest=canonical_hash(draft),
        authority=context.authority,
        target_findings=context.target_findings,
        overall_finding=context.overall_finding,
        language_envelopes=context.language_envelopes,
        coverage_obligations=context.coverage_obligations,
        uncertainty=context.uncertainty,
        eligible_basis_refs=context.selected_basis_refs,
        eligible_citation_refs=context.eligible_citation_refs,
    )


def validate_claim_extraction(
    draft: SectionDraft, proposal: ClaimExtractionProposal
) -> ClaimExtractionProposal:
    """Prove text/record joins; independent semantics must still check every block."""
    try:
        draft = SectionDraft.model_validate(draft.model_dump(mode="json"))
        proposal = ClaimExtractionProposal.model_validate(proposal.model_dump(mode="json"))
        if (
            proposal.scope,
            proposal.compilation_id,
            proposal.question_id,
            proposal.draft_digest,
        ) != (draft.scope, draft.compilation_id, draft.question_id, canonical_hash(draft)):
            raise ReportProposalError("extraction scope, question or actual draft text differs")
        blocks = {b.block_id: b for b in draft.blocks}
        if len(blocks) != len(draft.blocks):
            raise ReportProposalError("draft contains duplicate public block identities")
        if len({a.block_id for a in proposal.block_accounts}) != len(proposal.block_accounts) or {
            a.block_id for a in proposal.block_accounts
        } != set(blocks):
            raise ReportProposalError("every actual public block must be accounted exactly once")
        claims = {c.claim_id: c for c in proposal.claims}
        for claim in proposal.claims:
            block = blocks.get(claim.block_id)
            if (
                (claim.scope, claim.compilation_id) != (draft.scope, draft.compilation_id)
                or block is None
                or claim.block_text_digest != canonical_hash(block.text)
            ):
                raise ReportProposalError("claim scope, block or actual text digest differs")
            previous_end = -1
            for span in claim.spans:
                if span.start < previous_end or span.end > len(block.text):
                    raise ReportProposalError(
                        "claim spans overlap, are unordered or exceed Unicode text"
                    )
                previous_end = span.end
            if len({(t.target.kind, t.target.id) for t in claim.target_scopes}) != len(
                claim.target_scopes
            ):
                raise ReportProposalError("duplicate native claim target")
            for refs in (
                claim.basis_candidates,
                claim.citation_candidates,
                claim.required_qualification_refs,
            ):
                validate_authority_refs(refs, draft.scope)
        accounted: set[str] = set()
        for account in proposal.block_accounts:
            if account.block_text_digest != canonical_hash(blocks[account.block_id].text):
                raise ReportProposalError("block account has stale actual text digest")
            expected = {c.claim_id for c in claims.values() if c.block_id == account.block_id}
            if (
                len(set(account.claim_ids)) != len(account.claim_ids)
                or set(account.claim_ids) != expected
                or accounted & set(account.claim_ids)
            ):
                raise ReportProposalError("account assigns duplicate, foreign or missing claims")
            if not account.claim_ids and account.non_material_reason is None:
                raise ReportProposalError("empty block accounting requires an untrusted reason")
            accounted.update(account.claim_ids)
        if accounted != set(claims):
            raise ReportProposalError("extraction leaves an actual claim unaccounted")
        link_keys: set[str] = set()
        for link in proposal.basis_links:
            claim = claims[link.claim_id]
            if (link.scope, link.compilation_id) != (
                draft.scope,
                draft.compilation_id,
            ) or link.authority_ref not in claim.basis_candidates:
                raise ReportProposalError("basis link scope or proposed candidate differs")
            key = canonical_hash(link)
            if key in link_keys:
                raise ReportProposalError("duplicate basis link")
            link_keys.add(key)
        return proposal
    except ValueError as exc:
        if isinstance(exc, ReportProposalError):
            raise
        raise ReportProposalError("extraction violates strict text accounting") from exc
