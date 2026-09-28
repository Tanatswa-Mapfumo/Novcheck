from novelty_harness.domain.enums import PrecedentState
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    EvidenceProposition,
)
from novelty_harness.evidence.precedent.counterfactuals import counterfactual_removal
from novelty_harness.evidence.precedent.gates import (
    classify_precedent,
    summarize_multi_source,
)
from tests.unit.evidence.precedent.test_classification import (
    NOW,
    RELATIONSHIP,
    commitment,
    facts_for,
    proposition,
)


def combination_proposition() -> EvidenceProposition:
    return proposition(
        commitment("f1", ComparisonDimension.FEATURES, text="component one"),
        commitment("f2", ComparisonDimension.FEATURES, text="component two"),
        commitment(
            "rel",
            ComparisonDimension.RELATIONSHIPS,
            text="sensor controls relay",
            relationship=RELATIONSHIP,
        ),
    )


def component_only_proposition() -> EvidenceProposition:
    return proposition(
        commitment("f1", ComparisonDimension.FEATURES, text="component one"),
        commitment("f2", ComparisonDimension.FEATURES, text="component two"),
        commitment(
            "rel",
            ComparisonDimension.RELATIONSHIPS,
            text="sensor controls relay",
            relationship=RELATIONSHIP,
        ),
    )


def test_three_sources_stitched_components_never_become_direct() -> None:
    target = combination_proposition()
    source_a = classify_precedent(
        facts_for(
            target,
            states={"f1": "SUPPORTED", "f2": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            source_id="src_a",
        ),
        clock=lambda: NOW,
    )
    source_b = classify_precedent(
        facts_for(
            target,
            states={"f1": "NOT_SUPPORTED", "f2": "SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            source_id="src_b",
        ),
        clock=lambda: NOW,
    )
    source_c = classify_precedent(
        facts_for(
            target,
            states={"f1": "NOT_SUPPORTED", "f2": "NOT_SUPPORTED", "rel": "SUPPORTED"},
            matching=(ComparisonDimension.RELATIONSHIPS,),
            source_id="src_c",
        ),
        clock=lambda: NOW,
    )
    assert source_a.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    assert source_b.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    assert source_c.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    assert source_c.relation != PrecedentState.DIRECT_PRECEDENT
    summary = summarize_multi_source((source_a, source_b, source_c), mcu_id="mcu_1")
    assert summary.combination_context == "MULTI_SOURCE_COMBINATION_ONLY"
    assert summary.single_source_direct_eligible is False
    assert summary.stitched_direct_forbidden is True
    assert summary.contributing_roots == 3
    assert all(
        classification.relation != PrecedentState.DIRECT_PRECEDENT
        for classification in (source_a, source_b, source_c)
    )


def test_all_components_without_the_relationship_is_not_direct() -> None:
    target = component_only_proposition()
    classification = classify_precedent(
        facts_for(
            target,
            states={"f1": "SUPPORTED", "f2": "SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            missing=(ComparisonDimension.RELATIONSHIPS,),
            source_id="src_a",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    assert classification.configuration_gap
    summary = summarize_multi_source((classification,), mcu_id="mcu_1")
    assert summary.single_source_direct_eligible is False
    assert summary.combination_context == "NONE"


def test_one_source_with_everything_is_the_only_direct_path() -> None:
    target = combination_proposition()
    classification = classify_precedent(
        facts_for(
            target,
            states={"f1": "SUPPORTED", "f2": "SUPPORTED", "rel": "SUPPORTED"},
            matching=(
                ComparisonDimension.FEATURES,
                ComparisonDimension.RELATIONSHIPS,
            ),
            decisive=True,
            chronology="PREDATES_CUTOFF",
            source_id="src_a",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.DIRECT_PRECEDENT
    assert classification.single_source is True
    summary = summarize_multi_source((classification,), mcu_id="mcu_1")
    assert summary.single_source_direct_eligible is True
    assert summary.combination_context == "NONE"


def test_versions_and_family_duplicates_count_as_one_lineage_root() -> None:
    target = combination_proposition()
    first = classify_precedent(
        facts_for(
            target,
            states={"f1": "SUPPORTED", "f2": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            source_id="src_a",
        ),
        clock=lambda: NOW,
    )
    second = classify_precedent(
        facts_for(
            target,
            states={"f1": "SUPPORTED", "f2": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            source_id="src_b",
        ),
        clock=lambda: NOW,
    )
    summary = summarize_multi_source(
        (first, second),
        mcu_id="mcu_1",
        independent_root_of={"src_a": "src_root", "src_b": "src_root"},
    )
    assert summary.independent_roots == 1
    assert summary.contributing_roots == 1
    assert summary.combination_context == "NONE"
    assert summary.single_source_direct_eligible is False


def test_multiple_component_sources_remain_combination_context_only() -> None:
    target = combination_proposition()
    left = classify_precedent(
        facts_for(
            target,
            states={"f1": "SUPPORTED", "f2": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            source_id="src_a",
        ),
        clock=lambda: NOW,
    )
    right = classify_precedent(
        facts_for(
            target,
            states={"f1": "NOT_SUPPORTED", "f2": "SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(ComparisonDimension.FEATURES,),
            source_id="src_b",
        ),
        clock=lambda: NOW,
    )
    summary = summarize_multi_source((left, right), mcu_id="mcu_1")
    assert summary.combination_context == "MULTI_SOURCE_COMBINATION_ONLY"
    assert summary.contributing_roots == 2
    assert "never constitute one-source direct precedent" in summary.summary[0]


def test_counterfactual_removal_localizes_the_remaining_distinction() -> None:
    target = proposition(
        commitment("mech", ComparisonDimension.MECHANISM, text="threshold drives a coil"),
        commitment("f1", ComparisonDimension.FEATURES, text="component one"),
        commitment("f2", ComparisonDimension.FEATURES, text="component two"),
        commitment("f3", ComparisonDimension.FEATURES, text="component three"),
    )
    classification = classify_precedent(
        facts_for(
            target,
            states={
                "mech": "SUPPORTED",
                "f1": "SUPPORTED",
                "f2": "SUPPORTED",
                "f3": "NOT_SUPPORTED",
            },
            matching=(ComparisonDimension.MECHANISM, ComparisonDimension.FEATURES),
            missing=(ComparisonDimension.FEATURES,),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT
    diagnostic = counterfactual_removal(classification)
    assert diagnostic.diagnostic_only is True
    assert diagnostic.removed_element == "component three"
    assert diagnostic.remaining_distinction is None
    assert diagnostic.becomes_substantially_equivalent is True
    unchanged = classify_precedent(
        facts_for(
            target,
            states={
                "mech": "SUPPORTED",
                "f1": "SUPPORTED",
                "f2": "SUPPORTED",
                "f3": "NOT_SUPPORTED",
            },
            matching=(ComparisonDimension.MECHANISM, ComparisonDimension.FEATURES),
            missing=(ComparisonDimension.FEATURES,),
        ),
        clock=lambda: NOW,
    )
    assert unchanged == classification
