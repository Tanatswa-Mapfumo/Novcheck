"""Target-preserving composition and real frozen shape contracts."""

from datetime import UTC, date, datetime

import pytest

from novelty_harness.adjudication.frozen import (
    FrozenAdjudication,
    LanguagePermissionClass,
    TargetFinding,
    ValueFinding,
)
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.domain.enums import ValueMaturity, VerdictState

SCOPE = dict(
    assessment_id="asm_frozen",
    assessment_context_id="p7ctx_frozen",
    phase6_snapshot_id="p6snapshot_frozen",
)


def target(identifier, verdict, *, kind="MCU", whole=False):
    return TargetFinding(
        **SCOPE,
        target_id=identifier,
        target_kind=kind,
        claim_scope=f"Exact claim {identifier}",
        verdict=verdict,
        gate_a_id=f"p7gate_A_{identifier}",
        gate_b_id=f"p7gate_B_{identifier}",
        gate_c_id=f"p7gate_C_{identifier}",
        gate_d_id=f"p7gate_D_{identifier}",
        decisive_phase6_ids=(f"cls_{identifier}",)
        if verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
        else (),
        language_permission=(LanguagePermissionClass.ABSTENTION,)
        if verdict == VerdictState.UNASSESSABLE
        else (),
        whole_configuration=whole,
    )


def expected(*targets):
    return tuple(TargetRef(kind=item.target_kind, id=item.target_id) for item in targets)


def test_negative_mcu_plus_potential_combination_is_mixed() -> None:
    from novelty_harness.adjudication.frozen import compose_assessment

    findings = (
        target("mcu_a", VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL),
        target("combo_ab", VerdictState.POTENTIALLY_NOVEL, kind="COMBINATION", whole=True),
    )
    overall = compose_assessment(findings, expected(*findings))
    assert overall.verdict == VerdictState.MIXED_CONTRIBUTION_SPECIFIC
    assert overall.target_ids == ("combo_ab", "mcu_a")
    assert findings[0].verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
    assert findings[1].verdict == VerdictState.POTENTIALLY_NOVEL


def test_unassessable_target_is_not_dropped() -> None:
    from novelty_harness.adjudication.frozen import compose_assessment

    findings = (target("a", VerdictState.POTENTIALLY_NOVEL), target("b", VerdictState.UNASSESSABLE))
    overall = compose_assessment(findings, expected(*findings))
    assert overall.verdict == VerdictState.MIXED_CONTRIBUTION_SPECIFIC
    assert overall.target_ids == ("a", "b")
    assert any("b" in limit for limit in overall.limiting_factors)


def test_incomplete_target_universe_has_no_unqualified_whole_verdict() -> None:
    from novelty_harness.adjudication.frozen import compose_assessment

    finding = target("a", VerdictState.POTENTIALLY_NOVEL)
    overall = compose_assessment(
        (finding,), (*expected(finding), TargetRef(kind="COMBINATION", id="missing_combo"))
    )
    assert overall.verdict == VerdictState.UNASSESSABLE
    assert any("missing_combo" in limit for limit in overall.limiting_factors)


def test_whole_negative_requires_whole_configuration_target() -> None:
    from novelty_harness.adjudication.frozen import compose_assessment

    negative = VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
    components = (target("a", negative), target("b", negative))
    assert (
        compose_assessment(components, expected(*components)).verdict == VerdictState.UNASSESSABLE
    )
    partial_combo = target("combo_subset", negative, kind="COMBINATION")
    assert (
        compose_assessment(
            (*components, partial_combo), expected(*components, partial_combo)
        ).verdict
        == VerdictState.UNASSESSABLE
    )
    whole_combo = target("combo_whole", negative, kind="COMBINATION", whole=True)
    findings = (*components, whole_combo)
    assert compose_assessment(findings, expected(*findings)).verdict == negative


@pytest.mark.parametrize(
    "verdict",
    (
        VerdictState.POTENTIALLY_NOVEL,
        VerdictState.UNASSESSABLE,
        VerdictState.STRONG_EVIDENCE_OF_NOVELTY,
    ),
)
def test_all_same_scoped_verdict_is_preserved(verdict) -> None:
    from novelty_harness.adjudication.frozen import compose_assessment

    findings = (target("a", verdict), target("b", verdict))
    overall = compose_assessment(findings, expected(*findings))
    assert overall.verdict == verdict
    assert overall.target_ids == ("a", "b")


@pytest.mark.parametrize(
    "attack", ("duplicate", "foreign_context", "foreign_target", "wrong_kind", "mixed_target")
)
def test_composer_rejects_invalid_target_scope(attack) -> None:
    from novelty_harness.adjudication.frozen import compose_assessment

    original = target("a", VerdictState.POTENTIALLY_NOVEL)
    second = target("b", VerdictState.POTENTIALLY_NOVEL)
    universe = expected(original, second)
    if attack == "duplicate":
        findings = (original, original)
    elif attack == "foreign_context":
        findings = (original, second.model_copy(update={"assessment_context_id": "foreign"}))
    elif attack == "foreign_target":
        findings = (original, second.model_copy(update={"target_id": "foreign"}))
    elif attack == "wrong_kind":
        findings = (original, second.model_copy(update={"target_kind": "COMBINATION"}))
    else:
        findings = (
            original,
            second.model_copy(update={"verdict": VerdictState.MIXED_CONTRIBUTION_SPECIFIC}),
        )
    with pytest.raises(ValueError):
        compose_assessment(findings, universe)


def _frozen(findings, **changes):
    from novelty_harness.adjudication.frozen import compose_assessment

    return FrozenAdjudication(
        **SCOPE,
        adjudication_id="p7frozen_shape",
        run_id="p7run_shape",
        case_id="p7case_shape",
        as_of=date(2026, 9, 26),
        frozen_at=datetime(2026, 10, 4, tzinfo=UTC),
        target_findings=findings,
        overall_finding=compose_assessment(findings, expected(*findings)),
        expected_targets=expected(*findings),
        dependency_ids=("p7artifact_one",),
        **changes,
    )


def test_value_findings_do_not_change_composition() -> None:
    finding = target("a", VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL, whole=True)
    first = _frozen(
        (finding,),
        value_findings=(
            ValueFinding(
                **SCOPE,
                target_id="a",
                claim="Useful implementation",
                maturity=ValueMaturity.CLAIMED,
            ),
        ),
    )
    second = _frozen(
        (finding,),
        value_findings=(
            ValueFinding(
                **SCOPE,
                target_id="a",
                claim="Useful implementation",
                maturity=ValueMaturity.DEMONSTRATED,
            ),
        ),
    )
    assert first.target_findings == second.target_findings
    assert first.overall_finding == second.overall_finding
    assert first.forbidden_claims == ("UNIVERSAL_ABSENCE", "CERTAIN_NOVELTY")


def test_frozen_contract_rejects_foreign_findings_and_missing_forbidden_claims() -> None:
    finding = target("a", VerdictState.UNASSESSABLE)
    frozen = _frozen((finding,))
    for updates in (
        {
            "overall_finding": frozen.overall_finding.model_copy(
                update={"phase6_snapshot_id": "foreign"}
            )
        },
        {"forbidden_claims": ()},
        {"dependency_ids": ("duplicate", "duplicate")},
        {"permitted_language": (LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE,)},
    ):
        with pytest.raises(ValueError):
            FrozenAdjudication.model_validate({**frozen.model_dump(), **updates})
