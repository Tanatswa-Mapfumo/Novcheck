import json
from dataclasses import replace

import pytest

from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.intake.pipeline import UnderstandingComponents
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses


@pytest.mark.parametrize("unstable", [False, True])
async def test_phase1_slice_runs_real_understanding_ports_with_later_fixture_stages(
    tmp_path, unstable
):
    f = make_fixture()
    responses = understanding_responses()
    if unstable:
        responses["criticize_mcus"]["structural_tests"][0].update(passed=False, severity="MATERIAL")
    understanding = UnderstandingComponents(SemanticRunner(RecordedLLM(responses)), clock=f.clock)
    components = replace(
        f.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=understanding,
    )
    sink = InMemoryTraceSink()
    result = await run_vertical_slice(
        request=f.request,
        components=components,
        search_provider=f.search_provider,
        content_resolver=f.content_resolver,
        trace_sink=sink,
        artifact_writer=RunArtifactWriter(tmp_path),
        clock=f.clock,
    )
    assert result.record.stage.value == "REPORTED"
    assert result.record.status.value == "COMPLETED"
    assert result.summary.input_sufficiency.value == (
        "EXPLORATORY" if unstable else "HIGH_RESOLUTION"
    )
    assert (result.run_dir / "mcu_candidates_A.json").exists()
    assert (result.run_dir / "mcu_candidates_B.json").exists()
    assert (result.run_dir / "mcu_version.json").exists()
    assert len([e for e in sink.events if e.reason_code == "SEMANTIC_CALL"]) == 5
    for e in sink.events:
        if e.reason_code == "STAGE_TRANSITION" and e.stage.value in (
            "NORMALIZED",
            "SUFFICIENCY_ASSESSED",
            "MCU_DECOMPOSED",
            "MCU_RECONCILED",
        ):
            assert e.data["execution"] == "implemented"
    assert result.adjudication.provenance.kind == "fixture"
    assert result.adjudication.overall_state.value == "UNASSESSABLE"
    final = json.loads((result.run_dir / "canonical_idea.json").read_text())
    assert final["mcu_ids"] == ["mcu_control", "mcu_status"]


async def test_phase2_invalid_output_records_failed_call_and_failed_lifecycle(tmp_path):
    f = make_fixture()
    responses = understanding_responses()
    responses["decompose_b"]["extra"] = "invalid"
    understanding = UnderstandingComponents(SemanticRunner(RecordedLLM(responses)), clock=f.clock)
    sink = InMemoryTraceSink()
    with pytest.raises(ValueError):
        await run_vertical_slice(
            request=f.request,
            components=replace(
                f.components,
                normalizer=understanding,
                sufficiency_analyzer=understanding,
                decomposer=understanding,
                reconciler=understanding,
            ),
            search_provider=f.search_provider,
            content_resolver=f.content_resolver,
            trace_sink=sink,
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=f.clock,
        )
    invalid = [
        e
        for e in sink.events
        if e.reason_code == "SEMANTIC_CALL" and e.data["audit"]["validation_state"] == "INVALID"
    ]
    assert len(invalid) == 1
    assert invalid[0].status.value == "FAILURE"
    record = json.loads(next(tmp_path.glob("*/assessment_record.json")).read_text())
    assert record["status"] == "FAILED"
    assert not list(tmp_path.glob("*/adjudication.json"))
