"""Sealed Phase 7 assessment-context transactions in the Phase 6 database."""

from collections.abc import Callable
from functools import partial
from typing import cast
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from novelty_harness.adjudication.context import (
    Phase7InputManifest,
    SealedAssessmentContext,
    is_true_noop,
)
from novelty_harness.adjudication.counterfactual import (
    CounterfactualLocalization,
    validate_counterfactual,
)
from novelty_harness.adjudication.execution import (
    phase7_artifact_id,
    validate_semantic_configuration,
    validate_semantic_execution,
)
from novelty_harness.adjudication.frozen import (
    FrozenAdjudication,
    TargetFinding,
    compose_assessment,
    phase7_frozen_id,
)
from novelty_harness.adjudication.gates import (
    GateAFinding,
    GateBFinding,
    GateCFinding,
    GateDFinding,
    evaluate_gate_a_with_needs,
    evaluate_gate_b_with_gaps,
    evaluate_gate_c,
    evaluate_gate_d,
)
from novelty_harness.adjudication.judge import (
    CounterbalanceComparison,
    CounterbalanceRun,
    GateFacts,
    JudgeFinding,
    JudgeProbeRegistration,
    JudgeResolution,
    JudgeStability,
    classify_dispute_impact,
    compare_counterbalance,
    dispute_arguments,
    judge_probe_id,
    normalize_judge_finding,
    resolve_judge_comparisons,
    validate_judge_finding,
)
from novelty_harness.adjudication.models import (
    Phase7Artifact,
    Phase7RunRecord,
    Phase7RunState,
    Phase7RunTransition,
    SemanticConfiguration,
    TargetRef,
    TargetScoped,
)
from novelty_harness.adjudication.needs import (
    InputClarificationNeed,
    ResearchContinuation,
    ResearchEscalationOutcome,
    ResearchGapDisposition,
    ResearchGapRequest,
    artifact_proposed_needs,
    validate_research_disposition,
    validate_research_gap_request,
)
from novelty_harness.adjudication.packet import build_adjudication_case
from novelty_harness.adjudication.policy import POLICY_VERSION, VerdictPermissionPolicy
from novelty_harness.adjudication.prompts import JUDGE_RUBRIC_VERSION
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.adjudication.repository import Phase7AuthorityError
from novelty_harness.adjudication.roles import (
    DefenseCase,
    Dispute,
    ProsecutionCase,
    RebuttalCase,
    material_disputes,
    neutral_review_issues,
    validate_defense_case,
    validate_prosecution_case,
    validate_rebuttal_case,
)
from novelty_harness.domain.enums import VerdictState
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView
from novelty_harness.evidence.graph.phase7_models import (
    Phase7ArtifactRow,
    Phase7AssessmentContextRow,
    Phase7FrozenDependencyRow,
    Phase7FrozenManifestRow,
    Phase7InputManifestRow,
    Phase7QualificationRefRow,
    Phase7RunRow,
    Phase7RunTransitionRow,
)
from novelty_harness.evidence.mapping.dimensions import (
    build_combination_comparison_profile,
    build_mcu_comparison_profile,
)
from novelty_harness.runtime.budgets.controller import BudgetUsage
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def load_phase7_qualifications(
    engine: Engine,
    load_context: Callable[..., SealedAssessmentContext],
    context_id: str,
    target: TargetRef,
) -> tuple[RobustnessQualification, DomainQualification]:
    """Return repository-scoped unqualified records until trusted issuers exist."""

    target = TargetRef.model_validate_json(target.model_dump_json())
    with Session(engine) as session:
        context_row = session.get(Phase7AssessmentContextRow, context_id)
        if context_row is None:
            raise Phase7AuthorityError("Qualification context is missing")
        assessment_id = context_row.assessment_id
    context = load_context(assessment_id, context_id=context_id)
    # The Phase 6 view is already validated by load_context; the manifest's
    # graph determines exact MCU and combination identities for this context.
    profiles = {("MCU", str(mcu.mcu_id)) for mcu in context.manifest.mcu_graph.mcus} | {
        (
            "COMBINATION",
            str(
                build_combination_comparison_profile(
                    combination, context.manifest.mcu_graph.mcus
                ).target_id
            ),
        )
        for combination in context.manifest.mcu_graph.combinations
    }
    if (target.kind, target.id) not in profiles:
        raise Phase7AuthorityError("Qualification target is absent from sealed context")
    with Session(engine) as session:
        rows = tuple(
            session.scalars(
                select(Phase7QualificationRefRow).where(
                    Phase7QualificationRefRow.context_id == context_id,
                    Phase7QualificationRefRow.target_id == target.id,
                )
            )
        )
        if rows:
            raise Phase7AuthorityError("No trusted Phase 7 qualification issuer is registered")
    return _default_qualifications(context, target)


def _default_qualifications(
    context: SealedAssessmentContext, target: TargetRef
) -> tuple[RobustnessQualification, DomainQualification]:
    context_id = context.context_id
    robustness = RobustnessQualification(
        qualification_id="p7qual_"
        + canonical_hash(
            {"context_id": context_id, "target": target.id, "kind": "robustness-default"}
        ),
        assessment_id=context.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        target_id=target.id,
        status="NOT_YET_QUALIFIED",
    )
    domain = DomainQualification(
        qualification_id="p7qual_"
        + canonical_hash({"context_id": context_id, "target": target.id, "kind": "domain-default"}),
        assessment_id=context.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        target_id=target.id,
        status="NOT_QUALIFIED",
    )
    return robustness, domain


def _validate_manifest_against_view(
    manifest: Phase7InputManifest,
    view: Phase6AssessmentView,
) -> None:
    if (
        manifest.assessment_id != view.assessment_id
        or manifest.phase6_snapshot_id != view.snapshot_id
        or manifest.as_of != view.as_of
    ):
        raise ValueError("Input manifest differs from the Phase 6 assessment locator")
    graph = manifest.mcu_graph
    graph_mcus = {mcu.mcu_id for mcu in graph.mcus}
    graph_combinations = {combination.combination_id for combination in graph.combinations}
    if graph_mcus != set(manifest.cir.mcu_ids):
        raise ValueError("CIR and MCU graph target sets differ")
    if graph_combinations != set(manifest.cir.combination_ids):
        raise ValueError("CIR and MCU graph combination sets differ")
    expected_combination_profiles = {
        combination.combination_id: build_combination_comparison_profile(combination, graph.mcus)
        for combination in graph.combinations
    }
    expected_target_ids = graph_mcus | {
        profile.target_id for profile in expected_combination_profiles.values()
    }
    if set(item.target_id for item in view.targets) != expected_target_ids:
        raise ValueError("Input target universe differs from the Phase 6 snapshot")
    expected_profiles = {mcu.mcu_id: build_mcu_comparison_profile(mcu) for mcu in graph.mcus} | {
        profile.target_id: profile for profile in expected_combination_profiles.values()
    }
    for target in view.targets:
        if target != expected_profiles[target.target_id]:
            raise ValueError("Input target profile differs from the Phase 6 snapshot")
        if target.target_kind == "COMBINATION":
            expected = expected_combination_profiles.get(target.combination_id or "")
            if (
                expected is None
                or target.target_id != expected.target_id
                or (target.combination_members != expected.combination_members)
            ):
                raise ValueError("Combination target topology differs from sealed graph")
    if manifest.research_plan is not None:
        if (
            set(manifest.research_plan.mcu_ids) != graph_mcus
            or set(manifest.research_plan.combination_ids) != graph_combinations
        ):
            raise ValueError("Research plan target universe differs from the sealed graph")
    elif "phase3" not in manifest.unknown_upstream_artifacts:
        raise ValueError("Missing research plan must be explicit UNKNOWN")
    if manifest.research_result is None and "phase4" not in manifest.unknown_upstream_artifacts:
        raise ValueError("Missing research result must be explicit UNKNOWN")
    known_artifacts = {
        "cir": manifest.cir,
        "sufficiency": manifest.sufficiency,
        "mcu_graph": manifest.mcu_graph,
        "research_plan": manifest.research_plan,
        "research_result": manifest.research_result,
    }
    for name, expected_digest in manifest.upstream_artifact_digests.items():
        artifact = known_artifacts.get(name)
        if artifact is None or canonical_hash(artifact) != expected_digest:
            raise ValueError(f"Upstream artifact digest differs: {name}")


def seal_phase7_context(
    engine: Engine,
    load_phase6_assessment: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    snapshot_id: str,
    manifest: Phase7InputManifest,
    parent_context_id: str | None = None,
) -> SealedAssessmentContext:
    """Seal exact validated policy inputs to one repository-loaded Phase 6 view."""

    with Session(engine) as session, session.begin():
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        manifest = Phase7InputManifest.model_validate(manifest.model_dump(mode="json"))
        view = load_phase6_assessment(session, assessment_id, snapshot_id=snapshot_id)
        _validate_manifest_against_view(manifest, view)
        digest = manifest.content_digest()
        view_digest = canonical_hash(view)
        manifest_id = "p7manifest_" + digest
        context_id = "p7ctx_" + canonical_hash(
            {
                "assessment_id": str(assessment_id),
                "snapshot_id": snapshot_id,
                "phase6_view_digest": view_digest,
                "manifest_digest": digest,
            }
        )
        context = SealedAssessmentContext(
            context_id=context_id,
            assessment_id=assessment_id,
            snapshot_id=snapshot_id,
            phase6_view_digest=view_digest,
            manifest_id=manifest_id,
            manifest_digest=digest,
            manifest=manifest,
            parent_context_id=parent_context_id,
        )
        if parent_context_id is not None:
            parent = session.get(Phase7AssessmentContextRow, parent_context_id)
            if parent is None or parent.assessment_id != assessment_id:
                raise ValueError("Parent context is missing or belongs to another assessment")
            if parent.context_id == context_id:
                raise ValueError("A context cannot be its own successor")
        manifest_row = session.get(Phase7InputManifestRow, manifest_id)
        manifest_json = canonical_json(manifest)
        if manifest_row is None:
            session.add(
                Phase7InputManifestRow(
                    manifest_id=manifest_id,
                    assessment_id=assessment_id,
                    document_json=manifest_json,
                )
            )
        elif (
            manifest_row.assessment_id != assessment_id
            or manifest_row.document_json != manifest_json
        ):
            raise Phase7AuthorityError("Manifest identity conflicts with existing content")
        context_row = session.get(Phase7AssessmentContextRow, context_id)
        context_json = canonical_json(context)
        if context_row is None:
            session.add(
                Phase7AssessmentContextRow(
                    context_id=context_id,
                    assessment_id=assessment_id,
                    snapshot_id=snapshot_id,
                    manifest_id=manifest_id,
                    parent_context_id=parent_context_id,
                    document_json=context_json,
                )
            )
        elif (
            context_row.assessment_id != assessment_id
            or context_row.snapshot_id != snapshot_id
            or context_row.manifest_id != manifest_id
            or context_row.document_json != context_json
        ):
            raise Phase7AuthorityError("Context identity conflicts with existing content")
        session.flush()
        return load_phase7_context_in_session(
            session,
            partial(load_phase6_assessment, session),
            assessment_id,
            context_id=context_id,
        )


def load_phase7_context(
    engine: Engine,
    load_phase6_assessment: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    context_id: str,
) -> SealedAssessmentContext:
    """Revalidate both manifest content and Phase 6 view before returning authority."""

    with Session(engine) as session:
        session.connection().exec_driver_sql("BEGIN")
        context = load_phase7_context_in_session(
            session,
            partial(load_phase6_assessment, session),
            assessment_id,
            context_id=context_id,
        )
        session.commit()
        return context


def load_phase7_context_in_session(
    session: Session,
    load_phase6_assessment: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    context_id: str,
) -> SealedAssessmentContext:
    row = session.get(Phase7AssessmentContextRow, context_id)
    if row is None or row.assessment_id != assessment_id:
        raise Phase7AuthorityError("Sealed assessment context is missing or foreign")
    manifest_row = session.get(Phase7InputManifestRow, row.manifest_id)
    if manifest_row is None or manifest_row.assessment_id != assessment_id:
        raise Phase7AuthorityError("Context input manifest is missing or foreign")
    context = SealedAssessmentContext.model_validate_json(row.document_json)
    manifest = Phase7InputManifest.model_validate_json(manifest_row.document_json)
    if (
        context.context_id != row.context_id
        or context.assessment_id != row.assessment_id
        or context.snapshot_id != row.snapshot_id
        or context.manifest_id != row.manifest_id
        or context.parent_context_id != row.parent_context_id
        or context.manifest != manifest
        or context.manifest_digest != manifest.content_digest()
        or context.manifest_id != "p7manifest_" + context.manifest_digest
    ):
        raise Phase7AuthorityError("Persisted context or manifest identity is inconsistent")
    view = load_phase6_assessment(assessment_id, snapshot_id=context.snapshot_id)
    _validate_manifest_against_view(manifest, view)
    if context.phase6_view_digest != canonical_hash(view):
        raise Phase7AuthorityError("Bound Phase 6 view content has changed")
    expected_id = "p7ctx_" + canonical_hash(
        {
            "assessment_id": str(assessment_id),
            "snapshot_id": context.snapshot_id,
            "phase6_view_digest": context.phase6_view_digest,
            "manifest_digest": context.manifest_digest,
        }
    )
    if context.context_id != expected_id:
        raise Phase7AuthorityError("Context ID differs from sealed content")
    return context


def _allowed_run_transitions() -> dict[Phase7RunState, set[Phase7RunState]]:
    return {
        Phase7RunState.CASE_BUILT: {
            Phase7RunState.FIRST_PASSES_COMPLETE,
            Phase7RunState.ABSTAINED,
            Phase7RunState.FAILED,
        },
        Phase7RunState.FIRST_PASSES_COMPLETE: {
            Phase7RunState.ESCALATION_PENDING,
            Phase7RunState.JUDGING,
            Phase7RunState.ABSTAINED,
            Phase7RunState.FAILED,
        },
        Phase7RunState.ESCALATION_PENDING: {
            Phase7RunState.JUDGING,
            Phase7RunState.FIRST_PASSES_COMPLETE,
            Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE,
            Phase7RunState.FAILED,
        },
        Phase7RunState.JUDGING: {
            Phase7RunState.ESCALATION_PENDING,
            Phase7RunState.FROZEN,
            Phase7RunState.ABSTAINED,
            Phase7RunState.FAILED,
        },
    }


def _current_transition(session: Session, run_id: str) -> Phase7RunTransition:
    rows = tuple(
        session.scalars(
            select(Phase7RunTransitionRow).where(Phase7RunTransitionRow.run_id == run_id)
        )
    )
    if not rows:
        raise Phase7AuthorityError("Run has no state transition")
    header_row = session.get(Phase7RunRow, run_id)
    if header_row is None:
        raise Phase7AuthorityError("Run transition has no header")
    header = Phase7RunRecord.model_validate_json(header_row.document_json)
    by_id: dict[str, Phase7RunTransition] = {}
    for row in rows:
        transition = Phase7RunTransition.model_validate_json(row.document_json)
        payload: JsonValue = {"run_id": run_id, "state": transition.state}
        if transition.predecessor_id is not None:
            payload["predecessor_id"] = transition.predecessor_id
        if (
            transition.run_id != run_id
            or transition.predecessor_id != row.predecessor_id
            or transition.transition_id != row.transition_id
            or transition.state != row.state
            or (
                transition.assessment_id,
                transition.assessment_context_id,
                transition.phase6_snapshot_id,
            )
            != (header.assessment_id, header.assessment_context_id, header.phase6_snapshot_id)
            or row.document_json != canonical_json(transition)
            or transition.transition_id != "p7transition_" + canonical_hash(payload)
        ):
            raise Phase7AuthorityError("Run transition identity/scope/content differs")
        by_id[row.transition_id] = transition
    predecessor_ids = {
        item.predecessor_id for item in by_id.values() if item.predecessor_id is not None
    }
    tips = [item for item in by_id.values() if item.transition_id not in predecessor_ids]
    if len(tips) != 1:
        raise Phase7AuthorityError("Run transition chain has a fork or no tip")
    visited: set[str] = set()
    current = tips[0]
    while True:
        if current.transition_id in visited:
            raise Phase7AuthorityError("Run transition chain contains a cycle")
        visited.add(current.transition_id)
        if current.predecessor_id is None:
            if current.state != Phase7RunState.CASE_BUILT or len(visited) != len(by_id):
                raise Phase7AuthorityError("Run transition chain lacks its exact initial state")
            break
        predecessor = by_id.get(current.predecessor_id)
        if predecessor is None:
            raise Phase7AuthorityError("Run transition chain has a missing predecessor")
        if current.state not in _allowed_run_transitions().get(predecessor.state, set()):
            raise Phase7AuthorityError("Run transition chain contains an illegal state change")
        current = predecessor
    return tips[0]


def begin_phase7_run(
    engine: Engine,
    load_context: Callable[..., SealedAssessmentContext],
    load_view: Callable[..., Phase6AssessmentView],
    context_id: str,
    *,
    attempt_token: str | None = None,
) -> Phase7RunRecord:
    with Session(engine) as session:
        context_row = session.get(Phase7AssessmentContextRow, context_id)
        if context_row is None:
            raise Phase7AuthorityError("Run context is missing")
        assessment_id = context_row.assessment_id
    context = load_context(assessment_id, context_id=context_id)
    view = load_view(assessment_id, snapshot_id=context.snapshot_id)
    packet = build_adjudication_case(context, view)
    token = attempt_token if attempt_token is not None else uuid4().hex
    if not token:
        raise ValueError("Run attempt token cannot be empty")
    run_id = "p7run_" + canonical_hash(
        {"context_id": context_id, "case_id": packet.case_id, "attempt_token": token}
    )
    run = Phase7RunRecord(
        run_id=run_id,
        attempt_token=token,
        case_id=packet.case_id,
        assessment_id=assessment_id,
        assessment_context_id=context_id,
        phase6_snapshot_id=context.snapshot_id,
    )
    initial = Phase7RunTransition(
        transition_id="p7transition_" + canonical_hash({"run_id": run_id, "state": "CASE_BUILT"}),
        run_id=run_id,
        assessment_id=assessment_id,
        assessment_context_id=context_id,
        phase6_snapshot_id=context.snapshot_id,
        state=Phase7RunState.CASE_BUILT,
    )
    with Session(engine) as session, session.begin():
        existing = session.get(Phase7RunRow, run_id)
        if existing is None:
            session.add(
                Phase7RunRow(
                    run_id=run_id,
                    context_id=context_id,
                    assessment_id=assessment_id,
                    snapshot_id=context.snapshot_id,
                    attempt_token=token,
                    document_json=canonical_json(run),
                )
            )
            session.add(
                Phase7RunTransitionRow(
                    transition_id=initial.transition_id,
                    run_id=run_id,
                    predecessor_id=None,
                    state=initial.state,
                    document_json=canonical_json(initial),
                )
            )
        elif existing.document_json != canonical_json(run):
            raise Phase7AuthorityError("Run ID conflicts with existing content")
    return load_phase7_run(engine, run_id)


def load_phase7_run(engine: Engine, run_id: str) -> Phase7RunRecord:
    with Session(engine) as session:
        return load_phase7_run_in_session(session, run_id)


def load_phase7_run_in_session(session: Session, run_id: str) -> Phase7RunRecord:
    row = session.get(Phase7RunRow, run_id)
    if row is None:
        raise Phase7AuthorityError("Phase 7 run is missing")
    run = Phase7RunRecord.model_validate_json(row.document_json)
    if (
        run.run_id != row.run_id
        or run.assessment_context_id != row.context_id
        or run.assessment_id != row.assessment_id
        or run.phase6_snapshot_id != row.snapshot_id
        or run.attempt_token != row.attempt_token
        or run.state != Phase7RunState.CASE_BUILT
        or run.run_id
        != "p7run_"
        + canonical_hash(
            {
                "context_id": run.assessment_context_id,
                "case_id": run.case_id,
                "attempt_token": run.attempt_token,
            }
        )
        or row.document_json != canonical_json(run)
    ):
        raise Phase7AuthorityError("Persisted run identity is inconsistent")
    return run.model_copy(update={"state": _current_transition(session, run_id).state})


def load_phase7_artifacts(engine: Engine, run_id: str) -> tuple[Phase7Artifact, ...]:
    with Session(engine) as session:
        return load_phase7_artifacts_in_session(session, run_id)


def load_phase7_artifacts_in_session(session: Session, run_id: str) -> tuple[Phase7Artifact, ...]:
    rows = tuple(
        session.scalars(select(Phase7ArtifactRow).where(Phase7ArtifactRow.run_id == run_id))
    )
    artifacts = tuple(Phase7Artifact.model_validate_json(row.document_json) for row in rows)
    for row, artifact in zip(rows, artifacts, strict=True):
        if (
            artifact.artifact_id != row.artifact_id
            or artifact.run_id != row.run_id
            or artifact.assessment_context_id != row.context_id
            or artifact.assessment_id != row.assessment_id
            or artifact.phase6_snapshot_id != row.snapshot_id
            or artifact.kind != row.kind
            or artifact.target_id != row.target_id
        ):
            raise Phase7AuthorityError("Persisted artifact identity is inconsistent")
    return artifacts


def record_phase7_artifact(
    engine: Engine,
    load_context: Callable[..., SealedAssessmentContext],
    load_view: Callable[..., Phase6AssessmentView],
    run_id: str,
    artifact: Phase7Artifact,
) -> str:
    artifact = Phase7Artifact.model_validate_json(artifact.model_dump_json())
    run = load_phase7_run(engine, run_id)
    first_pass = artifact.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
    if first_pass and run.state != Phase7RunState.CASE_BUILT:
        raise Phase7AuthorityError("First-pass artifact requires CASE_BUILT run")
    judging_artifact = artifact.kind in {
        "JUDGE_RUN",
        "COUNTERBALANCE_COMPARISON",
        "JUDGE_RESOLUTION",
        "GATE_A",
        "GATE_B",
        "GATE_C",
        "GATE_D",
        "INPUT_NEED",
        "COUNTERFACTUAL",
        "ROBUSTNESS_QUALIFICATION",
        "DOMAIN_QUALIFICATION",
    }
    if judging_artifact and run.state != Phase7RunState.JUDGING:
        raise Phase7AuthorityError("Judge artifact requires JUDGING run")
    if artifact.kind in {"RESEARCH_GAP", "RESEARCH_GAP_DISPOSITION"} and run.state not in {
        Phase7RunState.FIRST_PASSES_COMPLETE,
        Phase7RunState.JUDGING,
    }:
        raise Phase7AuthorityError("Research artifact requires an active adjudication run")
    if (
        not first_pass
        and not judging_artifact
        and artifact.kind
        not in {"JUDGE_PROBE", "RESEARCH_GAP", "RESEARCH_GAP_DISPOSITION", "SEMANTIC_CONFIGURATION"}
        and run.state != Phase7RunState.FIRST_PASSES_COMPLETE
    ):
        raise Phase7AuthorityError("Dispute or rebuttal requires completed first passes")
    if (
        artifact.run_id != run_id
        or artifact.assessment_id != run.assessment_id
        or artifact.assessment_context_id != run.assessment_context_id
        or artifact.phase6_snapshot_id != run.phase6_snapshot_id
        or artifact.artifact_id
        != phase7_artifact_id(run_id, artifact.kind, artifact.document_json, artifact.execution)
    ):
        raise Phase7AuthorityError("Artifact identity differs from its run or content")
    context = load_context(run.assessment_id, context_id=run.assessment_context_id)
    packet = build_adjudication_case(
        context, load_view(run.assessment_id, snapshot_id=run.phase6_snapshot_id)
    )
    if packet.case_id != run.case_id:
        raise Phase7AuthorityError("Run case packet has changed")
    committed = load_phase7_artifacts(engine, run_id)
    rebuttal_role: str | None = None
    research_request_id: str | None = None
    if artifact.kind == "SEMANTIC_CONFIGURATION":
        if run.state not in {
            Phase7RunState.CASE_BUILT,
            Phase7RunState.FIRST_PASSES_COMPLETE,
            Phase7RunState.JUDGING,
        }:
            raise Phase7AuthorityError("Semantic configuration requires an active run")
        proposal = SemanticConfiguration.model_validate_json(artifact.document_json)
        validate_semantic_configuration(proposal)
        if proposal.target_id not in packet.target_ids:
            raise Phase7AuthorityError("Semantic configuration target is absent")
        # A role configuration must be sealed before that role's first output.
        if any(
            a.kind == proposal.semantic_kind and a.target_id == proposal.target_id
            for a in committed
        ) and not any(a.artifact_id == artifact.artifact_id for a in committed):
            if proposal.semantic_kind != "JUDGE_RUN":
                raise Phase7AuthorityError("Semantic configuration cannot change after execution")
    elif artifact.kind == "PROSECUTION_CASE":
        proposal = validate_prosecution_case(
            ProsecutionCase.model_validate_json(artifact.document_json), packet
        )
    elif artifact.kind == "DEFENSE_CASE":
        proposal = validate_defense_case(
            DefenseCase.model_validate_json(artifact.document_json), packet
        )
    elif artifact.kind == "JUDGE_PROBE":
        proposal = JudgeProbeRegistration.model_validate_json(artifact.document_json)
        if run.state not in {Phase7RunState.FIRST_PASSES_COMPLETE, Phase7RunState.JUDGING}:
            raise Phase7AuthorityError("Judge probe requires an active completed first pass")
        if proposal.registration_id != judge_probe_id(run_id, proposal):
            raise Phase7AuthorityError("Judge probe identity differs")
        dispute_ids = {
            Dispute.model_validate_json(item.document_json).dispute_id
            for item in committed
            if item.kind == "DISPUTE"
        }
        if proposal.dispute_id not in dispute_ids or not proposal.model_config_id.strip():
            raise Phase7AuthorityError("Judge probe lacks committed dispute/configuration")
    elif artifact.kind == "DISPUTE":
        proposal = Dispute.model_validate_json(artifact.document_json)
        prosecution = next(
            (
                ProsecutionCase.model_validate_json(item.document_json)
                for item in committed
                if item.kind == "PROSECUTION_CASE" and item.target_id == proposal.target_id
            ),
            None,
        )
        defense = next(
            (
                DefenseCase.model_validate_json(item.document_json)
                for item in committed
                if item.kind == "DEFENSE_CASE" and item.target_id == proposal.target_id
            ),
            None,
        )
        if prosecution is None or defense is None:
            raise Phase7AuthorityError("Dispute lacks committed role cases")
        rebuttals = tuple(
            sorted(
                (
                    RebuttalCase.model_validate_json(item.document_json)
                    for item in committed
                    if item.kind == "REBUTTAL" and item.target_id == proposal.target_id
                ),
                key=lambda item: item.rebuttal_id,
            )
        )
        if proposal not in neutral_review_issues(prosecution, defense, packet, rebuttals=rebuttals):
            raise Phase7AuthorityError("Dispute differs from committed role alternatives")
    elif artifact.kind == "COUNTERBALANCE_COMPARISON":
        proposal = CounterbalanceComparison.model_validate_json(artifact.document_json)
        judge_runs = {
            judge_run.run_id: judge_run
            for item in committed
            if item.kind == "JUDGE_RUN"
            for judge_run in (CounterbalanceRun.model_validate_json(item.document_json),)
        }
        if proposal.first_run_id not in judge_runs or proposal.second_run_id not in judge_runs:
            raise Phase7AuthorityError("Comparison lacks a committed full judge pair")
        if (
            compare_counterbalance(
                judge_runs[proposal.first_run_id], judge_runs[proposal.second_run_id]
            )
            != proposal
        ):
            raise Phase7AuthorityError("Comparison differs from committed judge findings")
    elif artifact.kind == "JUDGE_RUN":
        proposal = CounterbalanceRun.model_validate_json(artifact.document_json)
        dispute = next(
            (
                Dispute.model_validate_json(item.document_json)
                for item in committed
                if item.kind == "DISPUTE"
                and Dispute.model_validate_json(item.document_json).dispute_id
                == proposal.dispute_id
            ),
            None,
        )
        if dispute is None:
            raise Phase7AuthorityError("Judge run lacks a committed dispute")
        prosecution = next(
            ProsecutionCase.model_validate_json(item.document_json)
            for item in committed
            if item.kind == "PROSECUTION_CASE" and item.target_id == dispute.target_id
        )
        defense = next(
            DefenseCase.model_validate_json(item.document_json)
            for item in committed
            if item.kind == "DEFENSE_CASE" and item.target_id == dispute.target_id
        )
        rebuttals = tuple(
            sorted(
                (
                    RebuttalCase.model_validate_json(item.document_json)
                    for item in committed
                    if item.kind == "REBUTTAL" and item.target_id == dispute.target_id
                ),
                key=lambda item: item.rebuttal_id,
            )
        )
        if dispute not in neutral_review_issues(prosecution, defense, packet, rebuttals=rebuttals):
            raise Phase7AuthorityError("Judge run uses obsolete dispute candidates")
        arguments = dispute_arguments(dispute, prosecution, defense, rebuttals=rebuttals)
        validate_judge_finding(proposal.finding, packet, arguments)
        expected_judge_id = "p7judge_" + canonical_hash(
            {
                "run_id": run_id,
                "dispute_id": dispute.dispute_id,
                "packet_id": packet.case_id,
                "arguments": [item.model_dump(mode="json") for item in arguments],
                "order": list(proposal.order),
                "model_config_id": proposal.model_config_id,
                "rubric": JUDGE_RUBRIC_VERSION,
            }
        )
        if (
            proposal.run_id != expected_judge_id
            or proposal.packet_id != packet.case_id
            or proposal.evidence_digest != packet.digest
            or proposal.argument_ids != dispute.argument_ids
            or proposal.rubric_version != JUDGE_RUBRIC_VERSION
            or not proposal.model_config_id.strip()
        ):
            raise Phase7AuthorityError(
                "Judge run packet, arguments, rubric or configuration differs"
            )
    elif artifact.kind == "REBUTTAL":
        proposal = validate_rebuttal_case(
            RebuttalCase.model_validate_json(artifact.document_json), packet
        )
        rebuttal_role = proposal.role
        disputes = {
            dispute.dispute_id: dispute
            for item in committed
            if item.kind == "DISPUTE" and item.target_id == proposal.target_id
            for dispute in (Dispute.model_validate_json(item.document_json),)
        }
        if not set(proposal.dispute_ids) <= set(disputes) or not set(proposal.argument_ids) <= {
            argument_id
            for dispute_id in proposal.dispute_ids
            for argument_id in disputes[dispute_id].argument_ids
        }:
            raise Phase7AuthorityError("Rebuttal links differ from committed disputes")
    elif artifact.kind == "RESEARCH_GAP_DISPOSITION":
        proposal = ResearchGapDisposition.model_validate_json(artifact.document_json)
        gaps = _artifact_documents(committed, "RESEARCH_GAP", ResearchGapRequest)
        joined_gaps = [
            g
            for g in gaps
            if g.request_id == proposal.request_id and g.target_id == proposal.target_id
        ]
        if len(joined_gaps) != 1:
            raise Phase7AuthorityError("Research disposition lacks committed request")
        validate_research_disposition(joined_gaps[0], proposal, context, packet)
    elif artifact.kind == "RESEARCH_GAP":
        proposal = validate_research_gap_request(
            ResearchGapRequest.model_validate_json(artifact.document_json), packet
        )
        if (
            proposal.material_gate == "D"
            and artifact_proposed_needs(committed, proposal.target_id)[0]
        ):
            raise Phase7AuthorityError("Gate A clarification prevents external Gate D research")
        research_request_id = proposal.request_id
        known_arguments = (
            {
                argument.argument_id
                for item in committed
                if item.kind == "PROSECUTION_CASE" and item.target_id == proposal.target_id
                for argument in ProsecutionCase.model_validate_json(item.document_json).challenges
            }
            | {
                point.defense_id
                for item in committed
                if item.kind == "DEFENSE_CASE" and item.target_id == proposal.target_id
                for point in DefenseCase.model_validate_json(item.document_json).points
            }
            | {
                argument_id
                for item in committed
                if item.kind == "DISPUTE" and item.target_id == proposal.target_id
                for argument_id in Dispute.model_validate_json(item.document_json).argument_ids
            }
        )
        if set(proposal.linked_argument_ids) - known_arguments:
            raise Phase7AuthorityError("Research gap links an uncommitted role argument")
    elif artifact.kind == "JUDGE_RESOLUTION":
        proposal = JudgeResolution.model_validate_json(artifact.document_json)
        comparisons = {
            c.comparison_id: c
            for item in committed
            if item.kind == "COUNTERBALANCE_COMPARISON"
            for c in (CounterbalanceComparison.model_validate_json(item.document_json),)
        }
        primary = comparisons.get(proposal.primary_comparison_id)
        alternate = comparisons.get(proposal.alternate_comparison_id or "")
        if primary is None or (proposal.alternate_comparison_id is not None and alternate is None):
            raise Phase7AuthorityError("Resolution lacks committed comparison pairs")
        if resolve_judge_comparisons(primary, alternate) != proposal:
            raise Phase7AuthorityError("Resolution differs from the committed non-voting probes")
    elif artifact.kind in {"GATE_A", "GATE_B", "GATE_C", "GATE_D"}:
        gate_models: dict[str, type[TargetScoped]] = {
            "GATE_A": GateAFinding,
            "GATE_B": GateBFinding,
            "GATE_C": GateCFinding,
            "GATE_D": GateDFinding,
        }
        proposal = gate_models[artifact.kind].model_validate_json(artifact.document_json)
        profile = next(
            (p for p in packet.target_profiles if p.target_id == proposal.target_id), None
        )
        if profile is None:
            raise Phase7AuthorityError("Gate target is absent from packet")
        target = TargetRef(kind=profile.target_kind, id=profile.target_id)
        proposed_needs, proposed_gaps = artifact_proposed_needs(committed, target.id)
        if (
            artifact.kind == "GATE_A"
            and proposal != evaluate_gate_a_with_needs(packet, target, proposed_needs)[0]
        ):
            raise Phase7AuthorityError("Gate A differs from sealed input facts")
        if artifact.kind == "GATE_B" and proposal != evaluate_gate_b_with_gaps(
            packet, target, proposed_gaps
        ):
            raise Phase7AuthorityError("Gate B differs from sealed research facts")
    elif artifact.kind == "INPUT_NEED":
        proposal = InputClarificationNeed.model_validate_json(artifact.document_json)
        profile = next(
            (p for p in packet.target_profiles if p.target_id == proposal.target_id), None
        )
        if (
            profile is None
            or proposal
            not in evaluate_gate_a_with_needs(
                packet,
                TargetRef(kind=profile.target_kind, id=profile.target_id),
                artifact_proposed_needs(committed, proposal.target_id)[0],
            )[1]
        ):
            raise Phase7AuthorityError("Input clarification differs from sealed Gate A")
    elif artifact.kind == "COUNTERFACTUAL":
        localization = CounterfactualLocalization.model_validate_json(artifact.document_json)
        profile = next(
            (p for p in packet.target_profiles if p.target_id == localization.target_id), None
        )
        if profile is None:
            raise Phase7AuthorityError("Counterfactual target is absent from packet")
        proposal = validate_counterfactual(
            packet, TargetRef(kind=profile.target_kind, id=profile.target_id), localization
        )
    elif artifact.kind in {"ROBUSTNESS_QUALIFICATION", "DOMAIN_QUALIFICATION"}:
        model = (
            RobustnessQualification
            if artifact.kind == "ROBUSTNESS_QUALIFICATION"
            else DomainQualification
        )
        proposal = model.model_validate_json(artifact.document_json)
        profile = next(
            (p for p in packet.target_profiles if p.target_id == proposal.target_id), None
        )
        if profile is None:
            raise Phase7AuthorityError("Qualification target is absent from packet")
        defaults = _default_qualifications(
            context, TargetRef(kind=profile.target_kind, id=profile.target_id)
        )
        if proposal != defaults[0 if artifact.kind == "ROBUSTNESS_QUALIFICATION" else 1]:
            raise Phase7AuthorityError("Qualification has no production issuer authority")
    else:
        raise Phase7AuthorityError("Unsupported Phase 7 artifact kind")
    if (
        proposal.assessment_id != artifact.assessment_id
        or proposal.assessment_context_id != artifact.assessment_context_id
        or proposal.phase6_snapshot_id != artifact.phase6_snapshot_id
        or proposal.target_id != artifact.target_id
        or artifact.document_json != canonical_json(proposal)
    ):
        raise Phase7AuthorityError("Artifact document differs from its scoped proposal")
    validate_semantic_execution(artifact, committed)
    with Session(engine) as session, session.begin():
        validate_semantic_execution(artifact, load_phase7_artifacts_in_session(session, run_id))
        existing = session.get(Phase7ArtifactRow, artifact.artifact_id)
        if existing is not None:
            if existing.document_json != canonical_json(artifact):
                raise Phase7AuthorityError("Artifact ID conflicts with existing content")
            return artifact.artifact_id
        if artifact.kind == "JUDGE_PROBE":
            probe = JudgeProbeRegistration.model_validate_json(artifact.document_json)
            registered = tuple(
                JudgeProbeRegistration.model_validate_json(
                    Phase7Artifact.model_validate_json(row.document_json).document_json
                )
                for row in session.scalars(
                    select(Phase7ArtifactRow).where(
                        Phase7ArtifactRow.run_id == run_id, Phase7ArtifactRow.kind == "JUDGE_PROBE"
                    )
                )
            )
            registered = tuple(p for p in registered if p.dispute_id == probe.dispute_id)
            if any(
                p.probe_role == probe.probe_role or p.model_config_id == probe.model_config_id
                for p in registered
            ):
                raise Phase7AuthorityError("Judge probe designation/configuration is immutable")
            if probe.probe_role == "PRIMARY" and (
                registered or run.state != Phase7RunState.FIRST_PASSES_COMPLETE
            ):
                raise Phase7AuthorityError("Primary probe must precede judging")
            if probe.probe_role == "ALTERNATE" and (
                len(registered) != 1
                or registered[0].probe_role != "PRIMARY"
                or run.state != Phase7RunState.JUDGING
            ):
                raise Phase7AuthorityError("Alternate probe requires a sealed primary")
        if first_pass:
            same_role_target = tuple(
                session.scalars(
                    select(Phase7ArtifactRow).where(
                        Phase7ArtifactRow.run_id == run_id,
                        Phase7ArtifactRow.kind == artifact.kind,
                        Phase7ArtifactRow.target_id == artifact.target_id,
                    )
                )
            )
            if same_role_target:
                raise Phase7AuthorityError("Run already has this first-pass role for target")
        if artifact.kind == "REBUTTAL":
            if rebuttal_role is None:
                raise Phase7AuthorityError("Rebuttal role is missing")
            prior_rebuttals = tuple(
                session.scalars(
                    select(Phase7ArtifactRow).where(
                        Phase7ArtifactRow.run_id == run_id,
                        Phase7ArtifactRow.kind == "REBUTTAL",
                    )
                )
            )
            if any(
                RebuttalCase.model_validate_json(
                    Phase7Artifact.model_validate_json(row.document_json).document_json
                ).role
                == rebuttal_role
                for row in prior_rebuttals
            ):
                raise Phase7AuthorityError("Run already has a rebuttal for this role")
        if artifact.kind == "RESEARCH_GAP":
            if research_request_id is None:
                raise Phase7AuthorityError("Research request ID is missing")
            prior_gaps = tuple(
                session.scalars(
                    select(Phase7ArtifactRow).where(
                        Phase7ArtifactRow.run_id == run_id,
                        Phase7ArtifactRow.kind == "RESEARCH_GAP",
                    )
                )
            )
            if any(
                ResearchGapRequest.model_validate_json(
                    Phase7Artifact.model_validate_json(row.document_json).document_json
                ).request_id
                == research_request_id
                for row in prior_gaps
            ):
                raise Phase7AuthorityError("Run already records this research request ID")
        session.add(
            Phase7ArtifactRow(
                artifact_id=artifact.artifact_id,
                run_id=run_id,
                context_id=artifact.assessment_context_id,
                assessment_id=artifact.assessment_id,
                snapshot_id=artifact.phase6_snapshot_id,
                kind=artifact.kind,
                target_id=artifact.target_id,
                document_json=canonical_json(artifact),
            )
        )
    return artifact.artifact_id


def transition_phase7_run(
    engine: Engine,
    load_context: Callable[..., SealedAssessmentContext],
    load_view: Callable[..., Phase6AssessmentView],
    run_id: str,
    *,
    expected_state: Phase7RunState,
    next_state: Phase7RunState,
) -> Phase7RunTransition:
    expected_role_targets: set[tuple[str, str]] | None = None
    if next_state == Phase7RunState.FIRST_PASSES_COMPLETE:
        run_before = load_phase7_run(engine, run_id)
        context = load_context(
            run_before.assessment_id, context_id=run_before.assessment_context_id
        )
        packet = build_adjudication_case(
            context,
            load_view(run_before.assessment_id, snapshot_id=run_before.phase6_snapshot_id),
        )
        if packet.case_id != run_before.case_id:
            raise Phase7AuthorityError("Run case packet changed before first-pass completion")
        expected_role_targets = {
            (kind, target_id)
            for target_id in packet.target_ids
            for kind in ("PROSECUTION_CASE", "DEFENSE_CASE")
        }
    with Session(engine) as session, session.begin():
        row = session.get(Phase7RunRow, run_id)
        if row is None:
            raise Phase7AuthorityError("Phase 7 run is missing")
        run = Phase7RunRecord.model_validate_json(row.document_json)
        predecessor = _current_transition(session, run_id)
        if predecessor.state != expected_state:
            raise Phase7AuthorityError("Run changed before expected transition")
        if predecessor.state in {
            Phase7RunState.FROZEN,
            Phase7RunState.ABSTAINED,
            Phase7RunState.FAILED,
            Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE,
        }:
            raise Phase7AuthorityError("Terminal run cannot transition")
        allowed_next = _allowed_run_transitions()
        if next_state not in allowed_next.get(predecessor.state, set()):
            raise Phase7AuthorityError("Invalid run transition")
        if next_state == Phase7RunState.FIRST_PASSES_COMPLETE:
            artifacts = tuple(
                session.scalars(select(Phase7ArtifactRow).where(Phase7ArtifactRow.run_id == run_id))
            )
            artifacts = tuple(
                item for item in artifacts if item.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
            )
            actual_role_targets = {(item.kind, item.target_id) for item in artifacts}
            if (
                not expected_role_targets
                or actual_role_targets != expected_role_targets
                or len(artifacts) != len(actual_role_targets)
            ):
                raise Phase7AuthorityError("Both first passes for every target must be committed")
        transition = Phase7RunTransition(
            transition_id="p7transition_"
            + canonical_hash(
                {"run_id": run_id, "predecessor_id": predecessor.transition_id, "state": next_state}
            ),
            run_id=run_id,
            predecessor_id=predecessor.transition_id,
            assessment_id=run.assessment_id,
            assessment_context_id=run.assessment_context_id,
            phase6_snapshot_id=run.phase6_snapshot_id,
            state=next_state,
        )
        session.add(
            Phase7RunTransitionRow(
                transition_id=transition.transition_id,
                run_id=run_id,
                predecessor_id=predecessor.transition_id,
                state=next_state,
                document_json=canonical_json(transition),
            )
        )
    return transition


def complete_phase7_research(
    engine: Engine,
    load_context: Callable[..., SealedAssessmentContext],
    load_view: Callable[..., Phase6AssessmentView],
    run_id: str,
    outcome: ResearchEscalationOutcome,
) -> ResearchContinuation:
    """Commit a research-only successor, supersession and fresh run atomically."""

    outcome = ResearchEscalationOutcome.model_validate_json(outcome.model_dump_json())
    old_run = load_phase7_run(engine, run_id)
    if old_run.state != Phase7RunState.ESCALATION_PENDING:
        raise Phase7AuthorityError("Research completion requires ESCALATION_PENDING run")
    old_context = load_context(old_run.assessment_id, context_id=old_run.assessment_context_id)
    if (
        outcome.assessment_id != old_run.assessment_id
        or outcome.assessment_context_id != old_run.assessment_context_id
        or outcome.phase6_snapshot_id != old_run.phase6_snapshot_id
    ):
        raise Phase7AuthorityError("Research outcome belongs to another assessment world-state")
    if (
        outcome.updated_manifest.cir != old_context.manifest.cir
        or outcome.updated_manifest.sufficiency != old_context.manifest.sufficiency
        or outcome.updated_manifest.mcu_graph != old_context.manifest.mcu_graph
    ):
        raise Phase7AuthorityError("Research escalation cannot rewrite the user's target input")
    old_usage = old_context.manifest.budget_usage or BudgetUsage()
    for dimension in (
        "provider_calls",
        "llm_input_tokens",
        "llm_output_tokens",
        "retrieved_documents",
        "full_text_fetches",
        "deep_search_rounds",
        "elapsed_seconds",
    ):
        before = getattr(old_usage, dimension)
        after = getattr(outcome.budget_usage, dimension)
        cost = getattr(outcome.cost, dimension)
        if after < before or abs((after - before) - cost) > 0.000001:
            raise Phase7AuthorityError("Research cost differs from cumulative budget change")
    if (
        outcome.updated_manifest.query_history[: len(old_context.manifest.query_history)]
        != old_context.manifest.query_history
        or outcome.updated_manifest.providers_attempted[
            : len(old_context.manifest.providers_attempted)
        ]
        != old_context.manifest.providers_attempted
    ):
        raise Phase7AuthorityError("Research history cannot erase prior attempts")
    new_view = load_view(old_run.assessment_id, snapshot_id=outcome.updated_snapshot_id)
    _validate_manifest_against_view(outcome.updated_manifest, new_view)
    manifest_digest = outcome.updated_manifest.content_digest()
    view_digest = canonical_hash(new_view)
    manifest_id = "p7manifest_" + manifest_digest
    context_id = "p7ctx_" + canonical_hash(
        {
            "assessment_id": str(old_run.assessment_id),
            "snapshot_id": outcome.updated_snapshot_id,
            "phase6_view_digest": view_digest,
            "manifest_digest": manifest_digest,
        }
    )
    no_op = (
        outcome.updated_snapshot_id == old_context.snapshot_id
        and manifest_digest == old_context.manifest_digest
        and view_digest == old_context.phase6_view_digest
    )
    new_context = SealedAssessmentContext(
        context_id=context_id,
        assessment_id=old_run.assessment_id,
        snapshot_id=outcome.updated_snapshot_id,
        phase6_view_digest=view_digest,
        manifest_id=manifest_id,
        manifest_digest=manifest_digest,
        manifest=outcome.updated_manifest,
        parent_context_id=None if no_op else old_context.context_id,
    )
    if no_op and (
        not is_true_noop(old_context, new_context)
        or outcome.attempted_query_ids
        or outcome.new_source_ids
        or any(
            value != 0
            for value in outcome.cost.model_dump().values()
            if isinstance(value, (int, float))
        )
    ):
        raise Phase7AuthorityError("Reported research action is not a proven true no-op")
    new_run: Phase7RunRecord | None = None
    initial: Phase7RunTransition | None = None
    if not no_op:
        token = uuid4().hex
        packet = build_adjudication_case(new_context, new_view)
        new_run = Phase7RunRecord(
            run_id="p7run_"
            + canonical_hash(
                {"context_id": context_id, "case_id": packet.case_id, "attempt_token": token}
            ),
            attempt_token=token,
            case_id=packet.case_id,
            assessment_id=old_run.assessment_id,
            assessment_context_id=context_id,
            phase6_snapshot_id=outcome.updated_snapshot_id,
        )
        initial = Phase7RunTransition(
            transition_id="p7transition_"
            + canonical_hash({"run_id": new_run.run_id, "state": "CASE_BUILT"}),
            run_id=new_run.run_id,
            assessment_id=new_run.assessment_id,
            assessment_context_id=new_run.assessment_context_id,
            phase6_snapshot_id=new_run.phase6_snapshot_id,
            state=Phase7RunState.CASE_BUILT,
        )
    with Session(engine) as session, session.begin():
        predecessor = _current_transition(session, run_id)
        if predecessor.state != Phase7RunState.ESCALATION_PENDING:
            raise Phase7AuthorityError("Research run changed before completion")
        gap_rows = tuple(
            session.scalars(
                select(Phase7ArtifactRow).where(
                    Phase7ArtifactRow.run_id == run_id,
                    Phase7ArtifactRow.kind == "RESEARCH_GAP",
                )
            )
        )
        matching = [
            ResearchGapRequest.model_validate_json(
                Phase7Artifact.model_validate_json(row.document_json).document_json
            )
            for row in gap_rows
            if ResearchGapRequest.model_validate_json(
                Phase7Artifact.model_validate_json(row.document_json).document_json
            ).request_id
            == outcome.request_id
        ]
        if len(matching) != 1:
            raise Phase7AuthorityError("Completed research lacks an accepted request artifact")
        old_packet = build_adjudication_case(
            old_context, load_view(old_run.assessment_id, snapshot_id=old_run.phase6_snapshot_id)
        )
        dispositions = [
            ResearchGapDisposition.model_validate_json(
                Phase7Artifact.model_validate_json(row.document_json).document_json
            )
            for row in session.scalars(
                select(Phase7ArtifactRow).where(
                    Phase7ArtifactRow.run_id == run_id,
                    Phase7ArtifactRow.kind == "RESEARCH_GAP_DISPOSITION",
                )
            )
        ]
        accepted = [
            d for d in dispositions if d.request_id == outcome.request_id and d.status == "ACCEPT"
        ]
        if len(accepted) != 1:
            raise Phase7AuthorityError("Research completion lacks validated ACCEPT disposition")
        parent_artifacts = load_phase7_artifacts_in_session(session, run_id)
        if (
            matching[0].material_gate == "D"
            and artifact_proposed_needs(parent_artifacts, matching[0].target_id)[0]
        ):
            raise Phase7AuthorityError("Gate A clarification prevents Gate D continuation")
        validate_research_disposition(matching[0], accepted[0], old_context, old_packet)
        next_state = (
            (
                Phase7RunState.JUDGING
                if session.scalar(
                    select(Phase7RunTransitionRow.state).where(
                        Phase7RunTransitionRow.transition_id == predecessor.predecessor_id
                    )
                )
                == Phase7RunState.JUDGING
                else Phase7RunState.FIRST_PASSES_COMPLETE
            )
            if no_op
            else Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE
        )
        transition = Phase7RunTransition(
            transition_id="p7transition_"
            + canonical_hash(
                {
                    "run_id": run_id,
                    "predecessor_id": predecessor.transition_id,
                    "state": next_state,
                }
            ),
            run_id=run_id,
            predecessor_id=predecessor.transition_id,
            assessment_id=old_run.assessment_id,
            assessment_context_id=old_run.assessment_context_id,
            phase6_snapshot_id=old_run.phase6_snapshot_id,
            state=next_state,
        )
        if not no_op:
            if new_run is None or initial is None:
                raise Phase7AuthorityError("Successor run identity is missing")
            manifest_row = session.get(Phase7InputManifestRow, manifest_id)
            if manifest_row is None:
                session.add(
                    Phase7InputManifestRow(
                        manifest_id=manifest_id,
                        assessment_id=old_run.assessment_id,
                        document_json=canonical_json(outcome.updated_manifest),
                    )
                )
            elif manifest_row.document_json != canonical_json(outcome.updated_manifest):
                raise Phase7AuthorityError("Successor manifest identity conflicts")
            if session.get(Phase7AssessmentContextRow, context_id) is not None:
                raise Phase7AuthorityError("Successor context already exists for another attempt")
            session.add(
                Phase7AssessmentContextRow(
                    context_id=context_id,
                    assessment_id=old_run.assessment_id,
                    snapshot_id=outcome.updated_snapshot_id,
                    manifest_id=manifest_id,
                    parent_context_id=old_context.context_id,
                    document_json=canonical_json(new_context),
                )
            )
            session.add(
                Phase7RunRow(
                    run_id=new_run.run_id,
                    context_id=context_id,
                    assessment_id=new_run.assessment_id,
                    snapshot_id=new_run.phase6_snapshot_id,
                    attempt_token=new_run.attempt_token,
                    document_json=canonical_json(new_run),
                )
            )
            session.add(
                Phase7RunTransitionRow(
                    transition_id=initial.transition_id,
                    run_id=new_run.run_id,
                    predecessor_id=None,
                    state=initial.state,
                    document_json=canonical_json(initial),
                )
            )
        session.add(
            Phase7RunTransitionRow(
                transition_id=transition.transition_id,
                run_id=run_id,
                predecessor_id=predecessor.transition_id,
                state=next_state,
                document_json=canonical_json(transition),
            )
        )
    loaded_context = load_context(old_run.assessment_id, context_id=context_id)
    if not no_op and new_run is None:
        raise Phase7AuthorityError("Successor run was not committed")
    return ResearchContinuation(
        context=loaded_context,
        run_id=run_id if new_run is None else new_run.run_id,
        restarted=not no_op,
    )


def _artifact_documents[T: TargetScoped](
    artifacts: tuple[Phase7Artifact, ...], kind: str, model: type[T]
) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(item.document_json) for item in artifacts if item.kind == kind
    )


def _one_for_target[T: TargetScoped](documents: tuple[T, ...], target_id: str) -> T:
    matches = tuple(item for item in documents if item.target_id == target_id)
    if len(matches) != 1:
        raise Phase7AuthorityError(
            "Freeze needs exactly one scoped gate or qualification per target"
        )
    return matches[0]


def _validate_phase7_freeze_in_session(
    session: Session,
    load_view: Callable[..., Phase6AssessmentView],
    run_id: str,
    proposed: FrozenAdjudication,
) -> tuple[Phase7RunRecord, tuple[Phase7Artifact, ...]]:
    run = load_phase7_run_in_session(session, run_id)
    if run.state not in {Phase7RunState.JUDGING, Phase7RunState.FROZEN, Phase7RunState.ABSTAINED}:
        raise Phase7AuthorityError(
            "Freeze requires completed judging, never a FAILED or superseded run"
        )
    if (
        proposed.run_id != run_id
        or proposed.assessment_id != run.assessment_id
        or proposed.assessment_context_id != run.assessment_context_id
        or proposed.phase6_snapshot_id != run.phase6_snapshot_id
    ):
        raise Phase7AuthorityError("Frozen proposal has foreign run/context/snapshot scope")
    if (
        proposed.method_version != "phase7-adjudication-v1"
        or proposed.policy_version != POLICY_VERSION
        or proposed.adjudication_id != phase7_frozen_id(proposed)
    ):
        raise Phase7AuthorityError("Frozen identity or method/policy version is stale")
    view = load_view(run.assessment_id, snapshot_id=run.phase6_snapshot_id)
    context = load_phase7_context_in_session(
        session,
        load_view,
        run.assessment_id,
        context_id=run.assessment_context_id,
    )
    packet = build_adjudication_case(context, view)
    if (
        proposed.case_id != packet.case_id
        or run.case_id != packet.case_id
        or proposed.as_of != packet.as_of
    ):
        raise Phase7AuthorityError("Frozen packet identity or cutoff has changed")
    expected_targets = tuple(
        TargetRef(kind=p.target_kind, id=p.target_id)
        for p in sorted(packet.target_profiles, key=lambda p: p.target_id)
    )
    if proposed.expected_targets != expected_targets:
        raise Phase7AuthorityError("Frozen target universe differs from repository packet")
    artifacts = load_phase7_artifacts_in_session(session, run_id)
    if set(proposed.dependency_ids) != {item.artifact_id for item in artifacts}:
        raise Phase7AuthorityError("Frozen dependencies do not exactly cover committed artifacts")
    models: dict[str, type[TargetScoped]] = {
        "SEMANTIC_CONFIGURATION": SemanticConfiguration,
        "PROSECUTION_CASE": ProsecutionCase,
        "DEFENSE_CASE": DefenseCase,
        "REBUTTAL": RebuttalCase,
        "DISPUTE": Dispute,
        "RESEARCH_GAP": ResearchGapRequest,
        "RESEARCH_GAP_DISPOSITION": ResearchGapDisposition,
        "INPUT_NEED": InputClarificationNeed,
        "JUDGE_RUN": CounterbalanceRun,
        "JUDGE_PROBE": JudgeProbeRegistration,
        "COUNTERBALANCE_COMPARISON": CounterbalanceComparison,
        "JUDGE_RESOLUTION": JudgeResolution,
        "GATE_A": GateAFinding,
        "GATE_B": GateBFinding,
        "GATE_C": GateCFinding,
        "GATE_D": GateDFinding,
        "ROBUSTNESS_QUALIFICATION": RobustnessQualification,
        "DOMAIN_QUALIFICATION": DomainQualification,
        "COUNTERFACTUAL": CounterfactualLocalization,
    }
    for artifact in artifacts:
        if artifact.kind not in models:
            raise Phase7AuthorityError("Frozen dependency has unsupported artifact kind")
        document = models[artifact.kind].model_validate_json(artifact.document_json)
        if (
            artifact.run_id != run_id
            or artifact.assessment_id != run.assessment_id
            or artifact.assessment_context_id != run.assessment_context_id
            or artifact.phase6_snapshot_id != run.phase6_snapshot_id
            or artifact.target_id not in packet.target_ids
            or (
                document.assessment_id,
                document.assessment_context_id,
                document.phase6_snapshot_id,
                document.target_id,
            )
            != (
                artifact.assessment_id,
                artifact.assessment_context_id,
                artifact.phase6_snapshot_id,
                artifact.target_id,
            )
            or artifact.document_json != canonical_json(document)
            or artifact.artifact_id
            != phase7_artifact_id(run_id, artifact.kind, artifact.document_json, artifact.execution)
        ):
            raise Phase7AuthorityError(
                "Frozen dependency identity or canonical content has changed"
            )
    for artifact in artifacts:
        if artifact.kind == "SEMANTIC_CONFIGURATION":
            validate_semantic_configuration(
                SemanticConfiguration.model_validate_json(artifact.document_json)
            )
        validate_semantic_execution(artifact, artifacts)
    prosecutions = _artifact_documents(artifacts, "PROSECUTION_CASE", ProsecutionCase)
    defenses = _artifact_documents(artifacts, "DEFENSE_CASE", DefenseCase)
    rebuttals = tuple(
        sorted(
            _artifact_documents(artifacts, "REBUTTAL", RebuttalCase), key=lambda r: r.rebuttal_id
        )
    )
    if len({r.role for r in rebuttals}) != len(rebuttals):
        raise Phase7AuthorityError("Frozen run exceeds one rebuttal per role")
    stored_disputes = _artifact_documents(artifacts, "DISPUTE", Dispute)
    probes = _artifact_documents(artifacts, "JUDGE_PROBE", JudgeProbeRegistration)
    judge_runs = _artifact_documents(artifacts, "JUDGE_RUN", CounterbalanceRun)
    comparisons = _artifact_documents(
        artifacts, "COUNTERBALANCE_COMPARISON", CounterbalanceComparison
    )
    resolutions = _artifact_documents(artifacts, "JUDGE_RESOLUTION", JudgeResolution)
    localizations = _artifact_documents(artifacts, "COUNTERFACTUAL", CounterfactualLocalization)
    needs = _artifact_documents(artifacts, "INPUT_NEED", InputClarificationNeed)
    gaps = _artifact_documents(artifacts, "RESEARCH_GAP", ResearchGapRequest)
    for gap in gaps:
        validate_research_gap_request(gap, packet)
        known_arguments = (
            {
                a.argument_id
                for p in prosecutions
                if p.target_id == gap.target_id
                for a in p.challenges
            }
            | {
                point.defense_id
                for defense in defenses
                if defense.target_id == gap.target_id
                for point in defense.points
            }
            | {
                argument_id
                for dispute in stored_disputes
                if dispute.target_id == gap.target_id
                for argument_id in dispute.argument_ids
            }
        )
        if set(gap.linked_argument_ids) - known_arguments:
            raise Phase7AuthorityError("Frozen research gap links an uncommitted argument")
    dispositions = _artifact_documents(
        artifacts, "RESEARCH_GAP_DISPOSITION", ResearchGapDisposition
    )
    for target in expected_targets:
        _, proposed_gaps = artifact_proposed_needs(artifacts, target.id)
        for proposed_gap in proposed_gaps:
            joined = tuple(
                g
                for g in gaps
                if g.request_id == proposed_gap.request_id and g.target_id == target.id
            )
            if len(joined) != 1 or joined[0].model_copy(
                update={"dispatch_allowance": None}
            ) != proposed_gap.model_copy(update={"dispatch_allowance": None}):
                raise Phase7AuthorityError("Frozen proposed research gap lacks exact dependency")
            if (
                len(
                    [
                        d
                        for d in dispositions
                        if d.request_id == proposed_gap.request_id and d.target_id == target.id
                    ]
                )
                != 1
            ):
                raise Phase7AuthorityError("Frozen proposed research gap lacks disposition")
    if len({(d.target_id, d.request_id) for d in dispositions}) != len(dispositions):
        raise Phase7AuthorityError("Research request has conflicting dispositions")
    for disposition in dispositions:
        joined = tuple(
            g
            for g in gaps
            if g.request_id == disposition.request_id and g.target_id == disposition.target_id
        )
        if len(joined) != 1:
            raise Phase7AuthorityError("Research disposition lacks exact request dependency")
        validate_research_disposition(joined[0], disposition, context, packet)
    actual_findings: list[TargetFinding] = []
    expected_needs: list[InputClarificationNeed] = []
    required_disputes: list[Dispute] = []
    used_judge_runs: set[str] = set()
    used_comparisons: set[str] = set()
    used_resolutions: set[str] = set()
    for target in expected_targets:
        prosecution = validate_prosecution_case(_one_for_target(prosecutions, target.id), packet)
        defense = validate_defense_case(_one_for_target(defenses, target.id), packet)
        target_rebuttals = tuple(r for r in rebuttals if r.target_id == target.id)
        base = material_disputes(prosecution, defense, packet)
        current = neutral_review_issues(prosecution, defense, packet, rebuttals=target_rebuttals)
        required_disputes.extend(current)
        valid_disputes = (*base, *current)
        for dispute in stored_disputes:
            if dispute.target_id == target.id and dispute not in valid_disputes:
                raise Phase7AuthorityError("Frozen dispute omits or replaces a validated candidate")
        if any(dispute not in stored_disputes for dispute in current):
            raise Phase7AuthorityError("Frozen run lacks the complete current dispute set")
        for rebuttal in target_rebuttals:
            validate_rebuttal_case(rebuttal, packet)
            base_by_id = {d.dispute_id: d for d in base}
            if not set(rebuttal.dispute_ids) <= set(base_by_id) or not set(
                rebuttal.argument_ids
            ) <= {arg for d in base for arg in d.argument_ids}:
                raise Phase7AuthorityError("Frozen rebuttal links unselected arguments")
        proposed_needs, proposed_gaps = artifact_proposed_needs(artifacts, target.id)
        gate_a, input_needs = evaluate_gate_a_with_needs(packet, target, proposed_needs)
        gate_b = evaluate_gate_b_with_gaps(packet, target, proposed_gaps)
        expected_needs.extend(input_needs)
        if (
            session.scalar(
                select(Phase7QualificationRefRow.qualification_id).where(
                    Phase7QualificationRefRow.context_id == context.context_id,
                    Phase7QualificationRefRow.target_id == target.id,
                )
            )
            is not None
        ):
            raise Phase7AuthorityError("No production qualification issuer is registered")
        robustness, domain = _default_qualifications(context, target)
        if (
            _one_for_target(
                _artifact_documents(artifacts, "ROBUSTNESS_QUALIFICATION", RobustnessQualification),
                target.id,
            )
            != robustness
            or _one_for_target(
                _artifact_documents(artifacts, "DOMAIN_QUALIFICATION", DomainQualification),
                target.id,
            )
            != domain
        ):
            raise Phase7AuthorityError("Frozen qualification is not repository validated")
        witnesses: list[JudgeFinding] = []
        stability = JudgeStability.STABLE
        for dispute in current:
            facts = GateFacts(
                gate_a=gate_a,
                gate_b=gate_b,
                undisputed_c=evaluate_gate_c(packet, target, None),
                undisputed_d=evaluate_gate_d(packet, target, None, None),
                robustness=robustness,
                domain=domain,
            )
            impact = classify_dispute_impact(
                dispute,
                packet,
                facts,
                prosecution=prosecution,
                defense=defense,
                rebuttals=target_rebuttals,
            )
            arguments = dispute_arguments(dispute, prosecution, defense, rebuttals=target_rebuttals)
            dispute_runs = tuple(r for r in judge_runs if r.dispute_id == dispute.dispute_id)
            model_ids = {r.model_config_id for r in dispute_runs}
            if not model_ids or len(model_ids) > 2:
                raise Phase7AuthorityError(
                    "Frozen dispute requires primary and at most one alternate probe"
                )
            pair_by_model: dict[str, CounterbalanceComparison] = {}
            for model_id in sorted(model_ids):
                pair = tuple(r for r in dispute_runs if r.model_config_id == model_id)
                if len(pair) != 2:
                    raise Phase7AuthorityError(
                        "Frozen high-impact or invoked alternate lacks reversed-order pair"
                    )
                ordered = tuple(sorted(pair, key=lambda r: r.order))
                for judge_run in ordered:
                    validate_judge_finding(judge_run.finding, packet, arguments)
                    expected_id = "p7judge_" + canonical_hash(
                        {
                            "run_id": run_id,
                            "dispute_id": dispute.dispute_id,
                            "packet_id": packet.case_id,
                            "arguments": [arg.model_dump(mode="json") for arg in arguments],
                            "order": list(judge_run.order),
                            "model_config_id": model_id,
                            "rubric": JUDGE_RUBRIC_VERSION,
                        }
                    )
                    if (
                        judge_run.run_id != expected_id
                        or judge_run.packet_id != packet.case_id
                        or judge_run.evidence_digest != packet.digest
                        or judge_run.argument_ids != tuple(arg.argument_id for arg in arguments)
                        or judge_run.rubric_version != JUDGE_RUBRIC_VERSION
                    ):
                        raise Phase7AuthorityError(
                            "Frozen judge packet, arguments, evidence or rubric differs"
                        )
                    used_judge_runs.add(judge_run.run_id)
                comparison = compare_counterbalance(ordered[0], ordered[1])
                if comparison not in comparisons:
                    raise Phase7AuthorityError(
                        "Frozen run lacks its exact counterbalance comparison"
                    )
                pair_by_model[model_id] = comparison
                used_comparisons.add(comparison.comparison_id)
            target_resolutions = tuple(
                r
                for r in resolutions
                if r.primary_comparison_id in {c.comparison_id for c in pair_by_model.values()}
            )
            if len(target_resolutions) != 1:
                raise Phase7AuthorityError("Frozen dispute requires exactly one judge resolution")
            resolution = target_resolutions[0]
            primary = next(
                c
                for c in pair_by_model.values()
                if c.comparison_id == resolution.primary_comparison_id
            )
            alternate = next(
                (
                    c
                    for c in pair_by_model.values()
                    if c.comparison_id == resolution.alternate_comparison_id
                ),
                None,
            )
            probe_by_role = {p.probe_role: p for p in probes if p.dispute_id == dispute.dispute_id}
            if (
                len(probe_by_role) != len(pair_by_model)
                or "PRIMARY" not in probe_by_role
                or probe_by_role["PRIMARY"].model_config_id != primary.model_config_id
                or (
                    alternate is not None
                    and (
                        "ALTERNATE" not in probe_by_role
                        or probe_by_role["ALTERNATE"].model_config_id != alternate.model_config_id
                    )
                )
            ):
                raise Phase7AuthorityError("Frozen primary/alternate designation differs")
            if (
                len(pair_by_model) != (2 if alternate else 1)
                or resolve_judge_comparisons(primary, alternate) != resolution
            ):
                raise Phase7AuthorityError(
                    "Frozen judge resolution omits a probe or votes an outcome"
                )
            used_resolutions.add(resolution.resolution_id)
            if resolution.resolved_semantics is None:
                stability = JudgeStability.MATERIAL_ORDER_INSTABILITY
            else:
                stable_pair = alternate if primary.resolution_if_stable is None else primary
                assert stable_pair is not None
                witness = stable_pair.first_finding
                if normalize_judge_finding(witness) != resolution.resolved_semantics:
                    raise Phase7AuthorityError(
                        "Resolved semantics differ from retained stable witness"
                    )
                witnesses.append(witness)
            if impact.level == "HIGH_IMPACT" and not dispute_runs:
                raise Phase7AuthorityError("High-impact dispute has no judge pair")
        witness = witnesses[0] if witnesses else None
        if len(witnesses) > 1:
            if len({(w.proposed_gate_c, w.proposed_gate_d) for w in witnesses}) != 1:
                stability = JudgeStability.MATERIAL_ORDER_INSTABILITY
                witness = None
            else:
                witness = witnesses[0].model_copy(
                    update={
                        "finding_id": "p7judge_"
                        + canonical_hash(
                            {
                                "resolved_witness_ids": cast(
                                    JsonValue, sorted(w.finding_id for w in witnesses)
                                )
                            }
                        ),
                        "accepted_challenge_ids": tuple(
                            sorted({arg for w in witnesses for arg in w.accepted_challenge_ids})
                        ),
                        "phase6_basis_ids": tuple(
                            sorted({ref for w in witnesses for ref in w.phase6_basis_ids})
                        ),
                    }
                )
        if stability == JudgeStability.MATERIAL_ORDER_INSTABILITY:
            witness = None
        target_localizations = tuple(item for item in localizations if item.target_id == target.id)
        if len(target_localizations) > 1:
            raise Phase7AuthorityError("Frozen target has ambiguous counterfactual localization")
        localization = (
            validate_counterfactual(packet, target, target_localizations[0])
            if target_localizations
            else None
        )
        if localization != (witness.counterfactual if witness is not None else None):
            raise Phase7AuthorityError("Counterfactual is not the resolved judge proposal")
        gate_c = evaluate_gate_c(packet, target, witness)
        gate_d = evaluate_gate_d(packet, target, witness, localization)
        for kind, model, expected_gate in (
            ("GATE_A", GateAFinding, gate_a),
            ("GATE_B", GateBFinding, gate_b),
            ("GATE_C", GateCFinding, gate_c),
            ("GATE_D", GateDFinding, gate_d),
        ):
            if (
                _one_for_target(_artifact_documents(artifacts, kind, model), target.id)
                != expected_gate
            ):
                raise Phase7AuthorityError(
                    "Frozen gate differs from repository facts and resolved semantics"
                )
        finding = VerdictPermissionPolicy().evaluate(
            packet=packet,
            gate_a=gate_a,
            gate_b=gate_b,
            gate_c=gate_c,
            gate_d=gate_d,
            stability=stability,
            robustness=robustness,
            domain=domain,
        )
        actual_findings.append(finding)
    if (
        set(used_judge_runs) != {r.run_id for r in judge_runs}
        or set(used_comparisons) != {c.comparison_id for c in comparisons}
        or set(used_resolutions) != {r.resolution_id for r in resolutions}
    ):
        raise Phase7AuthorityError("Frozen run contains unused or incomplete judge dependencies")
    if tuple(actual_findings) != proposed.target_findings:
        raise Phase7AuthorityError(
            "Frozen verdict or language permission differs from deterministic policy"
        )
    if proposed.overall_finding != compose_assessment(tuple(actual_findings), expected_targets):
        raise Phase7AuthorityError(
            "Frozen whole-assessment permission differs from scoped composition"
        )
    required_limits = {
        *proposed.overall_finding.limiting_factors,
        *(limit for case in prosecutions for limit in case.limitations),
        *(limit for case in defenses for limit in case.limitations),
        *(limit for rebuttal in rebuttals for limit in rebuttal.limitations),
        *(limit for r in resolutions for limit in r.limiting_factors),
        *(limit for r in judge_runs for limit in r.finding.limitations),
        *(
            limit
            for r in prosecutions
            for challenge in r.challenges
            for limit in challenge.limitations
        ),
        *(limit for r in defenses for point in r.points for limit in point.limitations),
    }
    if not required_limits <= set(proposed.limiting_factors):
        raise Phase7AuthorityError("Frozen proposal omits required limitations")
    required_questions = {
        *packet.manifest.remaining_gaps,
        *packet.manifest.cir.unknowns,
        *(
            question
            for kind, model in (
                ("GATE_A", GateAFinding),
                ("GATE_B", GateBFinding),
                ("GATE_C", GateCFinding),
                ("GATE_D", GateDFinding),
            )
            for gate in _artifact_documents(artifacts, kind, model)
            for question in gate.unresolved_questions
        ),
    }
    if set(proposed.unresolved_questions) != required_questions:
        raise Phase7AuthorityError("Frozen unresolved questions differ from committed gates")
    expected_history = _superseded_contexts_in_session(
        session, load_view, run.assessment_id, context
    )
    if set(proposed.superseded_context_ids) != expected_history:
        raise Phase7AuthorityError("Frozen supersession history is not repository validated")
    for significance in proposed.novelty_significance:
        gate = _one_for_target(
            _artifact_documents(artifacts, "GATE_D", GateDFinding), significance.target_id
        )
        expected_state = (
            gate.state if gate.state in {"SUBSTANTIVE", "NON_SUBSTANTIVE"} else "UNRESOLVED"
        )
        if (
            significance.significance != expected_state
            or significance.differentiator != gate.differentiator
        ):
            raise Phase7AuthorityError("Frozen novelty significance differs from Gate D")
    for value in proposed.value_findings:
        if not any(
            value.claim == claim.statement and value.maturity == claim.maturity
            for claim in packet.manifest.cir.claimed_advantages
        ):
            raise Phase7AuthorityError("Frozen value finding differs from sealed input claims")
    if set(needs) != set(expected_needs):
        raise Phase7AuthorityError("Frozen input clarifications differ from sealed Gate A needs")
    checks = (
        (
            proposed.role_case_ids,
            tuple(
                a.artifact_id for a in artifacts if a.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
            ),
        ),
        (proposed.rebuttal_ids, tuple(r.rebuttal_id for r in rebuttals)),
        (proposed.input_need_ids, tuple(n.need_id for n in needs)),
        (proposed.research_gap_ids, tuple(g.request_id for g in gaps)),
        (proposed.judge_run_ids, tuple(r.run_id for r in judge_runs)),
        (proposed.counterbalance_comparison_ids, tuple(c.comparison_id for c in comparisons)),
        (proposed.judge_resolution_ids, tuple(r.resolution_id for r in resolutions)),
        (proposed.counterfactual_ids, tuple(item.localization_id for item in localizations)),
        (
            proposed.qualification_ids,
            tuple(
                q.qualification_id
                for q in (
                    *_artifact_documents(
                        artifacts, "ROBUSTNESS_QUALIFICATION", RobustnessQualification
                    ),
                    *_artifact_documents(artifacts, "DOMAIN_QUALIFICATION", DomainQualification),
                )
            ),
        ),
    )
    if any(set(actual) != set(expected) for actual, expected in checks):
        raise Phase7AuthorityError(
            "Frozen typed reference sets do not exactly cover their dependencies"
        )
    return run, artifacts


def freeze_phase7_adjudication(
    engine: Engine,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    run_id: str,
    proposed: FrozenAdjudication,
) -> str:
    proposed = FrozenAdjudication.model_validate_json(proposed.model_dump_json())
    with Session(engine) as session, session.begin():
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")

        def load_view(assessment_id: AssessmentId, *, snapshot_id: str) -> Phase6AssessmentView:
            return load_view_in_session(session, assessment_id, snapshot_id=snapshot_id)

        run, artifacts = _validate_phase7_freeze_in_session(session, load_view, run_id, proposed)
        existing = session.scalar(
            select(Phase7FrozenManifestRow).where(Phase7FrozenManifestRow.run_id == run_id)
        )
        if existing is not None:
            if (
                existing.adjudication_id != proposed.adjudication_id
                or existing.document_json != canonical_json(proposed)
            ):
                raise Phase7AuthorityError("Frozen run identity conflicts with immutable content")
            dependencies = tuple(
                session.scalars(
                    select(Phase7FrozenDependencyRow.artifact_id).where(
                        Phase7FrozenDependencyRow.adjudication_id == proposed.adjudication_id
                    )
                )
            )
            if set(dependencies) != set(proposed.dependency_ids):
                raise Phase7AuthorityError("Frozen dependency rows are missing or inconsistent")
            return proposed.adjudication_id
        if run.state != Phase7RunState.JUDGING:
            raise Phase7AuthorityError("Terminal run has no authoritative frozen manifest")
        terminal = (
            Phase7RunState.ABSTAINED
            if proposed.overall_finding.verdict == VerdictState.UNASSESSABLE
            else Phase7RunState.FROZEN
        )
        predecessor = _current_transition(session, run_id)
        transition = Phase7RunTransition(
            assessment_id=run.assessment_id,
            assessment_context_id=run.assessment_context_id,
            phase6_snapshot_id=run.phase6_snapshot_id,
            run_id=run_id,
            predecessor_id=predecessor.transition_id,
            state=terminal,
            transition_id="p7transition_"
            + canonical_hash(
                {"run_id": run_id, "predecessor_id": predecessor.transition_id, "state": terminal}
            ),
        )
        session.add(
            Phase7FrozenManifestRow(
                adjudication_id=proposed.adjudication_id,
                run_id=run_id,
                context_id=run.assessment_context_id,
                assessment_id=run.assessment_id,
                snapshot_id=run.phase6_snapshot_id,
                document_json=canonical_json(proposed),
            )
        )
        session.flush()
        session.add_all(
            Phase7FrozenDependencyRow(
                adjudication_id=proposed.adjudication_id, artifact_id=a.artifact_id
            )
            for a in artifacts
        )
        session.add(
            Phase7RunTransitionRow(
                transition_id=transition.transition_id,
                run_id=run_id,
                predecessor_id=predecessor.transition_id,
                state=terminal,
                document_json=canonical_json(transition),
            )
        )
    return proposed.adjudication_id


def load_frozen_adjudication_in_session(
    session: Session,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
) -> FrozenAdjudication:
    """Revalidate the unchanged Phase 7 closure in the caller's explicit transaction."""
    row = session.get(Phase7FrozenManifestRow, adjudication_id)
    if row is None or row.assessment_id != assessment_id:
        raise Phase7AuthorityError("Frozen adjudication is missing or foreign")
    try:
        proposed = FrozenAdjudication.model_validate_json(row.document_json)
        if (
            proposed.adjudication_id != adjudication_id
            or proposed.run_id != row.run_id
            or proposed.assessment_id != row.assessment_id
            or proposed.assessment_context_id != row.context_id
            or proposed.phase6_snapshot_id != row.snapshot_id
            or canonical_json(proposed) != row.document_json
        ):
            raise Phase7AuthorityError("Frozen manifest columns or canonical content differ")

        def load_view(assessment_id: AssessmentId, *, snapshot_id: str) -> Phase6AssessmentView:
            return load_view_in_session(session, assessment_id, snapshot_id=snapshot_id)

        run, artifacts = _validate_phase7_freeze_in_session(
            session, load_view, proposed.run_id, proposed
        )
        expected_terminal = (
            Phase7RunState.ABSTAINED
            if proposed.overall_finding.verdict == VerdictState.UNASSESSABLE
            else Phase7RunState.FROZEN
        )
        if run.state != expected_terminal:
            raise Phase7AuthorityError("Frozen manifest lacks its committed terminal run state")
        dependencies = set(
            session.scalars(
                select(Phase7FrozenDependencyRow.artifact_id).where(
                    Phase7FrozenDependencyRow.adjudication_id == adjudication_id
                )
            )
        )
        if dependencies != set(proposed.dependency_ids) or dependencies != {
            artifact.artifact_id for artifact in artifacts
        }:
            raise Phase7AuthorityError("Frozen dependency rows are missing or inconsistent")
    except ValueError as exc:
        if isinstance(exc, Phase7AuthorityError):
            raise
        raise Phase7AuthorityError(f"Frozen dependency authority validation failed: {exc}") from exc
    return proposed


def load_frozen_adjudication(
    engine: Engine,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
) -> FrozenAdjudication:
    """Return repository authority only after checking the complete frozen closure."""
    with Session(engine) as session:
        session.connection().exec_driver_sql("BEGIN")
        proposed = load_frozen_adjudication_in_session(
            session, load_view_in_session, assessment_id, adjudication_id=adjudication_id
        )
        session.commit()
        return proposed


def _superseded_contexts_in_session(
    session: Session,
    load_view: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    context: SealedAssessmentContext,
) -> set[str]:
    ancestor = context.parent_context_id
    expected_history: set[str] = set()
    visited = {context.context_id}
    while ancestor is not None:
        if ancestor in visited:
            raise Phase7AuthorityError("Frozen context history contains a cycle")
        visited.add(ancestor)
        parent = load_phase7_context_in_session(
            session, load_view, assessment_id, context_id=ancestor
        )
        for parent_run in session.scalars(
            select(Phase7RunRow).where(Phase7RunRow.context_id == ancestor)
        ):
            if (
                load_phase7_run_in_session(session, parent_run.run_id).state
                == Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE
            ):
                parent_packet = build_adjudication_case(
                    parent, load_view(assessment_id, snapshot_id=parent.snapshot_id)
                )
                parent_artifacts = load_phase7_artifacts_in_session(session, parent_run.run_id)
                for gap_row in session.scalars(
                    select(Phase7ArtifactRow).where(
                        Phase7ArtifactRow.run_id == parent_run.run_id,
                        Phase7ArtifactRow.kind == "RESEARCH_GAP",
                    )
                ):
                    gap = ResearchGapRequest.model_validate_json(
                        Phase7Artifact.model_validate_json(gap_row.document_json).document_json
                    )
                    validate_research_gap_request(gap, parent_packet)
                    if (
                        gap.material_gate == "D"
                        and artifact_proposed_needs(parent_artifacts, gap.target_id)[0]
                    ):
                        raise Phase7AuthorityError(
                            "Superseded research substituted for Gate A input"
                        )
                    dispositions = _artifact_documents(
                        parent_artifacts, "RESEARCH_GAP_DISPOSITION", ResearchGapDisposition
                    )
                    matched = [d for d in dispositions if d.request_id == gap.request_id]
                    if len(matched) != 1:
                        raise Phase7AuthorityError("Superseded research lacks a disposition")
                    validate_research_disposition(gap, matched[0], parent, parent_packet)
                expected_history.add(ancestor)
        ancestor = parent.parent_context_id
    return expected_history


def load_phase7_superseded_contexts(
    engine: Engine,
    load_view: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    context_id: str,
) -> tuple[str, ...]:
    with Session(engine) as session:
        session.connection().exec_driver_sql("BEGIN")
        load_view = partial(load_view, session)
        context = load_phase7_context_in_session(
            session, load_view, assessment_id, context_id=context_id
        )
        result = tuple(
            sorted(_superseded_contexts_in_session(session, load_view, assessment_id, context))
        )
        session.commit()
        return result
