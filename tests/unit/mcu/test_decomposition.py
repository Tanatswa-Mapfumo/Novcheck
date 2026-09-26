import pytest

from novelty_harness.intake.normalization import GroundingError
from novelty_harness.mcu.decomposition import (
    IndependenceFocusedDecomposer,
    RelationshipFocusedDecomposer,
)
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM, candidate, decomposition


def idea(text="Sensor controls relay."):
    return make_fixture().idea.model_copy(update={"original_input": text})


async def test_b_only_consumes_independent_original_context_and_distinct_prompt():
    a = candidate("mcu_private_A")
    llm = RecordedLLM(
        {
            "decompose_a": decomposition("INDEPENDENCE_FOCUSED", [a]),
            "decompose_b": decomposition("RELATIONSHIP_FOCUSED"),
        }
    )
    runner = SemanticRunner(llm)
    left = await IndependenceFocusedDecomposer(runner).decompose_result(idea())
    right = await RelationshipFocusedDecomposer(runner).decompose_result(idea())
    b_context = " ".join(block.text for block in llm.requests[1][2])
    assert "mcu_private_A" not in b_context
    assert left.strategy != right.strategy
    assert llm.requests[0][2][0].text != llm.requests[1][2][0].text
    assert (
        llm.requests[0][3].metadata["prompt_version"]
        != llm.requests[1][3].metadata["prompt_version"]
    )
    assert right.candidates[0].mcu.relationships[0].relation == "CONTROLS"


@pytest.mark.parametrize("mutation", ["support", "mechanism", "endpoint", "duplicate"])
async def test_untrusted_candidates_cannot_invent_or_dangle(mutation):
    c = candidate()
    items = [c]
    if mutation == "support":
        c["source_support"] = ["Secret mechanism"]
    elif mutation == "mechanism":
        c["mcu"]["mechanism"] = "Invented mechanism"
    elif mutation == "endpoint":
        c["mcu"]["relationships"][0]["object"] = "missing"
    else:
        items.append(c)
    llm = RecordedLLM({"decompose_a": decomposition("INDEPENDENCE_FOCUSED", items)})
    with pytest.raises((GroundingError, ValueError)):
        await IndependenceFocusedDecomposer(SemanticRunner(llm)).decompose(idea())


async def test_withheld_mechanism_can_produce_no_candidates_without_invention():
    llm = RecordedLLM(
        {
            "decompose_b": decomposition(
                "RELATIONSHIP_FOCUSED", [], global_unknowns=["Mechanism withheld"]
            )
        }
    )
    result = await RelationshipFocusedDecomposer(SemanticRunner(llm)).decompose_result(
        idea("Mechanism withheld.")
    )
    assert result.candidates == ()
    assert result.global_unknowns == ("Mechanism withheld",)
