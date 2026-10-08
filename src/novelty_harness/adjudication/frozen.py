"""Real Phase 7 frozen conclusion, separate from the historical fixture."""

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import model_validator

from novelty_harness.adjudication.models import Phase7Scoped, TargetRef, TargetScoped
from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.enums import ValueMaturity, VerdictState
from novelty_harness.runtime.tracing.hashing import canonical_hash


class LanguagePermissionClass(StrEnum):
    CLAIM_SPECIFIC_NEGATIVE = "CLAIM_SPECIFIC_NEGATIVE"
    SCOPED_POTENTIAL = "SCOPED_POTENTIAL"
    QUALIFIED_STRONG_POSITIVE = "QUALIFIED_STRONG_POSITIVE"
    MIXED_BY_TARGET = "MIXED_BY_TARGET"
    ABSTENTION = "ABSTENTION"
    COVERAGE_LIMITATION = "COVERAGE_LIMITATION"
    SEPARATE_VALUE_FINDING = "SEPARATE_VALUE_FINDING"


class NoveltySignificance(TargetScoped):
    contract_kind: Literal["phase7-novelty-significance-v1"] = "phase7-novelty-significance-v1"
    gate_d_id: str
    differentiator: str | None = None
    significance: Literal["SUBSTANTIVE", "NON_SUBSTANTIVE", "UNRESOLVED"]


class ValueFinding(TargetScoped):
    contract_kind: Literal["phase7-value-finding-v1"] = "phase7-value-finding-v1"
    claim: str
    maturity: ValueMaturity


class TargetFinding(TargetScoped):
    contract_kind: Literal["phase7-target-finding-v1"] = "phase7-target-finding-v1"
    target_kind: Literal["MCU", "COMBINATION"]
    claim_scope: str
    verdict: VerdictState
    gate_a_id: str
    gate_b_id: str
    gate_c_id: str
    gate_d_id: str
    decisive_phase6_ids: tuple[str, ...] = ()
    supporting_phase6_ids: tuple[str, ...] = ()
    challenged_phase6_ids: tuple[str, ...] = ()
    limiting_factors: tuple[str, ...] = ()
    language_permission: tuple[LanguagePermissionClass, ...] = ()
    whole_configuration: bool = False

    @model_validator(mode="after")
    def target_only_verdict(self) -> Self:
        if self.verdict == VerdictState.MIXED_CONTRIBUTION_SPECIFIC:
            raise ValueError("MIXED_CONTRIBUTION_SPECIFIC is an overall-only verdict")
        if not self.claim_scope.strip():
            raise ValueError("Target finding requires an exact claim scope")
        return self


class OverallFinding(Phase7Scoped):
    contract_kind: Literal["phase7-overall-finding-v1"] = "phase7-overall-finding-v1"
    verdict: VerdictState
    target_ids: tuple[str, ...]
    limiting_factors: tuple[str, ...] = ()


def compose_assessment(
    targets: tuple[TargetFinding, ...], expected_targets: tuple[TargetRef, ...]
) -> OverallFinding:
    """Compose scoped target meaning without votes, counts or averaging."""

    targets = tuple(TargetFinding.model_validate_json(item.model_dump_json()) for item in targets)
    expected_targets = tuple(
        TargetRef.model_validate_json(item.model_dump_json()) for item in expected_targets
    )
    if not targets or not expected_targets:
        raise ValueError("Composition requires a nonempty target universe and scoped findings")
    universe = {item.id: item.kind for item in expected_targets}
    if len(universe) != len(expected_targets) or len({item.target_id for item in targets}) != len(
        targets
    ):
        raise ValueError("Composition target IDs must be unique")
    first = targets[0]
    if any(
        (item.assessment_id, item.assessment_context_id, item.phase6_snapshot_id)
        != (first.assessment_id, first.assessment_context_id, first.phase6_snapshot_id)
        for item in targets
    ):
        raise ValueError("Composition findings have foreign assessment scope")
    if any(universe.get(item.target_id) != item.target_kind for item in targets):
        raise ValueError("Composition finding target or kind differs from expected universe")
    missing = tuple(sorted(set(universe) - {item.target_id for item in targets}))
    unassessable = tuple(
        sorted(item.target_id for item in targets if item.verdict == VerdictState.UNASSESSABLE)
    )
    limits = tuple(
        f"Target {item.target_id}: {limit}"
        for item in sorted(targets, key=lambda item: item.target_id)
        for limit in item.limiting_factors
    )
    limits = (
        *limits,
        *(f"Target {identifier} remains UNASSESSABLE" for identifier in unassessable),
    )
    verdicts = {item.verdict for item in targets}
    if missing:
        verdict = VerdictState.UNASSESSABLE
        limits = (*limits, *(f"Missing expected target {identifier}" for identifier in missing))
    elif len(verdicts) != 1:
        verdict = VerdictState.MIXED_CONTRIBUTION_SPECIFIC
        limits = (
            *limits,
            "Overall state retains the distinct per-target claim scopes and verdicts",
        )
    else:
        verdict = first.verdict
        if verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL and not any(
            item.whole_configuration and item.decisive_phase6_ids for item in targets
        ):
            verdict = VerdictState.UNASSESSABLE
            limits = (
                *limits,
                "No supported explicitly modeled whole-configuration target; "
                "component negatives remain scoped",
            )
    return OverallFinding(
        assessment_id=first.assessment_id,
        assessment_context_id=first.assessment_context_id,
        phase6_snapshot_id=first.phase6_snapshot_id,
        verdict=verdict,
        target_ids=tuple(sorted(item.target_id for item in targets)),
        limiting_factors=tuple(dict.fromkeys(limits)),
    )


class FrozenAdjudication(Phase7Scoped):
    contract_kind: Literal["phase7-frozen-adjudication-v1"] = "phase7-frozen-adjudication-v1"
    adjudication_id: str
    run_id: str
    case_id: str
    as_of: date
    frozen_at: UTCDateTime
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    expected_targets: tuple[TargetRef, ...]
    dependency_ids: tuple[str, ...]
    role_case_ids: tuple[str, ...] = ()
    rebuttal_ids: tuple[str, ...] = ()
    qualification_ids: tuple[str, ...] = ()
    counterfactual_ids: tuple[str, ...] = ()
    input_need_ids: tuple[str, ...] = ()
    research_gap_ids: tuple[str, ...] = ()
    judge_run_ids: tuple[str, ...] = ()
    counterbalance_comparison_ids: tuple[str, ...] = ()
    judge_resolution_ids: tuple[str, ...] = ()
    superseded_context_ids: tuple[str, ...] = ()
    novelty_significance: tuple[NoveltySignificance, ...] = ()
    value_findings: tuple[ValueFinding, ...] = ()
    permitted_language: tuple[LanguagePermissionClass, ...] = ()
    forbidden_claims: tuple[str, ...] = ("UNIVERSAL_ABSENCE", "CERTAIN_NOVELTY")
    limiting_factors: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    method_version: str = "phase7-adjudication-v1"
    policy_version: str = "phase7-verdict-permission-v2"

    @model_validator(mode="after")
    def exact_frozen_shape(self) -> Self:
        scope = (self.assessment_id, self.assessment_context_id, self.phase6_snapshot_id)
        target_by_id = {item.target_id: item for item in self.target_findings}
        if set(target_by_id) != {item.id for item in self.expected_targets}:
            raise ValueError("Frozen shape must retain every expected target finding")
        for finding in (
            *self.target_findings,
            self.overall_finding,
            *self.novelty_significance,
            *self.value_findings,
        ):
            if (
                finding.assessment_id,
                finding.assessment_context_id,
                finding.phase6_snapshot_id,
            ) != scope:
                raise ValueError("Frozen finding has foreign assessment/context/snapshot scope")
        if self.overall_finding != compose_assessment(self.target_findings, self.expected_targets):
            raise ValueError("Frozen overall finding differs from scoped composition")
        for finding in (*self.novelty_significance, *self.value_findings):
            if finding.target_id not in target_by_id:
                raise ValueError("Frozen value or significance has a foreign target")
        for finding in self.novelty_significance:
            if finding.gate_d_id != target_by_id[finding.target_id].gate_d_id:
                raise ValueError("Novelty significance differs from the target's Gate D reference")
        for refs in (
            self.dependency_ids,
            self.role_case_ids,
            self.rebuttal_ids,
            self.qualification_ids,
            self.counterfactual_ids,
            self.input_need_ids,
            self.research_gap_ids,
            self.judge_run_ids,
            self.counterbalance_comparison_ids,
            self.judge_resolution_ids,
            self.superseded_context_ids,
        ):
            if len(refs) != len(set(refs)):
                raise ValueError("Frozen references must be unique")
        if not {"UNIVERSAL_ABSENCE", "CERTAIN_NOVELTY"} <= set(self.forbidden_claims):
            raise ValueError("Frozen shape must forbid universal absence and certain novelty")
        allowed = {
            permission
            for finding in self.target_findings
            for permission in finding.language_permission
        }
        if self.overall_finding.verdict == VerdictState.MIXED_CONTRIBUTION_SPECIFIC:
            allowed.add(LanguagePermissionClass.MIXED_BY_TARGET)
        if self.overall_finding.verdict == VerdictState.UNASSESSABLE:
            allowed.add(LanguagePermissionClass.ABSTENTION)
        if self.value_findings:
            allowed.add(LanguagePermissionClass.SEPARATE_VALUE_FINDING)
        if set(self.permitted_language) - allowed:
            raise ValueError("Frozen language exceeds the scoped target permissions")
        return self


def phase7_frozen_id(proposed: FrozenAdjudication) -> str:
    """Identify semantic findings independently of their freeze observation time."""
    return "p7frozen_" + canonical_hash(
        proposed.model_dump(mode="json", exclude={"adjudication_id", "frozen_at"})
    )
