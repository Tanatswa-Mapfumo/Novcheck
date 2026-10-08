"""Independent meaning checks; deterministic validation certifies matching checks only."""

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import model_validator

from novelty_harness.adjudication.frozen import OverallFinding, TargetFinding
from novelty_harness.reporting.bundle import LanguageEnvelope, ReportInputBundle
from novelty_harness.reporting.claims import (
    ClaimBasisLink,
    ClaimExtractionProposal,
    ReportClaim,
    TextSpan,
    validate_claim_extraction,
)
from novelty_harness.reporting.drafts import (
    SectionAuthority,
    SectionDraft,
    project_section_authority,
)
from novelty_harness.reporting.firewall import (
    FirewallResult,
    check_report_recommendations,
    check_report_wording,
)
from novelty_harness.reporting.models import (
    AuthorityRef,
    Digest,
    NonBlank,
    QuestionId,
    ReportProposalError,
    ReportScoped,
)
from novelty_harness.reporting.obligations import CoverageObligation, ObligationSatisfaction
from novelty_harness.reporting.plan import QuestionPlan, ReportPlan
from novelty_harness.reporting.recommendations import (
    ValidationRequirement,
    minimum_validation_requirements,
)
from novelty_harness.reporting.uncertainty import UncertaintyItem, project_uncertainty
from novelty_harness.reporting.wording import ClaimWording, safe_claim_wording
from novelty_harness.runtime.tracing.hashing import canonical_hash

if TYPE_CHECKING:
    from novelty_harness.reporting.artifacts import ReportCompilationRecord


class VerificationDisposition(StrEnum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class VerifiedSection(ReportScoped):
    contract_kind: Literal["phase8-verified-section-v1"] = "phase8-verified-section-v1"
    draft: SectionDraft
    claims: tuple[ReportClaim, ...]
    basis_links: tuple[ClaimBasisLink, ...]
    verification_refs: tuple[NonBlank, ...]
    obligation_satisfaction: tuple[ObligationSatisfaction, ...]
    block_origins: dict[
        str, Literal["GENERATIVE_ACCEPTED", "GENERATIVE_REPAIRED", "DETERMINISTIC_FALLBACK"]
    ]
    source_artifact_refs: tuple[NonBlank, ...]


class ClaimVerificationContext(ReportScoped):
    contract_kind: Literal["phase8-claim-verification-context-v1"] = (
        "phase8-claim-verification-context-v1"
    )
    question_id: QuestionId
    bundle_digest: Digest
    authority_digest: Digest
    plan_id: NonBlank
    as_of: date
    question_plan: QuestionPlan
    draft: SectionDraft
    extraction: ClaimExtractionProposal
    authority: SectionAuthority
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    language_envelopes: tuple[LanguageEnvelope, ...]
    coverage_obligations: tuple[CoverageObligation, ...]
    uncertainty: tuple[UncertaintyItem, ...]
    eligible_basis_refs: tuple[AuthorityRef, ...]
    validation_requirements: tuple[ValidationRequirement, ...]
    claim_wording: tuple[ClaimWording, ...]


class ClaimVerification(ReportScoped):
    contract_kind: Literal["phase8-claim-verification-v1"] = "phase8-claim-verification-v1"
    claim_id: NonBlank
    text_digest: Digest
    basis_digest: Digest
    permission_digest: Digest
    disposition: VerificationDisposition
    unmet_qualification_refs: tuple[AuthorityRef, ...]
    reason_codes: tuple[NonBlank, ...]
    reason: NonBlank
    basis_refs: tuple[AuthorityRef, ...]


class BlockCompleteness(ReportScoped):
    contract_kind: Literal["phase8-block-completeness-v1"] = "phase8-block-completeness-v1"
    block_id: NonBlank
    text_digest: Digest
    claims_digest: Digest
    disposition: VerificationDisposition
    missing_assertion_spans: tuple[TextSpan, ...]
    unmet_obligation_ids: tuple[NonBlank, ...]
    unmet_qualification_refs: tuple[AuthorityRef, ...]
    reason_codes: tuple[NonBlank, ...]
    reason: NonBlank


class ClaimVerificationBatch(ReportScoped):
    contract_kind: Literal["phase8-claim-verification-batch-v1"] = (
        "phase8-claim-verification-batch-v1"
    )
    question_id: QuestionId
    context_digest: Digest
    draft_digest: Digest
    extraction_digest: Digest
    dispositions: tuple[ClaimVerification, ...]
    blocks: tuple[BlockCompleteness, ...]

    @property
    def accepted(self) -> bool:
        """Meaning disposition only; callers must first validate all input joins."""
        return (
            bool(self.blocks)
            and all(
                item.disposition == VerificationDisposition.SUPPORTED
                for item in (*self.dispositions, *self.blocks)
            )
            and not any(
                item.unmet_qualification_refs for item in (*self.dispositions, *self.blocks)
            )
            and not any(b.unmet_obligation_ids or b.missing_assertion_spans for b in self.blocks)
        )


class CompositionContext(ReportScoped):
    contract_kind: Literal["phase8-composition-context-v1"] = "phase8-composition-context-v1"
    bundle_digest: Digest
    drafts: tuple[SectionDraft, ...]
    extractions: tuple[ClaimExtractionProposal, ...]
    language_envelopes: tuple[LanguageEnvelope, ...]
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    coverage_obligations: tuple[CoverageObligation, ...]
    narrative_digest: Digest
    claims_digest: Digest
    permission_digest: Digest


class CompositionCheck(ReportScoped):
    contract_kind: Literal["phase8-composition-check-v1"] = "phase8-composition-check-v1"
    narrative_digest: Digest
    claims_digest: Digest
    permission_digest: Digest
    disposition: VerificationDisposition
    implicated_block_ids: tuple[NonBlank, ...]
    implicated_question_ids: tuple[QuestionId, ...]
    indeterminate_scope: bool
    reason_codes: tuple[NonBlank, ...]
    reason: NonBlank

    @property
    def accepted(self) -> bool:
        return self.disposition == VerificationDisposition.SUPPORTED

    @model_validator(mode="after")
    def localized_disposition(self) -> "CompositionCheck":
        if len(set(self.implicated_block_ids)) != len(self.implicated_block_ids) or len(
            set(self.implicated_question_ids)
        ) != len(self.implicated_question_ids):
            raise ValueError("composition localization duplicates an identity")
        if self.accepted and (
            self.indeterminate_scope or self.implicated_block_ids or self.implicated_question_ids
        ):
            raise ValueError("supported composition cannot contain implicated/indeterminate scope")
        if not self.accepted and not (
            self.indeterminate_scope or self.implicated_block_ids or self.implicated_question_ids
        ):
            raise ValueError(
                "rejected/unresolved composition requires explicit or indeterminate scope"
            )
        if not self.accepted and not self.reason_codes:
            raise ValueError("non-supported composition requires reason codes")
        return self


def build_claim_verification_context(
    draft: SectionDraft,
    extraction: ClaimExtractionProposal,
    bundle: ReportInputBundle,
    plan: ReportPlan,
) -> ClaimVerificationContext:
    draft = SectionDraft.model_validate(draft.model_dump(mode="json"))
    extraction = validate_claim_extraction(draft, extraction)
    plan = ReportPlan.model_validate(plan.model_dump(mode="json"))
    if (draft.scope, draft.compilation_id, plan.scope, plan.bundle_digest) != (
        bundle.scope,
        plan.compilation_id,
        bundle.scope,
        bundle.bundle_digest,
    ) or plan.plan_id != "p8plan_" + canonical_hash(
        plan.model_dump(mode="json", exclude={"plan_id"})
    ):
        raise ReportProposalError("verification plan/draft/bundle scope or identity differs")
    question = next((q for q in plan.questions if q.question_id == draft.question_id), None)
    if question is None:
        raise ReportProposalError("verification question is absent from plan")
    # Complete public comparison closure, including contradictory/residual records;
    # writer hints cannot remove evidence from an independent verifier's view.
    return ClaimVerificationContext(
        scope=bundle.scope,
        compilation_id=plan.compilation_id,
        question_id=draft.question_id,
        bundle_digest=bundle.bundle_digest,
        authority_digest=canonical_hash(
            [d.model_dump(mode="json") for d in bundle.dependency_manifest]
        ),
        plan_id=plan.plan_id,
        as_of=bundle.as_of,
        question_plan=question,
        draft=draft,
        extraction=extraction,
        authority=project_section_authority(bundle, bundle.eligible_comparisons),
        target_findings=bundle.target_findings,
        overall_finding=bundle.overall_finding,
        language_envelopes=bundle.language_envelopes,
        coverage_obligations=tuple(
            o for o in bundle.coverage_obligations if draft.question_id in o.question_ids
        ),
        uncertainty=project_uncertainty(bundle),
        eligible_basis_refs=tuple(
            d.authority_ref for d in bundle.dependency_manifest if d.authority_ref is not None
        ),
        validation_requirements=check_report_recommendations(
            minimum_validation_requirements(bundle), bundle
        ),
        claim_wording=check_report_wording(safe_claim_wording(bundle), bundle),
    )


def validate_verification_batch(
    context: ClaimVerificationContext, batch: ClaimVerificationBatch, firewall: FirewallResult
) -> ClaimVerificationBatch:
    try:
        context = ClaimVerificationContext.model_validate(context.model_dump(mode="json"))
        batch = ClaimVerificationBatch.model_validate(batch.model_dump(mode="json"))
        firewall = FirewallResult.model_validate(firewall.model_dump(mode="json"))
    except ValueError as error:
        raise ReportProposalError("verification contracts fail serialized validation") from error
    scope = (context.scope, context.compilation_id)
    if (batch.scope, batch.compilation_id) != scope or batch.question_id != context.question_id:
        raise ReportProposalError("verification result scope or question differs")
    if (batch.context_digest, batch.draft_digest, batch.extraction_digest) != (
        canonical_hash(context),
        canonical_hash(context.draft),
        canonical_hash(context.extraction),
    ):
        raise ReportProposalError("verification checks a different actual context/text/extraction")
    permission_digest = canonical_hash(
        [e.model_dump(mode="json") for e in context.language_envelopes]
    )
    if (firewall.scope, firewall.compilation_id) != scope or (
        firewall.question_id,
        firewall.draft_digest,
        firewall.extraction_digest,
        firewall.claims_digest,
        firewall.basis_digest,
        firewall.permission_digest,
        firewall.authority_digest,
        firewall.plan_id,
    ) != (
        context.question_id,
        batch.draft_digest,
        batch.extraction_digest,
        canonical_hash([c.model_dump(mode="json") for c in context.extraction.claims]),
        canonical_hash([link.model_dump(mode="json") for link in context.extraction.basis_links]),
        permission_digest,
        context.authority_digest,
        context.plan_id,
    ):
        raise ReportProposalError("verification has a stale/unrelated firewall receipt")
    if not firewall.accepted:
        raise ReportProposalError("semantic support cannot override deterministic rejection")
    claims = {c.claim_id: c for c in context.extraction.claims}
    blocks = {b.block_id: b for b in context.draft.blocks}
    if len(batch.dispositions) != len(claims) or {v.claim_id for v in batch.dispositions} != set(
        claims
    ):
        raise ReportProposalError("every extracted claim requires exactly one disposition")
    if len(batch.blocks) != len(blocks) or {b.block_id for b in batch.blocks} != set(blocks):
        raise ReportProposalError("every public block requires exactly one completeness check")
    refs = set(context.eligible_basis_refs)
    obligations = {o.obligation_id for o in context.coverage_obligations}
    for result in (*batch.dispositions, *batch.blocks):
        if (result.scope, result.compilation_id) != scope:
            raise ReportProposalError("nested verification scope differs")
        if any(ref not in refs for ref in result.unmet_qualification_refs):
            raise ReportProposalError("verification invents a qualification or basis")
        if len(set(result.unmet_qualification_refs)) != len(result.unmet_qualification_refs):
            raise ReportProposalError("verification duplicates an unmet qualification")
        if result.disposition != VerificationDisposition.SUPPORTED and not result.reason_codes:
            raise ReportProposalError("non-supported result requires explicit reason codes")
        if (
            result.disposition == VerificationDisposition.SUPPORTED
            and result.unmet_qualification_refs
        ):
            raise ReportProposalError("supported text cannot have unmet qualifications")
    for result in batch.dispositions:
        claim = claims[result.claim_id]
        links = tuple(
            link for link in context.extraction.basis_links if link.claim_id == claim.claim_id
        )
        expected_refs = tuple(dict.fromkeys(link.authority_ref for link in links))
        if (result.text_digest, result.basis_digest, result.permission_digest) != (
            canonical_hash(
                {
                    "block_text": blocks[claim.block_id].text,
                    "spans": [s.model_dump(mode="json") for s in claim.spans],
                }
            ),
            canonical_hash([link.model_dump(mode="json") for link in links]),
            permission_digest,
        ) or result.basis_refs != expected_refs:
            raise ReportProposalError("claim support check text/basis/permission differs")
        if any(ref not in refs for ref in result.basis_refs):
            raise ReportProposalError("claim verification basis is not admitted")
    for result in batch.blocks:
        block = blocks[result.block_id]
        block_claims = tuple(c for c in context.extraction.claims if c.block_id == block.block_id)
        if (result.text_digest, result.claims_digest) != (
            canonical_hash(block.text),
            canonical_hash([c.model_dump(mode="json") for c in block_claims]),
        ):
            raise ReportProposalError(
                "block completeness checks a different actual text/extraction"
            )
        if (
            len(set(result.unmet_obligation_ids)) != len(result.unmet_obligation_ids)
            or not set(result.unmet_obligation_ids) <= obligations
        ):
            raise ReportProposalError("block check invents or duplicates an obligation")
        if any(span.end > len(block.text) for span in result.missing_assertion_spans):
            raise ReportProposalError("missing assertion lies outside actual public text")
        if result.disposition == VerificationDisposition.SUPPORTED and (
            result.unmet_obligation_ids or result.missing_assertion_spans
        ):
            raise ReportProposalError("supported block cannot omit material assertions/limitations")
    return batch


def section_extraction(section: VerifiedSection) -> ClaimExtractionProposal:
    """Mechanical public-text projection, without a semantic completeness certificate."""
    from novelty_harness.reporting.claims import BlockClaimAccount

    return ClaimExtractionProposal(
        scope=section.scope,
        compilation_id=section.compilation_id,
        question_id=section.draft.question_id,
        draft_digest=canonical_hash(section.draft),
        claims=section.claims,
        basis_links=section.basis_links,
        block_accounts=tuple(
            BlockClaimAccount(
                block_id=b.block_id,
                block_text_digest=canonical_hash(b.text),
                claim_ids=tuple(c.claim_id for c in section.claims if c.block_id == b.block_id),
                non_material_reason=(
                    "No proposed material claim supplied; independent completeness remains required"
                    if not any(c.block_id == b.block_id for c in section.claims)
                    else None
                ),
            )
            for b in section.draft.blocks
        ),
    )


def build_composition_context(
    sections: tuple[VerifiedSection, ...],
    bundle: ReportInputBundle,
    compilation: "ReportCompilationRecord",
) -> CompositionContext:
    from novelty_harness.reporting.obligations import check_report_coverage

    if (compilation.scope, compilation.bundle_digest) != (bundle.scope, bundle.bundle_digest):
        raise ReportProposalError("composition compilation differs from the exact bundle")
    check_report_coverage(sections, bundle)
    drafts = tuple(s.draft for s in sections)
    extractions = tuple(section_extraction(s) for s in sections)
    return CompositionContext(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        bundle_digest=bundle.bundle_digest,
        drafts=drafts,
        extractions=extractions,
        language_envelopes=bundle.language_envelopes,
        target_findings=bundle.target_findings,
        overall_finding=bundle.overall_finding,
        coverage_obligations=bundle.coverage_obligations,
        narrative_digest=canonical_hash([d.model_dump(mode="json") for d in drafts]),
        claims_digest=canonical_hash([e.model_dump(mode="json") for e in extractions]),
        permission_digest=canonical_hash(
            [e.model_dump(mode="json") for e in bundle.language_envelopes]
        ),
    )


def validate_composition_check(
    context: CompositionContext, check: CompositionCheck
) -> CompositionCheck:
    try:
        context = CompositionContext.model_validate_json(context.model_dump_json(), strict=True)
        check = CompositionCheck.model_validate_json(check.model_dump_json(), strict=True)
    except ValueError as error:
        raise ReportProposalError("composition contracts fail serialized validation") from error
    if (
        check.scope,
        check.compilation_id,
        check.narrative_digest,
        check.claims_digest,
        check.permission_digest,
    ) != (
        context.scope,
        context.compilation_id,
        context.narrative_digest,
        context.claims_digest,
        context.permission_digest,
    ):
        raise ReportProposalError(
            "composition result checks a different narrative/claims/permissions"
        )
    if (
        context.narrative_digest
        != canonical_hash([d.model_dump(mode="json") for d in context.drafts])
        or context.claims_digest
        != canonical_hash([e.model_dump(mode="json") for e in context.extractions])
        or context.permission_digest
        != canonical_hash([e.model_dump(mode="json") for e in context.language_envelopes])
    ):
        raise ReportProposalError("composition context digests differ from actual public text")
    if tuple(d.question_id for d in context.drafts) != tuple(range(1, 10)):
        raise ReportProposalError("composition requires ordered Q1–Q9")
    if any(
        b not in {b.block_id for d in context.drafts for b in d.blocks}
        for b in check.implicated_block_ids
    ):
        raise ReportProposalError("composition refers to an unseen block")
    return check
