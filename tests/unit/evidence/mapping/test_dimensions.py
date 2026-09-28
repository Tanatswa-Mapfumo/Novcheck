import pytest

from novelty_harness.domain.enums import PrecedentState
from novelty_harness.domain.mcu import MCU, MCUCombination, MCUFeature, MCURelationship
from novelty_harness.evidence.mapping.dimensions import (
    CONTROL_FLOW_VERBS,
    build_combination_comparison_profile,
    build_mcu_comparison_profile,
    build_proposition,
)
from novelty_harness.evidence.mapping.models import ComparisonDimension
from novelty_harness.evidence.precedent.gates import classify_precedent
from tests.fixtures.phase5 import phase5_provenance
from tests.unit.evidence.precedent.test_classification import NOW, facts_for

ORIGIN = phase5_provenance("dimensions-test")


def mcu(mcu_id: str = "mcu_control", **overrides: object) -> MCU:
    values: dict[str, object] = {
        "mcu_id": mcu_id,
        "label": "Sensor control",
        "statement": "A sensor controls a relay",
        "mechanism": "temperature threshold drives a relay coil",
        "purpose": "switch a load automatically",
        "object_or_target": "relay",
        "intended_effect": "load switches without an operator",
        "context": "industrial cabinet",
        "features": (
            MCUFeature(feature_id="F1", concept="sensor"),
            MCUFeature(feature_id="F2", concept="relay"),
        ),
        "relationships": (MCURelationship(subject="sensor", relation="controls", object="relay"),),
        "provenance": ORIGIN,
    }
    values.update(overrides)
    return MCU.model_validate(values)


def test_same_features_with_different_relationship_stay_distinct() -> None:
    forward = build_mcu_comparison_profile(mcu())
    reversed_relationship = build_mcu_comparison_profile(
        mcu(relationships=(MCURelationship(subject="relay", relation="controls", object="sensor"),))
    )
    assert forward.features == reversed_relationship.features
    assert forward.relationships != reversed_relationship.relationships
    assert (
        build_proposition(forward).commitments
        != build_proposition(reversed_relationship).commitments
    )


def test_control_flow_is_derived_conservatively_from_stated_verbs() -> None:
    assert "triggers" in CONTROL_FLOW_VERBS
    workflow = build_mcu_comparison_profile(
        mcu(
            relationships=(
                MCURelationship(subject="risk", relation="triggers", object="review"),
                MCURelationship(subject="bracket", relation="mounts", object="panel"),
            )
        )
    )
    assert [item.describe() for item in workflow.control_flow] == ["risk triggers review"]
    proposition = build_proposition(workflow)
    dimensions = {item.commitment_id: item.dimension for item in proposition.commitments}
    assert dimensions["rel:0"] == ComparisonDimension.CONTROL_FLOW
    assert dimensions["rel:1"] == ComparisonDimension.RELATIONSHIPS


def test_missing_mechanism_stays_unknown_and_is_not_invented() -> None:
    profile = build_mcu_comparison_profile(mcu(mechanism=None, purpose=None, context=None))
    assert profile.mechanism is None
    assert ComparisonDimension.MECHANISM in profile.unknown_dimensions
    proposition = build_proposition(profile)
    assert all(item.commitment_id != "mech" for item in proposition.commitments)
    assert ComparisonDimension.MECHANISM in proposition.unknown_dimensions


def test_profile_never_invents_dimensions_for_a_bare_statement() -> None:
    bare = MCU(
        mcu_id="mcu_bare",
        label="Bare",
        statement="A vague idea",
        provenance=ORIGIN,
    )
    profile = build_mcu_comparison_profile(bare)
    assert set(profile.unknown_dimensions) == {
        ComparisonDimension.MECHANISM,
        ComparisonDimension.PURPOSE,
        ComparisonDimension.TARGET,
        ComparisonDimension.CONTEXT,
        ComparisonDimension.INTENDED_OUTCOME,
        ComparisonDimension.FEATURES,
        ComparisonDimension.RELATIONSHIPS,
        ComparisonDimension.CONTROL_FLOW,
    }
    proposition = build_proposition(profile)
    assert len(proposition.commitments) == 1
    assert proposition.commitments[0].commitment_id == "statement"
    assert proposition.commitments[0].text == "A vague idea"


def test_combination_profile_retains_member_and_configuration_structure() -> None:
    control = mcu()
    status = mcu(
        "mcu_status",
        label="Status indication",
        statement="An indicator shows the relay state",
        mechanism="lamp wired to the relay contact",
        purpose="show state",
        object_or_target="indicator",
        intended_effect="operator sees the state",
        context="industrial cabinet",
        features=(MCUFeature(feature_id="F3", concept="indicator"),),
        relationships=(MCURelationship(subject="relay", relation="drives", object="indicator"),),
    )
    combination = MCUCombination(
        combination_id="C1",
        label="Control and indication",
        statement="Control a relay and show its status",
        member_ids=("mcu_control", "mcu_status"),
        relationships=(
            MCURelationship(subject="control", relation="triggers", object="indication"),
        ),
        provenance=ORIGIN,
    )
    profile = build_combination_comparison_profile(combination, (control, status))
    assert profile.target_kind == "COMBINATION"
    assert profile.combination_members == ("mcu_control", "mcu_status")
    assert {item.mcu_id for item in profile.member_contributions} == {
        "mcu_control",
        "mcu_status",
    }
    assert profile.control_flow[0].relation == "triggers"
    proposition = build_proposition(profile)
    identifiers = {item.commitment_id for item in proposition.commitments}
    assert {
        "cfg",
        "member:mcu_control",
        "member:mcu_status",
        "crel:0",
        "member:mcu_status:feat:0",
        "member:mcu_status:rel:0",
    } <= identifiers
    configuration = next(item for item in proposition.commitments if item.commitment_id == "cfg")
    assert configuration.dimension == ComparisonDimension.ARCHITECTURE
    combination_relationship = next(
        item for item in proposition.commitments if item.commitment_id == "crel:0"
    )
    assert combination_relationship.dimension == ComparisonDimension.CONTROL_FLOW


def test_profiles_and_propositions_are_deterministic() -> None:
    first = build_mcu_comparison_profile(mcu())
    second = build_mcu_comparison_profile(mcu())
    assert first == second
    assert build_proposition(first) == build_proposition(second)
    assert build_proposition(first).proposition_id.startswith("prop_")


@pytest.mark.parametrize(
    "statement",
    (
        "Alpha and beta enable relay",
        "Alpha then beta enable relay",
        "Beta then alpha enable relay",
    ),
)
def test_split_features_do_not_cover_joint_or_ordered_statement(statement: str) -> None:
    profile = build_mcu_comparison_profile(
        mcu(
            "mcu_1",
            statement=statement,
            mechanism=None,
            purpose=None,
            object_or_target=None,
            intended_effect=None,
            context=None,
            features=(
                MCUFeature(feature_id="F1", concept="alpha enable relay"),
                MCUFeature(feature_id="F2", concept="beta enable relay"),
            ),
            relationships=(),
        )
    )
    proposition = build_proposition(profile)
    material = next(
        item for item in proposition.commitments if item.commitment_id == "statement:material"
    )
    assert material.text == statement
    assert material.dimension == ComparisonDimension.CONSTRAINTS
    assert material.relationship is None

    feature_only = {item.commitment_id: "SUPPORTED" for item in proposition.commitments}
    feature_only["statement:material"] = "NOT_SUPPORTED"
    partial = classify_precedent(
        facts_for(
            proposition,
            states=feature_only,
            matching=(ComparisonDimension.FEATURES,),
            decisive=False,
        ),
        clock=lambda: NOW,
    )
    assert partial.relation != PrecedentState.DIRECT_PRECEDENT
    complete = classify_precedent(
        facts_for(
            proposition,
            states={item.commitment_id: "SUPPORTED" for item in proposition.commitments},
            matching=(ComparisonDimension.FEATURES, ComparisonDimension.CONSTRAINTS),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert complete.relation == PrecedentState.DIRECT_PRECEDENT


def test_reversed_structured_relation_does_not_cover_statement_direction() -> None:
    proposition = build_proposition(
        build_mcu_comparison_profile(
            mcu(
                statement="Sensor controls relay",
                mechanism=None,
                purpose=None,
                object_or_target=None,
                intended_effect=None,
                context=None,
                features=(),
                relationships=(
                    MCURelationship(subject="relay", relation="controls", object="sensor"),
                ),
            )
        )
    )
    assert {item.commitment_id for item in proposition.commitments} == {
        "rel:0",
        "statement:material",
    }
    assert (
        next(
            item for item in proposition.commitments if item.commitment_id == "statement:material"
        ).relationship
        is None
    )


def test_combination_member_qualifier_survives_generic_mechanism() -> None:
    qualified = mcu(
        statement="A relay activates only after two sensors agree",
        mechanism="threshold switches relay",
    )
    other = mcu("mcu_status", statement="Indicator shows relay state", mechanism=None)
    combination = MCUCombination(
        combination_id="C2",
        label="Qualified control and status",
        statement="Qualified control also shows relay state",
        member_ids=(qualified.mcu_id, other.mcu_id),
        provenance=ORIGIN,
    )
    proposition = build_proposition(
        build_combination_comparison_profile(combination, (qualified, other))
    )
    material = next(
        item
        for item in proposition.commitments
        if item.commitment_id == "member:mcu_control:statement:material"
    )
    assert material.text == qualified.statement
    assert material.relationship is None
    assert any(item.commitment_id == "cfg" for item in proposition.commitments)
    assert all(
        item.commitment_id != "member:mcu_status:statement:material"
        for item in proposition.commitments
    )


def test_exactly_structured_joint_relationship_does_not_duplicate_statement() -> None:
    proposition = build_proposition(
        build_mcu_comparison_profile(
            mcu(
                statement="Alpha and beta enable relay",
                mechanism=None,
                purpose=None,
                object_or_target=None,
                intended_effect=None,
                context=None,
                features=(),
                relationships=(
                    MCURelationship(subject="alpha and beta", relation="enable", object="relay"),
                ),
            )
        )
    )
    assert [item.commitment_id for item in proposition.commitments] == ["rel:0"]
