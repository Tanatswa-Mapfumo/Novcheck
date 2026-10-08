"""Real Phase 7 coordination over repository-owned assessment state."""

import json
from typing import cast

from pydantic import JsonValue

from novelty_harness.adjudication.frozen import (
    FrozenAdjudication,
    LanguagePermissionClass,
    TargetFinding,
    compose_assessment,
    phase7_frozen_id,
)
from novelty_harness.adjudication.gates import (
    evaluate_gate_a,
    evaluate_gate_a_with_needs,
    evaluate_gate_b,
    evaluate_gate_b_with_gaps,
    evaluate_gate_c,
    evaluate_gate_d,
    gate_d_research_gap,
)
from novelty_harness.adjudication.judge import (
    CounterbalanceComparison,
    CounterbalanceRun,
    GateFacts,
    JudgeFinding,
    JudgeResolution,
    JudgeStability,
    compare_counterbalance,
    resolve_judge_comparisons,
)
from novelty_harness.adjudication.models import Phase7RunState, TargetRef, TargetScoped
from novelty_harness.adjudication.needs import (
    ResearchContinuation,
    ResearchEscalationBudget,
    ResearchGapDisposition,
    ResearchGapRequest,
    artifact_proposed_needs,
)
from novelty_harness.adjudication.packet import build_adjudication_case
from novelty_harness.adjudication.policy import VerdictPermissionPolicy
from novelty_harness.adjudication.prompts import (
    JUDGE_RUBRIC_VERSION,
)
from novelty_harness.adjudication.repository import (
    Phase7AdjudicationRepository,
    Phase7AuthorityError,
)
from novelty_harness.adjudication.roles import (
    DefenseCase,
    ProsecutionCase,
    material_disputes,
    neutral_review_issues,
)
from novelty_harness.application.phase7_model_adapter import (
    Phase7ModelCallRecord,
    Phase7ModelOutputError,
)
from novelty_harness.application.phase7_research import dispatch_research_gap
from novelty_harness.application.phase7_roles import (
    make_phase7_artifact,
    run_independent_first_passes,
    run_neutral_judging,
    run_rebuttals,
)
from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import AssessmentStage, TraceStatus, VerdictState
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.ports.adjudication import Phase7Ports
from novelty_harness.runtime.budgets.controller import DIMENSIONS, BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink


def _resolved_witness(
    comparisons: tuple[CounterbalanceComparison, ...],
    resolutions: tuple[JudgeResolution, ...],
) -> tuple[JudgeFinding | None, JudgeStability]:
    witnesses: list[JudgeFinding] = []
    for resolution in resolutions:
        if resolution.resolved_semantics is None:
            return None, JudgeStability.MATERIAL_ORDER_INSTABILITY
        primary = next(
            c for c in comparisons if c.comparison_id == resolution.primary_comparison_id
        )
        stable = (
            primary
            if primary.resolution_if_stable is not None
            else next(
                c for c in comparisons if c.comparison_id == resolution.alternate_comparison_id
            )
        )
        witnesses.append(stable.first_finding)
    if not witnesses:
        return None, JudgeStability.STABLE
    if len({(w.proposed_gate_c, w.proposed_gate_d) for w in witnesses}) != 1:
        return None, JudgeStability.MATERIAL_ORDER_INSTABILITY
    if len(witnesses) == 1:
        return witnesses[0], JudgeStability.STABLE
    return witnesses[0].model_copy(
        update={
            "finding_id": "p7judge_"
            + canonical_hash(
                {
                    "resolved_witness_ids": cast(
                        JsonValue, sorted(w.finding_id for w in witnesses)
                    ),
                }
            ),
            "accepted_challenge_ids": tuple(
                sorted({arg for w in witnesses for arg in w.accepted_challenge_ids})
            ),
            "phase6_basis_ids": tuple(
                sorted({ref for w in witnesses for ref in w.phase6_basis_ids})
            ),
        }
    ), JudgeStability.STABLE


async def run_phase7(
    assessment_id: AssessmentId,
    *,
    context_id: str,
    repository: Phase7AdjudicationRepository,
    ports: Phase7Ports,
) -> FrozenAdjudication:
    return await _run_phase7_attempt(
        assessment_id, context_id=context_id, repository=repository, ports=ports
    )


async def _run_phase7_attempt(
    assessment_id: AssessmentId,
    *,
    context_id: str,
    repository: Phase7AdjudicationRepository,
    ports: Phase7Ports,
    existing_run_id: str | None = None,
    prior_issued: tuple[str, ...] = (),
) -> FrozenAdjudication:
    """Build independent cases, resolve semantics, freeze and reload authority."""
    context = repository.load_phase7_context(assessment_id, context_id=context_id)
    packet = build_adjudication_case(
        context,
        repository.load_phase6_assessment(
            assessment_id,
            snapshot_id=context.snapshot_id,
        ),
    )
    run = (
        repository.load_phase7_run(existing_run_id)
        if existing_run_id is not None
        else repository.begin_phase7_run(context.context_id)
    )
    run_id: str = run.run_id
    targets = tuple(
        TargetRef(kind=p.target_kind, id=p.target_id)
        for p in sorted(packet.target_profiles, key=lambda p: p.target_id)
    )
    try:
        issued: list[str] = list(prior_issued)
        while True:
            if ports.target_roles and frozenset(ports.target_roles) != packet.target_ids:
                raise Phase7AuthorityError(
                    "Configured role target universe differs from repository case"
                )
            for target in targets:
                role_ports = ports.target_roles.get(target.id)
                prosecution, defense = await run_independent_first_passes(
                    run_id,
                    packet,
                    role_ports.prosecutor if role_ports else ports.prosecutor,
                    role_ports.defender if role_ports else ports.defender,
                    repository,
                )
                if role_ports is not None and (
                    prosecution.target_id != target.id or defense.target_id != target.id
                ):
                    raise Phase7AuthorityError("Role output differs from the configured target")
            committed = repository.load_phase7_artifacts(run_id)
            current_prosecution = {
                a.target_id: ProsecutionCase.model_validate_json(a.document_json)
                for a in committed
                if a.kind == "PROSECUTION_CASE"
            }
            current_defense = {
                a.target_id: DefenseCase.model_validate_json(a.document_json)
                for a in committed
                if a.kind == "DEFENSE_CASE"
            }
            disputed_targets = {
                target.id
                for target in targets
                if material_disputes(
                    current_prosecution[target.id], current_defense[target.id], packet
                )
            }
            request: ResearchGapRequest | None = None
            if ports.research_escalation is not None:
                for target in targets:
                    role_needs, role_gaps = artifact_proposed_needs(committed, target.id)
                    gate_a, input_needs = evaluate_gate_a_with_needs(packet, target, role_needs)
                    gate_c = evaluate_gate_c(packet, target, None)
                    if (
                        gate_a.state == "INSUFFICIENT"
                        or input_needs
                        or (
                            gate_c.state == "DIRECT_ESTABLISHED"
                            and target.id not in disputed_targets
                            and not role_gaps
                        )
                    ):
                        continue
                    request = (
                        role_gaps[0]
                        if role_gaps
                        else gate_d_research_gap(
                            packet, target, evaluate_gate_d(packet, target, None, None)
                        )
                    )
                    if request is None and packet.manifest.remaining_gaps:
                        reason = packet.manifest.remaining_gaps[0]
                        request = ResearchGapRequest(
                            assessment_id=assessment_id,
                            assessment_context_id=context.context_id,
                            phase6_snapshot_id=context.snapshot_id,
                            target_id=target.id,
                            request_id="p7gap_"
                            + canonical_hash(
                                {"case_id": packet.case_id, "target": target.id, "gap": reason}
                            ),
                            requesting_stage="ADJUDICATION",
                            gap_type="COVERAGE",
                            reason=reason,
                            research_hypothesis=(
                                "A remaining reviewed research branch may change "
                                "the claim comparison"
                            ),
                            material_gate="B",
                            priority="HIGH",
                            stop_condition="Screen the remaining branch or record its limit",
                            provenance="SEALED_RESEARCH_GAP",
                        )
                    if request is not None:
                        break
            if request is None or ports.research_escalation is None:
                break
            configured_budget = ports.research_budget
            budget = ResearchEscalationBudget(
                limits=configured_budget.limits
                if configured_budget
                else context.manifest.budget_limits or BudgetLimits(),
                usage=BudgetUsage.model_validate(
                    {
                        dimension: max(
                            getattr(context.manifest.budget_usage or BudgetUsage(), dimension),
                            getattr(
                                configured_budget.usage if configured_budget else BudgetUsage(),
                                dimension,
                            ),
                        )
                        for dimension in DIMENSIONS
                    }
                ),
                max_requests=configured_budget.max_requests if configured_budget else 1,
                issued_request_ids=tuple(
                    dict.fromkeys(
                        (
                            *(configured_budget.issued_request_ids if configured_budget else ()),
                            *issued,
                        )
                    )
                ),
            )
            continuation = await dispatch_research_gap(
                run_id, request, packet, budget, ports.research_escalation, repository
            )
            if not isinstance(continuation, ResearchContinuation):
                break
            issued.append(request.request_id)
            if not continuation.restarted:
                break
            context = continuation.context
            run_id = str(continuation.run_id)
            packet = build_adjudication_case(
                context,
                repository.load_phase6_assessment(assessment_id, snapshot_id=context.snapshot_id),
            )
            targets = tuple(
                TargetRef(kind=p.target_kind, id=p.target_id)
                for p in sorted(packet.target_profiles, key=lambda p: p.target_id)
            )
        artifacts = repository.load_phase7_artifacts(run_id)
        prosecutions = {
            a.target_id: ProsecutionCase.model_validate_json(a.document_json)
            for a in artifacts
            if a.kind == "PROSECUTION_CASE"
        }
        defenses = {
            a.target_id: DefenseCase.model_validate_json(a.document_json)
            for a in artifacts
            if a.kind == "DEFENSE_CASE"
        }
        disputes = tuple(
            d
            for target in targets
            for d in material_disputes(
                prosecutions[target.id],
                defenses[target.id],
                packet,
            )
        )
        rebuttals = await run_rebuttals(
            run_id, packet, disputes, ports.prosecutor_rebuttal, ports.defender_rebuttal, repository
        )
        disputes = tuple(
            d
            for target in targets
            for d in neutral_review_issues(
                prosecutions[target.id],
                defenses[target.id],
                packet,
                rebuttals=tuple(
                    sorted(
                        (r for r in rebuttals if r.target_id == target.id),
                        key=lambda r: r.rebuttal_id,
                    )
                ),
            )
        )
        facts: dict[str, GateFacts] = {}
        for target in targets:
            robustness, domain = repository.load_phase7_qualifications(context.context_id, target)
            facts[target.id] = GateFacts(
                gate_a=evaluate_gate_a(packet, target)[0],
                gate_b=evaluate_gate_b(packet, target),
                undisputed_c=evaluate_gate_c(packet, target, None),
                undisputed_d=evaluate_gate_d(packet, target, None, None),
                robustness=robustness,
                domain=domain,
            )
        judge_runs = await run_neutral_judging(
            run_id, packet, disputes, facts, ports.judge, repository
        )
        alternate_runs: tuple[CounterbalanceRun, ...] = ()
        if disputes and ports.alternate_judge is not None:
            alternate_runs = await run_neutral_judging(
                run_id,
                packet,
                disputes,
                facts,
                ports.alternate_judge,
                repository,
            )
        comparisons: list[CounterbalanceComparison] = []
        resolutions: list[JudgeResolution] = []
        for dispute in disputes:
            primary_pair = tuple(r for r in judge_runs if r.dispute_id == dispute.dispute_id)
            primary = compare_counterbalance(*primary_pair)
            alternate_pair = tuple(r for r in alternate_runs if r.dispute_id == dispute.dispute_id)
            alternate = compare_counterbalance(*alternate_pair) if alternate_pair else None
            comparisons.extend((primary, *((alternate,) if alternate else ())))
            resolution = resolve_judge_comparisons(primary, alternate)
            repository.record_phase7_artifact(
                run_id, make_phase7_artifact(run_id, "JUDGE_RESOLUTION", resolution)
            )
            resolutions.append(resolution)
        semantic_artifacts = repository.load_phase7_artifacts(run_id)
        recorded_request_ids = {
            ResearchGapRequest.model_validate_json(a.document_json).request_id
            for a in semantic_artifacts
            if a.kind == "RESEARCH_GAP"
        }
        for target in targets:
            proposed_needs, proposed_gaps = artifact_proposed_needs(semantic_artifacts, target.id)
            _, unresolved_input = evaluate_gate_a_with_needs(packet, target, proposed_needs)
            for request in proposed_gaps:
                if request.request_id in recorded_request_ids:
                    continue
                if ports.research_escalation is None or unresolved_input:
                    repository.record_phase7_artifact(
                        run_id, make_phase7_artifact(run_id, "RESEARCH_GAP", request)
                    )
                    disposition = ResearchGapDisposition(
                        assessment_id=request.assessment_id,
                        assessment_context_id=request.assessment_context_id,
                        phase6_snapshot_id=request.phase6_snapshot_id,
                        target_id=request.target_id,
                        request_id=request.request_id,
                        status="UNAVAILABLE",
                        reason="Input clarification takes precedence"
                        if unresolved_input
                        else "Research escalation port is unavailable",
                    )
                    repository.record_phase7_artifact(
                        run_id,
                        make_phase7_artifact(run_id, "RESEARCH_GAP_DISPOSITION", disposition),
                    )
                    continue
                configured = ports.research_budget
                budget = ResearchEscalationBudget(
                    limits=configured.limits
                    if configured
                    else context.manifest.budget_limits or BudgetLimits(),
                    usage=configured.usage
                    if configured
                    else context.manifest.budget_usage or BudgetUsage(),
                    max_requests=configured.max_requests if configured else 1,
                    issued_request_ids=tuple(
                        dict.fromkeys(
                            (*(configured.issued_request_ids if configured else ()), *issued)
                        )
                    ),
                )
                continuation = await dispatch_research_gap(
                    run_id, request, packet, budget, ports.research_escalation, repository
                )
                if isinstance(continuation, ResearchContinuation):
                    issued.append(request.request_id)
                    if continuation.restarted:
                        return await _run_phase7_attempt(
                            assessment_id,
                            context_id=continuation.context.context_id,
                            repository=repository,
                            ports=ports,
                            existing_run_id=continuation.run_id,
                            prior_issued=tuple(issued),
                        )
        semantic_artifacts = repository.load_phase7_artifacts(run_id)
        findings: list[TargetFinding] = []
        questions = {*packet.manifest.remaining_gaps, *packet.manifest.cir.unknowns}
        for target in targets:
            witness, stability = _resolved_witness(
                tuple(c for c in comparisons if c.target_id == target.id),
                tuple(r for r in resolutions if r.target_id == target.id),
            )
            proposed_needs, proposed_gaps = artifact_proposed_needs(semantic_artifacts, target.id)
            gate_a, needs = evaluate_gate_a_with_needs(packet, target, proposed_needs)
            localization = witness.counterfactual if witness is not None else None
            gates = (
                gate_a,
                evaluate_gate_b_with_gaps(packet, target, proposed_gaps),
                evaluate_gate_c(packet, target, witness),
                evaluate_gate_d(packet, target, witness, localization),
            )

            def record(kind: str, document: TargetScoped) -> None:
                repository.record_phase7_artifact(
                    run_id, make_phase7_artifact(run_id, kind, document)
                )

            for kind, gate in zip(("GATE_A", "GATE_B", "GATE_C", "GATE_D"), gates, strict=True):
                record(kind, gate)
                questions.update(gate.unresolved_questions)
            for need in needs:
                record("INPUT_NEED", need)
            if localization is not None:
                record("COUNTERFACTUAL", localization)
            robustness, domain = repository.load_phase7_qualifications(context.context_id, target)
            record("ROBUSTNESS_QUALIFICATION", robustness)
            record("DOMAIN_QUALIFICATION", domain)
            findings.append(
                VerdictPermissionPolicy().evaluate(
                    packet=packet,
                    gate_a=gates[0],
                    gate_b=gates[1],
                    gate_c=gates[2],
                    gate_d=gates[3],
                    stability=stability,
                    robustness=robustness,
                    domain=domain,
                )
            )
        overall = compose_assessment(tuple(findings), targets)
        permitted = {permission for f in findings for permission in f.language_permission}
        if overall.verdict == VerdictState.MIXED_CONTRIBUTION_SPECIFIC:
            permitted.add(LanguagePermissionClass.MIXED_BY_TARGET)
        if overall.verdict == VerdictState.UNASSESSABLE:
            permitted.add(LanguagePermissionClass.ABSTENTION)
        limits = {
            *overall.limiting_factors,
            *(limit for case in prosecutions.values() for limit in case.limitations),
            *(limit for case in defenses.values() for limit in case.limitations),
            *(limit for rebuttal in rebuttals for limit in rebuttal.limitations),
            *(limit for r in resolutions for limit in r.limiting_factors),
            *(limit for r in (*judge_runs, *alternate_runs) for limit in r.finding.limitations),
            *(
                limit
                for case in prosecutions.values()
                for argument in case.challenges
                for limit in argument.limitations
            ),
            *(
                limit
                for case in defenses.values()
                for point in case.points
                for limit in point.limitations
            ),
        }
        artifacts = repository.load_phase7_artifacts(run_id)

        def inner_ids(kind: str, field: str) -> tuple[str, ...]:
            import json

            return tuple(
                sorted(str(json.loads(a.document_json)[field]) for a in artifacts if a.kind == kind)
            )

        proposed = FrozenAdjudication(
            assessment_id=assessment_id,
            assessment_context_id=context.context_id,
            phase6_snapshot_id=context.snapshot_id,
            adjudication_id="pending",
            run_id=run_id,
            case_id=packet.case_id,
            superseded_context_ids=repository.load_phase7_superseded_contexts(
                assessment_id, context_id=context.context_id
            ),
            as_of=packet.as_of,
            frozen_at=utc_now(),
            target_findings=tuple(findings),
            expected_targets=targets,
            overall_finding=overall,
            dependency_ids=tuple(sorted(a.artifact_id for a in artifacts)),
            role_case_ids=tuple(
                sorted(
                    a.artifact_id
                    for a in artifacts
                    if a.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
                )
            ),
            rebuttal_ids=inner_ids("REBUTTAL", "rebuttal_id"),
            input_need_ids=inner_ids("INPUT_NEED", "need_id"),
            research_gap_ids=inner_ids("RESEARCH_GAP", "request_id"),
            counterfactual_ids=inner_ids("COUNTERFACTUAL", "localization_id"),
            qualification_ids=tuple(
                sorted(
                    (
                        *inner_ids("ROBUSTNESS_QUALIFICATION", "qualification_id"),
                        *inner_ids("DOMAIN_QUALIFICATION", "qualification_id"),
                    )
                )
            ),
            judge_run_ids=tuple(sorted(r.run_id for r in (*judge_runs, *alternate_runs))),
            counterbalance_comparison_ids=tuple(sorted(c.comparison_id for c in comparisons)),
            judge_resolution_ids=tuple(sorted(r.resolution_id for r in resolutions)),
            permitted_language=tuple(sorted(permitted)),
            limiting_factors=tuple(sorted(limits)),
            unresolved_questions=tuple(sorted(questions)),
        )
        proposed = proposed.model_copy(update={"adjudication_id": phase7_frozen_id(proposed)})
        adjudication_id = repository.freeze_phase7_adjudication(run_id, proposed)
        frozen = repository.load_frozen_adjudication(assessment_id, adjudication_id=adjudication_id)
        if ports.trace_sink is not None:
            publish_frozen_phase7_trace(
                assessment_id,
                adjudication_id=adjudication_id,
                repository=repository,
                sink=ports.trace_sink,
                call_records=_model_call_records(ports),
            )
        return frozen
    except Exception as error:
        state = repository.load_phase7_run(run_id).state
        if state not in {
            Phase7RunState.FAILED,
            Phase7RunState.FROZEN,
            Phase7RunState.ABSTAINED,
            Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE,
        }:
            repository.transition_phase7_run(
                run_id, expected_state=state, next_state=Phase7RunState.FAILED
            )
        if (
            repository.load_phase7_run(run_id).state == Phase7RunState.FAILED
            and ports.trace_sink is not None
        ):
            failure = TraceEvent(
                event_id="trace_"
                + canonical_hash({"run_id": run_id, "failure": type(error).__name__}),
                assessment_id=assessment_id,
                occurred_at=utc_now(),
                stage=AssessmentStage.PRELIMINARY_ADJUDICATION,
                component="phase7",
                status=TraceStatus.FAILURE,
                reason_code="PHASE7_MODEL_OUTPUT_INVALID"
                if isinstance(error, Phase7ModelOutputError)
                else "PHASE7_EXECUTION_FAILED",
                data={
                    "run_id": run_id,
                    "context_id": context.context_id,
                    "snapshot_id": context.snapshot_id,
                    "error_code": type(error).__name__,
                },
            )
            try:
                ports.trace_sink.emit(failure)
            except Exception:
                pass  # Preserve the original operational error; no verdict exists.
        raise


class Phase7TraceDeliveryError(RuntimeError):
    """Delivery failed after commit; these frozen locators can be retried."""

    def __init__(
        self, adjudication_id: str, call_records: tuple[Phase7ModelCallRecord, ...]
    ) -> None:
        super().__init__("Phase 7 trace delivery failed after authoritative freeze")
        self.adjudication_id = adjudication_id
        self.call_records = call_records


def _model_call_records(ports: Phase7Ports) -> tuple[Phase7ModelCallRecord, ...]:
    components = (
        ports.prosecutor,
        ports.defender,
        ports.prosecutor_rebuttal,
        ports.defender_rebuttal,
        ports.judge,
        ports.alternate_judge,
        *(p for roles in ports.target_roles.values() for p in (roles.prosecutor, roles.defender)),
    )
    records: dict[str, Phase7ModelCallRecord] = {}
    for component in components:
        values: object = getattr(component, "call_records", ())
        if isinstance(values, tuple):
            for record in cast(tuple[object, ...], values):
                if isinstance(record, Phase7ModelCallRecord):
                    records[canonical_hash(record)] = record
    return tuple(records[key] for key in sorted(records))


def publish_frozen_phase7_trace(
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
    repository: Phase7AdjudicationRepository,
    sink: TraceSink,
    call_records: tuple[Phase7ModelCallRecord, ...] = (),
) -> tuple[TraceEvent, ...]:
    """Revalidate committed authority before delivery; traces carry no authority."""
    frozen = repository.load_frozen_adjudication(assessment_id, adjudication_id=adjudication_id)
    artifacts = repository.load_phase7_artifacts(frozen.run_id)
    shared: dict[str, JsonValue] = {
        "run_id": frozen.run_id,
        "context_id": frozen.assessment_context_id,
        "snapshot_id": frozen.phase6_snapshot_id,
        "adjudication_id": frozen.adjudication_id,
        "packet_id": frozen.case_id,
        "rubric_version": JUDGE_RUBRIC_VERSION,
        "policy_version": frozen.policy_version,
    }
    input_hash = canonical_hash(
        {"context_id": frozen.assessment_context_id, "packet_id": frozen.case_id}
    )
    events: list[TraceEvent] = []
    for artifact in artifacts:
        document = cast(JsonValue, json.loads(artifact.document_json))
        events.append(
            TraceEvent(
                event_id="trace_"
                + canonical_hash({"run_id": frozen.run_id, "artifact_id": artifact.artifact_id}),
                assessment_id=assessment_id,
                occurred_at=frozen.frozen_at,
                stage=AssessmentStage.FINDINGS_FROZEN,
                component="phase7",
                status=TraceStatus.SUCCESS,
                reason_code="PHASE7_ARTIFACT_COMMITTED",
                provider_name=artifact.execution.provider_name if artifact.execution else None,
                provider_version=artifact.execution.provider_version
                if artifact.execution
                else None,
                latency_ms=artifact.execution.latency_ms if artifact.execution else None,
                request_hash=artifact.execution.request_hash if artifact.execution else input_hash,
                response_hash=artifact.execution.response_hash
                if artifact.execution
                else canonical_hash(document),
                data={
                    **shared,
                    "artifact_ids": [artifact.artifact_id],
                    "artifact_kind": artifact.kind,
                    "prompt_version": artifact.execution.prompt_version
                    if artifact.execution
                    else None,
                    "model_config_id": artifact.execution.model_config_id
                    if artifact.execution
                    else None,
                    "prompt_hash": artifact.execution.prompt_hash if artifact.execution else None,
                    "invocation_prompt_hash": artifact.execution.invocation_prompt_hash
                    if artifact.execution
                    else None,
                    "provider_name": artifact.execution.provider_name
                    if artifact.execution
                    else None,
                    "execution_mode": artifact.execution.execution_mode
                    if artifact.execution
                    else None,
                    "execution_configuration_id": artifact.execution.configuration_id
                    if artifact.execution
                    else None,
                    "usage_state": "UNKNOWN",
                },
            )
        )
    for record in call_records:
        record = Phase7ModelCallRecord.model_validate_json(record.model_dump_json())
        bound = tuple(
            a
            for a in artifacts
            if a.execution is not None and a.execution.request_hash == record.request_hash
        )
        if any(
            a.execution is not None
            and (
                a.execution.prompt_version != record.prompt_version
                or a.execution.response_hash != record.response_hash
                or a.execution.provider_name != record.provider_name
                or a.execution.model_name != record.model_name
                or a.execution.provider_version != record.provider_version
            )
            for a in bound
        ):
            raise Phase7AuthorityError("Trace provenance differs from repository execution")
        events.append(
            TraceEvent(
                event_id="trace_"
                + canonical_hash({"run_id": frozen.run_id, "call": record.model_dump(mode="json")}),
                assessment_id=assessment_id,
                occurred_at=frozen.frozen_at,
                stage=AssessmentStage.FINDINGS_FROZEN,
                component="phase7_model",
                status=TraceStatus.SUCCESS
                if record.validation_state == "VALIDATED"
                else TraceStatus.FAILURE,
                reason_code="PHASE7_MODEL_CALL_AUDITED",
                provider_name=record.provider_name,
                provider_version=record.provider_version,
                request_hash=record.request_hash,
                response_hash=record.response_hash,
                latency_ms=record.latency_ms,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                estimated_cost=record.cost_usd,
                data={
                    **shared,
                    "artifact_ids": [a.artifact_id for a in bound],
                    "execution_binding": "REPOSITORY_EXECUTION"
                    if bound
                    else "UNBOUND_OPERATIONAL_AUDIT",
                    "prompt_version": record.prompt_version,
                    "model_name": record.model_name,
                    "validation_state": record.validation_state,
                },
            )
        )
    events.append(
        TraceEvent(
            event_id="trace_"
            + canonical_hash(
                {"adjudication_id": frozen.adjudication_id, "event": "FROZEN_COMMITTED"}
            ),
            assessment_id=assessment_id,
            occurred_at=frozen.frozen_at,
            stage=AssessmentStage.FINDINGS_FROZEN,
            component="phase7",
            status=TraceStatus.SUCCESS,
            reason_code="PHASE7_FROZEN_COMMITTED",
            request_hash=input_hash,
            response_hash=canonical_hash(frozen),
            data={**shared, "artifact_ids": list(frozen.dependency_ids)},
        )
    )
    try:
        for event in events:
            sink.emit(event)
    except Exception as error:
        raise Phase7TraceDeliveryError(adjudication_id, call_records) from error
    return tuple(events)
