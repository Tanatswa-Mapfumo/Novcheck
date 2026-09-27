import json
from dataclasses import replace

import httpx

from novelty_harness.application.evidence_phase5 import (
    Phase5EvidenceComponents,
    project_passage,
    project_source,
)
from novelty_harness.application.research import Phase3ResearchComponents
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.domain.adjudication import MCUFinding
from novelty_harness.domain.enums import (
    EvidenceTier,
    PrecedentState,
    SupportVerificationState,
    VerdictState,
)
from novelty_harness.domain.evidence import EvidenceComparison, EvidenceEdge
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
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
from tests.fixtures.phase1 import FixtureAdjudicationEngine, fixture_provenance, make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses
from tests.fixtures.phase3 import applicability_response, planning_response
from tests.fixtures.phase4 import registry, stop_policy, wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.unit.research.test_search_critique import critic_response


class Phase6FixtureMapper:
    """Fixture-backed Phase 6 mapping over the real Phase 5 substrates."""

    async def map(self, mcus, sources, passages):
        source = sources[0]
        passage = passages[0]
        return (
            EvidenceEdge(
                edge_id="edge_phase6_fixture",
                source_id=source.source_id,
                mcu_id="mcu_control",
                proposition="Fixture Phase 6 mapping over real Phase 5 evidence",
                passage_ids=(passage.passage_id,),
                comparison=EvidenceComparison(
                    matching_elements=("sensor", "relay"),
                    matching_relationships=("sensor controls relay",),
                ),
                relation_type=PrecedentState.COMPONENT_PRECEDENT_ONLY,
                evidence_quality=EvidenceTier.A,
                support_verification=SupportVerificationState.SUPPORTED,
                provenance=fixture_provenance("Phase6FixtureMapper"),
            ),
        )

    async def verify(self, edge, mcus, sources, passages):
        return edge.model_copy(update={"provenance": fixture_provenance("Phase6FixtureVerifier")})


class EvidenceContinuation:
    """Project the real Phase 5 result into the fixture-backed Phase 6 boundary."""

    def __init__(self) -> None:
        self.evidence = None

    async def materialize(self, evidence, graph):
        self.evidence = evidence
        provenance = fixture_provenance("Phase6FixtureContinuation")
        sources = tuple(
            project_source(source, provenance=provenance) for source in evidence.sources
        )
        passages = tuple(
            project_passage(passage, provenance=provenance) for passage in evidence.passages
        )
        return sources, passages


async def test_slice_runs_real_phase5_and_keeps_phase_6_fixture_backed(tmp_path) -> None:
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
    continuation = EvidenceContinuation()
    adjudication = f.adjudication.model_copy(
        update={
            "mcus": (
                MCUFinding(
                    mcu_id="mcu_control",
                    precedent_state=PrecedentState.COMPONENT_PRECEDENT_ONLY,
                    verdict=VerdictState.UNASSESSABLE,
                    decisive_edges=("edge_phase6_fixture",),
                    limiting_factors=("Phase 6 mapping remains fixture-backed",),
                ),
                f.adjudication.mcus[1],
            ),
            "evidence_limitations": (
                "Phase 6 mapping/adjudication remain fixture-backed over real Phase 5 evidence",
            ),
        }
    )
    components = replace(
        f.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=understanding,
        mapper=Phase6FixtureMapper(),
        verifier=Phase6FixtureMapper(),
        adjudicator=FixtureAdjudicationEngine(adjudication),
    )
    sink = InMemoryTraceSink()
    resolver = SyntheticContentResolver()
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
            content_resolver=resolver,
            trace_sink=sink,
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=f.clock,
            research=research,
            adaptive_research=adaptive,
            evidence=Phase5EvidenceComponents(),
            evidence_fixture_continuation=continuation,
        )
    assert result.record.stage.value == "REPORTED" and result.record.status.value == "COMPLETED"
    assert continuation.evidence is not None
    assert continuation.evidence.sources and continuation.evidence.passages
    assert result.adjudication.provenance.kind == "fixture"
    assert not any(event.reason_code == "PHASE5_FIXTURE_BOUNDARY" for event in sink.events)
    assert any(event.reason_code == "PHASE6_FIXTURE_BOUNDARY" for event in sink.events)
    assert any(event.reason_code == "EVIDENCE_SOURCE_NORMALIZED" for event in sink.events)
    assert any(event.reason_code == "EVIDENCE_GRAPH_PERSISTED" for event in sink.events)
    assert any(event.reason_code == "RETRIEVAL_REQUEST" for event in sink.events)

    run_dir = result.run_dir
    phase5 = run_dir / "phase5"
    assert {
        "sources.jsonl",
        "source_versions.jsonl",
        "passages.jsonl",
        "provenance_edges.jsonl",
        "lineage_clusters.jsonl",
        "source_quality.jsonl",
        "source_relevance.jsonl",
        "evidence_normalization.json",
        "evidence_graph.sqlite3",
    } <= {path.name for path in phase5.iterdir()}
    summary = json.loads((phase5 / "evidence_normalization.json").read_text())
    assert summary["source_count"] == len(continuation.evidence.sources)
    assert summary["passage_count"] == len(continuation.evidence.passages)

    repository = SqlAlchemyEvidenceGraphRepository(phase5 / "evidence_graph.sqlite3")
    persisted = {node.node_id for node in repository.nodes()}
    assert {source.source_id for source in continuation.evidence.sources} <= persisted
    assert repository.lineage_clusters() == continuation.evidence.lineage_clusters
    repository.close()

    assert {f"q{i}" for i in range(1, 10)} <= json.loads((run_dir / "report.json").read_text())[
        "answers"
    ].keys()
