"""Hierarchical untrusted planning with a deterministic coverage firewall."""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from novelty_harness.adjudication.frozen import (
    LanguagePermissionClass,
    OverallFinding,
    TargetFinding,
)
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.domain.enums import PrecedentState, VerdictState
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
from novelty_harness.evidence.graph.assessment_view import CommittedComparisonView
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.mcu.overrides import MCUVersion
from novelty_harness.reporting.bundle import (
    LanguageEnvelope,
    ReportInputBundle,
    SourceMetadataObservation,
)
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    Digest,
    NonBlank,
    QuestionId,
    ReportClaimCategory,
    ReportContract,
    ReportOptions,
    ReportProposalError,
    ReportScoped,
    validate_authority_refs,
)
from novelty_harness.reporting.obligations import CoverageObligation
from novelty_harness.reporting.uncertainty import UncertaintyItem, project_uncertainty
from novelty_harness.runtime.tracing.hashing import canonical_hash


class PlannedClaimIntent(ReportContract):
    contract_kind: Literal["phase8-planned-claim-intent-v1"] = "phase8-planned-claim-intent-v1"
    category: ReportClaimCategory
    use: Literal[
        "ASSERTION", "ATTRIBUTED_INPUT_CLAIM", "RECOMMENDATION", "DISALLOWED_WORDING_EXAMPLE"
    ] = "ASSERTION"
    target: TargetRef | None = None
    claim_scope: NonBlank | None = None
    permission: LanguagePermissionClass | None = None
    comparison_ref: AuthorityRef | None = None
    precedent_class: PrecedentState | None = None


class SubsectionPlan(ReportContract):
    contract_kind: Literal["phase8-subsection-plan-v1"] = "phase8-subsection-plan-v1"
    subsection_id: NonBlank
    heading: NonBlank
    purpose: NonBlank
    evidence_refs: tuple[AuthorityRef, ...] = ()
    comparison_ids: tuple[NonBlank, ...] = ()
    intended_claims: tuple[PlannedClaimIntent, ...] = ()
    obligation_ids: tuple[NonBlank, ...]
    depth: int = Field(default=1, ge=1, le=2)
    parent_id: NonBlank | None = None
    visible: bool = True


class QuestionPlan(ReportContract):
    contract_kind: Literal["phase8-question-plan-v1"] = "phase8-question-plan-v1"
    question_id: QuestionId
    analytical_thesis: NonBlank
    subsections: tuple[SubsectionPlan, ...]
    target_ids: tuple[NonBlank, ...]
    evidence_refs: tuple[AuthorityRef, ...]
    adjudication_refs: tuple[AuthorityRef, ...]
    required_limitation_refs: tuple[AuthorityRef, ...]
    obligation_ids: tuple[NonBlank, ...]
    proposed_synthesis: tuple[NonBlank, ...] = ()
    desired_depth: Literal["SHORT", "STANDARD", "DETAILED"] = "STANDARD"

    @property
    def label(self) -> str:
        return CANONICAL_QUESTIONS[self.question_id - 1]


class ReportPlanProposal(ReportScoped):
    contract_kind: Literal["phase8-report-plan-proposal-v1"] = "phase8-report-plan-proposal-v1"
    bundle_digest: Digest
    questions: tuple[QuestionPlan, ...]


class ReportPlan(ReportScoped):
    contract_kind: Literal["phase8-report-plan-v1"] = "phase8-report-plan-v1"
    plan_id: NonBlank
    bundle_digest: Digest
    questions: tuple[QuestionPlan, ...]
    proposal_digest: Digest
    validation_method: Literal["p8-plan-firewall-v1"] = "p8-plan-firewall-v1"
    validation_basis_refs: tuple[AuthorityRef, ...]
    origin: Literal["PLANNER", "COVERAGE_FALLBACK"]


class PlannerContext(ReportScoped):
    contract_kind: Literal["phase8-planner-context-v1"] = "phase8-planner-context-v1"
    bundle_digest: Digest
    options: ReportOptions
    cir: CanonicalIdeaRepresentation
    graph: MCUGraph | MCUVersion
    target_profiles: tuple[MCUComparisonProfile, ...]
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    eligible_comparisons: tuple[CommittedComparisonView, ...]
    source_metadata: tuple[SourceMetadataObservation, ...]
    language_envelopes: tuple[LanguageEnvelope, ...]
    coverage_obligations: tuple[CoverageObligation, ...]
    uncertainty: tuple[UncertaintyItem, ...]
    eligible_basis_refs: tuple[AuthorityRef, ...]
    eligible_citation_refs: tuple[AuthorityRef, ...]


_EVIDENCE_KINDS = {
    AuthorityKind.COMPARISON,
    AuthorityKind.COMMIT,
    AuthorityKind.GRAPH_RELATION,
    AuthorityKind.PASSAGE,
    AuthorityKind.SOURCE,
    AuthorityKind.SOURCE_VERSION,
    AuthorityKind.CANDIDATE,
    AuthorityKind.LINEAGE,
}
_ALLOWED_CATEGORIES: dict[QuestionId, set[ReportClaimCategory]] = {
    1: {ReportClaimCategory.INPUT_DESCRIPTION, ReportClaimCategory.UNCERTAINTY_CLAIM},
    2: {
        ReportClaimCategory.SOURCE_FACT,
        ReportClaimCategory.EQUIVALENCE_DESCRIPTION,
        ReportClaimCategory.COVERAGE_CLAIM,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    3: {
        ReportClaimCategory.SOURCE_FACT,
        ReportClaimCategory.NOVELTY_INTERPRETATION,
        ReportClaimCategory.EQUIVALENCE_DESCRIPTION,
        ReportClaimCategory.NEGATIVE_CLAIM,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    4: {
        ReportClaimCategory.SOURCE_FACT,
        ReportClaimCategory.EQUIVALENCE_DESCRIPTION,
        ReportClaimCategory.NOVELTY_INTERPRETATION,
        ReportClaimCategory.POTENTIAL_NOVELTY_CLAIM,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    5: {
        ReportClaimCategory.SOURCE_FACT,
        ReportClaimCategory.EQUIVALENCE_DESCRIPTION,
        ReportClaimCategory.NOVELTY_INTERPRETATION,
        ReportClaimCategory.NEGATIVE_CLAIM,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    6: {
        ReportClaimCategory.NOVELTY_INTERPRETATION,
        ReportClaimCategory.INPUT_DESCRIPTION,
        ReportClaimCategory.VALUE_CLAIM,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    7: {
        ReportClaimCategory.VALIDATION_RECOMMENDATION,
        ReportClaimCategory.INPUT_DESCRIPTION,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    8: {
        ReportClaimCategory.NOVELTY_INTERPRETATION,
        ReportClaimCategory.NEGATIVE_CLAIM,
        ReportClaimCategory.POTENTIAL_NOVELTY_CLAIM,
        ReportClaimCategory.COVERAGE_CLAIM,
        ReportClaimCategory.UNCERTAINTY_CLAIM,
    },
    9: {
        ReportClaimCategory.UNCERTAINTY_CLAIM,
        ReportClaimCategory.COVERAGE_CLAIM,
        ReportClaimCategory.SOURCE_FACT,
        ReportClaimCategory.EQUIVALENCE_DESCRIPTION,
        ReportClaimCategory.NOVELTY_INTERPRETATION,
    },
}


def allowed_question_categories(question_id: QuestionId) -> tuple[ReportClaimCategory, ...]:
    """Expose the fixed shared question policy as an immutable projection."""
    return tuple(sorted(_ALLOWED_CATEGORIES[question_id], key=lambda category: category.value))


def _required_limitation_refs(
    question: QuestionPlan, bundle: ReportInputBundle
) -> tuple[AuthorityRef, ...]:
    selected = {r.native_id for r in question.evidence_refs}
    return tuple(
        dict.fromkeys(
            r
            for item in project_uncertainty(bundle)
            if not item.historical
            and (
                question.question_id in item.question_ids
                or any(ref.native_id in selected for ref in item.authority_refs)
            )
            and (item.target is None or item.target.id in question.target_ids)
            for r in item.authority_refs
        )
    )


def _check_intent(
    intent: PlannedClaimIntent, question: QuestionPlan, bundle: ReportInputBundle
) -> None:
    if intent.category not in _ALLOWED_CATEGORIES[question.question_id]:
        raise ReportProposalError("claim intent is disallowed for this question")
    if intent.target is not None:
        envelope = next((e for e in bundle.language_envelopes if e.target == intent.target), None)
        if (
            envelope is None
            or intent.target.id not in question.target_ids
            or intent.claim_scope != envelope.claim_scope
        ):
            raise ReportProposalError("claim target or scope differs from frozen envelope")
        if intent.permission is not None and intent.permission not in envelope.permitted_classes:
            raise ReportProposalError("claim intent exceeds target language ceiling")
        if intent.category == ReportClaimCategory.NEGATIVE_CLAIM and (
            envelope.verdict != VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
            or intent.permission != LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE
        ):
            raise ReportProposalError("negative intent lacks exact accepted target permission")
        if intent.category == ReportClaimCategory.POTENTIAL_NOVELTY_CLAIM and (
            envelope.verdict
            not in {VerdictState.POTENTIALLY_NOVEL, VerdictState.STRONG_EVIDENCE_OF_NOVELTY}
            or intent.permission
            not in {
                LanguagePermissionClass.SCOPED_POTENTIAL,
                LanguagePermissionClass.QUALIFIED_STRONG_POSITIVE,
            }
        ):
            raise ReportProposalError("positive intent lacks scoped frozen candidate permission")
    elif (
        intent.permission is not None
        or intent.claim_scope is not None
        or intent.category
        in {
            ReportClaimCategory.NEGATIVE_CLAIM,
            ReportClaimCategory.POTENTIAL_NOVELTY_CLAIM,
            ReportClaimCategory.NOVELTY_INTERPRETATION,
        }
    ):
        raise ReportProposalError("novelty or permission intent requires an exact native target")
    if (
        intent.category == ReportClaimCategory.VALUE_CLAIM
        and intent.use != "ATTRIBUTED_INPUT_CLAIM"
        and not any(v.kind == "AUTHORITATIVE_VALUE_FINDING" for v in bundle.value_projection)
    ):
        raise ReportProposalError("value assertion lacks assessed-value authority")
    if (
        intent.category == ReportClaimCategory.VALIDATION_RECOMMENDATION
        and intent.use != "RECOMMENDATION"
    ):
        raise ReportProposalError("validation intent must remain prospective")
    if intent.comparison_ref is not None:
        if (
            intent.comparison_ref not in question.evidence_refs
            or intent.comparison_ref.kind != AuthorityKind.COMPARISON
        ):
            raise ReportProposalError("comparison intent lacks selected committed basis")
        comparison = next(
            (
                c
                for c in bundle.eligible_comparisons
                if c.comparison.classification.classification_id == intent.comparison_ref.native_id
            ),
            None,
        )
        if (
            comparison is None
            or (intent.target is not None and intent.comparison_ref.target != intent.target)
            or intent.precedent_class != comparison.comparison.classification.relation
        ):
            raise ReportProposalError(
                "comparison intent changes accepted precedent class or target"
            )
    elif intent.precedent_class is not None:
        raise ReportProposalError("precedent-class intent requires its exact comparison")


def _validate_structure(
    proposal: ReportPlanProposal, bundle: ReportInputBundle, options: ReportOptions, *, limits: bool
) -> None:
    if proposal.scope != bundle.scope or proposal.bundle_digest != bundle.bundle_digest:
        raise ReportProposalError("plan scope or bundle digest differs")
    if tuple(q.question_id for q in proposal.questions) != tuple(range(1, 10)):
        raise ReportProposalError("plan must retain exact Q1–Q9 outer order")
    targets = {p.target_id for p in bundle.target_profiles}
    catalog = set(
        d.authority_ref for d in bundle.dependency_manifest if d.authority_ref is not None
    )
    obligations = {o.obligation_id: o for o in bundle.coverage_obligations}
    subsection_ids: set[str] = set()
    for q in proposal.questions:
        if len(set(q.target_ids)) != len(q.target_ids) or not set(q.target_ids) <= targets:
            raise ReportProposalError("plan target universe contains duplicate or foreign target")
        refs = (*q.evidence_refs, *q.adjudication_refs, *q.required_limitation_refs)
        for group in (q.evidence_refs, q.adjudication_refs, q.required_limitation_refs):
            validate_authority_refs(group, bundle.scope)
            if not set(group) <= catalog:
                raise ReportProposalError("plan references unadmitted authority")
        if any(r.kind not in _EVIDENCE_KINDS for r in q.evidence_refs):
            raise ReportProposalError("evidence group contains adjudication authority")
        if any(r.kind in _EVIDENCE_KINDS for r in q.adjudication_refs):
            raise ReportProposalError("adjudication group contains source authority")
        required = {
            o.obligation_id for o in obligations.values() if q.question_id in o.question_ids
        }
        if len(set(q.obligation_ids)) != len(q.obligation_ids) or set(q.obligation_ids) != required:
            raise ReportProposalError("plan omits mandatory question obligations or invents homes")
        if any(
            o.target is not None and o.target.id not in q.target_ids
            for identifier in required
            for o in (obligations[identifier],)
        ):
            raise ReportProposalError("obligation target is absent from its question")
        if not set(
            r for identifier in required for r in obligations[identifier].authority_refs
        ) <= set(refs):
            raise ReportProposalError("obligation lacks its complete selected basis")
        if not set(_required_limitation_refs(q, bundle)) <= set(q.required_limitation_refs):
            raise ReportProposalError("selected basis omits relevant complete limitations")
        if not q.subsections or (
            limits and len(q.subsections) > options.limits.max_subsections_per_question
        ):
            raise ReportProposalError("subsection generation limit exceeded or no visible home")
        visible: set[str] = set()
        prior_depths: dict[str, int] = {}
        for s in q.subsections:
            if s.subsection_id in subsection_ids:
                raise ReportProposalError("duplicate subsection identity")
            subsection_ids.add(s.subsection_id)
            if limits and s.depth > options.limits.max_hierarchy_depth:
                raise ReportProposalError("hierarchy generation limit exceeded")
            if (s.depth == 1 and s.parent_id is not None) or (
                s.depth > 1 and prior_depths.get(s.parent_id or "") != s.depth - 1
            ):
                raise ReportProposalError("subsection hierarchy parent/depth differs")
            prior_depths[s.subsection_id] = s.depth
            if (
                len(set(s.obligation_ids)) != len(s.obligation_ids)
                or not set(s.obligation_ids) <= required
            ):
                raise ReportProposalError("subsection has duplicate or foreign obligation")
            validate_authority_refs(s.evidence_refs, bundle.scope)
            if not set(s.evidence_refs) <= set(q.evidence_refs) or not set(s.comparison_ids) <= {
                r.native_id for r in s.evidence_refs if r.kind == AuthorityKind.COMPARISON
            }:
                raise ReportProposalError("subsection evidence/comparison group is foreign")
            if s.visible:
                visible.update(s.obligation_ids)
            for intent in s.intended_claims:
                _check_intent(intent, q, bundle)
        if visible != required:
            raise ReportProposalError("mandatory obligation has no visible subsection home")


def _validated_plan(
    proposal: ReportPlanProposal, bundle: ReportInputBundle, *, fallback: bool
) -> ReportPlan:
    refs = tuple(
        dict.fromkeys(
            r
            for q in proposal.questions
            for r in (*q.evidence_refs, *q.adjudication_refs, *q.required_limitation_refs)
        )
    )
    plan = ReportPlan(
        scope=proposal.scope,
        compilation_id=proposal.compilation_id,
        plan_id="pending",
        bundle_digest=proposal.bundle_digest,
        questions=proposal.questions,
        proposal_digest=canonical_hash(proposal),
        validation_basis_refs=refs,
        origin="COVERAGE_FALLBACK" if fallback else "PLANNER",
    )
    return plan.model_copy(
        update={
            "plan_id": "p8plan_" + canonical_hash(plan.model_dump(mode="json", exclude={"plan_id"}))
        }
    )


def validate_report_plan(
    proposal: ReportPlanProposal, bundle: ReportInputBundle, options: ReportOptions
) -> ReportPlan:
    try:
        proposal = ReportPlanProposal.model_validate(proposal.model_dump(mode="json"))
        _validate_structure(proposal, bundle, options, limits=True)
        return _validated_plan(proposal, bundle, fallback=False)
    except ValueError as exc:
        if isinstance(exc, ReportProposalError):
            raise
        raise ReportProposalError("plan proposal violates a strict structural contract") from exc


def build_coverage_plan(
    bundle: ReportInputBundle, compilation: "ReportCompilationRecord"
) -> ReportPlan:
    if (bundle.scope, bundle.bundle_digest) != (compilation.scope, compilation.bundle_digest):
        raise ReportProposalError("coverage plan attempt differs from bundle")
    refs = tuple(d.authority_ref for d in bundle.dependency_manifest if d.authority_ref is not None)
    evidence = tuple(r for r in refs if r.kind in _EVIDENCE_KINDS)
    adjudication = tuple(r for r in refs if r.kind not in _EVIDENCE_KINDS)
    questions: list[QuestionPlan] = []
    for number in range(1, 10):
        from typing import cast

        qid = cast(QuestionId, number)
        obligations = tuple(
            o.obligation_id for o in bundle.coverage_obligations if qid in o.question_ids
        )
        question = QuestionPlan(
            question_id=qid,
            analytical_thesis="Explain the retained authoritative findings and limitations",
            subsections=(
                SubsectionPlan(
                    subsection_id=f"q{number}-coverage",
                    heading=CANONICAL_QUESTIONS[number - 1],
                    purpose="Express the complete retained basis within its scope",
                    evidence_refs=evidence,
                    obligation_ids=obligations,
                ),
            ),
            target_ids=tuple(p.target_id for p in bundle.target_profiles),
            evidence_refs=evidence,
            adjudication_refs=adjudication,
            required_limitation_refs=(),
            obligation_ids=obligations,
            desired_depth=compilation.options.detail,
        )
        questions.append(
            question.model_copy(
                update={"required_limitation_refs": _required_limitation_refs(question, bundle)}
            )
        )
    proposal = ReportPlanProposal(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        bundle_digest=bundle.bundle_digest,
        questions=tuple(questions),
    )
    _validate_structure(proposal, bundle, compilation.options, limits=False)
    return _validated_plan(proposal, bundle, fallback=True)


def build_planner_context(
    bundle: ReportInputBundle, compilation: "ReportCompilationRecord"
) -> PlannerContext:
    if (compilation.scope, compilation.bundle_digest) != (bundle.scope, bundle.bundle_digest):
        raise ReportProposalError("planner context attempt differs from bundle")
    refs = tuple(d.authority_ref for d in bundle.dependency_manifest if d.authority_ref is not None)
    return PlannerContext(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        bundle_digest=bundle.bundle_digest,
        options=compilation.options,
        cir=bundle.cir,
        graph=bundle.graph_or_version,
        target_profiles=bundle.target_profiles,
        target_findings=bundle.target_findings,
        overall_finding=bundle.overall_finding,
        eligible_comparisons=bundle.eligible_comparisons,
        source_metadata=bundle.source_metadata,
        language_envelopes=bundle.language_envelopes,
        coverage_obligations=bundle.coverage_obligations,
        uncertainty=project_uncertainty(bundle),
        eligible_basis_refs=refs,
        eligible_citation_refs=tuple(r for r in refs if r.kind == AuthorityKind.PASSAGE),
    )


if TYPE_CHECKING:
    from novelty_harness.reporting.artifacts import ReportCompilationRecord
