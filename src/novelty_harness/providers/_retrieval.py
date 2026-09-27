from collections.abc import Callable
from copy import deepcopy
from datetime import date

from pydantic import ValidationError

from novelty_harness.domain.enums import EvidenceFamily, TraceStatus
from novelty_harness.domain.ids import MCUId, QueryId
from novelty_harness.ports.models import SearchPage, SourceRef
from novelty_harness.ports.retrieval_audit import BudgetExhausted, RetrievalRequestEvent
from novelty_harness.providers._base import HTTPSearchAdapter
from novelty_harness.providers.errors import FailureCategory, ProviderError, provider_error
from novelty_harness.providers.http import HTTPResult
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery
from novelty_harness.research.retrieval.executor import strategy_for
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCandidate,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class NativeRequests(HTTPSearchAdapter):
    def set_request_guard(self, guard: Callable[[], None] | None) -> None:
        if guard is None:
            self.runtime.request_guards.pop(self.name, None)
        elif self.name in self.runtime.request_guards:
            raise ValueError("A provider already has an active budget guard")
        else:
            self.runtime.request_guards[self.name] = guard

    def set_document_limit(self, limit: Callable[[], int | None] | None) -> None:
        self._document_limit = limit

    def retrieval_request_events(self) -> tuple[RetrievalRequestEvent, ...]:
        return tuple(getattr(self, "_request_events", []))

    async def text_retrieve(
        self,
        *,
        intent: SearchIntent,
        strategy: RetrievalStrategy,
        as_of: date,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch:
        from novelty_harness.ports.models import SearchQuery

        strategy = RetrievalStrategy(strategy)
        if strategy != strategy_for(intent):
            raise provider_error(
                self.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Text request cannot pretend to use another mechanism",
                intent.query_id,
            )
        compiled = self.compiler.compile(intent, as_of=as_of)
        params: dict[str, str | int | float | bool] = {}
        for key, value in compiled.params.items():
            if not isinstance(value, str | int | float | bool):
                raise provider_error(
                    self.name,
                    FailureCategory.BAD_REQUEST,
                    "Non-scalar request parameter",
                    intent.query_id,
                )
            params[key] = value
        self.apply_cursor(params, cursor)
        compiled = CompiledProviderQuery.model_validate({**compiled.model_dump(), "params": params})
        result = await self.native_request(compiled)
        data = self.runtime.parse_json(result, provider=self.name, query_id=intent.query_id)
        page, notes = self.parse(
            data,
            result,
            SearchQuery(
                query_id=intent.query_id,
                text=intent.text,
                purpose=intent.rationale,
                evidence_family=intent.evidence_family,
            ),
            date.max,
        )
        return self.native_batch(
            page=page,
            strategy=strategy,
            family=intent.evidence_family,
            mcu_id=intent.mcu_id,
            query_id=intent.query_id,
            seed=None,
            cursor=cursor,
            rank_offset=rank_offset,
            calls=(result,),
            compiled=(compiled,),
            next_cursor=page.next_cursor,
            limitations=(*compiled.compilation_notes, *notes),
        )

    async def native_request(
        self, compiled: CompiledProviderQuery, *, interval: float | None = None
    ) -> HTTPResult:
        params: dict[str, str | int | float | bool] = {}
        for key, value in compiled.params.items():
            if not isinstance(value, str | int | float | bool):
                raise provider_error(
                    self.name,
                    FailureCategory.BAD_REQUEST,
                    "Non-scalar native request parameter",
                    compiled.query_id,
                )
            params[key] = value
        limit_callback: Callable[[], int | None] | None = getattr(self, "_document_limit", None)
        remaining = limit_callback() if limit_callback else None
        if remaining is not None:
            for key in ("per_page", "rows", "limit"):
                if key in params:
                    params[key] = min(int(params[key]), max(1, remaining))
        actual = CompiledProviderQuery.model_validate({**compiled.model_dump(), "params": params})
        start = len(self.runtime.attempts)
        call = None
        failure = None
        try:
            result = await self.runtime.request(
                provider=self.name,
                query_id=compiled.query_id,
                method=compiled.method,
                endpoint=compiled.endpoint,
                params=self.request_params(params),
                headers=self.headers(),
                min_interval=self.min_interval() if interval is None else interval,
            )
            call = result.call
            return result
        except ProviderError as error:
            call, failure = error.failure.call, error.failure.category.value
            raise
        except BudgetExhausted:
            failure = "BUDGET_STOPPED"
            raise
        finally:
            attempts = self.runtime.attempts[start:]
            event = RetrievalRequestEvent(
                compiled_query=CompiledProviderQuery.model_validate(
                    self.runtime.redact(actual.model_dump(mode="json"))
                ),
                call=call,
                attempts=tuple(a.model_dump(mode="json") for a in attempts),
                failure_code=failure,
            )
            events: list[RetrievalRequestEvent] = getattr(self, "_request_events", [])
            events.append(event)
            self._request_events = events

    def native_batch(
        self,
        *,
        page: SearchPage,
        strategy: RetrievalStrategy,
        family: EvidenceFamily,
        mcu_id: MCUId | None,
        query_id: QueryId | None,
        seed: SourceRef | None,
        cursor: str | None,
        rank_offset: int,
        calls: tuple[HTTPResult, ...],
        compiled: tuple[CompiledProviderQuery, ...],
        limitations: tuple[str, ...] = (),
        next_cursor: str | None = None,
    ) -> RetrievalBatch:
        try:
            if page.call.status != TraceStatus.SUCCESS or rank_offset < 0:
                raise ValueError("Invalid native response")
            candidates = tuple(
                RetrievalCandidate(
                    candidate_key=self.name + ":" + canonical_hash(hit.source.provider_source_id),
                    source=hit.source,
                    mcu_id=mcu_id,
                    evidence_family=family,
                    provider_name=self.name,
                    strategy=strategy,
                    query_id=query_id,
                    local_rank=hit.rank + rank_offset,
                    provider_score=score
                    if isinstance((score := hit.metadata.get("provider_local_score")), int | float)
                    and not isinstance(score, bool)
                    else None,
                    discovered_at=self.runtime.clock(),
                    raw_metadata=deepcopy(hit.metadata),
                    seed_source=seed,
                    cursor=cursor,
                )
                for hit in page.results
            )
            return RetrievalBatch(
                strategy=strategy,
                provider_name=self.name,
                candidates=candidates,
                next_cursor=next_cursor,
                exhausted=next_cursor is None,
                call=page.call,
                limitations=limitations,
                calls=tuple(r.call for r in calls),
                compiled_queries=tuple(
                    next(
                        (
                            e.compiled_query
                            for e in reversed(self.retrieval_request_events())
                            if e.call is not None and e.call.request_hash == r.call.request_hash
                        ),
                        q,
                    )
                    for r, q in zip(calls, compiled, strict=True)
                ),
                had_failed_attempts=any(a.failure is not None for r in calls for a in r.attempts),
                complete=not any(
                    n == "Incomplete provider result set" or "window capped" in n
                    for n in limitations
                ),
            )
        except (ValueError, ValidationError):
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Invalid native retrieval response",
                query_id,
                page.call,
            ) from None
