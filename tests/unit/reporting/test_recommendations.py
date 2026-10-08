"""Prospective tests have no result, capability or research authority."""

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.models import AuthorityKind, ReportProposalError
from tests.unit.reporting.test_obligations import report_case as _report_case
from tests.unit.reporting.test_plan import compilation as _compilation

report_case = _report_case
compilation = _compilation


def ablation_requirement(bundle):
    from novelty_harness.reporting.recommendations import (
        ProposedSuccessCriterion,
        ValidationRequirement,
    )

    comparison = next(
        d.authority_ref
        for d in bundle.dependency_manifest
        if d.authority_ref.kind == AuthorityKind.COMPARISON
    )
    envelope = next(e for e in bundle.language_envelopes if e.target == comparison.target)
    return ValidationRequirement(
        scope=bundle.scope,
        requirement_id="proposal_ablation",
        target_ids=(envelope.target.id,),
        basis_refs=(comparison,),
        status="RECOMMENDATION",
        purpose="Test whether the claimed control-flow difference has a useful effect",
        proposed_method=(
            "If feasible, compare the submitted control flow with an ablation "
            "that disables its claimed relationship under otherwise matched conditions"
        ),
        baseline_refs=(comparison,),
        generic_baseline_description=None,
        proposed_measurements=("latency distribution", "failure rate"),
        proposed_success_criterion=ProposedSuccessCriterion(
            text="A proposed 10% latency reduction", label="PROPOSED_CHOICE_TO_JUSTIFY"
        ),
        missing_input_refs=(),
        missing_evidence_refs=(),
        limitations=envelope.required_limitations,
    )


def test_useful_prospective_ablation_is_not_an_experiment_result(report_case):
    from novelty_harness.reporting.recommendations import (
        ValidationRequirement,
        validate_validation_requirement,
    )

    proposal = ablation_requirement(report_case.bundle)
    validated = validate_validation_requirement(proposal, report_case.bundle)
    assert validated.status == "RECOMMENDATION"
    assert validated.basis_refs == proposal.basis_refs
    assert validated.proposed_measurements == ("latency distribution", "failure rate")
    assert validated.proposed_success_criterion.label == "PROPOSED_CHOICE_TO_JUSTIFY"
    for field in (
        "observed_result",
        "performed_experiment",
        "value_maturity",
        "benchmark_fact",
        "resolved_user_meaning",
        "research_performed",
    ):
        with pytest.raises(ValidationError):
            ValidationRequirement.model_validate(
                proposal.model_dump(mode="json") | {field: "10% faster"}
            )


def test_q7_cannot_invent_comparator_capability(report_case):
    from novelty_harness.reporting.recommendations import (
        ValidationRequirement,
        validate_validation_requirement,
    )

    proposal = ablation_requirement(report_case.bundle)
    with pytest.raises(ValidationError):
        ValidationRequirement.model_validate(
            proposal.model_dump(mode="json") | {"comparator_capabilities": ["zero latency"]}
        )
    foreign = proposal.baseline_refs[0].model_copy(update={"native_id": "source_invented"})
    with pytest.raises(ReportProposalError):
        validate_validation_requirement(
            proposal.model_copy(update={"baseline_refs": (foreign,)}), report_case.bundle
        )


@pytest.mark.parametrize(
    "premise",
    [
        "The comparator already achieves zero latency",
        "The experiment demonstrated a 25% improvement",
        "Research has resolved the missing user topology",
        "This benchmark is the externally established industry threshold",
    ],
)
def test_embedded_recommendation_premises_require_semantic_rejection(
    report_case, compilation, premise
):
    from novelty_harness.reporting.recommendations import validate_validation_requirement
    from novelty_harness.reporting.verification import validate_verification_batch
    from tests.unit.reporting.test_verification import scripted_batch, verification_case

    # Structural validity cannot establish an embedded natural-language premise.
    proposal = ablation_requirement(report_case.bundle).model_copy(
        update={"proposed_method": premise}
    )
    assert validate_validation_requirement(proposal, report_case.bundle).proposed_method == premise
    context, firewall = verification_case(report_case.bundle, compilation, text=premise)
    assert not validate_verification_batch(
        context,
        scripted_batch(
            context,
            disposition="REJECTED",
            block_disposition="REJECTED",
            code=("UNSUPPORTED_RECOMMENDATION_PREMISE",),
        ),
        firewall,
    ).accepted


def test_minimum_needs_preserve_missing_meaning_and_m1(report_case):
    from novelty_harness.reporting.recommendations import (
        minimum_validation_requirements,
        validate_validation_requirement,
    )

    requirements = minimum_validation_requirements(report_case.bundle)
    assert requirements
    assert all(r.status == "RECOMMENDATION" for r in requirements)
    assert any("value" in r.purpose.lower() and not r.target_ids for r in requirements)
    unknown_ids = {
        f.target_id for f in report_case.bundle.target_findings if f.verdict.value == "UNASSESSABLE"
    }
    assert unknown_ids <= {identifier for r in requirements for identifier in r.target_ids}
    assert all(validate_validation_requirement(r, report_case.bundle) == r for r in requirements)
    assert any(
        "clarif" in r.proposed_method.lower()
        for r in requirements
        if set(r.target_ids) & unknown_ids
    )


@pytest.mark.parametrize("mutation", ["target", "scope", "basis", "limitation", "criterion"])
def test_recommendations_reject_foreign_scope_and_unlabeled_criteria(report_case, mutation):
    from novelty_harness.reporting.recommendations import (
        ProposedSuccessCriterion,
        validate_validation_requirement,
    )

    proposal = ablation_requirement(report_case.bundle)
    if mutation == "criterion":
        with pytest.raises(ValidationError):
            ProposedSuccessCriterion(text="10% faster", label="OBSERVED_BENCHMARK")
        return
    if mutation == "target":
        proposal = proposal.model_copy(update={"target_ids": ("mcu_foreign",)})
    elif mutation == "scope":
        proposal = proposal.model_copy(
            update={"scope": proposal.scope.model_copy(update={"adjudication_id": "foreign"})}
        )
    elif mutation == "basis":
        proposal = proposal.model_copy(update={"basis_refs": ()})
    else:
        proposal = proposal.model_copy(update={"limitations": ()})
    with pytest.raises(ReportProposalError):
        validate_validation_requirement(proposal, report_case.bundle)


def test_verifier_receives_bound_prospective_context(report_case, compilation):
    from novelty_harness.reporting.firewall import (
        check_report_recommendations,
        check_report_wording,
    )
    from novelty_harness.reporting.recommendations import minimum_validation_requirements
    from novelty_harness.reporting.wording import safe_claim_wording
    from tests.unit.reporting.test_verification import verification_case

    context, _ = verification_case(report_case.bundle, compilation)
    requirements = minimum_validation_requirements(report_case.bundle)
    wordings = safe_claim_wording(report_case.bundle)
    assert context.validation_requirements == check_report_recommendations(
        requirements, report_case.bundle
    )
    assert context.claim_wording == check_report_wording(wordings, report_case.bundle)
    assert all(r.status == "RECOMMENDATION" for r in context.validation_requirements)
    bad = requirements[0].model_copy(update={"target_ids": ("unknown",)})
    with pytest.raises(ReportProposalError):
        check_report_recommendations((bad,), report_case.bundle)


def test_minimum_requirements_preserve_attributed_advantage_bases(report_case):
    from novelty_harness.reporting.recommendations import minimum_validation_requirements

    claimed = tuple(
        v for v in report_case.bundle.value_projection if v.kind == "ATTRIBUTED_INPUT_CLAIM"
    )
    assert claimed
    requirements = minimum_validation_requirements(report_case.bundle)
    for value in claimed:
        assert any(
            r.basis_refs == value.basis_refs and "claimed" in r.purpose.lower()
            for r in requirements
        )


def test_gate_record_cannot_be_named_as_a_comparator(report_case):
    from novelty_harness.reporting.recommendations import validate_validation_requirement

    proposal = ablation_requirement(report_case.bundle)
    gate = next(
        d.authority_ref
        for d in report_case.bundle.dependency_manifest
        if d.authority_ref.kind == AuthorityKind.GATE
        and d.authority_ref.target.id in proposal.target_ids
    )
    with pytest.raises(ReportProposalError):
        validate_validation_requirement(
            proposal.model_copy(update={"baseline_refs": (gate,)}), report_case.bundle
        )
