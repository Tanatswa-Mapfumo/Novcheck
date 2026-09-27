from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.enums import AssessmentStage, EvidenceFamily, ResearchDepth, TraceStatus
from novelty_harness.domain.ids import new_trace_event_id
from novelty_harness.domain.mcu import MCU
from novelty_harness.ports.retrieval import NativeRetrievalProvider
from novelty_harness.ports.retrieval_audit import (
    BudgetedRetrievalProvider,
    BudgetExhausted,
    RetrievalRequestEvent,
)
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.registry import ProviderRegistry
from novelty_harness.research.adaptive.controller import AdaptiveController
from novelty_harness.research.adaptive.escalation import multilingual_hook
from novelty_harness.research.adaptive.models import BranchState, ResearchAction
from novelty_harness.research.adaptive.stopping import (
    ConvergenceSignals,
    StopAssessment,
    StoppingPolicy,
    StopReason,
    assess_stop,
)
from novelty_harness.research.coverage import (
    CoverageCell,
    CoveragePolicy,
    CoverageState,
    QueryScreeningOutcome,
    evaluate_coverage,
)
from novelty_harness.research.expansion.chronology import (
    CandidateChronology,
    TemporalAssessment,
    assess_temporal,
    capture_chronology,
)
from novelty_harness.research.expansion.citations import EXPANSION_KINDS
from novelty_harness.research.fusion.clustering import (
    CandidateCluster,
    cluster_candidates,
    rekey_lists,
)
from novelty_harness.research.fusion.rrf import FusedCandidate, reciprocal_rank_fusion
from novelty_harness.research.models import FamilyApplicability, ResearchPlan
from novelty_harness.research.retrieval.executor import strategy_for
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCapabilities,
    RetrievalStrategy,
    mechanism_for,
)
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.budgets.controller import BudgetController, BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink


class AdaptiveCoverageCell(ContractModel):
    model_config = ConfigDict(frozen=True)
    screening: CoverageCell
    depth: ResearchDepth
    stop: StopAssessment
    strategies: frozenset[RetrievalStrategy]
    rounds: int = Field(ge=0)


class ResearchResult(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["adaptive-research-v1"] = "adaptive-research-v1"
    batches: tuple[RetrievalBatch, ...]
    fused_candidates: tuple[FusedCandidate, ...]
    candidate_clusters: tuple[CandidateCluster, ...]
    chronology: dict[str, CandidateChronology]
    temporal_assessments: dict[str, TemporalAssessment]
    branch_states: tuple[BranchState, ...]
    stop_assessments: tuple[StopAssessment, ...]
    coverage_matrix: tuple[AdaptiveCoverageCell, ...]
    expansion_events: tuple[ResearchAction, ...]
    request_events: tuple[RetrievalRequestEvent, ...]
    budget_usage: BudgetUsage
    limitations: tuple[str, ...]


def write_research_artifacts(
    writer: RunArtifactWriter, assessment: AssessmentRecord, result: ResearchResult
) -> None:
    identity = assessment.assessment_id
    for name, rows in (
        ("retrieval_batches", result.batches),
        ("fused_candidates", result.fused_candidates),
        ("candidate_clusters", result.candidate_clusters),
        ("expansion_events", result.expansion_events),
        ("branch_states", result.branch_states),
        ("stop_assessments", result.stop_assessments),
        ("request_events", result.request_events),
    ):
        writer.write_jsonl(identity, "phase4/" + name + ".jsonl", rows)
    writer.write_json(
        identity,
        "phase4/chronology.json",
        {k: v.model_dump(mode="json") for k, v in result.chronology.items()},
    )
    writer.write_json(
        identity,
        "phase4/temporal_assessments.json",
        {k: v.model_dump(mode="json") for k, v in result.temporal_assessments.items()},
    )
    writer.write_json(
        identity,
        "phase4/coverage_matrix.json",
        [c.model_dump(mode="json") for c in result.coverage_matrix],
    )
    writer.write_json(identity, "phase4/research_result.json", result)


async def run_adaptive_research(
    *,
    assessment: AssessmentRecord,
    mcus: Sequence[MCU],
    reviewed_plan: ResearchPlan,
    provider_registry: ProviderRegistry,
    coverage_policy: CoveragePolicy,
    budget_controller: BudgetController,
    budget_limits: BudgetLimits,
    stopping_policy: StoppingPolicy,
    trace_sink: TraceSink,
    artifact_writer: RunArtifactWriter | None = None,
    clock: Callable[[], datetime] = utc_now,
    apparent_novelty: frozenset[str] = frozenset(),
    strongest_candidates: int = 3,
    max_expansion_depth: int = 1,
    rrf_k: int = 60,
    multilingual_material: bool = False,
) -> ResearchResult:
    plan = ResearchPlan.model_validate(reviewed_plan.model_dump()).model_copy(deep=True)
    if (
        not plan.reviewed
        or plan.review is None
        or plan.review.status != "PASS"
        or plan.assessment_id != assessment.assessment_id
        or plan.as_of != assessment.request.as_of
        or set(plan.mcu_ids) != {m.mcu_id for m in mcus}
    ):
        raise ValueError("Adaptive research requires an assessment-bound, MCU-bound PASS plan")
    if strongest_candidates < 1 or max_expansion_depth < 1:
        raise ValueError("Expansion policy bounds must be positive")
    start = clock()
    usage = BudgetUsage()
    batches: list[RetrievalBatch] = []
    expansions: list[ResearchAction] = []
    states: dict[tuple[str, EvidenceFamily], BranchState] = {}
    queues: dict[tuple[str, EvidenceFamily], list[ResearchAction]] = {}
    scheduled: set[str] = set()
    completed: set[str] = set()
    failed: set[str] = set()
    top_history: dict[tuple[str, EvidenceFamily], list[tuple[str, ...]]] = {}
    citation_yield: dict[tuple[str, EvidenceFamily], list[int]] = {}
    successful: dict[tuple[str, EvidenceFamily], list[RetrievalBatch]] = {}
    required_neighborhoods: dict[
        tuple[str, EvidenceFamily], set[tuple[str, str, RetrievalStrategy]]
    ] = {}
    explored_neighborhoods: dict[
        tuple[str, EvidenceFamily], set[tuple[str, str, RetrievalStrategy]]
    ] = {}
    outcomes: dict[tuple[str, str], QueryScreeningOutcome] = {}
    names = {
        f: tuple(p.descriptor.name for p in provider_registry.providers_for(f))
        for f in EvidenceFamily
    }
    preflight = evaluate_coverage(plan, coverage_policy, names)
    providers: dict[str, NativeRetrievalProvider] = {}
    capabilities: dict[str, RetrievalCapabilities] = {}
    auditors: dict[str, BudgetedRetrievalProvider] = {}
    offsets: dict[str, int] = {}
    controller = AdaptiveController()
    intents = {q.query_id: q for q in plan.intents}

    def action_key(action: ResearchAction) -> str:
        return canonical_hash(action.model_dump(mode="json", exclude={"rationale"}))

    def enqueue(action: ResearchAction) -> None:
        key = action_key(action)
        if key not in scheduled:
            scheduled.add(key)
            queues[(action.mcu_id, action.evidence_family)].append(action)

    def elapsed() -> None:
        nonlocal usage
        usage = usage.model_copy(
            update={"elapsed_seconds": max(0, (clock() - start).total_seconds())}
        )

    def guard() -> None:
        nonlocal usage
        elapsed()
        wire_limits = budget_limits.model_copy(update={"max_deep_search_rounds": None})
        decision = budget_controller.permit(usage, wire_limits, BudgetUsage(provider_calls=1))
        if not decision.allowed:
            raise BudgetExhausted("Hard research budget prevents another wire attempt")
        usage = usage.model_copy(update={"provider_calls": usage.provider_calls + 1})

    def documents_remaining() -> int | None:
        limit = budget_limits.max_retrieved_documents
        return None if limit is None else max(0, limit - usage.retrieved_documents)

    def seconds_remaining() -> float | None:
        elapsed()
        limit = budget_limits.max_elapsed_seconds
        return None if limit is None else max(0, limit - usage.elapsed_seconds)

    def emit(
        reason: str,
        artifact: ContractModel,
        state: BranchState | None = None,
        failure: bool = False,
    ) -> None:
        event = TraceEvent(
            event_id=new_trace_event_id(),
            assessment_id=assessment.assessment_id,
            occurred_at=clock(),
            stage=AssessmentStage.ADAPTIVE_RESEARCH,
            component="adaptive_research",
            status=TraceStatus.FAILURE if failure else TraceStatus.SUCCESS,
            reason_code=reason,
            mcu_id=state.mcu_id if state else None,
            data={
                "execution": "implemented",
                "semantics_implemented": True,
                "artifact": artifact.model_dump(mode="json"),
            },
        )
        trace_sink.emit(event)

    def fuse(
        key: tuple[str, EvidenceFamily],
    ) -> tuple[list[FusedCandidate], list[CandidateCluster]]:
        lists = {
            str(i): list(b.candidates)
            for i, b in enumerate(batches)
            if b.candidates and (b.candidates[0].mcu_id, b.candidates[0].evidence_family) == key
        }
        clusters = cluster_candidates([c for rows in lists.values() for c in rows])
        return reciprocal_rank_fusion(rekey_lists(lists, clusters), k=rrf_k), clusters

    def coverage() -> tuple[CoverageCell, ...]:
        return evaluate_coverage(plan, coverage_policy, names, tuple(outcomes.values()))

    def convergence(key: tuple[str, EvidenceFamily]) -> ConvergenceSignals:
        rows, _ = fuse(key)
        active = successful.get(key, [])
        overlap = any(len({mechanism_for(c.strategy) for c in f.discoveries}) > 1 for f in rows)
        major_keys = {f.candidate_key for f in rows[:strongest_candidates]}
        major_sources = {
            (c.provider_name, c.source.provider_source_id)
            for f in rows
            if f.candidate_key in major_keys
            for c in f.discoveries
        }
        unexpanded = any(
            a.action_type == "EXPAND"
            and a.seed_source is not None
            and (a.seed_source.provider_name, a.seed_source.provider_source_id) in major_sources
            for a in queues[key]
        )
        failed_expansion = any(
            a.action_type == "EXPAND"
            and action_key(a) in failed
            and (a.mcu_id, a.evidence_family) == key
            for a in expansions
        )
        cell = next(c for c in coverage() if (c.mcu_id, c.evidence_family) == key)
        required = {
            item for item in required_neighborhoods.get(key, set()) if item[:2] in major_sources
        }
        fully_explored = required <= explored_neighborhoods.get(key, set())
        return ConvergenceSignals(
            successful_providers=frozenset(b.provider_name for b in active),
            successful_strategies=frozenset(b.strategy for b in active),
            coverage_floor_met=cell.state == CoverageState.SCREENED,
            top_cluster_history=tuple(top_history.get(key, [])),
            overlap_observed=overlap,
            major_candidates_explored=bool(major_sources)
            and fully_explored
            and not unexpanded
            and not failed_expansion,
            citation_yield=tuple(citation_yield.get(key, [])),
        )

    async def execute(action: ResearchAction, *, screening: bool) -> None:
        nonlocal usage
        key = (action.mcu_id, action.evidence_family)
        state = states[key]
        assert action.provider_name is not None and action.strategy is not None
        provider = providers.get(action.provider_name)
        elapsed()
        cost = BudgetUsage(deep_search_rounds=0 if screening else 1)
        if not budget_controller.permit(usage, budget_limits, cost).allowed:
            states[key] = state.model_copy(update={"budget_stopped": True})
            return
        usage = usage.model_copy(
            update={"deep_search_rounds": usage.deep_search_rounds + cost.deep_search_rounds}
        )
        emit("RESEARCH_ACTION", action, state)
        before = {f.candidate_key for f in fuse(key)[0]}
        batch: RetrievalBatch | None = None
        errors = list(state.access_failures)
        auditor = auditors.get(action.provider_name)
        request_start = len(auditor.retrieval_request_events()) if auditor else 0
        try:
            if provider is None:
                raise ValueError("Native retrieval capability unavailable")
            if auditor is None:
                if (
                    budget_limits.max_provider_calls is not None
                    or budget_limits.max_elapsed_seconds is not None
                    or budget_limits.max_retrieved_documents is not None
                ):
                    raise ValueError("Wire-level budget hook unavailable")
                guard()
            if action.action_type == "EXPAND":
                assert action.seed_source is not None
                expansions.append(action)
                raw = await provider.expand(
                    source=action.seed_source,
                    strategy=action.strategy,
                    as_of=plan.as_of,
                    mcu_id=action.mcu_id,
                    cursor=action.cursor,
                    rank_offset=action.rank_offset,
                )
            else:
                assert action.query_id is not None
                raw = await provider.retrieve(
                    intent=intents[action.query_id],
                    strategy=action.strategy,
                    as_of=plan.as_of,
                    cursor=action.cursor,
                    rank_offset=action.rank_offset,
                )
            batch = RetrievalBatch.model_validate(raw.model_dump())
            if (
                batch.provider_name != action.provider_name
                or batch.strategy != action.strategy
                or any(
                    (c.mcu_id, c.evidence_family) != key
                    or c.seed_source != action.seed_source
                    or c.query_id != (None if action.action_type == "EXPAND" else action.query_id)
                    for c in batch.candidates
                )
            ):
                raise ValueError("Mismatched retrieval branch/path")
            batches.append(batch)
            usage = usage.model_copy(
                update={"retrieved_documents": usage.retrieved_documents + len(batch.candidates)}
            )
            if batch.complete and not batch.had_failed_attempts:
                successful.setdefault(key, []).append(batch)
            else:
                errors.append(action.provider_name + ":incomplete retrieval or failed attempts")
            emit("RETRIEVAL_BATCH", batch, state)
            if batch.next_cursor is not None:
                next_action = action.model_copy(
                    update={
                        "action_type": "EXPAND" if action.action_type == "EXPAND" else "PAGE",
                        "cursor": batch.next_cursor,
                        "rank_offset": action.rank_offset
                        + (
                            batch.rank_span
                            if batch.rank_span is not None
                            else max(
                                (c.local_rank - action.rank_offset for c in batch.candidates),
                                default=0,
                            )
                        ),
                    }
                )
                prior = [
                    a
                    for a in expansions
                    if action.action_type == "EXPAND"
                    and a.provider_name == action.provider_name
                    and a.strategy == action.strategy
                    and a.seed_source == action.seed_source
                ]
                repeated = batch.next_cursor == action.cursor or any(
                    a.cursor == batch.next_cursor for a in prior
                )
                # Cursor history is independent of ranks, so repeats cannot become progress.
                cursor_identity = canonical_hash(
                    next_action.model_dump(mode="json", exclude={"rationale", "rank_offset"})
                )
                if repeated or cursor_identity in cursor_history:
                    errors.append(action.provider_name + ":pagination cursor cycle")
                else:
                    cursor_history.add(cursor_identity)
                    enqueue(next_action)
        except BudgetExhausted:
            states[key] = state.model_copy(update={"budget_stopped": True})
        except (ProviderError, ValueError) as error:
            code = (
                error.failure.category.value
                if isinstance(error, ProviderError)
                else "PARSE_OR_CAPABILITY_FAILURE"
            )
            errors.append(action.provider_name + ":" + code)
            failed.add(action_key(action))
        finally:
            for event in auditor.retrieval_request_events()[request_start:] if auditor else ():
                emit("RETRIEVAL_REQUEST", event, state, event.failure_code is not None)
        completed.add(action_key(action))
        if (
            action.action_type == "EXPAND"
            and action.seed_source is not None
            and batch is not None
            and batch.complete
            and not batch.had_failed_attempts
            and batch.next_cursor is None
        ):
            explored_neighborhoods.setdefault(key, set()).add(
                (action.provider_name, action.seed_source.provider_source_id, action.strategy)
            )
        if screening and action.query_id is not None:
            outcomes[(action.query_id, action.provider_name)] = QueryScreeningOutcome(
                query_id=action.query_id,
                provider_name=action.provider_name,
                success=batch is not None,
                inspected_results=len(batch.candidates) if batch else 0,
                had_failed_attempts=batch.had_failed_attempts if batch else bool(errors),
                complete=batch.complete if batch else False,
            )
        rows, _ = fuse(key)
        new = len({f.candidate_key for f in rows} - before)
        state = states[key]
        states[key] = state.model_copy(
            update={
                "depth": ResearchDepth.SCREENING
                if screening
                else ResearchDepth.ESCALATED
                if state.mcu_id in apparent_novelty or not before
                else ResearchDepth.DEEP,
                "providers_attempted": state.providers_attempted | {action.provider_name},
                "strategies_attempted": state.strategies_attempted | {action.strategy},
                "rounds": state.rounds + 1,
                "relevant_candidate_count": len(rows),
                "new_candidate_yield": (*state.new_candidate_yield, new),
                "access_failures": tuple(dict.fromkeys(errors)),
            }
        )
        top_history.setdefault(key, []).append(
            tuple(f.candidate_key for f in rows[:strongest_candidates])
        )
        if action.strategy in EXPANSION_KINDS:
            citation_yield.setdefault(key, []).append(new)
        for fused in rows[:strongest_candidates]:
            for c in fused.discoveries:
                cap = capabilities.get(c.provider_name)
                if cap is None:
                    continue
                depth = action.expansion_depth + 1 if c.seed_source is not None else 1
                for kind in sorted(cap.strategies & EXPANSION_KINDS):
                    neighborhood = (c.provider_name, c.source.provider_source_id, kind)
                    required_neighborhoods.setdefault(key, set()).add(neighborhood)
                    if depth > max_expansion_depth:
                        deferred = ":".join(
                            (c.provider_name, c.source.provider_source_id, kind.value)
                        )
                        if neighborhood not in explored_neighborhoods.get(key, set()):
                            states[key] = states[key].model_copy(
                                update={
                                    "deferred_neighborhoods": tuple(
                                        dict.fromkeys(
                                            (*states[key].deferred_neighborhoods, deferred)
                                        )
                                    )
                                }
                            )
                        continue
                    enqueue(
                        ResearchAction(
                            action_type="EXPAND",
                            mcu_id=state.mcu_id,
                            evidence_family=state.evidence_family,
                            strategy=kind,
                            provider_name=c.provider_name,
                            seed_source=c.source,
                            expansion_depth=depth,
                            rationale="Investigate strongest neighborhoods within depth and budget",
                        )
                    )
        emit("RESEARCH_BRANCH", states[key], states[key])

    cursor_history: set[str] = set()
    installed: list[BudgetedRetrievalProvider] = []
    try:
        for family in EvidenceFamily:
            for registered in provider_registry.providers_for(family):
                p = registered.provider
                if p.name in providers or not isinstance(p, NativeRetrievalProvider):
                    continue
                providers[p.name] = p
                capabilities[p.name] = RetrievalCapabilities.model_validate(
                    (await p.retrieval_capabilities()).model_dump()
                )
                if isinstance(p, BudgetedRetrievalProvider):
                    auditors[p.name] = p
                    offsets[p.name] = len(p.retrieval_request_events())
                    p.set_request_guard(guard)
                    installed.append(p)
                    p.set_document_limit(documents_remaining)
                    p.set_time_limit(seconds_remaining)
        for branch in plan.family_assessments:
            key = (branch.mcu_id, branch.evidence_family)
            cell = next(c for c in preflight if (c.mcu_id, c.evidence_family) == key)
            inactive = branch.applicability == FamilyApplicability.NOT_APPLICABLE
            gaps = (
                ()
                if inactive or cell.state == CoverageState.READY_FOR_SCREENING
                else (cell.state.value,)
            )
            states[key] = BranchState(
                mcu_id=branch.mcu_id,
                evidence_family=branch.evidence_family,
                depth=ResearchDepth.INACTIVE if inactive else ResearchDepth.SCREENING,
                access_failures=gaps,
            )
            queues[key] = []
            if inactive:
                continue
            emit(
                "MULTILINGUAL_COVERAGE",
                multilingual_hook(states[key], supported=False),
                states[key],
            )
            if multilingual_material:
                states[key] = states[key].model_copy(
                    update={"access_failures": (*gaps, "Material multilingual hook unavailable")}
                )
        initial: list[ResearchAction] = []
        for intent in plan.intents:
            key = (intent.mcu_id, intent.evidence_family)
            for name in names[intent.evidence_family]:
                initial.append(
                    ResearchAction(
                        action_type="RETRIEVE",
                        mcu_id=intent.mcu_id,
                        evidence_family=intent.evidence_family,
                        strategy=strategy_for(intent),
                        provider_name=name,
                        query_id=intent.query_id,
                        rationale=intent.rationale,
                    )
                )
            for name in names[intent.evidence_family]:
                caps = capabilities.get(name)
                if (
                    caps is not None
                    and RetrievalStrategy.SEMANTIC in caps.strategies
                    and not any(
                        a.provider_name == name and a.strategy == RetrievalStrategy.SEMANTIC
                        for a in queues[key]
                    )
                ):
                    enqueue(
                        ResearchAction(
                            action_type="RETRIEVE",
                            mcu_id=intent.mcu_id,
                            evidence_family=intent.evidence_family,
                            strategy=RetrievalStrategy.SEMANTIC,
                            provider_name=name,
                            query_id=intent.query_id,
                            rationale="Native semantic falsification path",
                        )
                    )
        for action in initial:
            await execute(action, screening=True)
        terminal: dict[tuple[str, EvidenceFamily], StopAssessment] = {}
        while True:
            eligible = [
                key
                for key, state in states.items()
                if queues[key] and key not in terminal and state.depth != ResearchDepth.INACTIVE
            ]
            if not eligible:
                break
            key = min(
                eligible, key=lambda k: (states[k].rounds, states[k].relevant_candidate_count, k)
            )
            state = states[key]
            stop = assess_stop(state, convergence(key), stopping_policy)
            if stop.reason in {StopReason.SATURATED, StopReason.BUDGET_STOPPED}:
                terminal[key] = stop
                continue
            action = controller.next_action(
                state,
                queues[key],
                apparent_novelty=state.mcu_id in apparent_novelty,
                coverage_floor_met=convergence(key).coverage_floor_met,
            )
            queues[key].remove(next(a for a in queues[key] if action_key(a) == action_key(action)))
            await execute(action, screening=False)
        cells = coverage()
        stops: list[StopAssessment] = []
        adaptive_cells: list[AdaptiveCoverageCell] = []
        fused_all: list[FusedCandidate] = []
        cluster_all: list[CandidateCluster] = []
        for cell in cells:
            key = (cell.mcu_id, cell.evidence_family)
            state = states[key]
            stop = terminal.get(key) or assess_stop(state, convergence(key), stopping_policy)
            if state.depth == ResearchDepth.INACTIVE:
                stop = StopAssessment(
                    reason=StopReason.CONTINUE,
                    signals={"budget_blocked": False, "excluded_with_rationale": True},
                )
            depth = (
                ResearchDepth(stop.reason.value)
                if stop.reason != StopReason.CONTINUE
                else state.depth
            )
            state = state.model_copy(update={"depth": depth})
            states[key] = state
            stops.append(stop)
            adaptive_cells.append(
                AdaptiveCoverageCell(
                    screening=cell,
                    depth=depth,
                    stop=stop,
                    strategies=state.strategies_attempted,
                    rounds=state.rounds,
                )
            )
            rows, clusters = fuse(key)
            fused_all.extend(rows)
            cluster_all.extend(clusters)
            for fused in rows:
                emit("CANDIDATE_FUSION", fused, state)
            emit(
                "RESEARCH_STOP",
                stop,
                state,
                stop.reason in {StopReason.ACCESS_BLOCKED, StopReason.BUDGET_STOPPED},
            )
        chronological = {
            canonical_hash(c.model_dump(mode="json")): capture_chronology(c)
            for b in batches
            for c in b.candidates
        }
        temporal = {k: assess_temporal(c, as_of=plan.as_of) for k, c in chronological.items()}
        for key, value in chronological.items():
            emit("CANDIDATE_CHRONOLOGY", value)
            emit("TEMPORAL_ELIGIBILITY", temporal[key])
        elapsed()
        result = ResearchResult(
            batches=tuple(batches),
            fused_candidates=tuple(fused_all),
            candidate_clusters=tuple(cluster_all),
            chronology=chronological,
            temporal_assessments=temporal,
            branch_states=tuple(states.values()),
            stop_assessments=tuple(stops),
            coverage_matrix=tuple(adaptive_cells),
            expansion_events=tuple(expansions),
            request_events=tuple(
                e
                for name, p in auditors.items()
                for e in p.retrieval_request_events()[offsets[name] :]
            ),
            budget_usage=usage,
            limitations=(
                "Candidate-level retrieval only; Phase 5+ evidence semantics "
                "remain fixture-backed/deferred",
                "Retrieved candidates are routing proxies, not verified relevant evidence",
                "Multilingual hooks unavailable unless explicit translated intents "
                "are supplied in the reviewed plan",
            ),
        )
        if artifact_writer is not None:
            write_research_artifacts(artifact_writer, assessment, result)
        return result
    finally:
        for p in installed:
            p.set_request_guard(None)
            p.set_document_limit(None)
            p.set_time_limit(None)
