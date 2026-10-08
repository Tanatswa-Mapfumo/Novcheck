import pytest
from pydantic import ValidationError

from novelty_harness.adjudication.frozen import FrozenAdjudication
from novelty_harness.adjudication.models import Phase7RunState, TargetRef
from novelty_harness.adjudication.needs import InputClarificationNeed, ResearchGapRequest
from novelty_harness.adjudication.roles import (
    DisputeResolutionCandidate,
    ProsecutionCase,
    RoleArgument,
)
from novelty_harness.domain.adjudication import FrozenAdjudication as FixtureFrozenAdjudication

SCOPE = {
    "assessment_id": "asm_contract",
    "assessment_context_id": "p7ctx_contract",
    "phase6_snapshot_id": "p6snap_contract",
    "target_id": "mcu_contract",
}


def _challenge(identifier: str = "p7arg_one") -> RoleArgument:
    return RoleArgument(
        **SCOPE,
        argument_id=identifier,
        thesis="Earlier source reproduces the claimed mechanism",
        effect="DIRECT_CHALLENGE",
    )


def test_phase7_contracts_are_frozen_distinct_and_typed() -> None:
    assert Phase7RunState.SUPERSEDED_BY_NEW_ASSESSMENT_STATE.value == (
        "SUPERSEDED_BY_NEW_ASSESSMENT_STATE"
    )
    assert FrozenAdjudication is not FixtureFrozenAdjudication
    assert TargetRef(kind="MCU", id="mcu_contract").id == "mcu_contract"

    case = ProsecutionCase(**SCOPE, case_id="p7case_prosecution", challenges=(_challenge(),))
    with pytest.raises(ValidationError):
        case.target_id = "mcu_other"
    with pytest.raises(ValidationError):
        ProsecutionCase.model_validate({**case.model_dump(), "verdict": "POTENTIALLY_NOVEL"})
    with pytest.raises(ValidationError):
        ProsecutionCase.model_validate({**case.model_dump(), "HIGH_IMPACT": True})
    with pytest.raises(ValidationError):
        ProsecutionCase(
            **SCOPE, case_id="p7case_duplicate", challenges=(_challenge(), _challenge())
        )

    with pytest.raises(ValidationError):
        ResearchGapRequest(
            **SCOPE,
            request_id="p7gap_wrong",
            requesting_stage="FIRST_PASS",
            gap_type="COVERAGE",
            reason="Missing external evidence",
            research_hypothesis="Historical product may exist",
            material_gate="A",
            stop_condition="TEST_COVERAGE_BRANCH",
        )
    assert (
        InputClarificationNeed(
            **SCOPE,
            need_id="p7need_one",
            reason="Mechanism unspecified",
            missing_input_fields=("mechanism",),
            resolution_requirement="Clarify mechanism",
        ).material_gate
        == "A"
    )

    candidate = DisputeResolutionCandidate(
        **SCOPE,
        candidate_id="p7candidate_one",
        dispute_id="p7dispute_one",
        gate_c_candidate="DIRECT_ESTABLISHED",
        basis_argument_ids=("p7arg_one",),
        bounded=True,
        reason="Direct chain accepted",
    )
    with pytest.raises(ValidationError):
        DisputeResolutionCandidate.model_validate(
            {**candidate.model_dump(), "verdict": "NOT_NOVEL_AT_CLAIMED_LEVEL"}
        )
    with pytest.raises(ValidationError):
        DisputeResolutionCandidate.model_validate(
            {**candidate.model_dump(), "language_ceiling": "CLAIM_SPECIFIC_NEGATIVE"}
        )


def test_phase7_contract_rejects_cross_snapshot_target() -> None:
    foreign = _challenge().model_copy(update={"phase6_snapshot_id": "p6snap_foreign"})
    with pytest.raises(ValidationError):
        ProsecutionCase(**SCOPE, case_id="p7case_foreign", challenges=(foreign,))


def test_pre_review_role_contract_cannot_be_reinterpreted() -> None:
    case = ProsecutionCase(**SCOPE, case_id="p7case_legacy", challenges=(_challenge(),))
    legacy = {**case.model_dump(), "contract_kind": "phase7-prosecution-case-v1"}
    with pytest.raises(ValidationError):
        ProsecutionCase.model_validate(legacy)
