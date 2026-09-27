from copy import deepcopy

from pydantic import ValidationError

from novelty_harness.domain.enums import EvidenceFamily, TraceStatus
from novelty_harness.domain.ids import MCUId, QueryId
from novelty_harness.ports.models import SearchPage, SourceRef
from novelty_harness.providers._base import HTTPSearchAdapter
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult
from novelty_harness.research.provider_queries import CompiledProviderQuery
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCandidate,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class NativeRequests(HTTPSearchAdapter):
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
        return await self.runtime.request(
            provider=self.name,
            query_id=compiled.query_id,
            method=compiled.method,
            endpoint=compiled.endpoint,
            params=self.request_params(params),
            headers=self.headers(),
            min_interval=self.min_interval() if interval is None else interval,
        )

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
                compiled_queries=compiled,
            )
        except (ValueError, ValidationError):
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Invalid native retrieval response",
                query_id,
                page.call,
            ) from None
