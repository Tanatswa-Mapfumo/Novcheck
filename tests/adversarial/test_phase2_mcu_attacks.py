from copy import deepcopy
from datetime import date

import pytest

from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.intake.pipeline import understand_idea
from novelty_harness.mcu.alignment import align_decompositions, signature
from novelty_harness.mcu.models import MCUDecomposition
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import FIXED_TIME
from tests.fixtures.phase2 import RecordedLLM, attack_responses, candidate, decomposition


async def understand(text, responses):
    return await understand_idea(
        AssessmentRequest(idea_id="idea_attack", input_text=text, as_of=date(2026, 9, 26)),
        runner=SemanticRunner(RecordedLLM(responses)),
        clock=lambda: FIXED_TIME,
    )


@pytest.mark.parametrize(
    "text,contribution,withheld,advantage,expected",
    [
        ("An AI thing.", False, False, (), "INSUFFICIENT"),
        (
            "Help users, with AI revolutionary disruptive scalable technology.",
            True,
            False,
            (),
            "EXPLORATORY",
        ),
        ("Reduce costs by 99%.", True, False, ("Reduce costs by 99%.",), "EXPLORATORY"),
        ("Reduce costs. Core mechanism withheld.", True, True, (), "EXPLORATORY"),
    ],
)
async def test_vague_buzzword_performance_and_withheld_ideas_cannot_gain_resolution(
    text,
    contribution,
    withheld,
    advantage,
    expected,
):
    result = await understand(
        text,
        attack_responses(text, contribution=contribution, withheld=withheld, advantages=advantage),
    )
    assert result.sufficiency.state.value == expected
    assert "mechanism" in result.sufficiency.unassessable_dimensions
    assert result.active_mcu_version.mcus == ()
    if advantage:
        assert result.cir.claimed_advantages[0].statement == "Reduce costs by 99%."
        assert result.cir.claimed_advantages[0].maturity.value == "CLAIMED"


async def test_renamed_established_concept_does_not_become_novel_or_invented():
    text = "A controller stores responses to repeated requests."
    c = candidate(statement=text)
    c["mcu"].update(
        label="Response caching",
        features=[
            {"feature_id": "F1", "concept": "controller"},
            {"feature_id": "F2", "concept": "responses"},
        ],
        relationships=[{"subject": "F1", "relation": "STORES", "object": "F2"}],
    )
    result = await understand(text, attack_responses(text, candidates=(c,), mechanism=True))
    assert result.active_mcu_version.mcus[0].mechanism == text
    assert not result.cir.claimed_advantages
    assert not result.cir.user_supplied_evidence


async def test_giant_bundle_is_split_without_losing_independent_relationships():
    clauses = ["Sensor controls relay.", "Indicator reduces checks.", "Logger stores events."]
    units = []
    for i, (clause, subject, predicate, obj) in enumerate(
        zip(
            clauses,
            ("Sensor", "Indicator", "Logger"),
            ("CONTROLS", "REDUCES", "STORES"),
            ("relay", "checks", "events"),
            strict=True,
        )
    ):
        c = candidate(f"mcu_{i}", clause)
        c["mcu"].update(
            features=[
                {"feature_id": f"F{i}a", "concept": subject},
                {"feature_id": f"F{i}b", "concept": obj},
            ],
            relationships=[{"subject": f"F{i}a", "relation": predicate, "object": f"F{i}b"}],
        )
        units.append(c)
    text = " ".join(clauses)
    responses = attack_responses(text, candidates=tuple(units), mechanism=True)
    giant = candidate("mcu_giant", text)
    giant["mcu"].update(
        features=[f for c in units for f in c["mcu"]["features"]],
        relationships=[r for c in units for r in c["mcu"]["relationships"]],
    )
    responses["decompose_a"]["candidates"] = [giant]
    responses["criticize_mcus"]["resolutions"] = [
        {
            "strategy": "INDEPENDENCE_FOCUSED",
            "input_mcu_id": "mcu_giant",
            "output_mcu_ids": ["mcu_0", "mcu_1", "mcu_2"],
            "reason": "Three independent mechanisms",
        },
        *[
            r
            for r in responses["criticize_mcus"]["resolutions"]
            if r["strategy"] == "RELATIONSHIP_FOCUSED"
        ],
    ]
    result = await understand(text, responses)
    assert len(result.active_mcu_version.mcus) == 3
    assert sum(len(m.relationships) for m in result.active_mcu_version.mcus) == 3
    assert result.reconciliation.resolutions[0].input_mcu_id == "mcu_giant"


async def test_fragmented_causal_contribution_is_restored_with_relationship():
    text = "Sensor controls relay."
    responses = attack_responses(text, candidates=(candidate(),), mechanism=True)
    fragments = []
    for name in ("Sensor", "relay"):
        c = candidate("mcu_" + name.casefold(), name)
        c["source_support"] = [text]
        c["mcu"].update(
            mechanism=None, features=[{"feature_id": "F", "concept": name}], relationships=[]
        )
        fragments.append(c)
    responses["decompose_a"]["candidates"] = fragments
    responses["criticize_mcus"]["resolutions"] = [
        {
            "strategy": "INDEPENDENCE_FOCUSED",
            "input_mcu_id": c["mcu"]["mcu_id"],
            "output_mcu_ids": ["mcu_control"],
            "reason": "Ordinary ingredients restored into causal unit",
        }
        for c in fragments
    ] + [
        r
        for r in responses["criticize_mcus"]["resolutions"]
        if r["strategy"] == "RELATIONSHIP_FOCUSED"
    ]
    result = await understand(text, responses)
    assert len(result.active_mcu_version.mcus) == 1
    assert signature(result.active_mcu_version.mcus[0]) == frozenset(
        {("sensor", "controls", "relay")}
    )


async def test_arbitrary_specificity_and_buzzwords_do_not_add_units_or_raise_state():
    base = "Sensor controls relay."
    results = []
    for text in (base, base + " Only for green cars on Tuesdays.", base + " Disruptive AI! " * 80):
        results.append(
            await understand(
                text, attack_responses(text, candidates=(candidate(),), mechanism=True)
            )
        )
    assert all(len(r.active_mcu_version.mcus) == 1 for r in results)
    assert len({r.sufficiency.state for r in results}) == 1
    assert len({signature(r.active_mcu_version.mcus[0]) for r in results}) == 1


def combined():
    text = "Sensor controls relay."
    units = []
    for name in ("Sensor", "relay"):
        c = candidate("mcu_" + name.casefold(), name)
        c["mcu"].update(
            mechanism=None, features=[{"feature_id": "F", "concept": name}], relationships=[]
        )
        c["source_support"] = [text]
        units.append(c)
    combination = {
        "combination": {
            "combination_id": "C1",
            "label": "Control configuration",
            "statement": text,
            "member_ids": ["mcu_sensor", "mcu_relay"],
            "relationships": [
                {"subject": "mcu_sensor", "relation": "CONTROLS", "object": "mcu_relay"}
            ],
            "provenance": units[0]["mcu"]["provenance"],
        },
        "source_support": [text],
    }
    return text, attack_responses(
        text, candidates=tuple(units), mechanism=True, combinations=(combination,)
    )


async def test_known_components_with_meaningful_configuration_remain_separate():
    text, responses = combined()
    result = await understand(text, responses)
    assert len(result.active_mcu_version.mcus) == 2
    assert len(result.active_mcu_version.combinations) == 1
    assert result.active_mcu_version.combinations[0].relationships[0].relation == "CONTROLS"
    assert all(not m.relationships for m in result.active_mcu_version.mcus)


async def test_reconciliation_cannot_silently_drop_combination_bearing_relationship():
    text, responses = combined()
    responses["criticize_mcus"]["combinations"][0]["combination"]["relationships"] = []
    with pytest.raises(ValueError, match="combination"):
        await understand(text, responses)


async def test_contradictory_specification_preserves_ambiguity_and_lowers_ceiling():
    text = "Sensor controls relay. Sensor never controls relay."
    result = await understand(
        text, attack_responses(text, ambiguity=("Contradictory control requirements",))
    )
    assert result.cir.unknowns == ("Contradictory control requirements",)
    assert result.sufficiency.state.value == "EXPLORATORY"


async def test_removing_true_differentiator_reduces_mechanism_resolution():
    full = "Sensor controls relay."
    removed = "Sensor. Relay."
    a = await understand(full, attack_responses(full, candidates=(candidate(),), mechanism=True))
    b = await understand(removed, attack_responses(removed))
    assert a.sufficiency.state.value == "HIGH_RESOLUTION"
    assert b.sufficiency.state.value == "EXPLORATORY"
    assert b.reconciliation.structural_tests[2].passed is None
    assert not b.active_mcu_version.mcus


async def test_paraphrase_changes_display_not_grounded_structure_and_relation_reversal_does():
    left = candidate()
    right = deepcopy(left)
    right["mcu"]["label"] = "Relay regulation by sensor"
    a = MCUDecomposition.model_validate(decomposition("INDEPENDENCE_FOCUSED", [left]))
    b = MCUDecomposition.model_validate(decomposition("RELATIONSHIP_FOCUSED", [right]))
    assert (await align_decompositions(a, b)).pairs[0].relation == "EQUIVALENT"
    right["mcu"]["relationships"][0].update(subject="F2", object="F1")
    b = MCUDecomposition.model_validate(decomposition("RELATIONSHIP_FOCUSED", [right]))
    assert (await align_decompositions(a, b)).pairs[0].relation == "DISTINCT"


async def test_full_understanding_of_paraphrased_equivalent_idea_is_structurally_stable():
    original = "Sensor controls relay."
    paraphrase = "Relay is controlled by Sensor."
    c = candidate(statement=paraphrase)
    a = await understand(
        original, attack_responses(original, candidates=(candidate(),), mechanism=True)
    )
    b = await understand(paraphrase, attack_responses(paraphrase, candidates=(c,), mechanism=True))
    assert a.sufficiency.state == b.sufficiency.state
    assert (
        a.reconciliation.decomposition_stability
        == b.reconciliation.decomposition_stability
        == "STABLE"
    )
    assert signature(a.active_mcu_version.mcus[0]) == signature(b.active_mcu_version.mcus[0])


async def test_different_words_equivalent_relationships_need_explicit_checked_mapping():
    from tests.unit.mcu.test_alignment import pair

    c = candidate("mcu_b")
    c["mcu"]["features"][0]["concept"] = "probe"
    c["mcu"]["features"][1]["concept"] = "switch"
    a, b = pair(right=c)
    proposed = {
        "prompt_version": "alignment-v1",
        "mappings": [
            {
                "left_mcu_id": "mcu_control",
                "right_mcu_id": "mcu_b",
                "feature_pairs": [
                    {"left_feature_id": "F1", "right_feature_id": "F1"},
                    {"left_feature_id": "F2", "right_feature_id": "F2"},
                ],
                "explanation": "Probe and switch name the same supplied roles",
            }
        ],
    }
    result = await align_decompositions(
        a, b, runner=SemanticRunner(RecordedLLM({"align_mcus": proposed}))
    )
    assert result.pairs[0].relation == "EQUIVALENT"
