from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, JsonValue

from novelty_harness.application.evidence_phase5 import (
    Phase5EvidenceComponents,
    Phase6FixtureContinuation,
)
from novelty_harness.application.evidence_phase5 import (
    project_passage as project_passage_legacy,
)
from novelty_harness.application.evidence_phase5 import (
    project_source as project_source_legacy,
)
from novelty_harness.application.evidence_phase6 import (
    GRAPH_REF,
    Phase6EvidenceComponents,
    project_verified_edges,
)
from novelty_harness.application.models import AssessmentSummary, VerticalSliceComponents
from novelty_harness.application.research import (
    DeferredFixtureContinuation,
    Phase3ResearchComponents,
)
from novelty_harness.application.research_phase4 import (
    Phase4ResearchComponents,
    Phase5FixtureContinuation,
)
from novelty_harness.application.understanding import (
    UnderstandingArtifactSource,
    UnderstandingUpdate,
)
from novelty_harness.domain.adjudication import FrozenAdjudication
from novelty_harness.domain.assessment import AssessmentRecord, AssessmentRequest
from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.enums import (
    AssessmentStage,
    AssessmentStatus,
    SufficiencyState,
    SupportVerificationState,
    TraceStatus,
)
from novelty_harness.domain.evidence import EvidenceEdge, SourcePassage, SourceRecord
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    SufficiencyAssessment,
)
from novelty_harness.domain.ids import new_assessment_id, new_trace_event_id
from novelty_harness.domain.mcu import MCU, MCUGraph
from novelty_harness.domain.reporting import CompiledReport
from novelty_harness.domain.research import SearchPlan, SearchPlanReview
from novelty_harness.domain.state_machine import advance_stage, change_status, complete_assessment
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.phase6_pipeline import Phase6EvidenceResult
from novelty_harness.ports.content import ContentResolver
from novelty_harness.ports.models import (
    ProviderCallMetadata,
    SearchPage,
    SearchQuery,
    SourceContent,
)
from novelty_harness.ports.search import SearchProvider
from novelty_harness.reporting.minimal import compile_minimal_report
from novelty_harness.research.screening import write_screening_artifacts
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import JsonlTraceSink, TraceSink


def _checked[T: ContractModel](value: object, kind: type[T]) -> T:
    if not isinstance(value, kind):
        raise ValueError(f"component must return {kind.__name__}")
    return kind.model_validate(value.model_dump(mode="python"))


def _origin(kind: str, detail: str) -> ArtifactProvenance:
    return ArtifactProvenance.model_validate(
        {"kind": kind, "component": "vertical_slice", "detail": detail}
    )


@dataclass(frozen=True, slots=True)
class VerticalSliceResult:
    record: AssessmentRecord
    run_dir: Path
    adjudication: FrozenAdjudication
    report: CompiledReport
    summary: AssessmentSummary


@dataclass(slots=True)
class _Run:
    record: AssessmentRecord
    writer: RunArtifactWriter
    sink: TraceSink
    local_sink: JsonlTraceSink
    clock: Callable[[], datetime]

    def collect_understanding(self, component: object) -> UnderstandingUpdate:
        if not isinstance(component, UnderstandingArtifactSource):
            return UnderstandingUpdate()
        update = component.drain_understanding_update()
        for name, artifact in update.artifacts:
            self.writer.write_json(self.record.assessment_id, name, artifact)
        for audit in update.calls:
            self.emit(
                reason="SEMANTIC_CALL",
                call=audit.call,
                output=audit,
                status=TraceStatus.SUCCESS
                if audit.validation_state == "VALIDATED"
                else TraceStatus.FAILURE,
                data={
                    "audit": audit.model_dump(mode="json"),
                    "execution": "implemented",
                    "semantics_implemented": True,
                },
            )
        return update

    def collect_research(self, research: Phase3ResearchComponents | None) -> None:
        for audit in research.drain_research_audits() if research else ():
            self.emit(
                reason="SEMANTIC_CALL",
                call=audit.call,
                output=audit,
                status=TraceStatus.SUCCESS
                if audit.validation_state == "VALIDATED"
                else TraceStatus.FAILURE,
                data={
                    "audit": audit.model_dump(mode="json"),
                    "execution": "implemented",
                    "semantics_implemented": True,
                },
            )

    def emit(
        self,
        *,
        reason: str,
        data: dict[str, JsonValue],
        status: TraceStatus = TraceStatus.SUCCESS,
        output: BaseModel | JsonValue = None,
        call: ProviderCallMetadata | None = None,
    ) -> None:
        event = TraceEvent(
            event_id=new_trace_event_id(),
            assessment_id=self.record.assessment_id,
            occurred_at=self.clock(),
            stage=self.record.stage,
            component="vertical_slice",
            status=status,
            reason_code=reason,
            data=data,
            request_hash=call.request_hash if call else None,
            response_hash=canonical_hash(output) if output is not None else None,
            provider_name=call.provider_name if call else None,
            provider_version=call.provider_version if call else None,
            latency_ms=(call.finished_at - call.started_at).total_seconds() * 1000
            if call
            else None,
        )
        self.local_sink.emit(event)
        self.sink.emit(event)

    def stage(
        self,
        target: AssessmentStage,
        origin: ArtifactProvenance,
        output: BaseModel | JsonValue = None,
    ) -> None:
        updated, event = advance_stage(
            self.record,
            target,
            actor=origin.component,
            reason=origin.detail,
            occurred_at=self.clock(),
        )
        self.record = updated
        self.emit(
            reason="STAGE_TRANSITION",
            output=output,
            status=TraceStatus.SKIPPED if origin.kind == "deferred" else TraceStatus.SUCCESS,
            data={
                "lifecycle": event.model_dump(mode="json"),
                "execution": origin.kind,
                "semantics_implemented": origin.kind == "implemented",
                "detail": origin.detail,
            },
        )
        self.writer.write_json(self.record.assessment_id, "assessment_record.json", self.record)

    def provider_call(self, name: str, call: ProviderCallMetadata, response: BaseModel) -> None:
        if call.provider_name != name:
            raise ValueError("provider metadata does not match the injected provider")
        self.emit(
            reason="PROVIDER_CALL",
            status=call.status,
            call=call,
            output=response,
            data={
                "call": call.model_dump(mode="json"),
                "execution": "injected_provider",
                "semantics_implemented": False,
            },
        )
        if call.status != TraceStatus.SUCCESS:
            raise ValueError("provider returned an explicit unsuccessful call")


@dataclass(frozen=True)
class _ResearchTraceSink:
    run: _Run

    def emit(self, event: TraceEvent) -> None:
        self.run.local_sink.emit(event)
        self.run.sink.emit(event)


async def _screen(
    run: _Run,
    plan: SearchPlan,
    search: SearchProvider,
    resolver: ContentResolver,
) -> tuple[tuple[SourceRecord, ...], tuple[SourcePassage, ...]]:
    sources: dict[str, SourceRecord] = {}
    passages: dict[str, SourcePassage] = {}
    retrievals: list[JsonValue] = []
    origin = _origin("implemented", "Transport wrapping only; source interpretation is deferred.")
    for planned in plan.queries:
        query = SearchQuery(
            query_id=planned.query_id,
            text=planned.text,
            evidence_family=planned.evidence_family,
            purpose=planned.rationale,
            filters=planned.filters,
        )
        cursor: str | None = None
        seen: set[str | None] = set()
        while True:
            if cursor in seen:
                raise ValueError("provider pagination cursor cycle")
            seen.add(cursor)
            page = _checked(await search.search(query, cursor), SearchPage)
            run.provider_call(search.name, page.call, page)
            retrievals.append(
                {
                    "schema_version": "0.1",
                    "query_id": query.query_id,
                    "cursor": cursor,
                    "page": page.model_dump(mode="json"),
                }
            )
            for hit in page.results:
                content = _checked(await resolver.resolve(hit.source), SourceContent)
                run.provider_call(resolver.name, content.call, content)
                if content.source != hit.source:
                    raise ValueError("resolved content does not match the requested source")
                identity: dict[str, JsonValue] = (
                    {"canonical_url": hit.source.canonical_url}
                    if hit.source.canonical_url
                    else {
                        "provider_name": hit.source.provider_name,
                        "provider_source_id": hit.source.provider_source_id,
                    }
                )
                source_id = "src_" + canonical_hash(identity)
                content_hash = canonical_hash(content.text)
                previous = sources.get(source_id)
                if previous and previous.content_hash != content_hash:
                    raise ValueError("conflicting content for one source identity")
                discoveries = tuple(
                    dict.fromkeys(
                        (
                            *(previous.discovered_by_queries if previous else ()),
                            query.query_id,
                        )
                    )
                )
                families = tuple(
                    dict.fromkeys(
                        (
                            *(previous.evidence_families if previous else ()),
                            query.evidence_family,
                        )
                    )
                )
                sources[source_id] = SourceRecord(
                    source_id=source_id,
                    canonical_title=hit.source.title,
                    canonical_url=hit.source.canonical_url,
                    source_type="unknown",
                    access_state="unknown",
                    content_hash=content_hash,
                    provider_name=hit.source.provider_name,
                    provider_source_id=hit.source.provider_source_id,
                    discovered_by_queries=discoveries,
                    evidence_families=families,
                    provenance=origin,
                )
                if content.text and content.text.strip():
                    passage_id = "pass_" + canonical_hash(
                        {
                            "source_id": source_id,
                            "locator": "resolved_content",
                            "text": content.text,
                        }
                    )
                    passages[passage_id] = SourcePassage(
                        passage_id=passage_id,
                        source_id=source_id,
                        text=content.text,
                        locator="resolved_content",
                        content_hash=content_hash,
                        provenance=origin,
                    )
            cursor = page.next_cursor
            if cursor is None:
                break
    run.writer.write_jsonl(run.record.assessment_id, "retrieval_events.jsonl", retrievals)
    return tuple(sources.values()), tuple(passages.values())


def _check_edges(
    edges: Sequence[EvidenceEdge],
    mcus: Sequence[MCU],
    sources: Sequence[SourceRecord],
    passages: Sequence[SourcePassage],
    *,
    extra_mcu_ids: Sequence[str] = (),
    extra_passage_sources: Mapping[str, str] | None = None,
) -> None:
    """Validate edge identities against persisted evidence.

    Phase 6 combination targets and same-source context-expansion passages are
    legitimate identities and are supplied explicitly; anything else remains
    foreign and is rejected.
    """

    mcu_ids = {mcu.mcu_id for mcu in mcus} | set(extra_mcu_ids)
    source_ids = {source.source_id for source in sources}
    passage_sources = {passage.passage_id: passage.source_id for passage in passages}
    for identity, source_id in (extra_passage_sources or {}).items():
        existing = passage_sources.get(identity)
        if existing is not None and existing != source_id:
            raise ValueError("context-expansion passage identity conflicts with a source")
        passage_sources[identity] = source_id
    if len({edge.edge_id for edge in edges}) != len(edges):
        raise ValueError("duplicate evidence edge IDs")
    for edge in edges:
        if edge.mcu_id not in mcu_ids or edge.source_id not in source_ids:
            raise ValueError("evidence references an unknown MCU or source")
        if any(passage_sources.get(identity) != edge.source_id for identity in edge.passage_ids):
            raise ValueError("evidence passage does not belong to its referenced source")


async def run_vertical_slice(
    *,
    request: AssessmentRequest,
    components: VerticalSliceComponents,
    search_provider: SearchProvider,
    content_resolver: ContentResolver,
    trace_sink: TraceSink,
    artifact_writer: RunArtifactWriter,
    clock: Callable[[], datetime] = utc_now,
    research: Phase3ResearchComponents | None = None,
    fixture_continuation: DeferredFixtureContinuation | None = None,
    adaptive_research: Phase4ResearchComponents | None = None,
    adaptive_fixture_continuation: Phase5FixtureContinuation | None = None,
    evidence: Phase5EvidenceComponents | None = None,
    evidence_fixture_continuation: Phase6FixtureContinuation | None = None,
    phase6: Phase6EvidenceComponents | None = None,
) -> VerticalSliceResult:
    if evidence is not None and (evidence_fixture_continuation is None) == (phase6 is None):
        raise ValueError(
            "Phase 5 evidence normalization requires exactly one Phase 6 continuation: "
            "the explicit fixture or real Phase 6 verification"
        )
    if evidence is None and (evidence_fixture_continuation is not None or phase6 is not None):
        raise ValueError("Phase 6 components require Phase 5 evidence normalization")
    if evidence is not None and adaptive_research is None:
        raise ValueError("Phase 5 evidence normalization requires Phase 4 adaptive research")
    if evidence is not None and adaptive_fixture_continuation is not None:
        raise ValueError(
            "Choose either the Phase 5 fixture continuation or real Phase 5 normalization"
        )
    if evidence_fixture_continuation is not None and phase6 is not None:
        raise ValueError(
            "Choose either the Phase 6 fixture continuation or real Phase 6 verification"
        )
    if (
        (research is None) != (fixture_continuation is None and adaptive_research is None)
        or (fixture_continuation is not None and adaptive_research is not None)
        or (
            adaptive_research is not None
            and adaptive_fixture_continuation is None
            and evidence is None
        )
        or (adaptive_research is None and adaptive_fixture_continuation is not None)
    ):
        raise ValueError(
            "Phase 3 research and explicit deferred fixture continuation are required together"
        )
    request = _checked(request, AssessmentRequest)
    now = clock()
    record = AssessmentRecord(
        assessment_id=new_assessment_id(), request=request, created_at=now, updated_at=now
    )
    directory = artifact_writer.assessment_dir(record.assessment_id)
    artifact_writer.write_json(record.assessment_id, "request.json", request)
    run = _Run(
        record, artifact_writer, trace_sink, JsonlTraceSink(directory / "trace.jsonl"), clock
    )
    artifact_writer.write_json(record.assessment_id, "assessment_record.json", record)
    run.emit(
        reason="ASSESSMENT_RECEIVED",
        output=request,
        data={"execution": "implemented", "semantics_implemented": True},
    )
    try:
        idea = _checked(
            await components.normalizer.normalize(request.model_copy(deep=True)),
            CanonicalIdeaRepresentation,
        )
        run.collect_understanding(components.normalizer)
        if idea.original_input != request.input_text:
            raise ValueError("normalization must preserve exact original input")
        if idea.idea_id != request.idea_id or idea.context.temporal_cutoff != request.as_of:
            raise ValueError("CIR identity/cutoff does not match the request")
        artifact_writer.write_json(record.assessment_id, "canonical_idea.json", idea)
        run.stage(AssessmentStage.NORMALIZED, idea.provenance, idea)
        sufficiency = _checked(
            await components.sufficiency_analyzer.analyze(idea), SufficiencyAssessment
        )
        run.collect_understanding(components.sufficiency_analyzer)
        if sufficiency.idea_id != idea.idea_id:
            raise ValueError("sufficiency references another idea")
        artifact_writer.write_json(record.assessment_id, "sufficiency.json", sufficiency)
        run.stage(AssessmentStage.SUFFICIENCY_ASSESSED, sufficiency.provenance, sufficiency)
        candidates = tuple(
            _checked(mcu, MCU) for mcu in await components.decomposer.decompose(idea)
        )
        run.collect_understanding(components.decomposer)
        origin = (
            candidates[0].provenance
            if candidates
            else _origin("deferred", "No MCU candidates supplied.")
        )
        run.stage(AssessmentStage.MCU_DECOMPOSED, origin)
        graph = _checked(await components.reconciler.reconcile(idea, candidates), MCUGraph)
        understanding_update = run.collect_understanding(components.reconciler)
        mcu_ids = {mcu.mcu_id for mcu in graph.mcus}
        if graph.idea_id != idea.idea_id or len(mcu_ids) != len(graph.mcus):
            raise ValueError("MCU graph has invalid identity bindings")
        if any(
            identity not in mcu_ids for combo in graph.combinations for identity in combo.member_ids
        ):
            raise ValueError("combination references unknown MCU")
        if understanding_update.finalized_idea is not None:
            finalized = _checked(understanding_update.finalized_idea, CanonicalIdeaRepresentation)
            if (
                finalized.original_input != idea.original_input
                or finalized.idea_id != idea.idea_id
                or finalized.context != idea.context
                or set(finalized.mcu_ids) != mcu_ids
                or set(finalized.combination_ids) != {c.combination_id for c in graph.combinations}
            ):
                raise ValueError("final understanding CIR binding mismatch")
            idea = finalized
            artifact_writer.write_json(record.assessment_id, "canonical_idea.json", idea)
            run.emit(
                reason="MCU_GRAPH_BOUND",
                output=idea,
                data={"execution": "implemented", "semantics_implemented": True},
            )
        ceiling = understanding_update.assessment_ceiling
        if ceiling is not None and list(SufficiencyState).index(ceiling) < list(
            SufficiencyState
        ).index(sufficiency.state):
            sufficiency = SufficiencyAssessment.model_validate(
                {
                    **sufficiency.model_dump(),
                    "state": ceiling,
                    "consequences": (
                        *sufficiency.consequences,
                        "MCU_DECOMPOSITION_INSTABILITY: see mcu_reconciliation.json "
                        "for affected MCUs",
                    ),
                }
            )
            artifact_writer.write_json(record.assessment_id, "sufficiency.json", sufficiency)
            run.emit(
                reason="MCU_DECOMPOSITION_INSTABILITY",
                output=sufficiency,
                data={
                    "assessment_ceiling": ceiling.value,
                    "execution": "implemented",
                    "semantics_implemented": True,
                },
            )
        artifact_writer.write_json(record.assessment_id, "mcu_graph.json", graph)
        run.stage(AssessmentStage.MCU_RECONCILED, graph.provenance, graph)
        preparation = (
            (
                await research.prepare(
                    assessment_id=record.assessment_id,
                    idea=idea,
                    graph=graph,
                    writer=artifact_writer,
                )
            )
            if research
            else None
        )
        run.collect_research(research)
        plan = (
            preparation.legacy_plan
            if preparation
            else _checked(await components.planner.plan(idea, graph), SearchPlan)
        )
        if plan.idea_id != idea.idea_id or any(
            query.mcu_id not in mcu_ids for query in plan.queries
        ):
            raise ValueError("search plan references another idea or unknown MCU")
        artifact_writer.write_json(record.assessment_id, "search_plan.json", plan)
        run.stage(AssessmentStage.SEARCH_PLANNED, plan.provenance, plan)
        plan_hash = canonical_hash(plan)
        review = (
            preparation.legacy_review
            if preparation
            else _checked(
                await components.plan_reviewer.review(plan.model_copy(deep=True)), SearchPlanReview
            )
        )
        artifact_writer.write_json(record.assessment_id, "search_plan_review.json", review)
        if review.plan_hash != plan_hash or not review.approved:
            raise ValueError("search plan review is unapproved or does not match the plan")
        run.stage(AssessmentStage.SEARCH_PLAN_REVIEWED, review.provenance, review)
        run.stage(
            AssessmentStage.SCREENING,
            _origin(
                "implemented",
                "Execute injected provider queries; no coverage or saturation inferred.",
            ),
        )
        evidence_origin: ArtifactProvenance | None = None
        phase6_result: Phase6EvidenceResult | None = None
        if research and preparation and adaptive_research and adaptive_fixture_continuation:
            adaptive_result = await adaptive_research.execute(
                assessment=run.record,
                mcus=graph.mcus,
                plan=preparation.plan,
                trace_sink=_ResearchTraceSink(run),
                writer=artifact_writer,
                clock=clock,
            )
            run.stage(
                AssessmentStage.ADAPTIVE_RESEARCH,
                _origin(
                    "implemented",
                    "Real diversified retrieval and explicit adaptive stopping; "
                    "evidence semantics deferred",
                ),
                adaptive_result,
            )
            run.emit(
                reason="PHASE5_FIXTURE_BOUNDARY",
                output=adaptive_result,
                data={
                    "execution": "fixture",
                    "semantics_implemented": False,
                    "detail": "Phase 4 candidate retrieval ended; "
                    "Phase 5+ evidence/adjudication remain fixture-backed",
                },
            )
            sources, passages = await adaptive_fixture_continuation.materialize(
                adaptive_result, graph
            )
            sources = tuple(_checked(s, SourceRecord) for s in sources)
            passages = tuple(_checked(p, SourcePassage) for p in passages)
            if any(s.provenance.kind != "fixture" for s in (*sources, *passages)):
                raise ValueError("Phase 5+ continuation must be visibly fixture-backed")
        elif (
            research
            and preparation
            and adaptive_research
            and evidence
            and (evidence_fixture_continuation or phase6)
        ):
            adaptive_result = await adaptive_research.execute(
                assessment=run.record,
                mcus=graph.mcus,
                plan=preparation.plan,
                trace_sink=_ResearchTraceSink(run),
                writer=artifact_writer,
                clock=clock,
            )
            run.stage(
                AssessmentStage.ADAPTIVE_RESEARCH,
                _origin(
                    "implemented",
                    "Real diversified retrieval and explicit adaptive stopping; "
                    "source/evidence semantics normalized by Phase 5",
                ),
                adaptive_result,
            )
            evidence_result = await evidence.execute(
                assessment=run.record,
                research=adaptive_result,
                resolver=content_resolver,
                writer=artifact_writer,
                trace_sink=_ResearchTraceSink(run),
                clock=clock,
            )
            evidence_origin = _origin(
                "implemented",
                "Canonical source/version/passage normalization, provenance, lineage "
                "and separated quality/relevance; no Phase 6 adjudication.",
            )
            run.stage(
                AssessmentStage.EVIDENCE_NORMALIZED,
                evidence_origin,
                {
                    "graph_ref": evidence_result.graph_ref,
                    "source_count": len(evidence_result.sources),
                    "version_count": len(evidence_result.versions),
                    "passage_count": len(evidence_result.passages),
                    "independent_evidence_count": sum(
                        cluster.independent_roots for cluster in evidence_result.lineage_clusters
                    ),
                    "cycle_count": len(evidence_result.cycles),
                },
            )
            if phase6 is not None:
                phase6_result = await phase6.execute(
                    assessment=run.record,
                    evidence=evidence_result,
                    mcus=graph.mcus,
                    combinations=graph.combinations,
                    as_of=request.as_of,
                    writer=artifact_writer,
                    trace_sink=_ResearchTraceSink(run),
                    clock=clock,
                )
                sources = tuple(
                    project_source_legacy(source, provenance=source.provenance)
                    for source in evidence_result.sources
                )
                passages = tuple(
                    project_passage_legacy(passage, provenance=passage.provenance)
                    for passage in evidence_result.passages
                )
                run.emit(
                    reason="PHASE7_FIXTURE_BOUNDARY",
                    output=adaptive_result,
                    data={
                        "execution": "fixture",
                        "semantics_implemented": False,
                        "detail": "Phase 6 mapping/verification/classification completed; "
                        "Phase 7+ adjudication remains fixture-backed",
                    },
                )
            else:
                assert evidence_fixture_continuation is not None
                run.emit(
                    reason="PHASE6_FIXTURE_BOUNDARY",
                    output=adaptive_result,
                    data={
                        "execution": "fixture",
                        "semantics_implemented": False,
                        "detail": "Phase 5 evidence normalization completed; "
                        "Phase 6+ mapping/adjudication remain fixture-backed",
                    },
                )
                sources, passages = await evidence_fixture_continuation.materialize(
                    evidence_result, graph
                )
                sources = tuple(_checked(s, SourceRecord) for s in sources)
                passages = tuple(_checked(p, SourcePassage) for p in passages)
                if any(s.provenance.kind != "fixture" for s in (*sources, *passages)):
                    raise ValueError("Phase 6+ continuation must be visibly fixture-backed")
        elif research and preparation and fixture_continuation:
            screening = await research.executor.execute(preparation.plan)
            write_screening_artifacts(
                artifact_writer, preparation.plan, screening, prefix="phase3/"
            )
            for event in screening.events:
                run.emit(
                    reason="PHASE3_SCREENING",
                    output=event,
                    call=event.call,
                    status=TraceStatus.FAILURE
                    if event.state == "PROVIDER_FAILURE"
                    else TraceStatus.SUCCESS,
                    data={
                        "execution": "implemented",
                        "semantics_implemented": True,
                        "screening": event.model_dump(mode="json"),
                    },
                )
            run.emit(
                reason="PHASE4_FIXTURE_BOUNDARY",
                output=screening,
                data={
                    "execution": "fixture",
                    "semantics_implemented": False,
                    "detail": "Phase 3 screening ended; "
                    "later research/evidence/adjudication remain fixture-backed",
                },
            )
            sources, passages = await fixture_continuation.materialize(screening, graph)
            sources = tuple(_checked(s, SourceRecord) for s in sources)
            passages = tuple(_checked(p, SourcePassage) for p in passages)
            if any(s.provenance.kind != "fixture" for s in (*sources, *passages)):
                raise ValueError("Phase 4+ continuation must be visibly fixture-backed")
        else:
            sources, passages = await _screen(run, plan, search_provider, content_resolver)
        if adaptive_research is None:
            run.stage(
                AssessmentStage.ADAPTIVE_RESEARCH,
                _origin(
                    "deferred", "Adaptive research is not implemented in this compatibility path."
                ),
            )
        artifact_writer.write_jsonl(record.assessment_id, "sources.jsonl", sources)
        artifact_writer.write_jsonl(record.assessment_id, "passages.jsonl", passages)
        if evidence_origin is None:
            run.stage(
                AssessmentStage.EVIDENCE_NORMALIZED,
                _origin(
                    "deferred",
                    "Transport records and hashes only; "
                    "semantic normalization and provenance reasoning deferred.",
                ),
            )
        if phase6_result is not None:
            phase6_repository = SqlAlchemyEvidenceGraphRepository(
                artifact_writer.assessment_dir(record.assessment_id) / GRAPH_REF
            )
            try:
                verified: list[EvidenceEdge] = list(
                    project_verified_edges(phase6_result, phase6_repository)
                )
            finally:
                phase6_repository.close()
            _check_edges(
                verified,
                graph.mcus,
                sources,
                passages,
                extra_mcu_ids=tuple(
                    proposition.mcu_id for proposition in phase6_result.propositions
                ),
                extra_passage_sources={
                    expansion.window_passage.passage_id: expansion.window_passage.source_id
                    for expansion in phase6_result.expansions
                    if expansion.available and expansion.window_passage is not None
                },
            )
            run.stage(
                AssessmentStage.EVIDENCE_MAPPED,
                _origin(
                    "implemented",
                    "Passage-grounded mapping proposals over real Phase 5 evidence; "
                    "support is verified separately.",
                ),
                {
                    "mapping_count": len(phase6_result.mappings),
                    "claim_count": len(phase6_result.claims),
                    "failure_count": len(phase6_result.failures),
                },
            )
        else:
            mapped = tuple(
                _checked(edge, EvidenceEdge)
                for edge in await components.mapper.map(graph.mcus, sources, passages)
            )
            _check_edges(mapped, graph.mcus, sources, passages)
            run.stage(
                AssessmentStage.EVIDENCE_MAPPED,
                mapped[0].provenance
                if mapped
                else _origin("deferred", "No mapped evidence supplied."),
            )
            verified = []
            for edge in mapped:
                checked = _checked(
                    await components.verifier.verify(edge, graph.mcus, sources, passages),
                    EvidenceEdge,
                )
                if checked.edge_id != edge.edge_id:
                    raise ValueError("verification replaced the evidence edge identity")
                verified.append(checked)
            _check_edges(verified, graph.mcus, sources, passages)
        artifact_writer.write_jsonl(record.assessment_id, "evidence_edges.jsonl", verified)
        run.stage(
            AssessmentStage.EVIDENCE_VERIFIED,
            verified[0].provenance
            if verified
            else _origin("deferred", "No verified evidence supplied."),
        )
        run.stage(
            AssessmentStage.ADVERSARIAL_CHALLENGE,
            _origin("deferred", "Prosecutor reasoning is not implemented."),
        )
        run.stage(
            AssessmentStage.DEFENCE_REVIEW,
            _origin("deferred", "Defender reasoning is not implemented."),
        )
        adjudication = _checked(
            await components.adjudicator.adjudicate(
                assessment_id=record.assessment_id,
                as_of=request.as_of,
                idea=idea,
                sufficiency=sufficiency,
                mcus=graph.mcus,
                edges=verified,
            ),
            FrozenAdjudication,
        )
        if (
            adjudication.assessment_id != record.assessment_id
            or adjudication.as_of != request.as_of
        ):
            raise ValueError("adjudication is not bound to the current assessment/cutoff")
        supported_ids = {
            edge.edge_id
            for edge in verified
            if edge.support_verification == SupportVerificationState.SUPPORTED
        }
        if any(finding.mcu_id not in mcu_ids for finding in adjudication.mcus):
            raise ValueError("adjudication references unknown MCU")
        if len({finding.mcu_id for finding in adjudication.mcus}) != len(adjudication.mcus):
            raise ValueError("adjudication contains duplicate MCU findings")
        query_ids = {query.query_id for query in plan.queries}
        for coverage in adjudication.coverage_matrix:
            if coverage.mcu_id not in mcu_ids:
                raise ValueError("coverage references unknown MCU")
            if any(identity not in query_ids for identity in coverage.query_ids):
                raise ValueError("coverage references unknown query")
        if any(
            identity not in supported_ids
            for finding in adjudication.mcus
            for identity in finding.decisive_edges
        ):
            raise ValueError("adjudication references missing or unsupported decisive evidence")
        edge_mcus = {edge.edge_id: edge.mcu_id for edge in verified}
        if any(
            edge_mcus[identity] != finding.mcu_id
            for finding in adjudication.mcus
            for identity in finding.decisive_edges
        ):
            raise ValueError("decisive evidence does not belong to the finding MCU")
        run.stage(AssessmentStage.PRELIMINARY_ADJUDICATION, adjudication.provenance, adjudication)
        run.stage(
            AssessmentStage.ROBUSTNESS_REVIEW,
            _origin("deferred", "Robustness reasoning is not implemented."),
        )
        artifact_writer.write_json(record.assessment_id, "adjudication.json", adjudication)
        run.stage(
            AssessmentStage.FINDINGS_FROZEN,
            _origin("implemented", "Persist immutable injected findings; no new verdict."),
            adjudication,
        )
        report = compile_minimal_report(
            idea=idea,
            sufficiency=sufficiency,
            mcus=graph.mcus,
            edges=verified,
            adjudication=adjudication,
        )
        artifact_writer.write_json(record.assessment_id, "report.json", report)
        artifact_writer.write_text(record.assessment_id, "report.md", report.markdown)
        run.stage(AssessmentStage.REPORTED, report.provenance, report)
        final_record, completion = complete_assessment(
            run.record,
            actor="vertical_slice",
            reason="Required structured artifacts and Markdown report produced.",
            occurred_at=clock(),
        )
        summary = AssessmentSummary(
            id=record.assessment_id,
            as_of=request.as_of,
            stage=final_record.stage,
            status=final_record.status,
            input_sufficiency=sufficiency.state,
            overall_verdict=adjudication.overall_state,
            mcu_findings=adjudication.mcus,
            closest_precedents=tuple(
                dict.fromkeys(
                    edge.source_id
                    for edge in verified
                    if edge.edge_id in supported_ids
                    and any(edge.edge_id in finding.decisive_edges for finding in adjudication.mcus)
                )
            ),
            value_findings=adjudication.value_findings,
            evidence_limitations=adjudication.evidence_limitations,
            coverage_matrix=adjudication.coverage_matrix,
            trace_ref="trace.jsonl",
            provenance=adjudication.provenance,
        )
        artifact_writer.write_json(record.assessment_id, "assessment.json", summary)
        artifact_writer.write_json(record.assessment_id, "assessment_record.json", final_record)
        run.emit(
            reason="STATUS_TRANSITION",
            data={
                "lifecycle": completion.model_dump(mode="json"),
                "execution": "implemented",
                "semantics_implemented": True,
            },
        )
        run.record = final_record
        return VerticalSliceResult(final_record, directory, adjudication, report, summary)
    except Exception as error:
        run.collect_research(research)
        for component in (
            components.normalizer,
            components.sufficiency_analyzer,
            components.decomposer,
            components.reconciler,
        ):
            run.collect_understanding(component)
        run.record, failure = change_status(
            run.record,
            AssessmentStatus.FAILED,
            actor="vertical_slice",
            reason="Execution failed without fallback.",
            occurred_at=clock(),
        )
        artifact_writer.write_json(record.assessment_id, "assessment_record.json", run.record)
        run.emit(
            reason="EXECUTION_FAILURE",
            status=TraceStatus.FAILURE,
            data={
                "lifecycle": failure.model_dump(mode="json"),
                "error_type": type(error).__name__,
                "error": str(error),
                "execution": "implemented",
                "semantics_implemented": False,
            },
        )
        raise
