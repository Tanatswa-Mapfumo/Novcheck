import pytest

from novelty_harness.mcu.alignment import align_decompositions
from novelty_harness.mcu.models import MCUDecomposition
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase2 import RecordedLLM, candidate, decomposition


def pair(left=None, right=None):
    return (
        MCUDecomposition.model_validate(
            decomposition("INDEPENDENCE_FOCUSED", [left or candidate()])
        ),
        MCUDecomposition.model_validate(
            decomposition("RELATIONSHIP_FOCUSED", [right or candidate("mcu_b")])
        ),
    )


async def test_paraphrase_same_grounded_mechanism_graph_aligns_not_ids_or_display_label():
    left, right = pair()
    c = right.candidates[0]
    altered = c.model_copy(update={"mcu": c.mcu.model_copy(update={"label": "Relay regulation"})})
    right = right.model_copy(update={"candidates": (altered,)})
    result = await align_decompositions(left, right)
    assert result.pairs[0].relation == "EQUIVALENT"
    assert result.unmatched_left == result.unmatched_right == ()


@pytest.mark.parametrize("change", ["reverse", "predicate", "qualifier"])
async def test_same_nouns_different_meaning_not_forced_equivalent(change):
    c = candidate("mcu_b")
    if change == "reverse":
        c["mcu"]["relationships"][0].update(subject="F2", object="F1")
    elif change == "predicate":
        c["mcu"]["relationships"][0]["relation"] = "VERIFIES"
    else:
        c["mcu"]["context"] = "Only on Tuesdays"
    result = await align_decompositions(*pair(right=c))
    assert result.pairs[0].relation != "EQUIVALENT"
    assert result.pairs[0].relationship_differences


async def test_different_concepts_same_topology_is_unresolved_without_semantic_mapping():
    c = candidate("mcu_b")
    c["mcu"]["features"][0]["concept"] = "probe"
    c["mcu"]["features"][1]["concept"] = "switch"
    result = await align_decompositions(*pair(right=c))
    assert result.pairs[0].relation == "UNRESOLVED"


async def test_merge_split_is_subsumption_not_equivalence():
    c = candidate("mcu_b")
    c["mcu"]["features"] = c["mcu"]["features"][:1]
    c["mcu"]["relationships"] = []
    result = await align_decompositions(*pair(right=c))
    assert result.pairs[0].relation == "LEFT_SUBSUMES_RIGHT"


async def test_ambiguous_multiple_matches_are_preserved():
    left, right = pair()
    second = right.candidates[0].model_copy(
        update={"mcu": right.candidates[0].mcu.model_copy(update={"mcu_id": "mcu_c"})}
    )
    result = await align_decompositions(
        left, right.model_copy(update={"candidates": (*right.candidates, second)})
    )
    assert len(result.pairs) == 2
    assert all(p.relation == "UNRESOLVED" for p in result.pairs)


@pytest.mark.parametrize("reverse,expected", [(False, "EQUIVALENT"), (True, "UNRESOLVED")])
async def test_semantic_alias_mapping_must_preserve_directed_relationships(reverse, expected):
    c = candidate("mcu_b")
    c["mcu"]["features"][0]["concept"] = "probe"
    c["mcu"]["features"][1]["concept"] = "switch"
    if reverse:
        c["mcu"]["relationships"][0].update(subject="F2", object="F1")
    proposal = {
        "prompt_version": "alignment-v1",
        "mappings": [
            {
                "left_mcu_id": "mcu_control",
                "right_mcu_id": "mcu_b",
                "feature_pairs": [
                    {"left_feature_id": "F1", "right_feature_id": "F1"},
                    {"left_feature_id": "F2", "right_feature_id": "F2"},
                ],
                "explanation": "Aliases for the same supplied mechanism",
            }
        ],
    }
    result = await align_decompositions(
        *pair(right=c), runner=SemanticRunner(RecordedLLM({"align_mcus": proposal}))
    )
    assert result.pairs[0].relation == expected
