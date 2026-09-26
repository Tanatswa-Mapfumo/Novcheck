import json
from dataclasses import replace

import pytest

from novelty_harness.application.models import AssessmentSummary
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.domain.adjudication import FrozenAdjudication
from novelty_harness.domain.assessment import AssessmentRecord, AssessmentRequest, LifecycleEvent
from novelty_harness.domain.enums import AssessmentStage, AssessmentStatus, SupportVerificationState
from novelty_harness.domain.evidence import EvidenceEdge, SourcePassage, SourceRecord
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, SufficiencyAssessment
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.domain.reporting import CANONICAL_QUESTIONS, CompiledReport
from novelty_harness.domain.research import SearchPlan, SearchPlanReview
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink, JsonlTraceSink
from tests.fixtures.phase1 import FixtureAdjudicationEngine, FixtureIdeaNormalizer, make_fixture


async def run_fixture(root, *, components=None, search_provider=None, trace_sink=None):
    fixture = make_fixture()
    sink = trace_sink if trace_sink is not None else InMemoryTraceSink()
    result = await run_vertical_slice(
        request=fixture.request,
        components=components or fixture.components,
        search_provider=search_provider or fixture.search_provider,
        content_resolver=fixture.content_resolver,
        trace_sink=sink,
        artifact_writer=RunArtifactWriter(root),
        clock=fixture.clock,
    )
    return result, sink


async def test_synthetic_idea_traverses_full_lifecycle_and_artifacts(tmp_path):
    fixture = make_fixture()
    result, sink = await run_fixture(tmp_path)
    assert result.record.stage == AssessmentStage.REPORTED
    assert result.record.status == AssessmentStatus.COMPLETED
    assert [
        event.stage for event in sink.events if event.reason_code == "STAGE_TRANSITION"
    ] == list(AssessmentStage)[1:]
    assert sink.events[0].stage == AssessmentStage.RECEIVED
    assert sink.events[-1].data["lifecycle"]["to_value"] == "COMPLETED"
    for event in sink.events:
        if "lifecycle" in event.data:
            LifecycleEvent.model_validate(event.data["lifecycle"])
    deferred = {
        AssessmentStage.ADAPTIVE_RESEARCH,
        AssessmentStage.ADVERSARIAL_CHALLENGE,
        AssessmentStage.DEFENCE_REVIEW,
        AssessmentStage.ROBUSTNESS_REVIEW,
    }
    for stage in deferred:
        event = next(event for event in sink.events if event.stage == stage)
        assert event.data["execution"] == "deferred"
        assert event.data["semantics_implemented"] is False
    fixture_stages = {
        AssessmentStage.NORMALIZED,
        AssessmentStage.SUFFICIENCY_ASSESSED,
        AssessmentStage.MCU_DECOMPOSED,
        AssessmentStage.MCU_RECONCILED,
        AssessmentStage.SEARCH_PLANNED,
        AssessmentStage.SEARCH_PLAN_REVIEWED,
        AssessmentStage.EVIDENCE_MAPPED,
        AssessmentStage.EVIDENCE_VERIFIED,
        AssessmentStage.PRELIMINARY_ADJUDICATION,
    }
    for stage in fixture_stages:
        event = next(event for event in sink.events if event.stage == stage)
        assert event.data["execution"] == "fixture"
        assert event.data["semantics_implemented"] is False

    directory = result.run_dir
    for name, model in {
        "request.json": AssessmentRequest,
        "canonical_idea.json": CanonicalIdeaRepresentation,
        "sufficiency.json": SufficiencyAssessment,
        "mcu_graph.json": MCUGraph,
        "search_plan.json": SearchPlan,
        "search_plan_review.json": SearchPlanReview,
        "adjudication.json": FrozenAdjudication,
        "assessment.json": AssessmentSummary,
        "assessment_record.json": AssessmentRecord,
        "report.json": CompiledReport,
    }.items():
        model.model_validate_json((directory / name).read_text())
    for name, model in {
        "sources.jsonl": SourceRecord,
        "passages.jsonl": SourcePassage,
        "evidence_edges.jsonl": EvidenceEdge,
        "trace.jsonl": TraceEvent,
    }.items():
        rows = [
            model.model_validate_json(line) for line in (directory / name).read_text().splitlines()
        ]
        assert rows
    idea = CanonicalIdeaRepresentation.model_validate_json(
        (directory / "canonical_idea.json").read_text()
    )
    request = AssessmentRequest.model_validate_json((directory / "request.json").read_text())
    assert idea.original_input == request.input_text == fixture.request.input_text
    frozen = FrozenAdjudication.model_validate_json((directory / "adjudication.json").read_text())
    report = CompiledReport.model_validate_json((directory / "report.json").read_text())
    assert report.adjudication_hash == canonical_hash(frozen)
    assert report.overall_verdict == frozen.overall_state
    assert (directory / "report.md").read_text() == report.markdown
    for index, question in enumerate(CANONICAL_QUESTIONS, 1):
        assert f"## Q{index}. {question}" in report.markdown
    edges = [
        EvidenceEdge.model_validate_json(line)
        for line in (directory / "evidence_edges.jsonl").read_text().splitlines()
    ]
    assert edges[0].support_verification == SupportVerificationState.SUPPORTED
    assert edges[0].source_id == fixture.sources[0].source_id
    assert edges[0].passage_ids == (fixture.passages[0].passage_id,)
    assert any(event.reason_code == "PROVIDER_CALL" for event in sink.events)
    assert len([event for event in sink.events if event.reason_code == "PROVIDER_CALL"]) == 2


def stable_artifact(value):
    if isinstance(value, dict):
        return {
            key: stable_artifact(item)
            for key, item in value.items()
            if key
            not in {
                "assessment_id",
                "id",
                "event_id",
                "adjudication_hash",
                "response_hash",
            }
        }
    if isinstance(value, list):
        return [stable_artifact(item) for item in value]
    return value


async def test_repeated_runs_preserve_semantic_artifacts(tmp_path):
    first, _ = await run_fixture(tmp_path / "first")
    second, _ = await run_fixture(tmp_path / "second")
    assert first.record.assessment_id != second.record.assessment_id
    for path in first.run_dir.iterdir():
        other = second.run_dir / path.name
        if path.suffix == ".json":
            assert stable_artifact(json.loads(path.read_text())) == stable_artifact(
                json.loads(other.read_text())
            )
        elif path.suffix == ".jsonl":
            assert [
                stable_artifact(json.loads(line)) for line in path.read_text().splitlines()
            ] == [stable_artifact(json.loads(line)) for line in other.read_text().splitlines()]
        else:
            assert path.read_bytes() == other.read_bytes()


async def test_injected_jsonl_sink_matches_run_local_trace(tmp_path):
    external = tmp_path / "external.jsonl"
    result, _ = await run_fixture(tmp_path / "runs", trace_sink=JsonlTraceSink(external))
    assert external.read_bytes() == (result.run_dir / "trace.jsonl").read_bytes()


async def test_mismatched_original_input_fails_explicitly(tmp_path):
    fixture = make_fixture()
    bad_idea = fixture.idea.model_copy(update={"original_input": "Silently changed input"})
    components = replace(
        fixture.components, normalizer=FixtureIdeaNormalizer(fixture.request, bad_idea)
    )
    sink = InMemoryTraceSink()
    with pytest.raises(ValueError, match="original input"):
        await run_fixture(tmp_path, components=components, trace_sink=sink)
    directory = next(tmp_path.iterdir())
    record = AssessmentRecord.model_validate_json(
        (directory / "assessment_record.json").read_text()
    )
    assert record.status == AssessmentStatus.FAILED
    assert sink.events[-1].reason_code == "EXECUTION_FAILURE"
    assert not (directory / "report.md").exists()


async def test_provider_failure_does_not_become_a_success_or_silent_fallback(tmp_path):
    class FailingSearch:
        name = "fixture-failed-search"

        async def search(self, query, cursor=None):
            raise RuntimeError("fixture provider unavailable")

    sink = InMemoryTraceSink()
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await run_fixture(tmp_path, search_provider=FailingSearch(), trace_sink=sink)
    record = AssessmentRecord.model_validate_json(
        (next(tmp_path.iterdir()) / "assessment_record.json").read_text()
    )
    assert record.status == AssessmentStatus.FAILED
    assert sink.events[-1].data["error_type"] == "RuntimeError"
    assert not any(event.stage == AssessmentStage.FINDINGS_FROZEN for event in sink.events)


async def test_decisive_edge_must_belong_to_the_finding_mcu(tmp_path):
    fixture = make_fixture()
    wrong_finding = fixture.adjudication.mcus[1].model_copy(
        update={"decisive_edges": (fixture.edges[0].edge_id,)}
    )
    wrong = fixture.adjudication.model_copy(update={"mcus": (wrong_finding,)})
    components = replace(fixture.components, adjudicator=FixtureAdjudicationEngine(wrong))
    with pytest.raises(ValueError, match="finding MCU"):
        await run_fixture(tmp_path, components=components)


async def test_assessment_summary_copies_frozen_findings_without_fabricated_coverage(tmp_path):
    fixture = make_fixture()
    result, _ = await run_fixture(tmp_path)
    raw = json.loads((result.run_dir / "assessment.json").read_text())
    assert {
        "id",
        "as_of",
        "input_sufficiency",
        "overall_verdict",
        "mcu_findings",
        "closest_precedents",
        "value_findings",
        "evidence_limitations",
        "coverage_matrix",
        "trace_ref",
        "schema_version",
    } <= raw.keys()
    summary = AssessmentSummary.model_validate(raw)
    assert summary == result.summary
    assert summary.id == result.record.assessment_id
    assert summary.as_of == fixture.request.as_of
    assert summary.input_sufficiency == fixture.sufficiency.state
    assert summary.overall_verdict == result.adjudication.overall_state
    assert summary.mcu_findings == result.adjudication.mcus
    assert summary.value_findings == result.adjudication.value_findings
    assert summary.evidence_limitations == result.adjudication.evidence_limitations
    assert summary.closest_precedents == (fixture.sources[0].source_id,)
    assert summary.coverage_matrix == result.adjudication.coverage_matrix == ()
    assert summary.provenance.kind == "fixture"
    assert (result.run_dir / summary.trace_ref).is_file()
    assert "novelty_score" not in raw and "confidence" not in raw


async def test_summary_round_trips_and_rejects_unknown_fields(tmp_path):
    from pydantic import ValidationError

    result, _ = await run_fixture(tmp_path)
    assert AssessmentSummary.model_validate_json(result.summary.model_dump_json()) == result.summary
    with pytest.raises(ValidationError):
        AssessmentSummary.model_validate({**result.summary.model_dump(), "confidence": 0.99})
