import json
from dataclasses import replace

import httpx

from novelty_harness.application.research import Phase3ResearchComponents
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.intake.pipeline import UnderstandingComponents
from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.research.critique import SearchPlanCritic
from novelty_harness.research.planning import SearchStrategist
from novelty_harness.research.revision import SearchPlanReviser
from novelty_harness.research.screening import ScreeningExecutor
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import FixtureAdjudicationEngine, make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses
from tests.fixtures.phase3 import applicability_response, planning_response
from tests.integration.test_phase3_screening_pipeline import handler, registry_for
from tests.unit.research.test_search_critique import critic_response


class FixtureContinuation:
    def __init__(self, fixture):
        self.fixture = fixture
        self.screening = None

    async def materialize(self, screening, graph):
        self.screening = screening
        hit = next(h for h in screening.hits if h.mcu_id == "mcu_control")
        source = self.fixture.sources[0].model_copy(
            update={
                "provider_name": hit.provider_name,
                "provider_source_id": hit.source.provider_source_id,
                "canonical_url": hit.source.canonical_url,
                "canonical_title": hit.source.title,
                "discovered_by_queries": (hit.query_id,),
                "source_id": "src_" + canonical_hash({"canonical_url": hit.source.canonical_url}),
            }
        )
        original = self.fixture.passages[0]
        passage = original.model_copy(
            update={
                "source_id": source.source_id,
                "passage_id": "pass_"
                + canonical_hash(
                    {
                        "source_id": source.source_id,
                        "locator": original.locator,
                        "text": original.text,
                    }
                ),
            }
        )
        return (source,), (passage,)

    async def map(self, mcus, sources, passages):
        return (
            self.fixture.edges[0].model_copy(
                update={"source_id": sources[0].source_id, "passage_ids": (passages[0].passage_id,)}
            ),
        )

    async def verify(self, edge, mcus, sources, passages):
        return edge.model_copy(deep=True)


async def test_full_slice_uses_real_understanding_planning_screening_and_explicit_later_fixtures(
    tmp_path,
):
    f = make_fixture()
    understanding = UnderstandingComponents(
        SemanticRunner(RecordedLLM(understanding_responses())), clock=f.clock
    )
    runner = SemanticRunner(
        RecordedLLM(
            {
                "assess_families": applicability_response(),
                "plan_research": planning_response(),
                "criticize_search": critic_response(),
            }
        )
    )
    components = replace(
        f.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=understanding,
        adjudicator=FixtureAdjudicationEngine(
            f.adjudication.model_copy(
                update={
                    "unresolved_questions": ("Phase 4+ reasoning remains deferred",),
                    "evidence_limitations": (
                        "Real screening logic with synthetic HTTP responses; "
                        "fixture evidence/adjudication",
                    ),
                }
            )
        ),
    )
    sink = InMemoryTraceSink()
    continuation = FixtureContinuation(f)
    components = replace(components, mapper=continuation, verifier=continuation)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler())) as client:
        research = Phase3ResearchComponents(
            EvidenceFamilyApplicabilityAssessor(runner),
            SearchStrategist(runner),
            SearchPlanCritic(runner),
            SearchPlanReviser(runner),
            ScreeningExecutor(registry_for(client), CoveragePolicy.standard(), clock=f.clock),
        )
        result = await run_vertical_slice(
            request=f.request,
            components=components,
            search_provider=f.search_provider,
            content_resolver=f.content_resolver,
            trace_sink=sink,
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=f.clock,
            research=research,
            fixture_continuation=continuation,
        )
    assert result.record.stage.value == "REPORTED" and result.record.status.value == "COMPLETED"
    assert continuation.screening.hits
    assert not f.search_provider.calls and not f.content_resolver.calls
    assert (result.run_dir / "phase3/coverage_matrix.json").exists()
    assert (result.run_dir / "mcu_version.json").exists()
    assert result.adjudication.provenance.kind == "fixture"
    assert any(
        e.reason_code == "PHASE4_FIXTURE_BOUNDARY" and e.data["execution"] == "fixture"
        for e in sink.events
    )
    assert any(e.reason_code == "PHASE3_SCREENING" for e in sink.events)
    assert len([e for e in sink.events if e.reason_code == "SEMANTIC_CALL"]) == 8
    answers = json.loads((result.run_dir / "report.json").read_text())["answers"]
    assert {f"q{i}" for i in range(1, 10)} <= answers.keys()
