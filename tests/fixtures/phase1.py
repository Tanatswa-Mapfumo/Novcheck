"""Synthetic snapshots, not an implementation of novelty intelligence."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from novelty_harness.application.models import VerticalSliceComponents
from novelty_harness.domain.adjudication import FrozenAdjudication, MCUFinding
from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.domain.enums import (
    EvidenceFamily,
    EvidenceTier,
    PrecedentState,
    SufficiencyState,
    SupportVerificationState,
    TraceStatus,
    VerdictState,
)
from novelty_harness.domain.evidence import (
    EvidenceComparison,
    EvidenceEdge,
    SourcePassage,
    SourceRecord,
)
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    ClaimedAdvantage,
    IdeaContext,
    ProblemDescription,
    SufficiencyAssessment,
)
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCU, MCUCombination, MCUFeature, MCUGraph, MCURelationship
from novelty_harness.domain.research import PlannedQuery, SearchPlan, SearchPlanReview
from novelty_harness.ports.models import (
    Passage,
    ProviderCallMetadata,
    ProviderCapabilities,
    ProviderHealth,
    SearchPage,
    SearchQuery,
    SearchResult,
    SourceContent,
    SourceRef,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash
from tests.fixtures.providers import MockContentResolver, MockSearchProvider

FIXED_TIME = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def fixture_provenance(component: str) -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="fixture",
        component=component,
        detail="Deterministic synthetic snapshot; semantic implementation deferred.",
    )


class FixtureIdeaNormalizer:
    def __init__(self, request: AssessmentRequest, idea: CanonicalIdeaRepresentation) -> None:
        self.request = request.model_copy(deep=True)
        self.idea = idea.model_copy(deep=True)

    async def normalize(self, request: AssessmentRequest) -> CanonicalIdeaRepresentation:
        if request != self.request:
            raise ValueError("request has no configured fixture")
        return self.idea.model_copy(deep=True)


class FixtureSufficiencyAnalyzer:
    def __init__(self, result: SufficiencyAssessment) -> None:
        self.result = result

    async def analyze(self, idea: CanonicalIdeaRepresentation) -> SufficiencyAssessment:
        return self.result.model_copy(deep=True)


class FixtureMCUDecomposer:
    def __init__(self, mcus: tuple[MCU, ...]) -> None:
        self.mcus = mcus

    async def decompose(self, idea: CanonicalIdeaRepresentation) -> tuple[MCU, ...]:
        return tuple(mcu.model_copy(deep=True) for mcu in self.mcus)


class FixtureMCUReconciler:
    def __init__(self, graph: MCUGraph) -> None:
        self.graph = graph

    async def reconcile(
        self, idea: CanonicalIdeaRepresentation, candidates: Sequence[MCU]
    ) -> MCUGraph:
        return self.graph.model_copy(deep=True)


class FixtureSearchPlanner:
    def __init__(self, result: SearchPlan) -> None:
        self.result = result

    async def plan(self, idea: CanonicalIdeaRepresentation, graph: MCUGraph) -> SearchPlan:
        return self.result.model_copy(deep=True)


class FixtureSearchPlanReviewer:
    async def review(self, plan: SearchPlan) -> SearchPlanReview:
        return SearchPlanReview(
            plan_hash=canonical_hash(plan),
            approved=True,
            provenance=fixture_provenance(type(self).__name__),
        )


class FixtureEvidenceMapper:
    def __init__(self, edges: tuple[EvidenceEdge, ...]) -> None:
        self.edges = edges

    async def map(
        self,
        mcus: Sequence[MCU],
        sources: Sequence[SourceRecord],
        passages: Sequence[SourcePassage],
    ) -> tuple[EvidenceEdge, ...]:
        return tuple(edge.model_copy(deep=True) for edge in self.edges)


class FixtureEvidenceVerifier:
    def __init__(self, edges: tuple[EvidenceEdge, ...]) -> None:
        self.edges = {edge.edge_id: edge for edge in edges}

    async def verify(
        self,
        edge: EvidenceEdge,
        mcus: Sequence[MCU],
        sources: Sequence[SourceRecord],
        passages: Sequence[SourcePassage],
    ) -> EvidenceEdge:
        return self.edges[edge.edge_id].model_copy(deep=True)


class FixtureAdjudicationEngine:
    def __init__(self, result: FrozenAdjudication) -> None:
        self.result = result

    async def adjudicate(
        self,
        *,
        assessment_id: AssessmentId,
        as_of: date,
        idea: CanonicalIdeaRepresentation,
        sufficiency: SufficiencyAssessment,
        mcus: Sequence[MCU],
        edges: Sequence[EvidenceEdge],
    ) -> FrozenAdjudication:
        return FrozenAdjudication.model_validate(
            {**self.result.model_dump(), "assessment_id": assessment_id, "as_of": as_of}
        )


@dataclass(frozen=True, slots=True)
class FixtureScenario:
    request: AssessmentRequest
    idea: CanonicalIdeaRepresentation
    sufficiency: SufficiencyAssessment
    graph: MCUGraph
    plan: SearchPlan
    search_query: SearchQuery
    sources: tuple[SourceRecord, ...]
    passages: tuple[SourcePassage, ...]
    edges: tuple[EvidenceEdge, ...]
    adjudication: FrozenAdjudication
    components: VerticalSliceComponents
    search_provider: MockSearchProvider
    content_resolver: MockContentResolver
    clock: Callable[[], datetime]


def make_fixture() -> FixtureScenario:
    request = AssessmentRequest(
        idea_id="idea_synthetic",
        input_text=(
            "  A temperature sensor controls a relay; "
            "a separate status indicator reduces operator checks.\n"
        ),
        as_of=date(2026, 9, 26),
        title="Synthetic sensor controller",
    )
    advantage = ClaimedAdvantage(dimension="workflow", statement="Reduce operator checks")
    idea = CanonicalIdeaRepresentation(
        idea_id=request.idea_id,
        original_input=request.input_text,
        original_input_ref="request.json#/input_text",
        title=request.title,
        problem=ProblemDescription(statement="Operate a relay and observe its status"),
        context=IdeaContext(temporal_cutoff=request.as_of, domains=("synthetic engineering",)),
        mcu_ids=("mcu_control", "mcu_status"),
        combination_ids=("C1",),
        claimed_advantages=(advantage,),
        unknowns=("No project-specific validation supplied",),
        provenance=fixture_provenance("FixtureIdeaNormalizer"),
    )
    sufficiency = SufficiencyAssessment(
        idea_id=request.idea_id,
        state=SufficiencyState.ASSESSABLE,
        assessable_dimensions=("synthetic architecture flow",),
        unassessable_dimensions=("real novelty", "demonstrated value"),
        missing_information=("Real evidence and project validation",),
        consequences=("Only fixture-backed architectural output is produced",),
        provenance=fixture_provenance("FixtureSufficiencyAnalyzer"),
    )
    mcus = (
        MCU(
            mcu_id="mcu_control",
            label="Sensor-to-relay control",
            statement="Temperature sensor controls a relay",
            mechanism="Sensor controls relay",
            features=(
                MCUFeature(feature_id="F1", concept="sensor"),
                MCUFeature(feature_id="F2", concept="relay"),
            ),
            relationships=(MCURelationship(subject="F1", relation="CONTROLS", object="F2"),),
            provenance=fixture_provenance("FixtureMCUDecomposer"),
        ),
        MCU(
            mcu_id="mcu_status",
            label="Status indication",
            statement="Show relay status",
            provenance=fixture_provenance("FixtureMCUDecomposer"),
        ),
    )
    graph = MCUGraph(
        idea_id=request.idea_id,
        mcus=mcus,
        combinations=(
            MCUCombination(
                combination_id="C1",
                label="Control and indication",
                statement="Control a relay and show status",
                member_ids=("mcu_control", "mcu_status"),
                provenance=fixture_provenance("FixtureMCUReconciler"),
            ),
        ),
        provenance=fixture_provenance("FixtureMCUReconciler"),
    )
    query = PlannedQuery(
        query_id="qry_control",
        mcu_id="mcu_control",
        family="RELATIONAL",
        evidence_family=EvidenceFamily.SOFTWARE,
        text="synthetic sensor controls relay",
        rationale="Exercise deterministic provider plumbing, not landscape research",
        generated_by="FixtureSearchPlanner",
        provenance=fixture_provenance("FixtureSearchPlanner"),
    )
    plan = SearchPlan(
        idea_id=request.idea_id,
        queries=(query,),
        provenance=fixture_provenance("FixtureSearchPlanner"),
    )
    search_query = SearchQuery(
        query_id=query.query_id,
        text=query.text,
        evidence_family=query.evidence_family,
        purpose=query.rationale,
    )
    ref = SourceRef(
        provider_name="fixture-search",
        provider_source_id="synthetic-manual",
        canonical_url="https://example.invalid/synthetic-manual",
        title="Synthetic controller manual",
    )
    text = (
        "Synthetic example: a temperature sensor controls a relay. "
        "This is test data, not real prior art."
    )
    source_id = "src_" + canonical_hash({"canonical_url": ref.canonical_url})
    passage_id = "pass_" + canonical_hash(
        {"source_id": source_id, "locator": "resolved_content", "text": text}
    )
    source = SourceRecord(
        source_id=source_id,
        canonical_title=ref.title,
        canonical_url=ref.canonical_url,
        source_type="unknown",
        access_state="full_text",
        content_hash=canonical_hash(text),
        provider_name=ref.provider_name,
        provider_source_id=ref.provider_source_id,
        discovered_by_queries=(query.query_id,),
        evidence_families=(query.evidence_family,),
        provenance=fixture_provenance("FixtureSource"),
    )
    passage = SourcePassage(
        passage_id=passage_id,
        source_id=source_id,
        text=text,
        locator="resolved_content",
        content_hash=canonical_hash(text),
        provenance=fixture_provenance("FixturePassage"),
    )
    edge = EvidenceEdge(
        edge_id="edge_control",
        source_id=source_id,
        mcu_id="mcu_control",
        proposition="Synthetic manual describes sensor-to-relay control",
        passage_ids=(passage_id,),
        comparison=EvidenceComparison(
            matching_elements=("sensor", "relay"), matching_relationships=("sensor controls relay",)
        ),
        relation_type=PrecedentState.COMPONENT_PRECEDENT_ONLY,
        evidence_quality=EvidenceTier.A,
        predates_cutoff=None,
        support_verification=SupportVerificationState.SUPPORTED,
        provenance=fixture_provenance("FixtureEvidenceVerifier"),
    )
    adjudication = FrozenAdjudication(
        assessment_id="asm_fixture",
        as_of=request.as_of,
        frozen_at=FIXED_TIME,
        overall_state=VerdictState.UNASSESSABLE,
        mcus=(
            MCUFinding(
                mcu_id="mcu_control",
                precedent_state=PrecedentState.COMPONENT_PRECEDENT_ONLY,
                verdict=VerdictState.UNASSESSABLE,
                decisive_edges=(edge.edge_id,),
                limiting_factors=("All evidence is synthetic",),
            ),
            MCUFinding(
                mcu_id="mcu_status",
                precedent_state=PrecedentState.UNRESOLVED,
                verdict=VerdictState.UNASSESSABLE,
            ),
        ),
        established_findings=("Fixture-only sensor-to-relay example is present",),
        strongest_challenges=(edge.proposition,),
        value_findings=(advantage,),
        validation_requirements=("Measure operator checks against an appropriate baseline",),
        permitted_language=("This run proves architecture only; real novelty is unassessed.",),
        forbidden_claims=("Nobody has ever done this",),
        unresolved_questions=("Real search, MCU interpretation, and adjudication are deferred",),
        evidence_limitations=(
            "Synthetic sources only; no search coverage or saturation established",
        ),
        provenance=fixture_provenance("FixtureAdjudicationEngine"),
    )

    def call(name: str, request_hash: str) -> ProviderCallMetadata:
        return ProviderCallMetadata(
            provider_name=name,
            provider_version="fixture-1",
            started_at=FIXED_TIME,
            finished_at=FIXED_TIME,
            request_hash=request_hash,
            status=TraceStatus.SUCCESS,
        )

    search = MockSearchProvider(
        name=ref.provider_name,
        query=search_query,
        pages={
            None: SearchPage(
                results=[SearchResult(source=ref, rank=1)],
                call=call(ref.provider_name, canonical_hash(search_query)),
            )
        },
        capabilities=ProviderCapabilities(
            evidence_families={EvidenceFamily.SOFTWARE}, supports_full_text=True
        ),
        health=ProviderHealth(healthy=True),
        capabilities_call=call(ref.provider_name, canonical_hash("capabilities")),
        health_call=call(ref.provider_name, canonical_hash("health")),
    )
    resolver = MockContentResolver(
        name="fixture-content",
        content=SourceContent(
            source=ref,
            text=text,
            content_type="text/plain",
            call=call("fixture-content", canonical_hash(ref)),
        ),
        passage=Passage(passage_id=passage_id, source=ref, text=text, locator="resolved_content"),
        passage_call=call(
            "fixture-content",
            canonical_hash({"source": ref.model_dump(mode="json"), "locator": "resolved_content"}),
        ),
    )
    components = VerticalSliceComponents(
        normalizer=FixtureIdeaNormalizer(request, idea),
        sufficiency_analyzer=FixtureSufficiencyAnalyzer(sufficiency),
        decomposer=FixtureMCUDecomposer(mcus),
        reconciler=FixtureMCUReconciler(graph),
        planner=FixtureSearchPlanner(plan),
        plan_reviewer=FixtureSearchPlanReviewer(),
        mapper=FixtureEvidenceMapper(
            (
                edge.model_copy(
                    update={
                        "support_verification": SupportVerificationState.INSUFFICIENT_CONTEXT,
                        "provenance": fixture_provenance("FixtureEvidenceMapper"),
                    }
                ),
            )
        ),
        verifier=FixtureEvidenceVerifier((edge,)),
        adjudicator=FixtureAdjudicationEngine(adjudication),
    )
    return FixtureScenario(
        request=request,
        idea=idea,
        sufficiency=sufficiency,
        graph=graph,
        plan=plan,
        search_query=search_query,
        sources=(source,),
        passages=(passage,),
        edges=(edge,),
        adjudication=adjudication,
        components=components,
        search_provider=search,
        content_resolver=resolver,
        clock=lambda: FIXED_TIME,
    )
