import json

import pytest

from novelty_harness.intake.pipeline import understand_idea
from novelty_harness.mcu.overrides import MCUVersion
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase1 import FIXED_TIME, make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses


@pytest.mark.parametrize("unstable", [False, True])
async def test_understanding_pipeline_persists_independent_versions_and_propagates_ceiling(
    tmp_path, unstable
):
    responses = understanding_responses()
    if unstable:
        responses["criticize_mcus"]["structural_tests"][0].update(passed=False, severity="MATERIAL")
    llm = RecordedLLM(responses)
    runner = SemanticRunner(llm)
    result = await understand_idea(
        make_fixture().request,
        runner=runner,
        writer=RunArtifactWriter(tmp_path),
        assessment_id="asm_understanding",
        clock=lambda: FIXED_TIME,
    )
    assert result.cir.original_input == make_fixture().request.input_text
    assert result.cir.mcu_ids == ("mcu_control", "mcu_status")
    assert result.sufficiency.state.value == ("EXPLORATORY" if unstable else "HIGH_RESOLUTION")
    assert result.active_mcu_version.source_reconciliation_hash
    assert [r[0] for r in llm.requests] == [
        "normalize_idea",
        "assess_sufficiency",
        "decompose_a",
        "decompose_b",
        "criticize_mcus",
    ]
    files = (
        "canonical_idea.json",
        "sufficiency.json",
        "mcu_candidates_A.json",
        "mcu_candidates_B.json",
        "mcu_alignment.json",
        "mcu_reconciliation.json",
        "mcu_graph.json",
        "mcu_version.json",
    )
    for name in files:
        assert (
            json.loads((tmp_path / "asm_understanding" / name).read_text())["schema_version"]
            == "0.1"
        )
    version = MCUVersion.model_validate_json(
        (tmp_path / "asm_understanding/mcu_version.json").read_text()
    )
    assert version == result.active_mcu_version


async def test_invalid_semantic_output_leaves_failure_audit_not_a_completed_graph(tmp_path):
    responses = understanding_responses()
    responses["normalize_idea"]["invented"] = True
    with pytest.raises(ValueError):
        await understand_idea(
            make_fixture().request,
            runner=SemanticRunner(RecordedLLM(responses)),
            writer=RunArtifactWriter(tmp_path),
            assessment_id="asm_failed",
            clock=lambda: FIXED_TIME,
        )
    audit = [
        json.loads(line)
        for line in (tmp_path / "asm_failed/semantic_calls.jsonl").read_text().splitlines()
    ]
    assert audit[-1]["validation_state"] == "INVALID"
    assert not (tmp_path / "asm_failed/mcu_version.json").exists()
