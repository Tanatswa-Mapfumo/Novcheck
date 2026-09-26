from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, JsonValue

from novelty_harness.application.models import AssessmentSummary, VerticalSliceComponents
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
from novelty_harness.ports.content import ContentResolver
from novelty_harness.ports.models import (
    ProviderCallMetadata,
    SearchPage,
    SearchQuery,
    SourceContent,
)
from novelty_harness.ports.search import SearchProvider
from novelty_harness.reporting.minimal import compile_minimal_report
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
) -> None:
    mcu_ids = {mcu.mcu_id for mcu in mcus}
    source_ids = {source.source_id for source in sources}
    passage_sources = {passage.passage_id: passage.source_id for passage in passages}
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
) -> VerticalSliceResult:
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
        plan = _checked(await components.planner.plan(idea, graph), SearchPlan)
        if plan.idea_id != idea.idea_id or any(
            query.mcu_id not in mcu_ids for query in plan.queries
        ):
            raise ValueError("search plan references another idea or unknown MCU")
        artifact_writer.write_json(record.assessment_id, "search_plan.json", plan)
        run.stage(AssessmentStage.SEARCH_PLANNED, plan.provenance, plan)
        plan_hash = canonical_hash(plan)
        review = _checked(
            await components.plan_reviewer.review(plan.model_copy(deep=True)), SearchPlanReview
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
        sources, passages = await _screen(run, plan, search_provider, content_resolver)
        run.stage(
            AssessmentStage.ADAPTIVE_RESEARCH,
            _origin("deferred", "Adaptive research is not implemented."),
        )
        artifact_writer.write_jsonl(record.assessment_id, "sources.jsonl", sources)
        artifact_writer.write_jsonl(record.assessment_id, "passages.jsonl", passages)
        run.stage(
            AssessmentStage.EVIDENCE_NORMALIZED,
            _origin(
                "deferred",
                "Transport records and hashes only; "
                "semantic normalization and provenance reasoning deferred.",
            ),
        )
        mapped = tuple(
            _checked(edge, EvidenceEdge)
            for edge in await components.mapper.map(graph.mcus, sources, passages)
        )
        _check_edges(mapped, graph.mcus, sources, passages)
        run.stage(
            AssessmentStage.EVIDENCE_MAPPED,
            mapped[0].provenance if mapped else _origin("deferred", "No mapped evidence supplied."),
        )
        verified: list[EvidenceEdge] = []
        for edge in mapped:
            checked = _checked(
                await components.verifier.verify(edge, graph.mcus, sources, passages), EvidenceEdge
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
