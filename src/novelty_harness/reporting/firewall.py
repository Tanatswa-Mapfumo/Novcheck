"""Deterministic claim joins; a passing receipt is not semantic support."""

import re
from typing import Literal

from pydantic import model_validator

from novelty_harness.adjudication.frozen import LanguagePermissionClass
from novelty_harness.domain.enums import PrecedentState, VerdictState
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.claims import (
    ClaimExtractionProposal,
    ClaimUse,
    ReportClaim,
    validate_claim_extraction,
)
from novelty_harness.reporting.drafts import SectionDraft, contains_unsafe_public_text
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    Digest,
    NonBlank,
    QuestionId,
    ReportClaimCategory,
    ReportScoped,
    authority_dependency_id,
)
from novelty_harness.reporting.plan import ReportPlan, allowed_question_categories
from novelty_harness.reporting.recommendations import (
    ValidationRequirement,
    validate_validation_requirement,
)
from novelty_harness.reporting.wording import ClaimWording, validate_claim_wording
from novelty_harness.runtime.tracing.hashing import canonical_hash


class FirewallViolation(ReportScoped):
    contract_kind: Literal["phase8-firewall-violation-v1"] = "phase8-firewall-violation-v1"
    claim_id: NonBlank | None = None
    block_id: NonBlank | None = None
    reason_code: NonBlank
    reason: NonBlank
    authority_refs: tuple[AuthorityRef, ...] = ()


class FirewallResult(ReportScoped):
    """Only deterministic checks passed; extraction/completeness/entailment remain independent."""

    contract_kind: Literal["phase8-firewall-result-v1"] = "phase8-firewall-result-v1"
    question_id: QuestionId
    draft_digest: Digest
    extraction_digest: Digest
    claims_digest: Digest
    basis_digest: Digest
    permission_digest: Digest
    authority_digest: Digest
    plan_id: NonBlank
    method_version: Literal["p8-semantic-firewall-v1"] = "p8-semantic-firewall-v1"
    accepted: bool
    violations: tuple[FirewallViolation, ...]

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(v.reason_code for v in self.violations))

    @model_validator(mode="after")
    def mechanical_disposition(self) -> "FirewallResult":
        if self.accepted != (not self.violations):
            raise ValueError("firewall receipt cannot override a deterministic rejection")
        if any(
            (v.scope, v.compilation_id) != (self.scope, self.compilation_id)
            for v in self.violations
        ):
            raise ValueError("firewall violation scope differs")
        return self


_UNIVERSAL_ABSENCE = re.compile(
    r"UNIVERSAL_ABSENCE|no prior art exists|nothing like this anywhere|never existed anywhere",
    re.IGNORECASE,
)
_SOURCE_STITCH = re.compile(
    r"SOURCE_STITCHING|sources stitched|(?:sources|references) together establish one direct",
    re.IGNORECASE,
)
_CERTAINTY = re.compile(r"CERTAIN_NOVELTY|certainly novel|definitely novel", re.IGNORECASE)
_CONTENT_KINDS = {
    AuthorityKind.PASSAGE,
    AuthorityKind.COMPARISON,
    AuthorityKind.GRAPH_RELATION,
    AuthorityKind.COMMIT,
}


def check_report_recommendations(
    proposals: tuple[ValidationRequirement, ...], bundle: ReportInputBundle
) -> tuple[ValidationRequirement, ...]:
    """Bind prospective records; embedded premises still need semantic verification."""
    from novelty_harness.reporting.models import ReportProposalError

    checked = tuple(validate_validation_requirement(p, bundle) for p in proposals)
    if len({p.requirement_id for p in checked}) != len(checked):
        raise ReportProposalError("duplicate prospective requirement")
    return checked


def check_report_wording(
    proposals: tuple[ClaimWording, ...], bundle: ReportInputBundle
) -> tuple[ClaimWording, ...]:
    """Bind target permissions, without accepting arbitrary wording text."""
    from novelty_harness.reporting.models import ReportProposalError

    checked = tuple(validate_claim_wording(p, bundle) for p in proposals)
    if len({canonical_hash(p) for p in checked}) != len(checked):
        raise ReportProposalError("duplicate wording record")
    return checked


def _content_closure_ids(claim: ReportClaim, bundle: ReportInputBundle) -> set[str]:
    """Follow content authority, never source metadata alone, to committed comparisons."""
    content = {r.native_id for r in claim.basis_candidates if r.kind in _CONTENT_KINDS}
    result = set(content)
    for comparison in bundle.eligible_comparisons:
        ids = {
            comparison.commit_id,
            comparison.comparison.classification.classification_id,
            comparison.comparison.comparison.chain.edge.edge_id,
            *comparison.graph_edge_ids,
            *(p.passage.passage_id for p in comparison.cited_passages),
        }
        if content & ids:
            result.update(ids)
    return result


def check_report_claims(
    draft: SectionDraft,
    extraction: ClaimExtractionProposal,
    bundle: ReportInputBundle,
    plan: ReportPlan,
) -> FirewallResult:
    violations: list[FirewallViolation] = []

    def reject(
        code: str,
        reason: str,
        claim: ReportClaim | None = None,
        block_id: str | None = None,
        refs: tuple[AuthorityRef, ...] = (),
    ) -> None:
        violations.append(
            FirewallViolation(
                scope=bundle.scope,
                compilation_id=plan.compilation_id,
                claim_id=claim.claim_id if claim is not None else None,
                block_id=claim.block_id if claim is not None else block_id,
                reason_code=code,
                reason=reason,
                authority_refs=refs,
            )
        )

    def receipt() -> FirewallResult:
        return FirewallResult(
            scope=bundle.scope,
            compilation_id=plan.compilation_id,
            question_id=draft.question_id,
            draft_digest=canonical_hash(draft),
            extraction_digest=canonical_hash(extraction),
            claims_digest=canonical_hash([c.model_dump(mode="json") for c in extraction.claims]),
            basis_digest=canonical_hash(
                [link.model_dump(mode="json") for link in extraction.basis_links]
            ),
            permission_digest=canonical_hash(
                [e.model_dump(mode="json") for e in bundle.language_envelopes]
            ),
            authority_digest=canonical_hash(
                [d.model_dump(mode="json") for d in bundle.dependency_manifest]
            ),
            plan_id=plan.plan_id,
            accepted=not violations,
            violations=tuple(violations),
        )

    if (draft.scope, draft.compilation_id) != (bundle.scope, plan.compilation_id):
        reject("REPORT_SCOPE_MISMATCH", "public draft belongs to another authority scope")
    if (plan.scope, plan.bundle_digest) != (
        bundle.scope,
        bundle.bundle_digest,
    ) or plan.plan_id != "p8plan_" + canonical_hash(
        plan.model_dump(mode="json", exclude={"plan_id"})
    ):
        reject("PLAN_SCOPE_MISMATCH", "plan scope, bundle or realized plan identity differs")
    try:
        extraction = validate_claim_extraction(draft, extraction)
    except ValueError:
        reject("INVALID_EXTRACTION", "independent extraction does not account exact actual text")
        return receipt()
    question = next((q for q in plan.questions if q.question_id == draft.question_id), None)
    if question is None:
        reject("PLAN_SCOPE_MISMATCH", "question has no validated plan")
        return receipt()
    catalog = {
        authority_dependency_id(d.authority_ref): d.authority_ref
        for d in bundle.dependency_manifest
        if d.authority_ref is not None
    }
    eligible = set(
        (*question.evidence_refs, *question.adjudication_refs, *question.required_limitation_refs)
    )
    # Passage and commitment selection brings its admitted full comparison closure.
    selected_content = {r.native_id for r in eligible if r.kind in _CONTENT_KINDS}
    for comparison in bundle.eligible_comparisons:
        ids = {
            comparison.commit_id,
            comparison.comparison.classification.classification_id,
            *comparison.graph_edge_ids,
            *(p.passage.passage_id for p in comparison.cited_passages),
        }
        if selected_content & ids:
            eligible.update(r for r in catalog.values() if r.native_id in ids)
    obligations = set(question.obligation_ids)
    linked = {identifier for block in draft.blocks for identifier in block.obligation_ids}
    if obligations - linked:
        reject(
            "MISSING_OBLIGATION_LINK", "mandatory question obligations lack proposed public homes"
        )
    if linked - obligations:
        reject("FOREIGN_OBLIGATION_LINK", "public block proposes foreign coverage obligations")
    blocks = {b.block_id: b for b in draft.blocks}
    for block in draft.blocks:
        if contains_unsafe_public_text(block.text):
            reject(
                "UNSAFE_PUBLIC_TEXT",
                "public prose contains raw markup or a free URL",
                block_id=block.block_id,
            )
        for token in block.citation_tokens:
            if (
                token.offset > len(block.text)
                or token.authority_ref.kind != AuthorityKind.PASSAGE
                or catalog.get(authority_dependency_id(token.authority_ref)) != token.authority_ref
            ):
                reject(
                    "CITATION_NOT_COMMITTED_PASSAGE",
                    "public citation token lacks exact admitted passage ancestry",
                    block_id=block.block_id,
                    refs=(token.authority_ref,),
                )
    for block in draft.blocks:
        proposed_example = (
            draft.question_id == 8
            and "unsupported" in block.text.lower()
            and any(
                claim.block_id == block.block_id
                and claim.use == ClaimUse.DISALLOWED_WORDING_EXAMPLE
                for claim in extraction.claims
            )
        )
        if not proposed_example:
            for expression, code in (
                (_UNIVERSAL_ABSENCE, "UNIVERSAL_ABSENCE"),
                (_SOURCE_STITCH, "SOURCE_STITCHING"),
                (_CERTAINTY, "UNSUPPORTED_CERTAINTY"),
            ):
                if expression.search(block.text):
                    reject(
                        code,
                        "known unsafe actual public text cannot be hidden by extraction hints",
                        block_id=block.block_id,
                    )
    envelopes = {(e.target.kind, e.target.id): e for e in bundle.language_envelopes}
    for claim in extraction.claims:
        if not claim.basis_candidates:
            reject("MISSING_CLAIM_BASIS", "material claim proposes no admitted basis", claim)
        if not any(link.claim_id == claim.claim_id for link in extraction.basis_links):
            reject(
                "MISSING_BASIS_LINK",
                "material claim lacks an explicit proposition/basis mapping",
                claim,
            )
        if claim.category not in allowed_question_categories(draft.question_id):
            reject("QUESTION_USE_MISMATCH", "claim category is disallowed in this question", claim)
        example = claim.use == ClaimUse.DISALLOWED_WORDING_EXAMPLE
        visible_example = (
            example
            and draft.question_id == 8
            and "unsupported" in blocks[claim.block_id].text.lower()
        )
        if example and not visible_example:
            reject(
                "EXAMPLE_LABEL_MISSING",
                "disallowed wording example lacks an explicit public label",
                claim,
            )
        for expression, code in (
            (_UNIVERSAL_ABSENCE, "UNIVERSAL_ABSENCE"),
            (_SOURCE_STITCH, "SOURCE_STITCHING"),
            (_CERTAINTY, "UNSUPPORTED_CERTAINTY"),
        ):
            if expression.search(claim.normalized_assertion) and not visible_example:
                reject(code, "known unsafe wording cannot confer claim permission", claim)
        targets = {(t.target.kind, t.target.id) for t in claim.target_scopes}
        if (
            claim.category
            in {
                ReportClaimCategory.NEGATIVE_CLAIM,
                ReportClaimCategory.POTENTIAL_NOVELTY_CLAIM,
                ReportClaimCategory.NOVELTY_INTERPRETATION,
            }
            and not targets
            and not example
        ):
            reject(
                "TARGET_SCOPE_MISSING",
                "novelty interpretation requires an exact native target scope",
                claim,
            )
        for target in claim.target_scopes:
            envelope = envelopes.get((target.target.kind, target.target.id))
            if (
                envelope is None
                or target.target.id not in question.target_ids
                or target.claim_scope != envelope.claim_scope
            ):
                reject(
                    "TARGET_SCOPE_MISMATCH",
                    "claim target or scope differs from its frozen envelope",
                    claim,
                )
                continue
            if not example and claim.category == ReportClaimCategory.NEGATIVE_CLAIM:
                if (
                    envelope.verdict != VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
                    or LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE
                    not in envelope.permitted_classes
                ):
                    reject(
                        "TARGET_PERMISSION_EXCEEDED",
                        "target has no accepted scoped negative permission",
                        claim,
                    )
                finding = next(f for f in bundle.target_findings if f.target_id == target.target.id)
                needed = set((*finding.decisive_phase6_ids, *finding.supporting_phase6_ids))
                if not needed & _content_closure_ids(claim, bundle):
                    reject(
                        "MISSING_ACCEPTED_NEGATIVE_BASIS",
                        "negative claim lacks its accepted Phase6 content basis",
                        claim,
                    )
            if not example and claim.category == ReportClaimCategory.POTENTIAL_NOVELTY_CLAIM:
                if envelope.verdict not in {
                    VerdictState.POTENTIALLY_NOVEL,
                    VerdictState.STRONG_EVIDENCE_OF_NOVELTY,
                } or not set(envelope.permitted_classes) & {
                    LanguagePermissionClass.SCOPED_POTENTIAL,
                    LanguagePermissionClass.QUALIFIED_STRONG_POSITIVE,
                }:
                    reject(
                        "TARGET_PERMISSION_EXCEEDED",
                        "target has no accepted candidate permission",
                        claim,
                    )
                qualification_ids = {
                    qualification.qualification_id
                    for qualification in bundle.qualifications
                    if qualification.target_id == target.target.id
                }
                required = set(
                    ref
                    for ref in catalog.values()
                    if ref.kind == AuthorityKind.QUALIFICATION
                    and ref.native_id in qualification_ids
                )
                if not required <= set(claim.required_qualification_refs):
                    reject(
                        "MISSING_QUALIFICATION_LINK",
                        "candidate claim omits attached qualification references",
                        claim,
                    )
        if (
            claim.category == ReportClaimCategory.VALUE_CLAIM
            and claim.use != ClaimUse.ATTRIBUTED_INPUT_CLAIM
            and not any(v.kind == "AUTHORITATIVE_VALUE_FINDING" for v in bundle.value_projection)
        ):
            reject(
                "NO_ASSESSED_VALUE_BASIS",
                "current authority provides no measured value finding",
                claim,
            )
        if (
            claim.category == ReportClaimCategory.VALIDATION_RECOMMENDATION
            and claim.use != ClaimUse.RECOMMENDATION
        ):
            reject(
                "RECOMMENDATION_STATUS_MISMATCH",
                "validation must remain explicitly prospective",
                claim,
            )
        refs = tuple(
            dict.fromkeys(
                (
                    *claim.basis_candidates,
                    *claim.citation_candidates,
                    *claim.required_qualification_refs,
                )
            )
        )
        for ref in refs:
            admitted = catalog.get(authority_dependency_id(ref))
            if ref.scope != bundle.scope or (
                ref.target is not None
                and targets
                and (ref.target.kind, ref.target.id) not in targets
            ):
                reject(
                    "BASIS_SCOPE_MISMATCH",
                    "basis belongs to another claim target or report scope",
                    claim,
                    refs=(ref,),
                )
            if admitted is None:
                reject(
                    "BASIS_NOT_ADMITTED",
                    "basis is not an admitted exact native field",
                    claim,
                    refs=(ref,),
                )
            elif admitted.digest != ref.digest:
                reject(
                    "BASIS_DIGEST_MISMATCH",
                    "basis content differs from its admitted native digest",
                    claim,
                    refs=(ref,),
                )
            elif admitted != ref:
                reject(
                    "BASIS_SCOPE_MISMATCH",
                    "basis target or native ancestry differs",
                    claim,
                    refs=(ref,),
                )
            if ref not in eligible:
                reject(
                    "BASIS_NOT_SELECTED",
                    "basis is outside the planned complete display closure",
                    claim,
                    refs=(ref,),
                )
        for ref in claim.citation_candidates:
            if (
                ref.kind != AuthorityKind.PASSAGE
                or catalog.get(authority_dependency_id(ref)) != ref
            ):
                reject(
                    "CITATION_NOT_COMMITTED_PASSAGE",
                    "citation needs exact committed source/version/passage ancestry",
                    claim,
                    refs=(ref,),
                )
        content = _content_closure_ids(claim, bundle)
        if (
            "DIRECT_PRECEDENT" in claim.normalized_assertion
            and not visible_example
            and not any(
                c.comparison.classification.relation == PrecedentState.DIRECT_PRECEDENT
                and c.comparison.classification.classification_id in content
                for c in bundle.eligible_comparisons
            )
        ):
            reject(
                "CLASSIFICATION_UPGRADE",
                "direct label lacks a selected accepted direct comparison",
                claim,
            )
    return receipt()
