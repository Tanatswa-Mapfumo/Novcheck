import pytest

from tests.fixtures.phase2 import reconciliation_proposal
from tests.unit.mcu.test_reconciliation import run


@pytest.mark.parametrize(
    "name",
    [
        "REMOVAL",
        "INDEPENDENCE",
        "RELATIONSHIP_PRESERVATION",
        "MERGE",
        "PARAPHRASE_STABILITY",
        "SPECIFICITY",
    ],
)
@pytest.mark.parametrize("passed", [False, None])
async def test_each_material_structural_failure_or_unknown_caps_resolution(name, passed):
    proposal = reconciliation_proposal()
    for test in proposal["structural_tests"]:
        if test["test_name"] == name:
            test.update(passed=passed, severity="MATERIAL")
    result = await run(proposal)
    assert result.decomposition_stability == "MATERIAL_DISAGREEMENT"
    assert result.assessment_ceiling.value == "EXPLORATORY"
    assert result.unresolved_disagreements
    assert result.affected_mcu_ids == ("mcu_control",)
