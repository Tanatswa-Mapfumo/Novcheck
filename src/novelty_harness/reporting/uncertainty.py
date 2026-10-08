"""Actual bound uncertainty, with upstream identities retained during grouping."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from novelty_harness.adjudication.models import TargetRef
from novelty_harness.adjudication.roles import ProsecutionCase
from novelty_harness.reporting.models import (
    AuthorityRef,
    NonBlank,
    QuestionId,
    ReportContract,
    ReportScope,
)


class UncertaintyItem(ReportContract):
    contract_kind: Literal["phase8-uncertainty-item-v1"] = "phase8-uncertainty-item-v1"
    scope: ReportScope
    uncertainty_id: NonBlank
    target: TargetRef | None = None
    upstream_kind: NonBlank
    state: NonBlank
    reason: NonBlank
    question_ids: tuple[QuestionId, ...] = (9,)
    claim_ids: tuple[str, ...] = ()
    authority_refs: tuple[AuthorityRef, ...]
    historical: bool = False


def project_uncertainty(bundle: "ReportInputBundle") -> tuple[UncertaintyItem, ...]:
    """Describe recorded uncertainty; do not resolve it or infer search saturation."""
    from novelty_harness.reporting.bundle import basis_json, field_ref, native_ref
    from novelty_harness.reporting.models import AuthorityKind, authority_dependency_id
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    items: list[UncertaintyItem] = []

    def add(
        ref: AuthorityRef,
        state: str,
        reason: str,
        kind: str,
        questions: tuple[QuestionId, ...] = (2, 3, 4, 5, 8, 9),
        *,
        history: bool = False,
    ) -> None:
        items.append(
            UncertaintyItem(
                scope=bundle.scope,
                uncertainty_id="p8unc_"
                + canonical_hash(
                    {
                        "ref": authority_dependency_id(ref),
                        "state": state,
                        "kind": kind,
                    }
                ),
                target=ref.target,
                upstream_kind=kind,
                state=state,
                reason=reason,
                question_ids=questions,
                authority_refs=(ref,),
                historical=history,
            )
        )

    def limits(ref: AuthorityRef, document: BaseModel, field: str, kind: str) -> None:
        values: tuple[str, ...] = getattr(document, field)
        for index, value in enumerate(values):
            add(field_ref(ref, value, field, index), "UNRESOLVED", value, kind)

    frozen = bundle.frozen_adjudication
    frozen_ref = native_ref(bundle, AuthorityKind.FROZEN)
    for field in ("limiting_factors", "unresolved_questions"):
        limits(frozen_ref, frozen, field, "FROZEN_LIMITATION")
    for finding in bundle.target_findings:
        limits(
            native_ref(bundle, AuthorityKind.TARGET_FINDING, target_id=finding.target_id),
            finding,
            "limiting_factors",
            "TARGET_LIMITATION",
        )
    overall_ref = native_ref(bundle, AuthorityKind.OVERALL_FINDING)
    limits(overall_ref, bundle.overall_finding, "limiting_factors", "OVERALL_LIMITATION")
    for gate in bundle.gate_findings:
        ref = native_ref(bundle, AuthorityKind.GATE, native_id=gate.gate_id)
        for field in ("limiting_factors", "unresolved_questions"):
            limits(ref, gate, field, "GATE_LIMITATION")
    closure = bundle.judge_resolutions_and_limitations
    for case in closure.role_cases:
        ref = native_ref(bundle, AuthorityKind.ROLE, native_id=case.case_id)
        limits(ref, case, "limitations", "ROLE_LIMITATION")
        field = "challenges" if isinstance(case, ProsecutionCase) else "points"
        arguments = case.challenges if isinstance(case, ProsecutionCase) else case.points
        for index, argument in enumerate(arguments):
            limits(
                field_ref(ref, argument, field, index), argument, "limitations", "ROLE_LIMITATION"
            )
    for rebuttal in closure.rebuttals:
        limits(
            native_ref(bundle, AuthorityKind.REBUTTAL, native_id=rebuttal.rebuttal_id),
            rebuttal,
            "limitations",
            "REBUTTAL_LIMITATION",
        )
    cir_ref = native_ref(bundle, AuthorityKind.CIR)
    for index, unknown in enumerate(bundle.cir.unknowns):
        add(
            field_ref(cir_ref, unknown, "unknowns", index),
            "UNSPECIFIED",
            unknown,
            "INPUT_UNKNOWN",
            (1, 7, 9),
        )
    from novelty_harness.reporting.value import project_value

    for value in project_value(bundle):
        if value.kind == "NO_VALUE_ASSESSMENT":
            for ref in value.basis_refs:
                add(
                    ref,
                    "NO_VALUE_ASSESSMENT",
                    "No accepted assessed-value validation basis",
                    "VALUE_AVAILABILITY",
                    (6, 7, 9),
                )
    for observation in bundle.source_metadata:
        limits(observation.source_ref, observation.source, "limitations", "SOURCE_LIMITATION")
        add(
            field_ref(observation.source_ref, observation.source.access_state, "access_state"),
            observation.source.access_state.value,
            "Recorded source access: " + observation.source.access_state.value,
            "SOURCE_ACCESS_STATE",
            (2, 3, 4, 9),
        )
        if observation.version is not None and observation.version_ref is not None:
            limits(
                observation.version_ref,
                observation.version,
                "limitations",
                "SOURCE_VERSION_LIMITATION",
            )
    for resolution in closure.judge_resolutions:
        ref = native_ref(bundle, AuthorityKind.JUDGE_RESOLUTION, native_id=resolution.resolution_id)
        for field in ("limiting_factors", "unresolved_dimensions"):
            limits(ref, resolution, field, "JUDGE_LIMITATION")
    for run in closure.judge_runs:
        ref = native_ref(bundle, AuthorityKind.JUDGE_RUN, native_id=run.run_id)
        for index, limitation in enumerate(run.finding.limitations):
            add(
                field_ref(ref, limitation, "finding", "limitations", index),
                "UNRESOLVED",
                limitation,
                "JUDGE_LIMITATION",
            )
    for localization in bundle.counterfactuals:
        limits(
            native_ref(
                bundle, AuthorityKind.COUNTERFACTUAL, native_id=localization.localization_id
            ),
            localization,
            "limiting_factors",
            "COUNTERFACTUAL_LIMITATION",
        )
    for need in bundle.input_needs:
        add(
            native_ref(bundle, AuthorityKind.INPUT_NEED, native_id=need.need_id),
            "CLARIFICATION_REQUIRED",
            need.reason,
            "INPUT_NEED",
            (1, 7, 8, 9),
        )
    for gap in bundle.research_gaps:
        add(
            native_ref(bundle, AuthorityKind.RESEARCH_GAP, native_id=gap.request_id),
            "EXTERNAL_EVIDENCE_GAP",
            gap.reason,
            "RESEARCH_GAP",
            (2, 4, 7, 9),
        )
    state = bundle.research_state
    ref = native_ref(bundle, AuthorityKind.RESEARCH_STATE)
    for field in ("unknown_upstream_artifacts", "remaining_gaps", "access_failures"):
        for index, value in enumerate(getattr(state, field)):
            add(
                field_ref(ref, value, field, index),
                "UNKNOWN" if field == "unknown_upstream_artifacts" else "UNRESOLVED",
                value,
                field.upper(),
                (2, 4, 7, 9),
            )
    for field in (
        "budget_usage",
        "query_history",
        "providers_attempted",
        "stop_reason",
        "budget_limits",
        "research_plan",
        "research_result",
        "coverage_policy",
    ):
        value = getattr(state, field)
        status = (
            str(value)
            if field == "stop_reason" and value
            else "UNKNOWN"
            if value is None
            else "RECORDED"
        )
        add(
            field_ref(ref, value, field),
            status,
            f"{field}: {basis_json(value)}",
            field.upper(),
            (2, 4, 9),
        )
    for index, cell in enumerate(state.coverage_cells):
        cell_ref = field_ref(ref, cell, "coverage_cells", index)
        add(cell_ref, cell.state.value, basis_json(cell), "COVERAGE_CELL", (2, 4, 9))
    coverage_ref = native_ref(bundle, AuthorityKind.COVERAGE)
    view = closure.phase6_view
    add(coverage_ref, "BOUNDED_LOCAL_SCOPE", basis_json(view.coverage), "COVERAGE", (2, 4, 9))
    for candidate in view.candidate_outcomes:
        if candidate.decision != "ASSESSED" or candidate.limitations:
            candidate_ref = next(
                d.authority_ref
                for d in bundle.dependency_manifest
                if d.authority_ref is not None
                and d.authority_ref.kind == "CANDIDATE"
                and d.authority_ref.digest == canonical_hash(candidate)
            )
            add(
                candidate_ref,
                candidate.decision,
                candidate.reason or basis_json(candidate),
                "CANDIDATE_LIMITATION",
                (2, 4, 9),
            )
    for comparison in bundle.eligible_comparisons:
        cls = comparison.comparison.classification
        chain = comparison.comparison.comparison.chain
        cmp_ref = native_ref(bundle, AuthorityKind.COMPARISON, native_id=cls.classification_id)
        for field in (
            "missing_elements",
            "missing_relationships",
            "configuration_gap",
            "scoped_coverage",
            "contradictions",
            "unresolved",
            "unassessable_reason",
        ):
            value = getattr(cls, field)
            if value:
                add(
                    field_ref(cmp_ref, value, "comparison", "classification", field),
                    "RECORDED_RESIDUAL",
                    basis_json(value),
                    "COMPARISON_LIMITATION",
                )
        for field in ("unsupported_portions", "contradictions", "context_needed"):
            value = getattr(chain.verification, field)
            if value:
                add(
                    field_ref(
                        cmp_ref, value, "comparison", "comparison", "chain", "verification", field
                    ),
                    "SUPPORT_LIMITATION",
                    basis_json(value),
                    "COMPARISON_LIMITATION",
                )
        if chain.edge.chronology.state != "PREDATES_CUTOFF":
            add(
                field_ref(
                    cmp_ref,
                    chain.edge.chronology,
                    "comparison",
                    "comparison",
                    "chain",
                    "edge",
                    "chronology",
                ),
                chain.edge.chronology.state,
                basis_json(chain.edge.chronology),
                "CHRONOLOGY_LIMITATION",
            )
        if chain.verification.context_completeness != "COMPLETE":
            add(
                field_ref(
                    cmp_ref,
                    chain.verification.context_completeness,
                    "comparison",
                    "comparison",
                    "chain",
                    "verification",
                    "context_completeness",
                ),
                chain.verification.context_completeness,
                "Recorded context is incomplete or unknown",
                "CONTEXT_LIMITATION",
            )
    for ancestor in closure.superseded_context_refs:
        add(
            ancestor,
            "HISTORICAL",
            "Superseded context retained as history, not current evidence",
            "SUPERSESSION",
            (9,),
            history=True,
        )
    return tuple(items)


if TYPE_CHECKING:
    from novelty_harness.reporting.bundle import ReportInputBundle
