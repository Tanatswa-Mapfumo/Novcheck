import pytest

from novelty_harness.intake.sufficiency import SufficiencyReasoning, apply_sufficiency_ceiling
from tests.fixtures.phase1 import make_fixture


def reasoning(**updates):
    return SufficiencyReasoning.model_validate(
        {
            "proposed_state": "HIGH_RESOLUTION",
            "assessable_dimensions": ["mechanism"],
            "unassessable_dimensions": [],
            "missing_information": [],
            "consequences": [],
            "prompt_version": "sufficiency-v1",
            "signals": {
                "problem_defined": True,
                "contribution_identifiable": True,
                "mechanism_described": True,
                "relationship_structure_described": True,
                "comparison_scope_identifiable": True,
                "critical_unknowns": [],
                **updates,
            },
            "source_attributions": [
                {"field_path": name, "supporting_excerpt": "A temperature sensor controls a relay"}
                for name in (
                    "problem_defined",
                    "contribution_identifiable",
                    "mechanism_described",
                    "relationship_structure_described",
                    "comparison_scope_identifiable",
                )
            ],
        }
    )


@pytest.mark.parametrize(
    "updates,expected",
    [
        ({"contribution_identifiable": False}, "INSUFFICIENT"),
        ({"mechanism_described": False}, "EXPLORATORY"),
        ({"comparison_scope_identifiable": False}, "EXPLORATORY"),
        ({"relationship_structure_described": False}, "ASSESSABLE"),
        ({"critical_unknowns": ["contradiction unresolved"]}, "ASSESSABLE"),
        ({"withheld_mechanism": True}, "EXPLORATORY"),
        ({}, "HIGH_RESOLUTION"),
    ],
)
def test_structural_signals_apply_deterministic_ceiling(updates, expected):
    idea = make_fixture().idea.model_copy(update={"unknowns": ()})
    result = apply_sufficiency_ceiling(reasoning(**updates), idea)
    assert result.state.value == expected
    if updates.get("withheld_mechanism") or updates.get("mechanism_described") is False:
        assert "mechanism" in result.unassessable_dimensions
        assert "mechanism" not in result.assessable_dimensions
        assert result.missing_information


def test_irrelevant_detail_and_performance_claim_cannot_raise_sufficiency():
    base = make_fixture().idea
    limited = reasoning(mechanism_described=False)
    for text in (
        base.original_input,
        base.original_input + " revolutionary " * 500,
        base.original_input + " Reduce checks by 99%.",
    ):
        result = apply_sufficiency_ceiling(
            limited, base.model_copy(update={"original_input": text})
        )
        assert result.state.value == "EXPLORATORY"


def test_positive_signals_without_input_support_do_not_raise_resolution():
    ungrounded = reasoning().model_copy(update={"source_attributions": ()})
    assert apply_sufficiency_ceiling(ungrounded, make_fixture().idea).state.value == "INSUFFICIENT"


def test_proposed_low_state_is_never_promoted_and_contradiction_caps_resolution():
    idea = make_fixture().idea.model_copy(update={"unknowns": ()})
    low = SufficiencyReasoning.model_validate(
        {**reasoning().model_dump(), "proposed_state": "EXPLORATORY"}
    )
    assert apply_sufficiency_ceiling(low, idea).state.value == "EXPLORATORY"
    assert (
        apply_sufficiency_ceiling(reasoning(contradictory_specification=True), idea).state.value
        == "EXPLORATORY"
    )
