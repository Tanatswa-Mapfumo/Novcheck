"""Pre-judge impact and counterbalance contracts for Phase 7."""

import pytest

from novelty_harness.adjudication.gates import (
    evaluate_gate_a,
    evaluate_gate_b,
    evaluate_gate_d,
)
from novelty_harness.adjudication.judge import GateFacts, classify_dispute_impact
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.adjudication.roles import DefenseCase, DefensePoint, material_disputes
from tests.fixtures.phase7_execution import executed_artifact_async
from tests.unit.adjudication.test_roles import build_packet, scope, valid_case


def _dispute_fixture(tmp_path):
    packet = build_packet(tmp_path)
    prosecution = valid_case(packet)
    challenge = prosecution.challenges[0]
    defense = DefenseCase(
        **scope(packet, challenge.target_id),
        case_id="p7defense_impact",
        points=(
            DefensePoint(
                **scope(packet, challenge.target_id),
                defense_id="p7def_impact",
                disposition="OBJECTION",
                thesis="The cited source does not reproduce the claimed relation",
                comparison_ids=challenge.comparison_ids,
            ),
        ),
    )
    dispute = material_disputes(prosecution, defense, packet)[0]
    target = TargetRef(kind="MCU", id=dispute.target_id)
    scope_ids = scope(packet, target.id)
    gate_a, _ = evaluate_gate_a(packet, target)
    facts = GateFacts(
        gate_a=gate_a,
        gate_b=evaluate_gate_b(packet, target),
        undisputed_c=None,
        undisputed_d=evaluate_gate_d(packet, target, None, None),
        robustness=RobustnessQualification(qualification_id="p7qual_robust_impact", **scope_ids),
        domain=DomainQualification(qualification_id="p7qual_domain_impact", **scope_ids),
    )
    return packet, prosecution, defense, dispute, facts


def test_impact_uses_explicit_resolution_candidates(tmp_path) -> None:
    packet, prosecution, defense, dispute, facts = _dispute_fixture(tmp_path)
    assert {candidate.gate_c_candidate for candidate in dispute.candidates} == {
        "DIRECT_ESTABLISHED",
        "NO_DIRECT_IN_REVIEWED_SCOPE",
    }
    impact = classify_dispute_impact(
        dispute, packet, facts, prosecution=prosecution, defense=defense
    )
    assert impact.level == "HIGH_IMPACT"
    assert "gate_c" in impact.changed_dimensions


def test_caller_cannot_remove_unfavorable_candidate_resolution(tmp_path) -> None:
    packet, prosecution, defense, dispute, facts = _dispute_fixture(tmp_path)
    trimmed = dispute.model_copy(update={"candidates": dispute.candidates[:1]})
    with pytest.raises(ValueError, match="candidate|resolution"):
        classify_dispute_impact(trimmed, packet, facts, prosecution=prosecution, defense=defense)


def test_unbounded_resolution_space_defaults_high_impact(tmp_path) -> None:
    packet, prosecution, defense, _, facts = _dispute_fixture(tmp_path)
    challenge = prosecution.challenges[0].model_copy(
        update={"counterfactual": "Removing control flow changes the mechanism"}
    )
    prosecution = prosecution.model_copy(update={"challenges": (challenge,)})
    point = defense.points[0].model_copy(
        update={"counterfactual": "Removing control flow may leave the same mechanism"}
    )
    defense = defense.model_copy(update={"points": (point,)})
    dispute = material_disputes(prosecution, defense, packet)[0]
    assert dispute.resolution_space_unbounded
    impact = classify_dispute_impact(
        dispute, packet, facts, prosecution=prosecution, defense=defense
    )
    assert impact.level == "HIGH_IMPACT"
    assert "unbounded_resolution_space" in impact.changed_dimensions


@pytest.mark.parametrize(
    "dimension",
    (
        "gate_c",
        "target_verdict",
        "assessability",
        "maximum_language_class",
        "claim_specific_negative_permission",
    ),
)
def test_high_impact_for_each_semantic_consequence(tmp_path, dimension: str) -> None:
    packet, prosecution, defense, dispute, facts = _dispute_fixture(tmp_path)
    impact = classify_dispute_impact(
        dispute, packet, facts, prosecution=prosecution, defense=defense
    )
    assert dimension in impact.changed_dimensions


def test_missing_undisputed_gate_baseline_defaults_high_impact(tmp_path) -> None:
    packet, prosecution, defense, dispute, facts = _dispute_fixture(tmp_path)
    missing = facts.model_copy(update={"undisputed_d": None})
    impact = classify_dispute_impact(
        dispute, packet, missing, prosecution=prosecution, defense=defense
    )
    assert impact.level == "HIGH_IMPACT"
    assert "missing_undisputed_baseline" in impact.changed_dimensions


def test_caller_cannot_replace_candidate_phase6_basis(tmp_path) -> None:
    packet, prosecution, defense, dispute, facts = _dispute_fixture(tmp_path)
    forged = dispute.candidates[0].model_copy(update={"basis_phase6_ids": ("cls_foreign",)})
    supplied = dispute.model_copy(update={"candidates": (forged, dispute.candidates[1])})
    with pytest.raises(ValueError, match="validated resolution candidate"):
        classify_dispute_impact(supplied, packet, facts, prosecution=prosecution, defense=defense)


def test_model_cannot_supply_high_impact_flag(tmp_path) -> None:
    packet, prosecution, defense, dispute, facts = _dispute_fixture(tmp_path)
    forged = dispute.model_dump(mode="json")
    forged["high_impact"] = False
    with pytest.raises(ValueError):
        type(dispute).model_validate(forged)


def _judging_fixture(tmp_path, *, observation_clock=None):
    from tests.unit.adjudication.test_roles import _committed_dispute_run

    packet, repository, run, prosecution, defense, disputes = _committed_dispute_run(
        tmp_path, observation_clock=observation_clock
    )
    target = TargetRef(kind="MCU", id=prosecution.target_id)
    gate_a, _ = evaluate_gate_a(packet, target)
    robustness, domain = repository.load_phase7_qualifications(packet.assessment_context_id, target)
    facts = GateFacts(
        gate_a=gate_a,
        gate_b=evaluate_gate_b(packet, target),
        undisputed_d=evaluate_gate_d(packet, target, None, None),
        robustness=robustness,
        domain=domain,
    )
    return packet, repository, run, prosecution, defense, disputes, {target.id: facts}


@pytest.fixture
def judging_fixture(tmp_path):
    return _judging_fixture(tmp_path)


class ScriptedJudge:
    model_config_id = "scripted-primary-v1"

    def __init__(self, finding, *, fail_second=False):
        self.finding = finding
        self.fail_second = fail_second
        self.calls = []

    async def judge(self, packet, arguments, *, order, rubric_version):
        self.calls.append((packet, arguments, order, rubric_version, self.model_config_id))
        if self.fail_second and len(self.calls) == 2:
            raise RuntimeError("judge provider failed")
        return self.finding


def _scripted_judge(packet, prosecution, **changes):
    from novelty_harness.adjudication.judge import JudgeFinding

    finding = JudgeFinding(
        **scope(packet, prosecution.target_id),
        finding_id="p7judge_scripted",
        accepted_challenge_ids=(prosecution.challenges[0].argument_id,),
        phase6_basis_ids=prosecution.challenges[0].comparison_ids,
        proposed_gate_c="DIRECT_ESTABLISHED",
        proposed_gate_d="NOT_APPLICABLE_TO_DIRECT",
        reason="The exact Phase 6 chain supports the scoped claim",
    )
    return ScriptedJudge(finding.model_copy(update=changes))


@pytest.mark.asyncio
async def test_direct_dispute_requires_reversed_order(judging_fixture) -> None:
    from novelty_harness.adjudication.judge import CounterbalanceRun
    from novelty_harness.adjudication.models import Phase7RunState
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    judge = _scripted_judge(packet, prosecution)
    try:
        results = await run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        assert [call[2] for call in judge.calls] == [("A", "B"), ("B", "A")]
        assert len(results) == 2
        assert len({result.run_id for result in results}) == 2
        committed = repository.load_phase7_artifacts(run.run_id)
        stored = tuple(
            CounterbalanceRun.model_validate_json(item.document_json)
            for item in committed
            if item.kind == "JUDGE_RUN"
        )
        assert set(item.run_id for item in stored) == set(item.run_id for item in results)
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.JUDGING
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_counterbalance_inputs_differ_only_in_order(judging_fixture) -> None:
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    judge = _scripted_judge(packet, prosecution)
    try:
        results = await run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        first, second = judge.calls
        assert first[:2] == second[:2]
        assert first[3:] == second[3:]
        assert first[2] == tuple(reversed(second[2]))
        assert results[0].argument_ids == results[1].argument_ids
        assert results[0].evidence_digest == results[1].evidence_digest == packet.digest
        assert results[0].model_config_id == results[1].model_config_id
        assert {item.argument_id for item in first[1]} == set(disputes[0].argument_ids)
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ("trim", "replace", "omit_dispute", "packet"))
async def test_judge_rejects_trimmed_resolution_candidates(judging_fixture, attack) -> None:
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    judge = _scripted_judge(packet, prosecution)
    supplied = disputes
    if attack == "trim":
        supplied = (disputes[0].model_copy(update={"candidates": disputes[0].candidates[:1]}),)
    elif attack == "replace":
        candidate = disputes[0].candidates[0].model_copy(update={"basis_phase6_ids": ("fake",)})
        supplied = (
            disputes[0].model_copy(update={"candidates": (candidate, disputes[0].candidates[1])}),
        )
    elif attack == "omit_dispute":
        supplied = ()
    else:
        packet = packet.model_copy(update={"phase6_view_digest": "wrong"})
    try:
        with pytest.raises(ValueError):
            await run_neutral_judging(run.run_id, packet, supplied, facts, judge, repository)
        assert judge.calls == []
        assert not any(a.kind == "JUDGE_RUN" for a in repository.load_phase7_artifacts(run.run_id))
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ("passage", "argument", "target", "extra_reclassification"))
async def test_judge_cannot_reclassify_phase6_or_add_passage(judging_fixture, attack) -> None:
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    changes = {
        "passage": {"phase6_basis_ids": ("passage_fabricated",)},
        "argument": {"accepted_challenge_ids": ("argument_fabricated",)},
        "target": {"target_id": "foreign"},
        "extra_reclassification": {"phase6_classification": "DIRECT_PRECEDENT"},
    }[attack]
    judge = _scripted_judge(packet, prosecution, **changes)
    try:
        with pytest.raises(ValueError):
            await run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        assert not any(a.kind == "JUDGE_RUN" for a in repository.load_phase7_artifacts(run.run_id))
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_alternate_high_impact_judge_is_also_counterbalanced(judging_fixture) -> None:
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    primary = _scripted_judge(packet, prosecution)
    alternate = _scripted_judge(packet, prosecution)
    alternate.model_config_id = "scripted-alternate-v1"
    try:
        first = await run_neutral_judging(run.run_id, packet, disputes, facts, primary, repository)
        second = await run_neutral_judging(
            run.run_id, packet, disputes, facts, alternate, repository
        )
        assert len(first) == len(second) == 2
        assert [call[2] for call in alternate.calls] == [("A", "B"), ("B", "A")]
        assert len({item.run_id for item in (*first, *second)}) == 4
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ("provider_failure", "config_change", "foreign_second_finding"))
async def test_incomplete_counterbalance_is_operational_failure(judging_fixture, attack) -> None:
    from novelty_harness.adjudication.models import Phase7RunState
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture

    class BrokenJudge(ScriptedJudge):
        async def judge(self, packet, arguments, *, order, rubric_version):
            finding = await super().judge(
                packet, arguments, order=order, rubric_version=rubric_version
            )
            if len(self.calls) == 2:
                if attack == "config_change":
                    self.model_config_id = "swapped-model"
                elif attack == "foreign_second_finding":
                    finding = finding.model_copy(update={"assessment_context_id": "foreign"})
            return finding

    judge = BrokenJudge(
        _scripted_judge(packet, prosecution).finding, fail_second=attack == "provider_failure"
    )
    try:
        with pytest.raises((ValueError, RuntimeError)):
            await run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.FAILED
        assert (
            len([a for a in repository.load_phase7_artifacts(run.run_id) if a.kind == "JUDGE_RUN"])
            == 1
        )
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_repository_rejects_wrong_packet_judge_run(judging_fixture) -> None:
    from novelty_harness.application.phase7_roles import make_phase7_artifact, run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    judge = _scripted_judge(packet, prosecution)
    try:
        results = await run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        forged = results[1].model_copy(update={"packet_id": "other_packet"})
        with pytest.raises(ValueError, match="packet"):
            repository.record_phase7_artifact(
                run.run_id, make_phase7_artifact(run.run_id, "JUDGE_RUN", forged)
            )
        assert (
            len([a for a in repository.load_phase7_artifacts(run.run_id) if a.kind == "JUDGE_RUN"])
            == 2
        )
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_counterbalance_includes_bounded_rebuttals(judging_fixture) -> None:
    from novelty_harness.adjudication.roles import RebuttalCase
    from novelty_harness.application.phase7_roles import make_phase7_artifact, run_neutral_judging

    packet, repository, run, prosecution, defense, disputes, facts = judging_fixture
    judge = _scripted_judge(packet, prosecution)
    rebuttals = tuple(
        RebuttalCase(
            **scope(packet, prosecution.target_id),
            rebuttal_id=f"p7rebuttal_{role}",
            role=role,
            dispute_ids=(disputes[0].dispute_id,),
            argument_ids=disputes[0].argument_ids,
            comparison_ids=prosecution.challenges[0].comparison_ids,
            points=(f"Bounded additional position {role}",),
        )
        for role in ("PROSECUTOR", "DEFENDER")
    )
    try:
        repository.record_phase7_artifact(
            run.run_id, make_phase7_artifact(run.run_id, "DISPUTE", disputes[0])
        )
        for rebuttal in rebuttals:
            repository.record_phase7_artifact(
                run.run_id,
                await executed_artifact_async(repository, run.run_id, "REBUTTAL", rebuttal),
            )
        current = material_disputes(
            prosecution,
            defense,
            packet,
            rebuttals=tuple(sorted(rebuttals, key=lambda r: r.rebuttal_id)),
        )
        await run_neutral_judging(run.run_id, packet, current, facts, judge, repository)
        texts = tuple(argument.thesis for argument in judge.calls[0][1])
        assert all(any(rebuttal.points[0] in text for text in texts) for rebuttal in rebuttals)
        assert judge.calls[0][1] == judge.calls[1][1]
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_clear_direct_reduced_path_cannot_omit_neutral_judging(judging_fixture) -> None:
    from novelty_harness.adjudication.models import Phase7RunState
    from novelty_harness.adjudication.repository import Phase7AuthorityError
    from novelty_harness.adjudication.roles import ProsecutionCase
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, _, prosecution, defense, _, _ = judging_fixture
    run = repository.begin_phase7_run(packet.assessment_context_id, attempt_token="clear-direct")
    conceded = defense.model_copy(
        update={"points": (defense.points[0].model_copy(update={"disposition": "CONCESSION"}),)}
    )
    judge = _scripted_judge(packet, prosecution)
    try:
        for target_id in sorted(packet.target_ids):
            cases = (
                prosecution
                if target_id == prosecution.target_id
                else ProsecutionCase(
                    **scope(packet, target_id), case_id=f"p7pro_{target_id}", challenges=()
                ),
                conceded
                if target_id == defense.target_id
                else DefenseCase(
                    **scope(packet, target_id), case_id=f"p7def_{target_id}", points=()
                ),
            )
            for kind, case in zip(("PROSECUTION_CASE", "DEFENSE_CASE"), cases, strict=True):
                repository.record_phase7_artifact(
                    run.run_id, await executed_artifact_async(repository, run.run_id, kind, case)
                )
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.CASE_BUILT,
            next_state=Phase7RunState.FIRST_PASSES_COMPLETE,
        )
        assert material_disputes(prosecution, conceded, packet) == ()
        with pytest.raises(Phase7AuthorityError, match="complete resolution"):
            await run_neutral_judging(run.run_id, packet, (), {}, judge, repository)
        assert judge.calls == []
    finally:
        repository.close()


def _judge_pair(
    *,
    model="primary",
    first_c="DIRECT_ESTABLISHED",
    second_c=None,
    first_d="NOT_APPLICABLE_TO_DIRECT",
    second_d=None,
    basis=("cls_actual",),
):
    from novelty_harness.adjudication.judge import CounterbalanceRun, JudgeFinding

    scopes = dict(
        assessment_id="asm_pair",
        assessment_context_id="p7ctx_pair",
        phase6_snapshot_id="p6snapshot_pair",
        target_id="mcu_pair",
    )
    findings = tuple(
        JudgeFinding(
            **scopes,
            finding_id=f"p7finding_{model}_{index}",
            accepted_challenge_ids=("arg_a",),
            phase6_basis_ids=basis,
            proposed_gate_c=gate_c,
            proposed_gate_d=gate_d,
            reason="Scoped semantic finding",
        )
        for index, gate_c, gate_d in (
            (0, first_c, first_d),
            (1, second_c or first_c, second_d or first_d),
        )
    )
    return tuple(
        CounterbalanceRun(
            **scopes,
            run_id=f"p7judge_{model}_{index}",
            dispute_id="p7dispute_pair",
            packet_id="p7case_pair",
            argument_ids=("arg_a", "arg_b"),
            order=order,
            evidence_digest="sealed_digest",
            rubric_version="p7-judge-rubric-v1",
            model_config_id=model,
            finding=finding,
        )
        for index, finding, order in zip((0, 1), findings, (("A", "B"), ("B", "A")), strict=True)
    )


def test_two_stable_models_that_materially_disagree_remain_unresolved() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons
    from novelty_harness.domain.enums import VerdictState

    primary = compare_counterbalance(*_judge_pair())
    alternate = compare_counterbalance(
        *_judge_pair(
            model="alternate", first_c="NO_DIRECT_IN_REVIEWED_SCOPE", first_d="SUBSTANTIVE"
        )
    )
    resolution = resolve_judge_comparisons(primary, alternate)
    assert resolution.resolved_semantics is None
    assert resolution.permitted_ceiling == VerdictState.UNASSESSABLE
    assert {"gate_c", "gate_d"} <= set(resolution.unresolved_dimensions)
    assert resolution.primary_comparison_id == primary.comparison_id
    assert resolution.alternate_comparison_id == alternate.comparison_id


def test_counterbalance_comparison_retains_both_findings_and_citations() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance

    first, second = _judge_pair()
    comparison = compare_counterbalance(first, second)
    assert comparison.first_finding == first.finding
    assert comparison.second_finding == second.finding
    assert comparison.first_run_id == first.run_id
    assert comparison.second_run_id == second.run_id
    assert comparison.resolution_if_stable.decisive_phase6_ids == first.finding.phase6_basis_ids


def test_judge_wording_variation_is_nonmaterial() -> None:
    from novelty_harness.adjudication.judge import JudgeStability, compare_counterbalance

    first, second = _judge_pair(basis=("cls_actual", "passage_actual"))
    second = second.model_copy(
        update={
            "finding": second.finding.model_copy(
                update={
                    "reason": "Same semantics with different wording",
                    "phase6_basis_ids": ("passage_actual", "cls_actual"),
                }
            )
        }
    )
    comparison = compare_counterbalance(first, second)
    assert comparison.stability == JudgeStability.MINOR_ORDER_VARIATION
    assert comparison.resolution_if_stable is not None
    assert comparison.materially_disputed_dimensions == ()


def test_different_decisive_citation_is_material() -> None:
    from novelty_harness.adjudication.judge import JudgeStability, compare_counterbalance

    first, second = _judge_pair()
    second = second.model_copy(
        update={
            "finding": second.finding.model_copy(
                update={"phase6_basis_ids": ("different_passage",)}
            )
        }
    )
    comparison = compare_counterbalance(first, second)
    assert comparison.stability == JudgeStability.MATERIAL_ORDER_INSTABILITY
    assert comparison.resolution_if_stable is None
    assert "decisive_phase6_ids" in comparison.materially_disputed_dimensions


@pytest.mark.parametrize(
    "second_c,second_d",
    (
        ("NO_DIRECT_IN_REVIEWED_SCOPE", "SUBSTANTIVE"),
        ("UNASSESSABLE", "UNRESOLVED"),
        ("DIRECT_ESTABLISHED", "UNRESOLVED"),
    ),
)
def test_gate_or_assessability_flip_abstains(second_c, second_d) -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons
    from novelty_harness.domain.enums import VerdictState

    primary = compare_counterbalance(*_judge_pair(second_c=second_c, second_d=second_d))
    resolution = resolve_judge_comparisons(primary, None)
    assert resolution.resolved_semantics is None
    assert resolution.permitted_ceiling == VerdictState.UNASSESSABLE


def test_primary_stable_needs_no_heterogeneous_tiebreak() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair())
    resolution = resolve_judge_comparisons(primary, None)
    assert resolution.resolved_semantics == primary.resolution_if_stable
    assert resolution.alternate_comparison_id is None
    assert resolution.permitted_ceiling is None


def test_primary_unstable_without_alternate_remains_unresolved() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair(second_c="DISPUTED"))
    resolution = resolve_judge_comparisons(primary, None)
    assert resolution.resolved_semantics is None
    assert resolution.unresolved_dimensions
    assert resolution.limiting_factors


def test_both_pairs_unstable_remain_unresolved() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair(second_c="DISPUTED"))
    alternate = compare_counterbalance(
        *_judge_pair(model="alternate", second_c="NO_DIRECT_IN_REVIEWED_SCOPE")
    )
    assert resolve_judge_comparisons(primary, alternate).resolved_semantics is None


def test_stable_alternate_can_resolve_order_unstable_primary() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair(second_c="DISPUTED"))
    alternate = compare_counterbalance(*_judge_pair(model="alternate"))
    resolution = resolve_judge_comparisons(primary, alternate)
    assert resolution.resolved_semantics == alternate.resolution_if_stable
    assert any("primary" in limit.lower() for limit in resolution.limiting_factors)
    assert resolution.primary_comparison_id == primary.comparison_id


def test_heterogeneous_majority_vote_is_not_supported() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair(second_c="NO_DIRECT_IN_REVIEWED_SCOPE"))
    alternate_single = _judge_pair(model="alternate")[0]
    with pytest.raises(ValueError, match="comparison|pair"):
        resolve_judge_comparisons(primary, alternate_single)


@pytest.mark.parametrize(
    "field,value",
    (
        ("packet_id", "foreign"),
        ("evidence_digest", "foreign"),
        ("model_config_id", "other"),
        ("order", ("A", "B")),
        ("assessment_context_id", "foreign"),
    ),
)
def test_counterbalance_rejects_nonidentical_pair(field, value) -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance

    first, second = _judge_pair()
    with pytest.raises(ValueError):
        compare_counterbalance(first, second.model_copy(update={field: value}))


def test_primary_stable_alternate_unstable_remains_unresolved() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair())
    alternate = compare_counterbalance(*_judge_pair(model="alternate", second_d="UNRESOLVED"))
    assert resolve_judge_comparisons(primary, alternate).resolved_semantics is None


def test_two_stable_agreeing_pairs_use_common_resolution() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair())
    alternate = compare_counterbalance(*_judge_pair(model="alternate"))
    assert (
        resolve_judge_comparisons(primary, alternate).resolved_semantics
        == primary.resolution_if_stable
    )


def test_caller_cannot_forge_stable_comparison() -> None:
    from novelty_harness.adjudication.judge import (
        JudgeStability,
        compare_counterbalance,
        resolve_judge_comparisons,
    )

    primary = compare_counterbalance(*_judge_pair(second_c="DISPUTED"))
    forged = primary.model_copy(update={"stability": JudgeStability.STABLE})
    with pytest.raises(ValueError):
        resolve_judge_comparisons(forged, None)


@pytest.mark.asyncio
async def test_comparisons_are_committed_from_complete_pairs(judging_fixture) -> None:
    from novelty_harness.adjudication.judge import CounterbalanceComparison, compare_counterbalance
    from novelty_harness.application.phase7_roles import make_phase7_artifact, run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture
    judge = _scripted_judge(packet, prosecution)
    try:
        results = await run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        expected = compare_counterbalance(*results)
        artifacts = repository.load_phase7_artifacts(run.run_id)
        actual = tuple(
            CounterbalanceComparison.model_validate_json(a.document_json)
            for a in artifacts
            if a.kind == "COUNTERBALANCE_COMPARISON"
        )
        assert actual == (expected,)
        forged = expected.model_copy(update={"second_run_id": "missing_second_run"})
        with pytest.raises(ValueError):
            repository.record_phase7_artifact(
                run.run_id, make_phase7_artifact(run.run_id, "COUNTERBALANCE_COMPARISON", forged)
            )
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_alternate_fabricated_citation_cannot_resolve_instability(judging_fixture) -> None:
    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = judging_fixture

    class UnstableJudge(ScriptedJudge):
        async def judge(self, packet, arguments, *, order, rubric_version):
            finding = await super().judge(
                packet, arguments, order=order, rubric_version=rubric_version
            )
            if len(self.calls) == 2:
                return finding.model_copy(update={"proposed_gate_c": "DISPUTED"})
            return finding

    primary = UnstableJudge(_scripted_judge(packet, prosecution).finding)
    alternate = _scripted_judge(packet, prosecution, phase6_basis_ids=("fabricated_passage",))
    alternate.model_config_id = "alternate"
    try:
        await run_neutral_judging(run.run_id, packet, disputes, facts, primary, repository)
        with pytest.raises(ValueError, match="Phase 6"):
            await run_neutral_judging(run.run_id, packet, disputes, facts, alternate, repository)
        assert (
            len(
                [
                    a
                    for a in repository.load_phase7_artifacts(run.run_id)
                    if a.kind == "COUNTERBALANCE_COMPARISON"
                ]
            )
            == 1
        )
        assert not any(
            a.kind == "JUDGE_RESOLUTION" for a in repository.load_phase7_artifacts(run.run_id)
        )
    finally:
        repository.close()


def test_positive_instability_only_limits_future_ceiling() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons
    from novelty_harness.domain.enums import VerdictState

    primary = compare_counterbalance(
        *_judge_pair(
            first_c="NO_DIRECT_IN_REVIEWED_SCOPE",
            second_c="SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA",
            first_d="SUBSTANTIVE",
        )
    )
    resolution = resolve_judge_comparisons(primary, None)
    assert resolution.permitted_ceiling == VerdictState.POTENTIALLY_NOVEL
    assert resolution.resolved_semantics is None


def test_alternate_cross_context_comparison_fails() -> None:
    from novelty_harness.adjudication.judge import compare_counterbalance, resolve_judge_comparisons

    primary = compare_counterbalance(*_judge_pair())
    foreign_runs = tuple(
        run.model_copy(
            update={
                "assessment_context_id": "foreign",
                "finding": run.finding.model_copy(update={"assessment_context_id": "foreign"}),
            }
        )
        for run in _judge_pair(model="alternate")
    )
    alternate = compare_counterbalance(*foreign_runs)
    with pytest.raises(ValueError, match="sealed dispute"):
        resolve_judge_comparisons(primary, alternate)


def test_judge_probe_designation_is_committed_before_calls(tmp_path) -> None:
    import asyncio
    import json

    from novelty_harness.application.phase7_roles import run_neutral_judging

    packet, repository, run, prosecution, _, disputes, facts = _judging_fixture(tmp_path)
    inner = _scripted_judge(packet, prosecution)

    class InspectingJudge:
        model_config_id = inner.model_config_id

        async def judge(self, packet, arguments, *, order, rubric_version):
            registrations = [
                json.loads(item.document_json)
                for item in repository.load_phase7_artifacts(run.run_id)
                if item.kind == "JUDGE_PROBE"
            ]
            assert len(registrations) == 1
            assert registrations[0]["probe_role"] == "PRIMARY"
            assert registrations[0]["model_config_id"] == self.model_config_id
            return await inner.judge(packet, arguments, order=order, rubric_version=rubric_version)

    try:
        asyncio.run(
            run_neutral_judging(run.run_id, packet, disputes, facts, InspectingJudge(), repository)
        )
    finally:
        repository.close()


def test_counterfactual_localization_flip_is_material() -> None:
    from novelty_harness.adjudication.counterfactual import CounterfactualLocalization
    from novelty_harness.adjudication.judge import (
        JudgeFinding,
        JudgeStability,
        compare_counterbalance,
    )

    first, second = _judge_pair(
        first_c="SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA", first_d="SUBSTANTIVE"
    )
    scope = first.finding.model_dump(
        include={"assessment_id", "assessment_context_id", "phase6_snapshot_id", "target_id"}
    )
    localization = CounterfactualLocalization(
        **scope,
        localization_id="p7cf_probe",
        nearest_comparison_id="cls_actual",
        removed_element="control-flow change",
        substantial_equivalence_after_removal=True,
        reason="Localized removal effect",
    )
    for changed, effects in ((first, True), (second, False)):
        finding = JudgeFinding.model_validate(
            {
                **changed.finding.model_dump(),
                "counterfactual": localization.model_copy(
                    update={"substantial_equivalence_after_removal": effects}
                ),
            }
        )
        if changed == first:
            first = first.model_copy(update={"finding": finding})
        else:
            second = second.model_copy(update={"finding": finding})
    comparison = compare_counterbalance(first, second)
    assert comparison.stability == JudgeStability.MATERIAL_ORDER_INSTABILITY
    assert "counterfactual" in comparison.materially_disputed_dimensions
