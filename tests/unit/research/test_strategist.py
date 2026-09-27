from datetime import date

import pytest

from novelty_harness.research.models import EvidenceFamilyAssessment
from novelty_harness.research.planning import SearchStrategist
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM
from tests.fixtures.phase3 import applicability_response, planning_response


async def build(data=None, **idea_updates):
    fixture = make_fixture()
    provider = RecordedLLM({"plan_research": data or planning_response()})
    result = await SearchStrategist(SemanticRunner(provider)).build_plan(
        assessment_id="asm_research",
        as_of=date(2026, 9, 26),
        idea=fixture.idea.model_copy(update=idea_updates),
        mcus=fixture.graph.mcus,
        combinations=fixture.graph.combinations,
        applicability=[
            EvidenceFamilyAssessment.model_validate(
                {k: v for k, v in a.items() if k not in {"exclusion_basis", "exclusion_support"}}
            )
            for a in applicability_response()["assessments"]
        ],
    )
    return result, provider


async def test_multi_query_plan_preserves_cutoff_and_explicit_omissions():
    result, _ = await build()
    assert result.as_of == date(2026, 9, 26)
    assert not result.reviewed
    assert len(result.intents) == 162
    assert len(result.omissions) == 36
    assert any(q.relationship_terms for q in result.intents)
    assert all(not q.filters for q in result.intents)


@pytest.mark.parametrize("change", ["rename", "buzzword", "context"])
async def test_core_query_families_survive_surface_changes(change):
    baseline, _ = await build()
    changed, _ = await build(title=change, original_input=f"{change}: unchanged mechanism")
    assert [(q.query_family, q.text) for q in baseline.intents] == [
        (q.query_family, q.text) for q in changed.intents
    ]


@pytest.mark.parametrize("mutation", ["omit", "relation", "historical", "filter", "version"])
async def test_invalid_plan_output_rejected(mutation):
    data = planning_response()
    if mutation == "omit":
        data["omissions"].pop()
    elif mutation == "relation":
        q = next(q for q in data["intents"] if q["query_family"] == "RELATIONSHIP")
        q["text"] = "temperature sensor relay"
    elif mutation == "historical":
        q = next(q for q in data["intents"] if q["query_family"] == "HISTORICAL_TERMINOLOGY")
        q["historical_terms"] = []
    elif mutation == "filter":
        data["intents"][0]["filters"] = {"language": "en"}
    else:
        data["prompt_version"] = "made-up"
    with pytest.raises(ValueError):
        await build(data)
