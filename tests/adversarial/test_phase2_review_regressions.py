from copy import deepcopy
from datetime import date

import pytest

from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.intake.pipeline import understand_idea
from novelty_harness.mcu.overrides import MCUOverrideOperation, apply_override
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import FIXED_TIME, make_fixture
from tests.fixtures.phase2 import RecordedLLM, attack_responses, candidate, understanding_responses


async def understand(text, responses):
    return await understand_idea(
        AssessmentRequest(idea_id="idea_review", input_text=text, as_of=date(2026, 9, 26)),
        runner=SemanticRunner(RecordedLLM(responses)),
        clock=lambda: FIXED_TIME,
    )


async def test_shared_paragraph_does_not_make_identical_independent_units_disagree():
    text = make_fixture().request.input_text
    responses = understanding_responses()
    for task in ("decompose_a", "decompose_b"):
        for unit in responses[task]["candidates"]:
            unit["source_support"] = [text]
    responses["align_mcus"] = {"prompt_version": "alignment-v1", "mappings": []}
    result = await understand(text, responses)
    assert result.reconciliation.decomposition_stability == "STABLE"
    assert result.reconciliation.unresolved_disagreements == ()
    assert result.sufficiency.state.value == "HIGH_RESOLUTION"
    assert len(result.active_mcu_version.mcus) == 2


@pytest.mark.parametrize("predicate", ["CONTROLS", "S"])
async def test_input_components_do_not_ground_an_invented_relationship_predicate(predicate):
    text = "Sensor. Relay."
    unit = candidate(statement=text)
    unit["mcu"]["relationships"][0]["relation"] = predicate
    responses = attack_responses(text, candidates=(unit,), mechanism=True)
    with pytest.raises(ValueError, match="relationship.*support"):
        await understand(text, responses)


async def test_reconciliation_cannot_remove_a_supported_operating_restriction():
    text = "Sensor controls relay only above 50 degrees."
    unit = candidate(statement=text)
    responses = attack_responses(text, candidates=(unit,), mechanism=True)
    shortened = responses["criticize_mcus"]["candidates"][0]
    # The proposal remains extractively grounded, but broadens the mechanism.
    shortened["mcu"].update(statement="Sensor controls relay", mechanism=None)
    responses["decompose_a"]["candidates"] = [deepcopy(unit)]
    responses["decompose_b"]["candidates"] = [deepcopy(unit)]
    responses["decompose_a"]["candidates"][0]["mcu"].update(statement=text, mechanism=text)
    responses["decompose_b"]["candidates"][0]["mcu"].update(statement=text, mechanism=text)
    with pytest.raises(ValueError, match="material.*qualifier"):
        await understand(text, responses)


@pytest.mark.parametrize("withheld", [False, True])
async def test_later_positive_signals_cannot_remove_normalized_mechanism_blocker(withheld):
    text = "Reduce costs." + (" Core mechanism withheld." if withheld else "")
    responses = attack_responses(text, mechanism=True, withheld=withheld)
    responses["normalize_idea"]["mechanism"] = None
    responses["normalize_idea"]["source_attributions"] = [
        a
        for a in responses["normalize_idea"]["source_attributions"]
        if a["field_path"] != "mechanism"
    ]
    responses["assess_sufficiency"]["signals"]["withheld_mechanism"] = False
    for check in responses["criticize_mcus"]["structural_tests"]:
        check.update(passed=True, severity="INFO")
    result = await understand(text, responses)
    assert result.sufficiency.state.value == "EXPLORATORY"
    assert "mechanism" in result.sufficiency.unassessable_dimensions
    assert "mechanism" not in result.sufficiency.assessable_dimensions
    if withheld:
        assert "Core mechanism withheld" in result.cir.unknowns
        assert "Core mechanism withheld" in result.sufficiency.missing_information


def combination_responses():
    text = "Sensor controls relay. Relay controls Sensor. Sensor reduces relay."
    units = []
    for name in ("Sensor", "relay"):
        unit = candidate("mcu_" + name.casefold(), name)
        unit["mcu"].update(
            mechanism=None,
            features=[{"feature_id": "F", "concept": name}],
            relationships=[],
        )
        units.append(unit)
    combination = {
        "combination": {
            "combination_id": "C1",
            "label": "Control configuration",
            "statement": "Sensor controls relay.",
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


@pytest.mark.parametrize("difference", ["direction", "predicate"])
async def test_opposing_combination_graphs_cannot_acquire_stable_consensus(difference):
    text, responses = combination_responses()
    other = deepcopy(responses["decompose_b"]["combinations"][0])
    other["combination"]["combination_id"] = "C2"
    relation = other["combination"]["relationships"][0]
    if difference == "direction":
        other["combination"]["statement"] = "Relay controls Sensor."
        relation.update(subject="mcu_relay", object="mcu_sensor")
    else:
        other["combination"]["statement"] = "Sensor reduces relay."
        relation["relation"] = "REDUCES"
    responses["decompose_b"]["combinations"] = [other]
    responses["criticize_mcus"]["combinations"].append(deepcopy(other))
    result = await understand(text, responses)
    assert result.reconciliation.decomposition_stability == "MATERIAL_DISAGREEMENT"
    assert result.reconciliation.assessment_ceiling.value == "EXPLORATORY"
    assert result.sufficiency.state.value == "EXPLORATORY"
    assert set(result.reconciliation.affected_mcu_ids) == {"mcu_sensor", "mcu_relay"}
    assert any("combination" in d for d in result.reconciliation.unresolved_disagreements)
    assert len(result.active_mcu_version.combinations) == 2


def merge_operation(**updates):
    return MCUOverrideOperation(
        operation_id="override_merge",
        kind="MERGE_MCUS",
        payload={
            "payload_version": "0.2",
            "mcu_ids": ["mcu_sensor", "mcu_relay"],
            "mcu": candidate("mcu_merged")["mcu"],
            "combination_retirements": ["C1"],
            **updates,
        },
        reason="The causal relationship is one contribution, not two ingredients.",
        actor="user",
        occurred_at=FIXED_TIME,
    )


async def test_user_can_explicitly_retire_a_combination_while_merging_all_members():
    text, responses = combination_responses()
    parent = (await understand(text, responses)).active_mcu_version
    before = parent.model_dump_json()
    child = apply_override(parent, merge_operation())
    assert child.combinations == ()
    assert [m.mcu_id for m in child.mcus] == ["mcu_merged"]
    assert len(child.mcus[0].relationships) == 1
    assert child.parent_version_id == parent.version_id
    audit = child.overrides[-1]
    assert audit.payload["combination_retirements"] == ["C1"]
    assert audit.previous_combinations == parent.combinations
    assert audit.before_graph_hash != audit.after_graph_hash
    assert parent.model_dump_json() == before


@pytest.mark.parametrize(
    "change,message",
    [
        ({"combination_retirements": ["missing"]}, "unknown combination"),
        ({"combination_retirements": ["C1", "C1"]}, "duplicate combination retirement"),
        ({"payload_version": "0.1"}, "payload version"),
        ({"combination_updates": "same"}, "retired.*updated"),
    ],
)
async def test_invalid_combination_retirements_reject_without_mutating_history(change, message):
    text, responses = combination_responses()
    parent = (await understand(text, responses)).active_mcu_version
    before = parent.model_dump_json()
    if change.get("combination_updates") == "same":
        change = {"combination_updates": [parent.combinations[0].model_dump(mode="json")]}
    with pytest.raises(ValueError, match=message):
        apply_override(parent, merge_operation(**change))
    assert parent.model_dump_json() == before
