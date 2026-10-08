"""Independent Phase 7 first passes and durable role artifacts."""

import asyncio
from collections.abc import Mapping
from typing import Literal

from novelty_harness.adjudication.execution import phase7_artifact_id
from novelty_harness.adjudication.judge import (
    CounterbalanceRun,
    GateFacts,
    JudgeProbeRegistration,
    classify_dispute_impact,
    compare_counterbalance,
    dispute_arguments,
    judge_probe_id,
    validate_judge_finding,
)
from novelty_harness.adjudication.models import (
    Phase7Artifact,
    Phase7RunState,
    SemanticConfiguration,
    SemanticExecutionRecord,
    TargetScoped,
)
from novelty_harness.adjudication.needs import clarify_unproved_gate_d
from novelty_harness.adjudication.packet import AdjudicationCasePacket, build_adjudication_case
from novelty_harness.adjudication.prompts import JUDGE_RUBRIC_VERSION
from novelty_harness.adjudication.repository import (
    Phase7AdjudicationRepository,
    Phase7AuthorityError,
)
from novelty_harness.adjudication.roles import (
    DefenseCase,
    Dispute,
    ProsecutionCase,
    RebuttalCase,
    RoleArgument,
    material_disputes,
    neutral_review_issues,
    validate_defense_case,
    validate_prosecution_case,
    validate_rebuttal_case,
)
from novelty_harness.application.phase7_execution import (
    completed_invocation,
    invocation_configuration,
)
from novelty_harness.ports.adjudication import (
    DefensePort,
    EvidenceJudgePort,
    ProsecutionPort,
    RebuttalPort,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def make_phase7_artifact(
    run_id: str,
    kind: str,
    case: TargetScoped,
    *,
    execution: SemanticExecutionRecord | None = None,
) -> Phase7Artifact:
    document_json = canonical_json(case)
    return Phase7Artifact(
        artifact_id=phase7_artifact_id(run_id, kind, document_json, execution),
        execution=execution,
        run_id=run_id,
        kind=kind,
        document_json=document_json,
        assessment_id=case.assessment_id,
        assessment_context_id=case.assessment_context_id,
        phase6_snapshot_id=case.phase6_snapshot_id,
        target_id=case.target_id,
    )


def register_invocation(
    run_id: str,
    packet: AdjudicationCasePacket,
    port: object,
    kind: str,
    target_id: str,
    repository: Phase7AdjudicationRepository,
) -> tuple[SemanticConfiguration, str]:
    scope = TargetScoped(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        target_id=target_id,
    )
    config = invocation_configuration(port, kind, scope)
    artifact = make_phase7_artifact(run_id, "SEMANTIC_CONFIGURATION", config)
    repository.record_phase7_artifact(run_id, artifact)
    return config, artifact.artifact_id


async def run_independent_first_passes(
    run_id: str,
    packet: AdjudicationCasePacket,
    prosecutor: ProsecutionPort,
    defender: DefensePort,
    repository: Phase7AdjudicationRepository,
) -> tuple[ProsecutionCase, DefenseCase]:
    """Commit separately produced cases against one repository-derived packet."""

    run = repository.load_phase7_run(run_id)
    context = repository.load_phase7_context(
        run.assessment_id, context_id=run.assessment_context_id
    )
    authoritative_packet = build_adjudication_case(
        context,
        repository.load_phase6_assessment(run.assessment_id, snapshot_id=run.phase6_snapshot_id),
    )
    if (
        run.case_id != authoritative_packet.case_id
        or packet.case_id != authoritative_packet.case_id
        or canonical_hash(packet) != canonical_hash(authoritative_packet)
    ):
        raise Phase7AuthorityError("First-pass case packet is not the run's repository case")
    if run.state != Phase7RunState.CASE_BUILT:
        raise Phase7AuthorityError("First passes require a CASE_BUILT run")
    completed_roles = {
        (a.kind, a.target_id)
        for a in repository.load_phase7_artifacts(run_id)
        if a.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
    }
    configurations = {
        (kind, target): register_invocation(
            run_id, authoritative_packet, port, kind, target, repository
        )
        for kind, port in (("PROSECUTION_CASE", prosecutor), ("DEFENSE_CASE", defender))
        for target in authoritative_packet.target_ids
        if (kind, target) not in completed_roles
    }
    try:
        # Separate port calls receive only the same immutable case packet. Neither
        # first-pass role can see the other's response before both have returned.
        prosecution, defense = await asyncio.gather(
            prosecutor.propose(authoritative_packet),
            defender.propose(authoritative_packet),
        )
        prosecution = validate_prosecution_case(
            clarify_unproved_gate_d(prosecution, authoritative_packet), authoritative_packet
        )
        defense = validate_defense_case(
            clarify_unproved_gate_d(defense, authoritative_packet), authoritative_packet
        )
        if prosecution.target_id != defense.target_id:
            raise Phase7AuthorityError("First-pass roles address different targets")
        repository.record_phase7_artifact(
            run_id,
            make_phase7_artifact(
                run_id,
                "PROSECUTION_CASE",
                prosecution,
                execution=completed_invocation(
                    prosecutor,
                    prosecution,
                    *configurations[("PROSECUTION_CASE", prosecution.target_id)],
                    authoritative_packet.model_dump(mode="json"),
                ),
            ),
        )
        repository.record_phase7_artifact(
            run_id,
            make_phase7_artifact(
                run_id,
                "DEFENSE_CASE",
                defense,
                execution=completed_invocation(
                    defender,
                    defense,
                    *configurations[("DEFENSE_CASE", defense.target_id)],
                    authoritative_packet.model_dump(mode="json"),
                ),
            ),
        )
        committed = repository.load_phase7_artifacts(run_id)
        expected = {
            (kind, target_id)
            for target_id in authoritative_packet.target_ids
            for kind in ("PROSECUTION_CASE", "DEFENSE_CASE")
        }
        if {
            (item.kind, item.target_id)
            for item in committed
            if item.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
        } == expected:
            repository.transition_phase7_run(
                run_id,
                expected_state=Phase7RunState.CASE_BUILT,
                next_state=Phase7RunState.FIRST_PASSES_COMPLETE,
            )
    except Exception:
        if repository.load_phase7_run(run_id).state == Phase7RunState.CASE_BUILT:
            repository.transition_phase7_run(
                run_id,
                expected_state=Phase7RunState.CASE_BUILT,
                next_state=Phase7RunState.FAILED,
            )
        raise
    return prosecution, defense


async def run_rebuttals(
    run_id: str,
    packet: AdjudicationCasePacket,
    disputes: tuple[Dispute, ...],
    prosecutor_port: RebuttalPort,
    defender_port: RebuttalPort,
    repository: Phase7AdjudicationRepository,
) -> tuple[RebuttalCase, ...]:
    """Permit one packet-bound rebuttal per role for material disputes only."""

    if not disputes:
        return ()
    run = repository.load_phase7_run(run_id)
    if run.state != Phase7RunState.FIRST_PASSES_COMPLETE:
        raise Phase7AuthorityError("Rebuttal requires completed first passes")
    context = repository.load_phase7_context(
        run.assessment_id, context_id=run.assessment_context_id
    )
    authoritative_packet = build_adjudication_case(
        context,
        repository.load_phase6_assessment(run.assessment_id, snapshot_id=run.phase6_snapshot_id),
    )
    if run.case_id != authoritative_packet.case_id or canonical_hash(packet) != canonical_hash(
        authoritative_packet
    ):
        raise Phase7AuthorityError("Rebuttal packet differs from the run's repository case")
    committed = repository.load_phase7_artifacts(run_id)
    if any(item.kind == "REBUTTAL" for item in committed):
        raise Phase7AuthorityError("Run has already used its one rebuttal per role")
    prosecutions = {
        item.target_id: ProsecutionCase.model_validate_json(item.document_json)
        for item in committed
        if item.kind == "PROSECUTION_CASE"
    }
    defenses = {
        item.target_id: DefenseCase.model_validate_json(item.document_json)
        for item in committed
        if item.kind == "DEFENSE_CASE"
    }
    expected = tuple(
        dispute
        for target_id in sorted(authoritative_packet.target_ids)
        for dispute in material_disputes(
            prosecutions[target_id], defenses[target_id], authoritative_packet
        )
    )
    if {item.dispute_id: item for item in disputes} != {item.dispute_id: item for item in expected}:
        raise Phase7AuthorityError("Rebuttal dispute set differs from committed role positions")
    for dispute in expected:
        repository.record_phase7_artifact(run_id, make_phase7_artifact(run_id, "DISPUTE", dispute))
    selected_target = min(item.target_id for item in expected)
    selected = tuple(item for item in expected if item.target_id == selected_target)
    selected_ids = tuple(item.dispute_id for item in selected)
    selected_arguments = {argument for item in selected for argument in item.argument_ids}
    rebuttal_configs = [
        register_invocation(
            run_id, authoritative_packet, port, "REBUTTAL", selected_target, repository
        )
        for port in (prosecutor_port, defender_port)
    ]
    try:
        prosecution_rebuttal, defense_rebuttal = await asyncio.gather(
            prosecutor_port.propose(authoritative_packet, selected_ids, defenses[selected_target]),
            defender_port.propose(
                authoritative_packet, selected_ids, prosecutions[selected_target]
            ),
        )
        rebuttals = (
            validate_rebuttal_case(
                clarify_unproved_gate_d(prosecution_rebuttal, authoritative_packet),
                authoritative_packet,
            ),
            validate_rebuttal_case(
                clarify_unproved_gate_d(defense_rebuttal, authoritative_packet),
                authoritative_packet,
            ),
        )
        for rebuttal, role in zip(rebuttals, ("PROSECUTOR", "DEFENDER"), strict=True):
            if (
                rebuttal.role != role
                or rebuttal.target_id != selected_target
                or not set(rebuttal.dispute_ids) <= set(selected_ids)
                or not set(rebuttal.argument_ids) <= selected_arguments
            ):
                raise Phase7AuthorityError("Rebuttal scope or links differ from selected disputes")
        for rebuttal, port, config in zip(
            rebuttals, (prosecutor_port, defender_port), rebuttal_configs, strict=True
        ):
            repository.record_phase7_artifact(
                run_id,
                make_phase7_artifact(
                    run_id,
                    "REBUTTAL",
                    rebuttal,
                    execution=completed_invocation(
                        port,
                        rebuttal,
                        *config,
                        {
                            "packet": authoritative_packet.model_dump(mode="json"),
                            "disputed_ids": list(selected_ids),
                            "other_case": (
                                defenses[selected_target]
                                if rebuttal.role == "PROSECUTOR"
                                else prosecutions[selected_target]
                            ).model_dump(mode="json"),
                        },
                    ),
                ),
            )
        current = material_disputes(
            prosecutions[selected_target],
            defenses[selected_target],
            authoritative_packet,
            rebuttals=tuple(sorted(rebuttals, key=lambda item: item.rebuttal_id)),
        )
        for dispute in current:
            repository.record_phase7_artifact(
                run_id, make_phase7_artifact(run_id, "DISPUTE", dispute)
            )
    except Exception:
        if repository.load_phase7_run(run_id).state == Phase7RunState.FIRST_PASSES_COMPLETE:
            repository.transition_phase7_run(
                run_id,
                expected_state=Phase7RunState.FIRST_PASSES_COMPLETE,
                next_state=Phase7RunState.FAILED,
            )
        raise
    return rebuttals


async def run_neutral_judging(
    run_id: str,
    packet: AdjudicationCasePacket,
    disputes: tuple[Dispute, ...],
    gate_facts_by_target: Mapping[str, GateFacts],
    judge_port: EvidenceJudgePort,
    repository: Phase7AdjudicationRepository,
) -> tuple[CounterbalanceRun, ...]:
    """Judge every committed dispute, counterbalancing each material consequence."""

    run = repository.load_phase7_run(run_id)
    if run.state not in {Phase7RunState.FIRST_PASSES_COMPLETE, Phase7RunState.JUDGING}:
        raise Phase7AuthorityError("Neutral judging requires completed first passes")
    context = repository.load_phase7_context(
        run.assessment_id, context_id=run.assessment_context_id
    )
    authoritative = build_adjudication_case(
        context,
        repository.load_phase6_assessment(run.assessment_id, snapshot_id=run.phase6_snapshot_id),
    )
    if run.case_id != authoritative.case_id or canonical_hash(packet) != canonical_hash(
        authoritative
    ):
        raise Phase7AuthorityError("Judge packet differs from the run's repository case")
    committed = repository.load_phase7_artifacts(run_id)
    prosecutions = {
        item.target_id: ProsecutionCase.model_validate_json(item.document_json)
        for item in committed
        if item.kind == "PROSECUTION_CASE"
    }
    defenses = {
        item.target_id: DefenseCase.model_validate_json(item.document_json)
        for item in committed
        if item.kind == "DEFENSE_CASE"
    }
    rebuttals = tuple(
        sorted(
            (
                RebuttalCase.model_validate_json(item.document_json)
                for item in committed
                if item.kind == "REBUTTAL"
            ),
            key=lambda item: item.rebuttal_id,
        )
    )
    expected = tuple(
        dispute
        for target_id in sorted(authoritative.target_ids)
        for dispute in neutral_review_issues(
            prosecutions[target_id],
            defenses[target_id],
            authoritative,
            rebuttals=tuple(item for item in rebuttals if item.target_id == target_id),
        )
    )
    if len(disputes) != len(expected) or {d.dispute_id: d for d in disputes} != {
        d.dispute_id: d for d in expected
    }:
        raise Phase7AuthorityError(
            "Judge dispute set differs from committed complete resolution candidates"
        )
    config_id = judge_port.model_config_id
    if not config_id.strip():
        raise Phase7AuthorityError("Judge must declare its model/configuration identity")
    schedules: list[
        tuple[
            Dispute,
            tuple[RoleArgument, RoleArgument],
            tuple[tuple[Literal["A", "B"], Literal["A", "B"]], ...],
        ]
    ] = []
    for dispute in expected:
        target_rebuttals = tuple(item for item in rebuttals if item.target_id == dispute.target_id)
        impact = classify_dispute_impact(
            dispute,
            authoritative,
            gate_facts_by_target[dispute.target_id],
            prosecution=prosecutions[dispute.target_id],
            defense=defenses[dispute.target_id],
            rebuttals=target_rebuttals,
        )
        arguments = dispute_arguments(
            dispute,
            prosecutions[dispute.target_id],
            defenses[dispute.target_id],
            rebuttals=target_rebuttals,
        )
        orders: tuple[tuple[Literal["A", "B"], Literal["A", "B"]], ...] = (
            (("A", "B"), ("B", "A")) if impact.level == "HIGH_IMPACT" else (("A", "B"),)
        )
        schedules.append((dispute, arguments, orders))
    if run.state == Phase7RunState.FIRST_PASSES_COMPLETE:
        for dispute in expected:
            repository.record_phase7_artifact(
                run_id, make_phase7_artifact(run_id, "DISPUTE", dispute)
            )
    for dispute in expected:
        registered = tuple(
            JudgeProbeRegistration.model_validate_json(item.document_json)
            for item in repository.load_phase7_artifacts(run_id)
            if item.kind == "JUDGE_PROBE"
            and item.target_id == dispute.target_id
            and JudgeProbeRegistration.model_validate_json(item.document_json).dispute_id
            == dispute.dispute_id
        )
        if any(item.model_config_id == config_id for item in registered):
            continue
        probe = JudgeProbeRegistration(
            assessment_id=run.assessment_id,
            assessment_context_id=run.assessment_context_id,
            phase6_snapshot_id=run.phase6_snapshot_id,
            target_id=dispute.target_id,
            registration_id="pending",
            dispute_id=dispute.dispute_id,
            model_config_id=config_id,
            probe_role="ALTERNATE" if registered else "PRIMARY",
        )
        probe = probe.model_copy(update={"registration_id": judge_probe_id(run_id, probe)})
        repository.record_phase7_artifact(
            run_id, make_phase7_artifact(run_id, "JUDGE_PROBE", probe)
        )
    judge_configurations = {
        d.target_id: register_invocation(
            run_id, authoritative, judge_port, "JUDGE_RUN", d.target_id, repository
        )
        for d in expected
    }
    if run.state == Phase7RunState.FIRST_PASSES_COMPLETE:
        repository.transition_phase7_run(
            run_id, expected_state=run.state, next_state=Phase7RunState.JUDGING
        )
    results: list[CounterbalanceRun] = []
    try:
        for dispute, arguments, orders in schedules:
            pair: list[CounterbalanceRun] = []
            for order in orders:
                if judge_port.model_config_id != config_id:
                    raise Phase7AuthorityError(
                        "Judge model/config changed between counterbalanced calls"
                    )
                finding = await judge_port.judge(
                    authoritative,
                    arguments,
                    order=order,
                    rubric_version=JUDGE_RUBRIC_VERSION,
                )
                if judge_port.model_config_id != config_id:
                    raise Phase7AuthorityError(
                        "Judge model/config changed during counterbalanced call"
                    )
                finding = validate_judge_finding(
                    clarify_unproved_gate_d(finding, authoritative), authoritative, arguments
                )
                judge_run = CounterbalanceRun(
                    assessment_id=run.assessment_id,
                    assessment_context_id=run.assessment_context_id,
                    phase6_snapshot_id=run.phase6_snapshot_id,
                    target_id=dispute.target_id,
                    run_id="p7judge_"
                    + canonical_hash(
                        {
                            "run_id": run_id,
                            "dispute_id": dispute.dispute_id,
                            "packet_id": authoritative.case_id,
                            "arguments": [item.model_dump(mode="json") for item in arguments],
                            "order": list(order),
                            "model_config_id": config_id,
                            "rubric": JUDGE_RUBRIC_VERSION,
                        }
                    ),
                    dispute_id=dispute.dispute_id,
                    packet_id=authoritative.case_id,
                    argument_ids=(arguments[0].argument_id, arguments[1].argument_id),
                    order=order,
                    evidence_digest=authoritative.digest,
                    rubric_version=JUDGE_RUBRIC_VERSION,
                    model_config_id=config_id,
                    finding=finding,
                    provenance="Neutral A/B labels; wording and stable IDs may reveal a role",
                )
                repository.record_phase7_artifact(
                    run_id,
                    make_phase7_artifact(
                        run_id,
                        "JUDGE_RUN",
                        judge_run,
                        execution=completed_invocation(
                            judge_port,
                            finding,
                            *judge_configurations[dispute.target_id],
                            {
                                "packet": authoritative.model_dump(mode="json"),
                                "arguments": [a.model_dump(mode="json") for a in arguments],
                                "order": list(order),
                                "rubric_version": JUDGE_RUBRIC_VERSION,
                            },
                        ),
                    ),
                )
                results.append(judge_run)
                pair.append(judge_run)
            if len(pair) == 2:
                comparison = compare_counterbalance(pair[0], pair[1])
                repository.record_phase7_artifact(
                    run_id, make_phase7_artifact(run_id, "COUNTERBALANCE_COMPARISON", comparison)
                )
    except Exception:
        repository.transition_phase7_run(
            run_id, expected_state=Phase7RunState.JUDGING, next_state=Phase7RunState.FAILED
        )
        raise
    return tuple(results)
