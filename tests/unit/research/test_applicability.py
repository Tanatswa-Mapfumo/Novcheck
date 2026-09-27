import pytest

from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM
from tests.fixtures.phase3 import applicability_response


async def assess(data, **idea_updates):
    fixture = make_fixture()
    provider = RecordedLLM({"assess_families": data})
    result = await EvidenceFamilyApplicabilityAssessor(SemanticRunner(provider)).assess(
        idea=fixture.idea.model_copy(update=idea_updates), mcus=fixture.graph.mcus
    )
    return result, provider


async def test_all_nine_families_per_mcu_independent_of_provider_configuration():
    result, provider = await assess(applicability_response())
    assert len(result) == 18
    assert all(a.applicability.value == "POSSIBLY_APPLICABLE" for a in result)
    assert len([a for a in result if a.evidence_family.value == "PATENT"]) == 2
    assert all("provider_registry" not in block.label for block in provider.requests[0][2])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "version", "extra"])
async def test_incomplete_or_invalid_semantic_family_output_rejects(mutation):
    data = applicability_response()
    if mutation == "missing":
        data["assessments"].pop()
    elif mutation == "duplicate":
        data["assessments"].append(data["assessments"][0])
    elif mutation == "unknown":
        data["assessments"][0]["mcu_id"] = "mcu_absent"
    elif mutation == "version":
        data["prompt_version"] = "untrusted-version"
    else:
        data["novelty"] = 1
    with pytest.raises(ValueError):
        await assess(data)


@pytest.mark.parametrize("basis", ["PROVIDER_AVAILABILITY", "USER_ASSERTION"])
async def test_provider_absence_or_user_no_patents_claim_cannot_exclude_family(basis):
    data = applicability_response()
    for row in data["assessments"]:
        if row["evidence_family"] == "PATENT":
            row.update(
                applicability="NOT_APPLICABLE",
                exclusion_reason="There are no patents",
                exclusion_basis=basis,
            )
    result, _ = await assess(data, original_input="There are no patents")
    patent = [a for a in result if a.evidence_family.value == "PATENT"]
    assert all(a.applicability.value == "UNRESOLVED" for a in patent)
    assert all(a.exclusion_reason is None and a.limitations for a in patent)


@pytest.mark.parametrize("framing", ["An academic theory", "A commercial product", "An idea"])
async def test_framing_does_not_remove_possible_evidence_ecosystems(framing):
    result, _ = await assess(applicability_response(), original_input=framing)
    for family in ("SCHOLARLY", "SOFTWARE", "PRODUCT", "PATENT"):
        assert all(
            a.applicability.value != "NOT_APPLICABLE"
            for a in result
            if a.evidence_family.value == family
        )


async def test_ungrounded_exclusion_is_retained_as_unresolved():
    data = applicability_response()
    data["assessments"][0].update(
        applicability="NOT_APPLICABLE",
        exclusion_reason="Not possible here",
        exclusion_basis="SEMANTIC_INCOMPATIBILITY",
        exclusion_support=["invented quote"],
    )
    result, _ = await assess(data)
    assert result[0].applicability.value == "UNRESOLVED"
