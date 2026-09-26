import pytest

from novelty_harness.mcu.alignment import align_decompositions
from novelty_harness.mcu.models import MCUDecomposition
from novelty_harness.mcu.reconciliation import reconcile_decompositions
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM, candidate, decomposition, reconciliation_proposal


async def run(proposal=None, right=None):
    left = MCUDecomposition.model_validate(decomposition("INDEPENDENCE_FOCUSED"))
    right = MCUDecomposition.model_validate(
        decomposition("RELATIONSHIP_FOCUSED", [right or candidate()])
    )
    aligned = await align_decompositions(left, right)
    idea = make_fixture().idea.model_copy(update={"original_input": "Sensor controls relay."})
    return await reconcile_decompositions(
        idea,
        left,
        right,
        aligned,
        runner=SemanticRunner(
            RecordedLLM({"criticize_mcus": proposal or reconciliation_proposal()})
        ),
    )


async def test_stable_graph_runs_all_six_tests_and_freezes_supported_structure():
    result = await run()
    assert result.decomposition_stability == "STABLE"
    assert result.assessment_ceiling.value == "HIGH_RESOLUTION"
    assert len(result.structural_tests) == 6
    assert {t.test_name for t in result.structural_tests} == {
        "REMOVAL",
        "INDEPENDENCE",
        "RELATIONSHIP_PRESERVATION",
        "MERGE",
        "PARAPHRASE_STABILITY",
        "SPECIFICITY",
    }
    assert result.mcus[0].relationships[0].relation == "CONTROLS"


async def test_material_relationship_disagreement_cannot_be_hidden_by_model_consensus():
    right = candidate()
    right["mcu"]["relationships"][0].update(subject="F2", object="F1")
    with pytest.raises(ValueError, match="relationship"):
        await run(reconciliation_proposal(), right)


async def test_preserved_opposing_interpretations_remain_material_not_consensus():
    a = candidate()
    b = candidate("mcu_reverse", "Relay controls Sensor.")
    b["mcu"]["relationships"][0].update(subject="F2", object="F1")
    left = MCUDecomposition.model_validate(decomposition("INDEPENDENCE_FOCUSED", [a]))
    right = MCUDecomposition.model_validate(decomposition("RELATIONSHIP_FOCUSED", [b]))
    aligned = await align_decompositions(left, right)
    proposal = reconciliation_proposal([a, b], right_ids=("mcu_reverse",))
    idea = make_fixture().idea.model_copy(
        update={"original_input": "Sensor controls relay. Relay controls Sensor."}
    )
    result = await reconcile_decompositions(
        idea, left, right, aligned, runner=SemanticRunner(RecordedLLM({"criticize_mcus": proposal}))
    )
    assert len(result.mcus) == 2
    assert result.decomposition_stability == "MATERIAL_DISAGREEMENT"
    assert result.assessment_ceiling.value == "EXPLORATORY"
    assert set(result.affected_mcu_ids) == {"mcu_control", "mcu_reverse"}


@pytest.mark.parametrize(
    "change", ["missing_test", "unknown_reference", "drop_resolution", "invent", "lose_link"]
)
async def test_structural_critic_output_is_validated_not_trusted(change):
    p = reconciliation_proposal()
    if change == "missing_test":
        p["structural_tests"].pop()
    elif change == "unknown_reference":
        p["structural_tests"][0]["mcu_ids"] = ["mcu_absent"]
    elif change == "drop_resolution":
        p["resolutions"].pop()
    elif change == "invent":
        p["candidates"][0]["mcu"]["mechanism"] = "Uses undisclosed fusion"
    else:
        p["candidates"][0]["mcu"]["relationships"] = []
    with pytest.raises(ValueError):
        await run(p)
