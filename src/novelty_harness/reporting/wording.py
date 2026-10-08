"""Target-specific wording records carry no independent language permission."""

from typing import Literal

from pydantic import Field

from novelty_harness.adjudication.frozen import LanguagePermissionClass
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.domain.enums import VerdictState
from novelty_harness.reporting.bundle import ReportInputBundle, native_ref
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    NonBlank,
    ReportContract,
    ReportProposalError,
    ReportScope,
)
from novelty_harness.reporting.recommendations import validate_report_basis_refs


class ClaimWording(ReportContract):
    contract_kind: Literal["phase8-claim-wording-v1"] = "phase8-claim-wording-v1"
    scope: ReportScope
    target: TargetRef
    claim_scope: NonBlank
    wording_text: NonBlank
    language_class: LanguagePermissionClass
    use: Literal["SUPPORTED", "QUALIFIED", "UNSUPPORTED_EXAMPLE"]
    basis_refs: tuple[AuthorityRef, ...] = Field(min_length=1)
    permission_refs: tuple[AuthorityRef, ...] = Field(min_length=1)
    necessary_limitations: tuple[NonBlank, ...]
    violation_reason_codes: tuple[NonBlank, ...] = ()


def validate_claim_wording(wording: ClaimWording, bundle: ReportInputBundle) -> ClaimWording:
    try:
        wording = ClaimWording.model_validate(wording.model_dump(mode="json"))
        envelope = next((e for e in bundle.language_envelopes if e.target == wording.target), None)
        if (
            envelope is None
            or wording.scope != bundle.scope
            or wording.claim_scope != envelope.claim_scope
        ):
            raise ReportProposalError("wording target, claim scope or report scope differs")
        validate_report_basis_refs(wording.basis_refs, bundle, (wording.target.id,))
        validate_report_basis_refs(wording.permission_refs, bundle, (wording.target.id,))
        if wording.permission_refs != envelope.authority_refs:
            raise ReportProposalError(
                "wording does not retain the exact target permission envelope"
            )
        if not set(envelope.required_limitations) <= set(wording.necessary_limitations):
            raise ReportProposalError("wording omits an attached material limitation")
        if wording.use == "UNSUPPORTED_EXAMPLE":
            if (
                not wording.wording_text.startswith("Unsupported example to avoid:")
                or not wording.violation_reason_codes
            ):
                raise ReportProposalError(
                    "unsupported example needs an explicit public label and reasons"
                )
        elif (
            wording.language_class not in envelope.permitted_classes
            or wording.violation_reason_codes
        ):
            raise ReportProposalError("wording exceeds the exact target language ceiling")
    except ValueError as error:
        if isinstance(error, ReportProposalError):
            raise
        raise ReportProposalError("wording fails strict contract validation") from error
    return wording


def safe_claim_wording(bundle: ReportInputBundle) -> tuple[ClaimWording, ...]:
    records: list[ClaimWording] = []
    for envelope in bundle.language_envelopes:
        ref = native_ref(bundle, AuthorityKind.TARGET_FINDING, target_id=envelope.target.id)
        if envelope.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL:
            language = LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE
            meaning = "is not novel at the claimed level within the accepted scope"
        elif envelope.verdict == VerdictState.POTENTIALLY_NOVEL:
            language = LanguagePermissionClass.SCOPED_POTENTIAL
            meaning = "remains potentially novel within the accepted scope and qualifications"
        elif envelope.verdict == VerdictState.STRONG_EVIDENCE_OF_NOVELTY:
            language = LanguagePermissionClass.QUALIFIED_STRONG_POSITIVE
            meaning = "has the accepted qualified strong-positive finding within its exact scope"
        else:
            language = LanguagePermissionClass.ABSTENTION
            meaning = "is unassessable; no positive or negative novelty conclusion is established"
        wording = ClaimWording(
            scope=bundle.scope,
            target=envelope.target,
            claim_scope=envelope.claim_scope,
            wording_text=(
                f"Target {envelope.target.id} {meaning}. Claim scope: {envelope.claim_scope!r}."
            ),
            language_class=language,
            use="QUALIFIED" if envelope.required_limitations else "SUPPORTED",
            basis_refs=(ref,),
            permission_refs=envelope.authority_refs,
            necessary_limitations=envelope.required_limitations,
        )
        records.append(validate_claim_wording(wording, bundle))
    return tuple(records)
