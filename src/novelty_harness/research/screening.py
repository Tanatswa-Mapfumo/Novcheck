from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, FiniteFloat

from novelty_harness.domain.base import ContractModel, UTCDateTime, utc_now
from novelty_harness.domain.enums import EvidenceFamily, TraceStatus
from novelty_harness.domain.ids import AssessmentId, MCUId, QueryId
from novelty_harness.ports.models import ProviderCallMetadata, SearchPage, SearchQuery, SourceRef
from novelty_harness.ports.search_audit import ScreeningDiagnostics, SearchAuditSource
from novelty_harness.providers.errors import (
    FailureCategory,
    ProviderError,
    ProviderFailure,
    provider_error,
)
from novelty_harness.providers.registry import ProviderRegistry
from novelty_harness.research.coverage import (
    CoverageCell,
    CoveragePolicy,
    QueryScreeningOutcome,
    evaluate_coverage,
)
from novelty_harness.research.models import ResearchPlan
from novelty_harness.research.provider_queries import CompiledProviderQuery, compile_intent
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter


class ScreeningHit(ContractModel):
    model_config = ConfigDict(frozen=True)
    query_id: QueryId
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    provider_name: str
    source: SourceRef
    provider_rank: int = Field(ge=1)
    provider_score: FiniteFloat | None = None
    snippet: str | None = None
    retrieved_at: UTCDateTime
    call_metadata: ProviderCallMetadata


class ScreeningEvent(ContractModel):
    model_config = ConfigDict(frozen=True)
    query_id: QueryId
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    provider_name: str
    state: Literal["SUCCESS", "ZERO_RESULTS", "PROVIDER_FAILURE"]
    at: UTCDateTime
    result_count: int = Field(ge=0)
    call: ProviderCallMetadata | None = None
    diagnostics: ScreeningDiagnostics


class ScreeningRunResult(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["screening-run-v1"] = "screening-run-v1"
    assessment_id: AssessmentId
    plan_review_id: str
    hits: tuple[ScreeningHit, ...]
    coverage: tuple[CoverageCell, ...]
    provider_failures: tuple[ProviderFailure, ...]
    compiled_queries: tuple[CompiledProviderQuery, ...]
    events: tuple[ScreeningEvent, ...]
    limitations: tuple[str, ...]


def write_screening_artifacts(
    writer: RunArtifactWriter, plan: ResearchPlan, result: ScreeningRunResult, *, prefix: str = ""
) -> None:
    identity = plan.assessment_id
    writer.write_json(
        identity,
        prefix + "family_applicability.json",
        [a.model_dump(mode="json") for a in plan.family_assessments],
    )
    writer.write_json(identity, prefix + "search_plan.json", plan)
    writer.write_json(identity, prefix + "search_plan_review.json", plan.review)
    writer.write_jsonl(identity, prefix + "compiled_queries.jsonl", result.compiled_queries)
    writer.write_jsonl(identity, prefix + "screening_events.jsonl", result.events)
    writer.write_jsonl(identity, prefix + "screening_hits.jsonl", result.hits)
    writer.write_json(
        identity,
        prefix + "coverage_matrix.json",
        [c.model_dump(mode="json") for c in result.coverage],
    )
    writer.write_jsonl(identity, prefix + "provider_failures.jsonl", result.provider_failures)


class ScreeningExecutor:
    def __init__(
        self,
        registry: ProviderRegistry,
        policy: CoveragePolicy,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.registry, self.policy, self.clock = registry, policy, clock

    async def execute(
        self, plan: ResearchPlan, *, writer: RunArtifactWriter | None = None
    ) -> ScreeningRunResult:
        plan = ResearchPlan.model_validate(plan.model_dump()).model_copy(deep=True)
        if not plan.reviewed or plan.review is None or plan.review.status != "PASS":
            raise ValueError("screening requires this plan's final PASS review")
        providers = {
            f: tuple(p.descriptor.name for p in self.registry.providers_for(f))
            for f in EvidenceFamily
        }
        compiled: list[CompiledProviderQuery] = []
        hits: list[ScreeningHit] = []
        outcomes: list[QueryScreeningOutcome] = []
        failures: list[ProviderFailure] = []
        events: list[ScreeningEvent] = []
        for intent in plan.intents:
            for registered in self.registry.providers_for(intent.evidence_family):
                name, provider = registered.descriptor.name, registered.provider
                page: SearchPage | None = None
                error: ProviderError | None = None
                try:
                    if registered.compiler is None:
                        raise provider_error(
                            name,
                            FailureCategory.CAPABILITY_MISMATCH,
                            "Provider has no registered compiler",
                            intent.query_id,
                        )
                    query = compile_intent(registered.compiler, intent, as_of=plan.as_of)
                    if query.provider_name != name:
                        raise ValueError("compiler targets the wrong provider")
                    compiled.append(query)
                    page = SearchPage.model_validate(
                        (
                            await provider.search(
                                SearchQuery(
                                    query_id=intent.query_id,
                                    text=intent.text,
                                    evidence_family=intent.evidence_family,
                                    purpose=intent.rationale,
                                    filters={**intent.filters, "as_of": plan.as_of.isoformat()},
                                )
                            )
                        ).model_dump()
                    )
                    if page.call.provider_name != name or page.call.status != TraceStatus.SUCCESS:
                        raise provider_error(
                            name,
                            FailureCategory.PROVIDER_UNAVAILABLE,
                            "Unsuccessful or mismatched provider call",
                            intent.query_id,
                            page.call,
                        )
                    if any(h.source.provider_name != name for h in page.results):
                        raise provider_error(
                            name,
                            FailureCategory.PARSE_FAILURE,
                            "Mismatched result provider",
                            intent.query_id,
                            page.call,
                        )
                except ProviderError as failure:
                    error = failure
                diagnostics = (
                    provider.screening_diagnostics(intent.query_id)
                    if isinstance(provider, SearchAuditSource)
                    else ScreeningDiagnostics()
                )
                if error is not None:
                    failures.append(error.failure)
                    page = None
                count = len(page.results) if page is not None else 0
                outcomes.append(
                    QueryScreeningOutcome(
                        query_id=intent.query_id,
                        provider_name=name,
                        success=page is not None,
                        inspected_results=count,
                        had_failed_attempts=diagnostics.had_failed_attempts,
                        complete=diagnostics.complete,
                        limitations=diagnostics.limitations,
                    )
                )
                events.append(
                    ScreeningEvent(
                        query_id=intent.query_id,
                        mcu_id=intent.mcu_id,
                        evidence_family=intent.evidence_family,
                        provider_name=name,
                        state="PROVIDER_FAILURE"
                        if error
                        else "SUCCESS"
                        if count
                        else "ZERO_RESULTS",
                        at=self.clock(),
                        result_count=count,
                        call=error.failure.call if error else page.call if page else None,
                        diagnostics=diagnostics,
                    )
                )
                for hit in page.results if page else ():
                    assert page is not None
                    score = hit.metadata.get("provider_local_score")
                    hits.append(
                        ScreeningHit(
                            query_id=intent.query_id,
                            mcu_id=intent.mcu_id,
                            evidence_family=intent.evidence_family,
                            provider_name=name,
                            source=hit.source.model_copy(deep=True),
                            provider_rank=hit.rank,
                            provider_score=float(score)
                            if isinstance(score, int | float) and not isinstance(score, bool)
                            else None,
                            snippet=hit.snippet,
                            retrieved_at=self.clock(),
                            call_metadata=page.call,
                        )
                    )
        coverage = evaluate_coverage(plan, self.policy, providers, outcomes)
        result = ScreeningRunResult(
            assessment_id=plan.assessment_id,
            plan_review_id=plan.review.review_id,
            hits=tuple(hits),
            coverage=coverage,
            provider_failures=tuple(failures),
            compiled_queries=tuple(compiled),
            events=tuple(events),
            limitations=(
                "Bounded first-page screening only; "
                "no saturation, evidence equivalence or novelty decision",
                *tuple(dict.fromkeys(n for c in coverage for n in c.limitations)),
            ),
        )
        if writer is not None:
            write_screening_artifacts(writer, plan, result)
        return result
