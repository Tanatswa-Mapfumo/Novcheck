from collections.abc import Callable
from copy import deepcopy
from datetime import date, datetime

from pydantic import ValidationError

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import TraceStatus
from novelty_harness.ports.models import SearchPage, SearchQuery
from novelty_harness.ports.search import SearchProvider
from novelty_harness.ports.search_audit import SearchAuditSource
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import ProviderQueryCompiler, compile_intent
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCandidate,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


def strategy_for(intent: SearchIntent) -> RetrievalStrategy:
    return {
        QueryFamily.RELATIONSHIP: RetrievalStrategy.RELATIONAL,
        QueryFamily.HISTORICAL_TERMINOLOGY: RetrievalStrategy.HISTORICAL_TERM,
        QueryFamily.ADJACENT_DOMAIN: RetrievalStrategy.ADJACENT_DOMAIN,
    }.get(intent.query_family, RetrievalStrategy.LEXICAL)


class RetrievalExecutor:
    def __init__(
        self,
        *,
        as_of: date,
        compiler: ProviderQueryCompiler,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.as_of, self.compiler, self.clock = as_of, compiler, clock

    async def execute_intent(
        self,
        *,
        intent: SearchIntent,
        provider: SearchProvider,
        strategy: RetrievalStrategy,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch:
        strategy = RetrievalStrategy(strategy)
        if strategy != strategy_for(intent) or rank_offset < 0:
            raise provider_error(
                provider.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Text execution cannot relabel retrieval intent",
                intent.query_id,
            )
        compiled = compile_intent(self.compiler, intent, as_of=self.as_of)
        if compiled.provider_name != provider.name:
            raise provider_error(
                provider.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Compiler targets a different provider",
                intent.query_id,
            )
        capability = await provider.capabilities()
        if intent.evidence_family not in capability.evidence_families or (
            cursor is not None and not capability.supports_pagination
        ):
            raise provider_error(
                provider.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Unsupported family or pagination",
                intent.query_id,
            )
        returned = await provider.search(
            SearchQuery(
                query_id=intent.query_id,
                text=intent.text,
                purpose=intent.rationale,
                evidence_family=intent.evidence_family,
                filters={**intent.filters, "as_of": self.as_of.isoformat()},
            ),
            cursor=cursor,
        )
        try:
            page = SearchPage.model_validate(returned.model_dump())
            if page.call.provider_name != provider.name or page.call.status != TraceStatus.SUCCESS:
                raise ValueError("Unsuccessful or mismatched provider response")
            candidates = tuple(
                RetrievalCandidate(
                    candidate_key=provider.name
                    + ":"
                    + canonical_hash(hit.source.provider_source_id),
                    source=hit.source.model_copy(deep=True),
                    mcu_id=intent.mcu_id,
                    evidence_family=intent.evidence_family,
                    provider_name=provider.name,
                    strategy=strategy,
                    query_id=intent.query_id,
                    local_rank=hit.rank + rank_offset,
                    provider_score=score
                    if isinstance((score := hit.metadata.get("provider_local_score")), int | float)
                    and not isinstance(score, bool)
                    else None,
                    discovered_at=self.clock(),
                    raw_metadata=deepcopy(hit.metadata),
                    cursor=cursor,
                )
                for hit in page.results
            )
            diagnostics = (
                provider.screening_diagnostics(intent.query_id)
                if isinstance(provider, SearchAuditSource)
                else None
            )
            exhausted = not candidates or page.next_cursor is None
            return RetrievalBatch(
                strategy=strategy,
                provider_name=provider.name,
                candidates=candidates,
                next_cursor=None if exhausted else page.next_cursor,
                exhausted=exhausted,
                call=page.call,
                limitations=diagnostics.limitations if diagnostics else (),
            )
        except (ValueError, ValidationError):
            raise provider_error(
                provider.name,
                FailureCategory.PARSE_FAILURE,
                "Invalid retrieval response identity or rank",
                intent.query_id,
                returned.call,
            ) from None
