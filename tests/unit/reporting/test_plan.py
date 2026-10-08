"""Planner structure cannot remove obligations or expand frozen permissions."""

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.models import ReportOptions, ReportProposalError
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


@pytest.fixture(scope="module")
def compilation(report_case):
    from novelty_harness.reporting.execution import ReportCompilationConfiguration

    return report_case.repository.begin_report_compilation(
        report_case.bundle.scope.assessment_id,
        adjudication_id=report_case.frozen.adjudication_id,
        options=ReportOptions(),
        configuration=ReportCompilationConfiguration(),
        attempt_token="planning",
    )


def proposal_from(plan):
    from novelty_harness.reporting.plan import ReportPlanProposal

    return ReportPlanProposal(
        scope=plan.scope,
        compilation_id=plan.compilation_id,
        bundle_digest=plan.bundle_digest,
        questions=plan.questions,
    )


def replace_question(proposal, number, **changes):
    return proposal.model_copy(
        update={
            "questions": tuple(
                q.model_copy(update=changes) if q.question_id == number else q
                for q in proposal.questions
            )
        }
    )


def test_planner_cannot_omit_decisive_precedent_or_limitation(report_case, compilation):
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan

    bundle = report_case.bundle
    plan = build_coverage_plan(bundle, compilation)
    assert {o for q in plan.questions for o in q.obligation_ids} == {
        o.obligation_id for o in bundle.coverage_obligations
    }
    proposal = proposal_from(plan)
    q2 = proposal.questions[1]
    decisive = next(
        o.obligation_id
        for o in bundle.coverage_obligations
        if o.requirement_kind == "DECISIVE_PRECEDENT" and 2 in o.question_ids
    )
    omitted = replace_question(
        proposal,
        2,
        obligation_ids=tuple(o for o in q2.obligation_ids if o != decisive),
        subsections=tuple(
            s.model_copy(
                update={"obligation_ids": tuple(o for o in s.obligation_ids if o != decisive)}
            )
            for s in q2.subsections
        ),
    )
    with pytest.raises(ReportProposalError):
        validate_report_plan(omitted, bundle, compilation.options)
    assert q2.required_limitation_refs
    with pytest.raises(ReportProposalError):
        validate_report_plan(
            replace_question(proposal, 2, required_limitation_refs=()), bundle, compilation.options
        )


def test_plan_keeps_q1_to_q9_and_generative_inner_hierarchy(report_case, compilation):
    from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan

    proposal = proposal_from(build_coverage_plan(report_case.bundle, compilation))
    q = proposal.questions[1]
    first = q.subsections[0].model_copy(
        update={"heading": "Closest mechanism", "purpose": "Explain the stored comparison"}
    )
    second = first.model_copy(
        update={
            "subsection_id": "q2-relationship",
            "heading": "Configuration and residual",
            "depth": 2,
            "parent_id": first.subsection_id,
        }
    )
    changed = replace_question(
        proposal,
        2,
        subsections=(first, second),
        analytical_thesis="Separate mechanism and configuration",
    )
    plan = validate_report_plan(changed, report_case.bundle, compilation.options)
    assert tuple(q.question_id for q in plan.questions) == tuple(range(1, 10))
    assert tuple(q.label for q in plan.questions) == CANONICAL_QUESTIONS
    assert plan.questions[1].subsections[1].heading == "Configuration and residual"
    with pytest.raises(ReportProposalError):
        validate_report_plan(
            changed.model_copy(update={"questions": tuple(reversed(changed.questions))}),
            report_case.bundle,
            compilation.options,
        )


@pytest.mark.parametrize("attack", ["hidden", "foreign", "duplicate", "depth"])
def test_plan_rejects_hidden_only_obligation_or_foreign_basis(report_case, compilation, attack):
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan

    bundle = report_case.bundle
    proposal = proposal_from(build_coverage_plan(bundle, compilation))
    q = proposal.questions[1]
    first = q.subsections[0]
    if attack == "hidden":
        changed = replace_question(
            proposal, 2, subsections=(first.model_copy(update={"visible": False}),)
        )
    elif attack == "foreign":
        ref = q.evidence_refs[0].model_copy(update={"native_id": "foreign-source"})
        changed = replace_question(proposal, 2, evidence_refs=(ref, *q.evidence_refs[1:]))
    elif attack == "duplicate":
        changed = replace_question(proposal, 2, subsections=(first, first))
    else:
        changed = replace_question(
            proposal, 2, subsections=(first.model_copy(update={"depth": 3}),)
        )
    with pytest.raises(ReportProposalError):
        validate_report_plan(changed, bundle, compilation.options)


@pytest.mark.parametrize(
    "field", ["gate_override", "research_action", "assessed_value", "scope_override", "validated"]
)
def test_plan_rejects_gate_research_value_or_scope_override(report_case, compilation, field):
    from novelty_harness.reporting.plan import ReportPlanProposal, build_coverage_plan

    proposal = proposal_from(build_coverage_plan(report_case.bundle, compilation))
    with pytest.raises(ValidationError):
        ReportPlanProposal.model_validate(
            proposal.model_dump(mode="json") | {field: "unauthorized"}
        )


def test_plan_heading_semantics_are_not_self_certified(report_case, compilation):
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan

    proposal = proposal_from(build_coverage_plan(report_case.bundle, compilation))
    q = proposal.questions[1]
    heading = "The configuration is unprecedented everywhere"
    changed = replace_question(
        proposal, 2, subsections=(q.subsections[0].model_copy(update={"heading": heading}),)
    )
    plan = validate_report_plan(changed, report_case.bundle, compilation.options)
    assert plan.questions[1].subsections[0].heading == heading
    assert not hasattr(plan.questions[1].subsections[0], "supported")
    assert (
        plan.validation_method == "p8-plan-firewall-v1"
    )  # Structure only; public text still needs extraction/verification.


def test_q3_cannot_promote_partial_to_direct(report_case, compilation):
    from novelty_harness.adjudication.frozen import LanguagePermissionClass
    from novelty_harness.reporting.plan import (
        PlannedClaimIntent,
        build_coverage_plan,
        validate_report_plan,
    )

    bundle = report_case.bundle
    selected = bundle.eligible_comparisons[0]
    cls = selected.comparison.classification
    partial_cls = cls.model_copy(update={"relation": "STRONG_PARTIAL_PRECEDENT"})
    partial = selected.model_copy(
        update={
            "comparison": selected.comparison.model_copy(update={"classification": partial_cls})
        }
    )
    variant = bundle.model_copy(
        update={"eligible_comparisons": (partial, *bundle.eligible_comparisons[1:])}
    )
    # This caller-only semantic variant cannot seed repository authority.
    proposal = proposal_from(build_coverage_plan(variant, compilation))
    q = proposal.questions[2]
    envelope = next(
        e for e in bundle.language_envelopes if e.verdict == "NOT_NOVEL_AT_CLAIMED_LEVEL"
    )
    ref = next(
        r
        for r in q.evidence_refs
        if r.kind == "COMPARISON" and r.native_id == cls.classification_id
    )
    intent = PlannedClaimIntent(
        category="NEGATIVE_CLAIM",
        target=envelope.target,
        claim_scope=envelope.claim_scope,
        permission=LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE,
        comparison_ref=ref,
        precedent_class="DIRECT_PRECEDENT",
    )
    changed = replace_question(
        proposal,
        3,
        subsections=(q.subsections[0].model_copy(update={"intended_claims": (intent,)}),),
    )
    with pytest.raises(ReportProposalError):
        validate_report_plan(changed, variant, compilation.options)


def test_q4_unassessable_has_no_positive_intent(report_case, compilation):
    from novelty_harness.adjudication.frozen import LanguagePermissionClass
    from novelty_harness.reporting.plan import (
        PlannedClaimIntent,
        build_coverage_plan,
        validate_report_plan,
    )

    bundle = report_case.bundle
    proposal = proposal_from(build_coverage_plan(bundle, compilation))
    q = proposal.questions[3]
    envelope = next(e for e in bundle.language_envelopes if e.verdict == "UNASSESSABLE")
    intent = PlannedClaimIntent(
        category="POTENTIAL_NOVELTY_CLAIM",
        target=envelope.target,
        claim_scope=envelope.claim_scope,
        permission=LanguagePermissionClass.SCOPED_POTENTIAL,
    )
    with pytest.raises(ReportProposalError):
        validate_report_plan(
            replace_question(
                proposal,
                4,
                subsections=(q.subsections[0].model_copy(update={"intended_claims": (intent,)}),),
            ),
            bundle,
            compilation.options,
        )


def test_zero_generation_limits_keep_complete_coverage_plan(report_case, compilation):
    from novelty_harness.reporting.models import ReportGenerationLimits
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan

    limited = compilation.model_copy(
        update={
            "options": ReportOptions(
                limits=ReportGenerationLimits(max_subsections_per_question=0, max_hierarchy_depth=0)
            )
        }
    )
    plan = build_coverage_plan(report_case.bundle, limited)
    assert len(plan.questions) == 9
    with pytest.raises(ReportProposalError):
        validate_report_plan(proposal_from(plan), report_case.bundle, limited.options)


def test_planner_context_has_complete_obligations_and_no_capabilities(report_case, compilation):
    from novelty_harness.reporting.plan import build_planner_context

    context = build_planner_context(report_case.bundle, compilation)
    assert context.coverage_obligations == report_case.bundle.coverage_obligations
    assert context.language_envelopes == report_case.bundle.language_envelopes
    assert not any(
        hasattr(context, name) for name in ("repository", "search", "provider", "browser")
    )


def test_rejected_plan_is_preserved_before_single_coverage_plan(report_case, compilation):
    from novelty_harness.reporting.artifacts import (
        ReportArtifactKind,
        ReportAttemptState,
        make_report_artifact,
    )
    from novelty_harness.reporting.plan import build_coverage_plan
    from novelty_harness.reporting.repository import ReportAuthorityError
    from tests.unit.reporting.test_attempts import status_artifact

    plan = build_coverage_plan(report_case.bundle, compilation)
    proposal = proposal_from(plan)
    rejected = replace_question(proposal, 2, obligation_ids=())
    artifact = make_report_artifact(
        compilation, ReportArtifactKind.PLAN_PROPOSAL, rejected, method_version="p8-plan-v1"
    )
    repo = report_case.repository
    repo.record_report_artifact(compilation.compilation_id, artifact)
    fallback = make_report_artifact(
        compilation, ReportArtifactKind.PLAN, plan, method_version="p8-plan-firewall-v1"
    )
    repo.record_report_artifact(compilation.compilation_id, fallback)
    initial = next(
        a.document
        for a in repo.load_report_artifacts(compilation.compilation_id)
        if a.kind == "STATUS"
    )
    status = status_artifact(
        compilation,
        initial,
        ReportAttemptState.PLANNED,
        reason="Rejected proposal; complete coverage plan",
    )
    repo.record_report_artifact(compilation.compilation_id, status)
    loaded = repo.load_report_artifacts(compilation.compilation_id)
    assert artifact in loaded and fallback in loaded and status in loaded
    changed = plan.model_copy(
        update={
            "questions": tuple(
                q.model_copy(update={"analytical_thesis": "Different realization"})
                for q in plan.questions
            )
        }
    )
    alternate = make_report_artifact(
        compilation, ReportArtifactKind.PLAN, changed, method_version="p8-plan-firewall-v1"
    )
    with pytest.raises(ReportAuthorityError):
        repo.record_report_artifact(compilation.compilation_id, alternate)
