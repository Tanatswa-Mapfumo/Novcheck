import json
from dataclasses import replace

import httpx

from novelty_harness.application.evidence_phase5 import Phase5EvidenceComponents
from novelty_harness.application.evidence_phase6 import Phase6EvidenceComponents
from novelty_harness.application.research import Phase3ResearchComponents
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.domain.adjudication import FrozenAdjudication, MCUFinding
from novelty_harness.domain.enums import (
    PrecedentState,
    SupportVerificationState,
    VerdictState,
)
from novelty_harness.domain.mcu import MCUCombination, MCURelationship
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
from tests.fixtures.phase1 import FIXED_TIME, fixture_provenance, make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses
from tests.fixtures.phase3 import applicability_response, planning_response
from tests.fixtures.phase4 import registry, stop_policy, wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.fixtures.phase6 import scripted_phase6_llm
from tests.unit.research.test_search_critique import critic_response


class CombinationReconciler:
    """Wrap the real understanding reconciler and add a combination contribution."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def reconcile(self, idea, candidates):
        graph = await self.inner.reconcile(idea, candidates)
        if graph.combinations or len(graph.mcus) < 2:
            return graph
        combination = MCUCombination(
            combination_id="C1",
            label="Combined control and indication",
            statement="Control the relay and show its status",
            member_ids=tuple(mcu.mcu_id for mcu in graph.mcus[:2]),
            relationships=(
                MCURelationship(subject="control", relation="triggers", object="indication"),
            ),
            provenance=fixture_provenance("CombinationReconciler"),
        )
        return graph.model_copy(update={"combinations": (combination,)})


class Phase7FixtureAdjudicator:
    """Fixture-backed Phase 7 adjudication over real Phase 6 verified edges."""

    async def adjudicate(
        self, *, assessment_id, as_of, idea, sufficiency, mcus, edges
    ) -> FrozenAdjudication:
        decisive_by_mcu: dict[str, str] = {}
        relation_by_mcu: dict[str, PrecedentState] = {}
        for edge in edges:
            if edge.support_verification == SupportVerificationState.SUPPORTED:
                decisive_by_mcu.setdefault(edge.mcu_id, edge.edge_id)
                relation_by_mcu.setdefault(edge.mcu_id, edge.relation_type)
        findings = tuple(
            MCUFinding(
                mcu_id=mcu.mcu_id,
                precedent_state=relation_by_mcu.get(mcu.mcu_id, PrecedentState.UNRESOLVED),
                verdict=VerdictState.UNASSESSABLE,
                decisive_edges=(
                    (decisive_by_mcu[mcu.mcu_id],) if mcu.mcu_id in decisive_by_mcu else ()
                ),
                limiting_factors=("Phase 7 adjudication remains explicitly fixture-backed",),
            )
            for mcu in mcus
        )
        return FrozenAdjudication(
            assessment_id=assessment_id,
            as_of=as_of,
            frozen_at=FIXED_TIME,
            overall_state=VerdictState.UNASSESSABLE,
            mcus=findings,
            established_findings=("Phase 6 verified local source/MCU comparisons are present",),
            value_findings=(),
            validation_requirements=("Real adjudication gates are deferred to Phase 7",),
            permitted_language=(
                "This run proves architecture through Phase 6; novelty is unassessed.",
            ),
            forbidden_claims=("Nobody has ever done this",),
            unresolved_questions=("Phase 7 adjudication, challenge and defence are deferred",),
            evidence_limitations=(
                "Fixture adjudication over real Phase 6 verified evidence; no novelty verdict",
            ),
            coverage_matrix=(),
            provenance=fixture_provenance("Phase7FixtureAdjudicator"),
        )


async def test_slice_runs_real_phase_6_and_keeps_phase_7_fixture_backed(tmp_path) -> None:
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
        reconciler=CombinationReconciler(understanding),
        adjudicator=Phase7FixtureAdjudicator(),
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
            content_resolver=SyntheticContentResolver(),
            trace_sink=sink,
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=f.clock,
            research=research,
            adaptive_research=adaptive,
            evidence=Phase5EvidenceComponents(),
            phase6=Phase6EvidenceComponents(SemanticRunner(scripted_phase6_llm())),
        )
    assert result.record.stage.value == "REPORTED" and result.record.status.value == "COMPLETED"
    assert result.adjudication.provenance.kind == "fixture"
    reasons = [event.reason_code for event in sink.events]
    assert "PHASE7_FIXTURE_BOUNDARY" in reasons
    assert "PHASE6_FIXTURE_BOUNDARY" not in reasons
    assert "EVIDENCE_MAPPING" in reasons and "SUPPORT_VERIFICATION" in reasons
    assert "PHASE6_GRAPH_PERSISTED" in reasons

    run_dir = result.run_dir
    phase6 = run_dir / "phase6"
    assert {
        "profiles.jsonl",
        "propositions.jsonl",
        "mappings.jsonl",
        "support_claims.jsonl",
        "support_verifications.jsonl",
        "context_expansions.jsonl",
        "verified_edges.jsonl",
        "precedent_classifications.jsonl",
        "multi_source_assessments.jsonl",
        "patent_screenings.jsonl",
        "phase6_result.json",
    } <= {path.name for path in phase6.iterdir()}
    summary = json.loads((phase6 / "phase6_result.json").read_text())
    assert summary["mapping_count"] > 0
    assert summary["verified_edge_count"] > 0
    persisted_edges = [
        json.loads(line)
        for line in (run_dir / "evidence_edges.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert persisted_edges
    # F11: a real Phase 6 combination target must pass the bridge.
    assert any(edge["mcu_id"].startswith("mcu_comb_") for edge in persisted_edges)

    repository = SqlAlchemyEvidenceGraphRepository(run_dir / "phase5" / "evidence_graph.sqlite3")
    kinds = {node.kind.value for node in repository.nodes()}
    assert {"SOURCE", "MCU", "EVIDENCE_PROPOSITION"} <= kinds
    assert any(edge.verification is not None for edge in repository.edges())
    repository.close()

    assert {f"q{i}" for i in range(1, 10)} <= json.loads((run_dir / "report.json").read_text())[
        "answers"
    ].keys()
