"""Prospective validation requirements do not establish experiment results."""

from typing import Literal

from pydantic import Field, model_validator

from novelty_harness.domain.enums import VerdictState
from novelty_harness.reporting.bundle import ReportInputBundle, native_ref
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    NonBlank,
    ReportContract,
    ReportProposalError,
    ReportScope,
    authority_dependency_id,
    validate_authority_refs,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class ProposedSuccessCriterion(ReportContract):
    contract_kind: Literal["phase8-proposed-success-criterion-v1"] = (
        "phase8-proposed-success-criterion-v1"
    )
    text: NonBlank
    label: Literal["PROPOSED_CHOICE_TO_JUSTIFY"] = "PROPOSED_CHOICE_TO_JUSTIFY"


class ValidationRequirement(ReportContract):
    contract_kind: Literal["phase8-validation-requirement-v1"] = "phase8-validation-requirement-v1"
    scope: ReportScope
    requirement_id: NonBlank
    target_ids: tuple[NonBlank, ...]
    basis_refs: tuple[AuthorityRef, ...] = Field(min_length=1)
    status: Literal["RECOMMENDATION"] = "RECOMMENDATION"
    purpose: NonBlank
    proposed_method: NonBlank
    baseline_refs: tuple[AuthorityRef, ...]
    generic_baseline_description: NonBlank | None = None
    proposed_measurements: tuple[NonBlank, ...] = Field(min_length=1)
    proposed_success_criterion: ProposedSuccessCriterion | None = None
    missing_input_refs: tuple[AuthorityRef, ...]
    missing_evidence_refs: tuple[AuthorityRef, ...]
    limitations: tuple[NonBlank, ...]

    @model_validator(mode="after")
    def canonical_address(self) -> "ValidationRequirement":
        object.__setattr__(
            self,
            "requirement_id",
            "p8require_" + canonical_hash(self.model_dump(mode="json", exclude={"requirement_id"})),
        )
        return self


def validate_report_basis_refs(
    refs: tuple[AuthorityRef, ...], bundle: ReportInputBundle, target_ids: tuple[str, ...]
) -> None:
    """Exact admitted record joins, never textual entailment or experimental authority."""
    validate_authority_refs(refs, bundle.scope)
    catalog = {
        authority_dependency_id(d.authority_ref): d.authority_ref
        for d in bundle.dependency_manifest
        if d.authority_ref is not None
    }
    for ref in refs:
        if catalog.get(authority_dependency_id(ref)) != ref:
            raise ReportProposalError("prospective basis is not an exact admitted record")
        if ref.target is not None and ref.target.id not in target_ids:
            raise ReportProposalError("prospective basis belongs to another target")


def validate_validation_requirement(
    proposal: ValidationRequirement, bundle: ReportInputBundle
) -> ValidationRequirement:
    try:
        proposal = ValidationRequirement.model_validate(proposal.model_dump(mode="json"))
        if proposal.scope != bundle.scope:
            raise ReportProposalError("recommendation scope differs")
        targets = {e.target.id: e for e in bundle.language_envelopes}
        if len(set(proposal.target_ids)) != len(proposal.target_ids) or not set(
            proposal.target_ids
        ) <= set(targets):
            raise ReportProposalError("recommendation target is absent or duplicated")
        for refs in (
            proposal.basis_refs,
            proposal.baseline_refs,
            proposal.missing_input_refs,
            proposal.missing_evidence_refs,
        ):
            validate_report_basis_refs(refs, bundle, proposal.target_ids)
        if not proposal.baseline_refs and proposal.generic_baseline_description is None:
            raise ReportProposalError("recommendation requires an admitted or generic baseline")
        if any(
            ref.kind
            not in {
                AuthorityKind.COMPARISON,
                AuthorityKind.SOURCE,
                AuthorityKind.SOURCE_VERSION,
                AuthorityKind.PASSAGE,
                AuthorityKind.TARGET,
                AuthorityKind.CIR,
                AuthorityKind.GRAPH,
            }
            for ref in proposal.baseline_refs
        ):
            raise ReportProposalError("baseline reference does not identify an admitted comparator")
        if any(r.kind != AuthorityKind.INPUT_NEED for r in proposal.missing_input_refs):
            raise ReportProposalError("missing user meaning must remain an input clarification")
        if any(
            r.kind
            not in {
                AuthorityKind.RESEARCH_GAP,
                AuthorityKind.COVERAGE,
                AuthorityKind.CANDIDATE,
                AuthorityKind.SOURCE,
                AuthorityKind.SOURCE_VERSION,
                AuthorityKind.COUNTERFACTUAL,
                AuthorityKind.VALUE_BASIS,
                AuthorityKind.CIR,
                AuthorityKind.FROZEN,
            }
            for r in proposal.missing_evidence_refs
        ):
            raise ReportProposalError("missing evidence reference has an unrelated native kind")
        required = {
            limit
            for identifier in proposal.target_ids
            for limit in targets[identifier].required_limitations
        }
        if not required <= set(proposal.limitations):
            raise ReportProposalError("recommendation drops its target's attached limitations")
    except ValueError as error:
        if isinstance(error, ReportProposalError):
            raise
        raise ReportProposalError("recommendation fails strict contract validation") from error
    return proposal


def minimum_validation_requirements(bundle: ReportInputBundle) -> tuple[ValidationRequirement, ...]:
    requirements: list[ValidationRequirement] = []
    envelopes = {e.target.id: e for e in bundle.language_envelopes}

    def add(
        target_ids: tuple[str, ...],
        basis: tuple[AuthorityRef, ...],
        *,
        purpose: str,
        method: str,
        missing_input: tuple[AuthorityRef, ...] = (),
        missing_evidence: tuple[AuthorityRef, ...] = (),
    ) -> None:
        limits = tuple(
            dict.fromkeys(
                limit
                for identifier in target_ids
                for limit in envelopes[identifier].required_limitations
            )
        )
        proposal = ValidationRequirement(
            scope=bundle.scope,
            requirement_id="pending",
            target_ids=target_ids,
            basis_refs=basis,
            purpose=purpose,
            proposed_method=method,
            baseline_refs=(),
            generic_baseline_description=(
                "A matched baseline with a justified protocol; no comparator capability is assumed"
            ),
            proposed_measurements=("the stated mechanism or outcome under a specified protocol",),
            missing_input_refs=missing_input,
            missing_evidence_refs=missing_evidence,
            limitations=(
                *limits,
                "Prospective requirement only; no experiment or research result is established.",
            ),
        )
        requirements.append(validate_validation_requirement(proposal, bundle))

    for envelope in bundle.language_envelopes:
        finding_ref = native_ref(bundle, AuthorityKind.TARGET_FINDING, target_id=envelope.target.id)
        if envelope.verdict == VerdictState.UNASSESSABLE:
            purpose = "Clarify the target before interpreting novelty or benefit"
            method = (
                "Clarify the mechanism, configuration and missing user meaning before "
                "designing a comparison; no meaning is resolved here."
            )
        else:
            purpose = (
                "Validate the claimed mechanism or difference within its accepted target scope"
            )
            method = (
                "Specify a prospective controlled comparison or feasible ablation of the "
                "claimed element or relationship; justify measurements and feasibility before "
                "drawing an outcome conclusion."
            )
        add((envelope.target.id,), (finding_ref,), purpose=purpose, method=method)
    for need in bundle.input_needs:
        ref = native_ref(bundle, AuthorityKind.INPUT_NEED, native_id=need.need_id)
        add(
            (need.target_id,),
            (ref,),
            purpose="Clarify the recorded missing input",
            method=(
                "Request the recorded missing fields or topology from the submitter; "
                "preserve unresolved meaning until supplied."
            ),
            missing_input=(ref,),
        )
    for gap in bundle.research_gaps:
        ref = native_ref(bundle, AuthorityKind.RESEARCH_GAP, native_id=gap.request_id)
        add(
            (gap.target_id,),
            (ref,),
            purpose="Address the retained evidence gap before stronger interpretation",
            method=(
                "Require resolution of the recorded gap in a future authorized "
                "validation process; this report performs no research."
            ),
            missing_evidence=(ref,),
        )
    for value in bundle.value_projection:
        if value.kind == "ATTRIBUTED_INPUT_CLAIM":
            add(
                (value.target.id,) if value.target is not None else (),
                value.basis_refs,
                purpose="Validate the attributed claimed advantage",
                method=(
                    "Define a prospective test of the submitter's claimed outcome against a "
                    "justified baseline; the attributed input is not an assessed benefit."
                ),
            )
        elif value.kind == "NO_VALUE_ASSESSMENT":
            add(
                (),
                value.basis_refs,
                purpose="Establish an authoritative value assessment",
                method=(
                    "Specify the claimed benefit, a justified matched baseline, relevant "
                    "outcome measurements and a prospective criterion; obtain evidence "
                    "before assessing value maturity."
                ),
            )
    return tuple(requirements)
