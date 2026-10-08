"""Verdict permission from exact categorical gates and separate qualifications."""

import pytest
from sqlalchemy import text

from novelty_harness.adjudication.context import SealedAssessmentContext
from novelty_harness.adjudication.gates import (
    evaluate_gate_a,
    evaluate_gate_b,
    evaluate_gate_c,
    evaluate_gate_d,
)
from novelty_harness.adjudication.judge import JudgeStability
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.adjudication.packet import build_adjudication_case
from novelty_harness.adjudication.policy import VerdictPermissionPolicy
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.adjudication.repository import Phase7AuthorityError
from novelty_harness.domain.enums import PrecedentState, ValueMaturity, VerdictState
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from tests.integration.test_phase6_evidence_pipeline import graph_database
from tests.unit.adjudication.test_gates import _matrix_packet, _partial_gate_d_inputs
from tests.unit.adjudication.test_roles import build_packet


def _qualifications(packet, target):
    scope = {
        "assessment_id": packet.assessment_id,
        "assessment_context_id": packet.assessment_context_id,
        "phase6_snapshot_id": packet.phase6_snapshot_id,
        "target_id": target.id,
    }
    return (
        RobustnessQualification(qualification_id="p7qual_robust_fixture", **scope),
        DomainQualification(qualification_id="p7qual_domain_fixture", **scope),
    )


def _evaluate(packet, target, *, judge=None, localization=None, robustness=None, domain=None):
    default_robustness, default_domain = _qualifications(packet, target)
    gate_a, _ = evaluate_gate_a(packet, target)
    return VerdictPermissionPolicy().evaluate(
        packet=packet,
        gate_a=gate_a,
        gate_b=evaluate_gate_b(packet, target),
        gate_c=evaluate_gate_c(packet, target, judge),
        gate_d=evaluate_gate_d(packet, target, judge, localization),
        stability=JudgeStability.STABLE,
        robustness=robustness or default_robustness,
        domain=domain or default_domain,
    )


def test_direct_scope_permits_claim_specific_negative(tmp_path) -> None:
    packet = build_packet(tmp_path)
    finding = _evaluate(packet, TargetRef(kind="MCU", id="mcu_control"))
    assert finding.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
    assert finding.claim_scope == "Temperature sensor controls a relay"
    assert finding.decisive_phase6_ids


def test_single_strong_partial_non_substantive_delta_can_be_negative(tmp_path) -> None:
    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "NON_SUBSTANTIVE")
    before = packet.comparisons[0].comparison.classification
    finding = _evaluate(packet, target, judge=judge, localization=localization)
    assert finding.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
    assert packet.comparisons[0].comparison.classification == before
    assert before.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT


def test_missing_input_or_weak_research_is_unassessable(tmp_path) -> None:
    packet = build_packet(tmp_path)
    finding = _evaluate(packet, TargetRef(kind="MCU", id="mcu_status"))
    assert finding.verdict == VerdictState.UNASSESSABLE
    weak_dir = tmp_path / "weak"
    weak_dir.mkdir()
    weak = _matrix_packet(weak_dir, "NO_MATCH")
    weak_finding = _evaluate(weak, TargetRef(kind="MCU", id="mcu_1"))
    assert weak_finding.verdict == VerdictState.UNASSESSABLE


def test_unqualified_strong_positive_is_denied(tmp_path) -> None:
    packet, target, judge, localization, gate_b = _strong_candidate_fixture(tmp_path)
    robustness, domain = _qualifications(packet, target)
    gate_a, _ = evaluate_gate_a(packet, target)
    finding = VerdictPermissionPolicy().evaluate(
        packet=packet,
        gate_a=gate_a,
        gate_b=gate_b,
        gate_c=evaluate_gate_c(packet, target, judge),
        gate_d=evaluate_gate_d(packet, target, judge, localization),
        stability=JudgeStability.STABLE,
        robustness=robustness,
        domain=domain,
    )
    assert finding.verdict == VerdictState.POTENTIALLY_NOVEL


def test_bounded_substantive_survivor_is_potential(tmp_path) -> None:
    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "SUBSTANTIVE")
    finding = _evaluate(packet, target, judge=judge, localization=localization)
    assert finding.verdict == VerdictState.POTENTIALLY_NOVEL
    assert "historical_research_unknown" in finding.limiting_factors


def _strong_candidate_fixture(tmp_path):
    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "SUBSTANTIVE")
    gate_b = evaluate_gate_b(packet, target).model_copy(
        update={
            "permissions": (
                "MEANINGFUL_BOUNDED_POSITIVE_COMPARISON",
                "STRONG_POSITIVE_COVERAGE",
            ),
            "limiting_factors": (),
        }
    )
    return packet, target, judge, localization, gate_b


def test_validated_fixture_qualifications_exercise_strong_policy_only(tmp_path) -> None:
    packet, target, judge, localization, gate_b = _strong_candidate_fixture(tmp_path)
    gate_a, _ = evaluate_gate_a(packet, target)
    robustness, domain = _qualifications(packet, target)
    robustness = robustness.model_copy(
        update={
            "status": "QUALIFIED",
            "issuer": "fixture:validated",
            "method_version": "fixture-robustness-v1",
            "validation_artifact_id": "p7fixture_robustness",
        }
    )
    domain = domain.model_copy(
        update={
            "status": "QUALIFIED",
            "issuer": "fixture:validated",
            "method_version": "fixture-domain-v1",
            "evidence_ref": "p7fixture_domain",
        }
    )
    finding = VerdictPermissionPolicy().evaluate(
        packet=packet,
        gate_a=gate_a,
        gate_b=gate_b,
        gate_c=evaluate_gate_c(packet, target, judge),
        gate_d=evaluate_gate_d(packet, target, judge, localization),
        stability=JudgeStability.STABLE,
        robustness=robustness,
        domain=domain,
    )
    assert finding.verdict == VerdictState.STRONG_EVIDENCE_OF_NOVELTY
    denied = VerdictPermissionPolicy().evaluate(
        packet=packet,
        gate_a=gate_a,
        gate_b=gate_b,
        gate_c=evaluate_gate_c(packet, target, judge),
        gate_d=evaluate_gate_d(packet, target, judge, localization),
        stability=JudgeStability.STABLE,
        robustness=robustness.model_copy(update={"issuer": "caller"}),
        domain=domain,
    )
    assert denied.verdict == VerdictState.POTENTIALLY_NOVEL


def test_value_maturity_cannot_change_verdict(tmp_path) -> None:
    packet = build_packet(tmp_path)
    target = TargetRef(kind="MCU", id="mcu_control")
    finding = _evaluate(packet, target)
    assert finding.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
    assert packet.manifest.cir.claimed_advantages
    value_claims = tuple(
        item.model_copy(update={"maturity": ValueMaturity.DEMONSTRATED})
        for item in packet.manifest.cir.claimed_advantages
    )
    cir = packet.manifest.cir.model_copy(update={"claimed_advantages": value_claims})
    manifest = packet.manifest.model_copy(update={"cir": cir})
    context = SealedAssessmentContext(
        context_id="p7ctx_fixture_demonstrated_value",
        assessment_id=packet.assessment_id,
        snapshot_id=packet.phase6_snapshot_id,
        phase6_view_digest=packet.phase6_view_digest,
        manifest_id="p7manifest_" + manifest.content_digest(),
        manifest_digest=manifest.content_digest(),
        manifest=manifest,
    )
    valued_packet = build_adjudication_case(context, packet.phase6_view)
    valued_finding = _evaluate(valued_packet, target)
    assert valued_finding.verdict == finding.verdict


def test_copied_qualification_from_foreign_context_is_rejected(tmp_path) -> None:
    packet = build_packet(tmp_path)
    target = TargetRef(kind="MCU", id="mcu_control")
    robust, domain = _qualifications(packet, target)
    with pytest.raises(ValueError, match="foreign target scope"):
        _evaluate(
            packet,
            target,
            robustness=robust.model_copy(update={"assessment_context_id": "p7ctx_foreign"}),
            domain=domain,
        )


def test_repository_defaults_cannot_qualify_production_strong_positive(tmp_path) -> None:
    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        robustness, domain = repository.load_phase7_qualifications(
            packet.assessment_context_id, TargetRef(kind="MCU", id="mcu_control")
        )
        assert robustness.status == "NOT_YET_QUALIFIED"
        assert domain.status == "NOT_QUALIFIED"
        assert (
            robustness.assessment_context_id
            == domain.assessment_context_id
            == (packet.assessment_context_id)
        )
    finally:
        repository.close()


def test_untrusted_qualified_row_cannot_authorize_production(tmp_path) -> None:
    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        with repository.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO phase7_qualification_refs "
                    "(qualification_id,context_id,assessment_id,snapshot_id,target_id,"
                    "status,issuer,document_json) "
                    "VALUES (:id,:context,:assessment,:snapshot,:target,"
                    "'QUALIFIED','fixture:validated','{}')"
                ),
                {
                    "id": "p7qual_forged",
                    "context": packet.assessment_context_id,
                    "assessment": packet.assessment_id,
                    "snapshot": packet.phase6_snapshot_id,
                    "target": "mcu_control",
                },
            )
        with pytest.raises(Phase7AuthorityError, match="issuer"):
            repository.load_phase7_qualifications(
                packet.assessment_context_id, TargetRef(kind="MCU", id="mcu_control")
            )
    finally:
        repository.close()


def test_whole_configuration_marker_comes_from_sealed_topology(tmp_path) -> None:
    packet = build_packet(tmp_path)
    component = next(profile for profile in packet.target_profiles if profile.target_kind == "MCU")
    combination = next(
        profile for profile in packet.target_profiles if profile.target_kind == "COMBINATION"
    )
    assert not _evaluate(packet, TargetRef(kind="MCU", id=component.target_id)).whole_configuration
    assert _evaluate(
        packet, TargetRef(kind="COMBINATION", id=combination.target_id)
    ).whole_configuration


def test_subset_combination_cannot_supply_whole_configuration_marker(tmp_path) -> None:
    from novelty_harness.adjudication.packet import build_adjudication_case
    from novelty_harness.evidence.mapping.dimensions import build_mcu_comparison_profile
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    packet = build_packet(tmp_path)
    extra = packet.manifest.mcu_graph.mcus[0].model_copy(update={"mcu_id": "mcu_extra"})
    graph = packet.manifest.mcu_graph.model_copy(
        update={"mcus": (*packet.manifest.mcu_graph.mcus, extra)}
    )
    manifest = packet.manifest.model_copy(update={"mcu_graph": graph})
    view = packet.phase6_view.model_copy(
        update={"targets": (*packet.target_profiles, build_mcu_comparison_profile(extra))}
    )
    # Pure policy fixture only: it cannot authorize a repository context or freeze.
    context = SealedAssessmentContext(
        assessment_id=packet.assessment_id,
        context_id="p7ctx_subset_fixture",
        snapshot_id=packet.phase6_snapshot_id,
        manifest_id="p7manifest_subset_fixture",
        manifest_digest=manifest.content_digest(),
        phase6_view_digest=canonical_hash(view),
        manifest=manifest,
    )
    subset_packet = build_adjudication_case(context, view)
    combination = next(
        profile for profile in subset_packet.target_profiles if profile.target_kind == "COMBINATION"
    )
    assert not _evaluate(
        subset_packet, TargetRef(kind="COMBINATION", id=combination.target_id)
    ).whole_configuration


def test_limited_complete_target_permits_scoped_negative(tmp_path) -> None:
    from novelty_harness.domain.enums import SufficiencyState

    packet = build_packet(tmp_path)
    manifest = packet.manifest.model_copy(
        update={
            "sufficiency": packet.manifest.sufficiency.model_copy(
                update={"state": SufficiencyState.EXPLORATORY}
            )
        }
    )
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        context = repository.seal_phase7_context(
            packet.assessment_id, snapshot_id=packet.phase6_snapshot_id, manifest=manifest
        )
        packet = build_adjudication_case(
            context,
            repository.load_phase6_assessment(
                packet.assessment_id, snapshot_id=context.snapshot_id
            ),
        )
    finally:
        repository.close()
    target = TargetRef(kind="MCU", id="mcu_control")
    gate_a, needs = evaluate_gate_a(packet, target)
    assert gate_a.state == "LIMITED" and not needs
    assert _evaluate(packet, target).verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL


def test_counterfactual_cannot_omit_independent_remaining_difference(tmp_path) -> None:
    from novelty_harness.adjudication.counterfactual import validate_counterfactual

    packet, target, judge, localization = _partial_gate_d_inputs(tmp_path, "NON_SUBSTANTIVE")
    entry = packet.comparisons[0]
    classification = entry.comparison.classification.model_copy(
        update={
            "missing_elements": (
                *entry.comparison.classification.missing_elements,
                "independent safety watchdog",
            )
        }
    )
    view = packet.phase6_view.model_copy(
        update={
            "committed_comparisons": (
                entry.model_copy(
                    update={
                        "comparison": entry.comparison.model_copy(
                            update={"classification": classification}
                        )
                    }
                ),
                *packet.comparisons[1:],
            )
        }
    )
    from novelty_harness.adjudication.packet import _case_id
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    digest = canonical_hash(view)
    packet = packet.model_copy(
        update={
            "phase6_view": view,
            "phase6_view_digest": digest,
            "case_id": _case_id(
                packet.assessment_context_id,
                packet.phase6_snapshot_id,
                packet.manifest_digest,
                digest,
            ),
        }
    )
    with pytest.raises(ValueError, match="remaining|complete|account"):
        validate_counterfactual(packet, target, localization)
    complete = localization.model_copy(
        update={"remaining_differences": ("independent safety watchdog",)}
    )
    assert validate_counterfactual(packet, target, complete) == complete
    assert complete.remaining_differences == ("independent safety watchdog",)


def test_limited_unstable_claim_meaning_cannot_permit_negative(tmp_path) -> None:
    packet = build_packet(tmp_path)
    target = TargetRef(kind="MCU", id="mcu_control")
    gate_a, _ = evaluate_gate_a(packet, target)
    robustness, domain = _qualifications(packet, target)
    finding = VerdictPermissionPolicy().evaluate(
        packet=packet,
        gate_a=gate_a.model_copy(
            update={"state": "LIMITED", "limiting_factors": ("unresolved_graph_decomposition",)}
        ),
        gate_b=evaluate_gate_b(packet, target),
        gate_c=evaluate_gate_c(packet, target, None),
        gate_d=evaluate_gate_d(packet, target, None, None),
        stability=JudgeStability.STABLE,
        robustness=robustness,
        domain=domain,
    )
    assert finding.verdict == VerdictState.UNASSESSABLE
