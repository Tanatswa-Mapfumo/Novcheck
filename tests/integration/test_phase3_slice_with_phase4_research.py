import json
from dataclasses import replace

import httpx

from novelty_harness.application.research import Phase3ResearchComponents
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.intake.pipeline import UnderstandingComponents
from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.research.critique import SearchPlanCritic
from novelty_harness.research.planning import SearchStrategist
from novelty_harness.research.revision import SearchPlanReviser
from novelty_harness.research.screening import ScreeningExecutor
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import FixtureAdjudicationEngine, make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses
from tests.fixtures.phase3 import applicability_response, planning_response
from tests.fixtures.phase4 import registry, stop_policy, wire
from tests.integration.test_phase2_slice_with_phase3_planner import FixtureContinuation
from tests.unit.research.test_search_critique import critic_response


class Continuation(FixtureContinuation):
    async def materialize(self, research, graph):
        self.research = research
        hit = next(
            c for f in research.fused_candidates for c in f.discoveries if c.mcu_id == "mcu_control"
        )
        source = self.fixture.sources[0].model_copy(
            update={
                "provider_name": hit.provider_name,
                "provider_source_id": hit.source.provider_source_id,
                "canonical_url": hit.source.canonical_url,
                "canonical_title": hit.source.title,
            }
        )
        return (source,), self.fixture.passages


async def test_vertical_slice_uses_real_phase2_through4_and_explicit_phase5_fixtures(tmp_path):
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
    continuation = Continuation(f)
    components = replace(
        f.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=understanding,
        mapper=continuation,
        verifier=continuation,
        adjudicator=FixtureAdjudicationEngine(
            f.adjudication.model_copy(
                update={
                    "evidence_limitations": (
                        "Phase 5+ evidence/adjudication remain fixture-backed",
                    )
                }
            )
        ),
    )
    sink = InMemoryTraceSink()
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        providers, _ = registry(client, clock=f.clock)
        policy = CoveragePolicy.standard()
        research = Phase3ResearchComponents(
            EvidenceFamilyApplicabilityAssessor(runner),
            SearchStrategist(runner),
            SearchPlanCritic(runner),
            SearchPlanReviser(runner),
            ScreeningExecutor(providers, policy),
        )
        adaptive = Phase4ResearchComponents(
            providers, policy, BudgetLimits(max_deep_search_rounds=80), stop_policy()
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
            adaptive_research=adaptive,
            adaptive_fixture_continuation=continuation,
        )
    assert result.record.stage.value == "REPORTED" and result.record.status.value == "COMPLETED"
    assert continuation.research.fused_candidates
    assert not f.search_provider.calls and not f.content_resolver.calls
    assert (result.run_dir / "phase4/research_result.json").exists()
    assert result.adjudication.provenance.kind == "fixture"
    assert any(e.reason_code == "PHASE5_FIXTURE_BOUNDARY" for e in sink.events)
    assert not any(e.reason_code == "PHASE4_FIXTURE_BOUNDARY" for e in sink.events)
    assert any(e.reason_code == "RETRIEVAL_REQUEST" for e in sink.events)
    persisted = [json.loads(s) for s in (result.run_dir / "trace.jsonl").read_text().splitlines()]
    assert any(e["reason_code"] == "RETRIEVAL_REQUEST" for e in persisted)
    assert {f"q{i}" for i in range(1, 10)} <= json.loads(
        (result.run_dir / "report.json").read_text()
    )["answers"].keys()
