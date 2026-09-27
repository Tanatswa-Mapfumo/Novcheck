from copy import deepcopy
from datetime import date

import pytest

from novelty_harness.research.models import EvidenceFamilyAssessment, ResearchPlan, SearchIntent


def plan_data():
    return {
        "assessment_id": "asm_research",
        "as_of": "2026-09-26",
        "mcu_ids": ["mcu_control"],
        "family_assessments": [
            {
                "mcu_id": "mcu_control",
                "evidence_family": "SCHOLARLY",
                "applicability": "APPLICABLE",
                "rationale": "Control mechanisms appear in literature",
            }
        ],
        "intents": [
            {
                "query_id": "qry_control",
                "mcu_id": "mcu_control",
                "evidence_family": "SCHOLARLY",
                "query_family": "RELATIONSHIP",
                "text": "sensor controls relay",
                "rationale": "Search the control relationship",
                "concepts": ["sensor", "relay"],
                "relationship_terms": ["controls"],
            }
        ],
    }


def test_research_plan_round_trip_retains_intent_and_cutoff():
    plan = ResearchPlan.model_validate(plan_data())
    assert ResearchPlan.model_validate_json(plan.model_dump_json()) == plan
    assert plan.as_of == date(2026, 9, 26)
    assert not plan.reviewed
    assert plan.intents[0].relationship_terms == ("controls",)


@pytest.mark.parametrize("field", ["text", "rationale", "concepts"])
def test_blank_intent_fields_reject(field):
    data = plan_data()["intents"][0]
    data[field] = [" "] if field == "concepts" else " "
    with pytest.raises(ValueError):
        SearchIntent.model_validate(data)


@pytest.mark.parametrize("mutation", ["unknown", "family", "id", "text", "review", "extra"])
def test_invalid_plan_references_duplicates_or_unbound_review_reject(mutation):
    data = plan_data()
    if mutation == "unknown":
        data["intents"][0]["mcu_id"] = "mcu_absent"
    elif mutation == "family":
        data["intents"][0]["evidence_family"] = "PATENT"
    elif mutation in ("id", "text"):
        duplicate = deepcopy(data["intents"][0])
        if mutation == "text":
            duplicate.update(query_id="qry_second", text=" SENSOR   controls relay ")
        data["intents"].append(duplicate)
    elif mutation == "review":
        data.update(reviewed=True, review_id="review_fake")
    else:
        data["novelty"] = 1
    with pytest.raises(ValueError):
        ResearchPlan.model_validate(data)


@pytest.mark.parametrize(
    "state,reason",
    [
        ("NOT_APPLICABLE", None),
        ("APPLICABLE", "No provider"),
        ("POSSIBLY_APPLICABLE", "No provider"),
        ("UNRESOLVED", "No provider"),
    ],
)
def test_exclusion_requires_semantic_rationale_and_cannot_replace_plausible_branch(state, reason):
    data = plan_data()["family_assessments"][0]
    data.update(applicability=state, exclusion_reason=reason)
    with pytest.raises(ValueError):
        EvidenceFamilyAssessment.model_validate(data)
