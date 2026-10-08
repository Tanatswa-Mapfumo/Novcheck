"""Deterministic per-target verdict and claim-language permissions."""

from novelty_harness.adjudication.frozen import LanguagePermissionClass, TargetFinding
from novelty_harness.adjudication.gates import (
    GateAFinding,
    GateBFinding,
    GateCFinding,
    GateDFinding,
)
from novelty_harness.adjudication.judge import JudgeStability
from novelty_harness.adjudication.packet import AdjudicationCasePacket
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.domain.enums import VerdictState

POLICY_VERSION = "phase7-verdict-permission-v2"


class VerdictPermissionPolicy:
    """Intersect categorical gate conclusions; never infer evidence or value."""

    def evaluate(
        self,
        *,
        packet: AdjudicationCasePacket,
        gate_a: GateAFinding,
        gate_b: GateBFinding,
        gate_c: GateCFinding,
        gate_d: GateDFinding,
        stability: JudgeStability,
        robustness: RobustnessQualification,
        domain: DomainQualification,
    ) -> TargetFinding:
        packet = AdjudicationCasePacket.model_validate_json(packet.model_dump_json())
        gate_a = GateAFinding.model_validate_json(gate_a.model_dump_json())
        gate_b = GateBFinding.model_validate_json(gate_b.model_dump_json())
        gate_c = GateCFinding.model_validate_json(gate_c.model_dump_json())
        gate_d = GateDFinding.model_validate_json(gate_d.model_dump_json())
        robustness = RobustnessQualification.model_validate_json(robustness.model_dump_json())
        domain = DomainQualification.model_validate_json(domain.model_dump_json())
        target_id = gate_a.target_id
        profile = next(
            (item for item in packet.target_profiles if item.target_id == target_id), None
        )
        if profile is None:
            raise ValueError("Verdict target is absent from packet")
        expected_scope = (
            packet.assessment_id,
            packet.assessment_context_id,
            packet.phase6_snapshot_id,
            target_id,
        )
        for artifact in (gate_a, gate_b, gate_c, gate_d, robustness, domain):
            if (
                artifact.assessment_id,
                artifact.assessment_context_id,
                artifact.phase6_snapshot_id,
                artifact.target_id,
            ) != expected_scope:
                raise ValueError("Verdict gate or qualification has foreign target scope")
        classification_by_id = {
            str(item.comparison.classification.classification_id): item
            for item in packet.comparisons
            if item.comparison.classification.mcu_id == target_id
        }
        if not set(gate_c.comparison_ids) <= set(classification_by_id):
            raise ValueError("Verdict Gate C cites absent Phase 6 comparison")
        negative_permission = (
            "CLAIM_SPECIFIC_NEGATIVE_SUPPORTED_BY_DECISIVE_EVIDENCE" in gate_b.permissions
        )
        bounded_permission = "MEANINGFUL_BOUNDED_POSITIVE_COMPARISON" in gate_b.permissions
        strong_permission = "STRONG_POSITIVE_COVERAGE" in gate_b.permissions
        stable = stability != JudgeStability.MATERIAL_ORDER_INSTABILITY
        input_ready = (
            gate_a.state in {"ASSESSABLE", "LIMITED"}
            and not gate_a.missing_fields
            and "unresolved_graph_decomposition" not in gate_a.limiting_factors
        )
        direct_negative = (
            gate_c.state == "DIRECT_ESTABLISHED"
            and gate_d.state == "NOT_APPLICABLE_TO_DIRECT"
            and bool(gate_c.comparison_ids)
        )
        partial_negative = (
            gate_c.state == "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA"
            and bool(gate_c.residual_delta)
            and gate_d.state == "NON_SUBSTANTIVE"
            and gate_c.comparison_ids == gate_d.nearest_comparison_ids
        )
        potential = (
            gate_c.state
            in {
                "NO_DIRECT_IN_REVIEWED_SCOPE",
                "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA",
            }
            and gate_d.state == "SUBSTANTIVE"
            and bounded_permission
        )
        qualified = (
            robustness.status == "QUALIFIED"
            and domain.status == "QUALIFIED"
            and robustness.issuer == "fixture:validated"
            and domain.issuer == "fixture:validated"
            and robustness.method_version is not None
            and robustness.validation_artifact_id is not None
            and domain.method_version is not None
            and domain.evidence_ref is not None
        )
        limitations = tuple(
            dict.fromkeys(
                (
                    *gate_a.limiting_factors,
                    *gate_b.limiting_factors,
                    *gate_c.limiting_factors,
                    *gate_d.limiting_factors,
                )
            )
        )
        if input_ready and negative_permission and stable and (direct_negative or partial_negative):
            verdict = VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL
            language = (LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE,)
            decisive = gate_c.comparison_ids
            supporting = gate_c.passage_ids
        elif input_ready and stable and potential:
            verdict = (
                VerdictState.STRONG_EVIDENCE_OF_NOVELTY
                if gate_a.state == "ASSESSABLE"
                and strong_permission
                and qualified
                and not limitations
                else VerdictState.POTENTIALLY_NOVEL
            )
            language = (
                (LanguagePermissionClass.QUALIFIED_STRONG_POSITIVE,)
                if verdict == VerdictState.STRONG_EVIDENCE_OF_NOVELTY
                else (LanguagePermissionClass.SCOPED_POTENTIAL,)
            )
            decisive = ()
            supporting = gate_c.comparison_ids
        else:
            verdict = VerdictState.UNASSESSABLE
            language = (LanguagePermissionClass.ABSTENTION,)
            decisive = ()
            supporting = ()
        if limitations and verdict != VerdictState.UNASSESSABLE:
            language = (*language, LanguagePermissionClass.COVERAGE_LIMITATION)
        return TargetFinding(
            assessment_id=packet.assessment_id,
            assessment_context_id=packet.assessment_context_id,
            phase6_snapshot_id=packet.phase6_snapshot_id,
            target_id=target_id,
            target_kind=profile.target_kind,
            claim_scope=profile.statement,
            whole_configuration=(
                set(profile.combination_members)
                == {mcu.mcu_id for mcu in packet.manifest.mcu_graph.mcus}
                if profile.target_kind == "COMBINATION"
                else len(packet.manifest.mcu_graph.mcus) == 1
                and not packet.manifest.mcu_graph.combinations
            ),
            verdict=verdict,
            gate_a_id=gate_a.gate_id,
            gate_b_id=gate_b.gate_id,
            gate_c_id=gate_c.gate_id,
            gate_d_id=gate_d.gate_id,
            decisive_phase6_ids=decisive,
            supporting_phase6_ids=supporting,
            limiting_factors=limitations,
            language_permission=language,
        )
