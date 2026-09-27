from datetime import date

from pydantic import Field, JsonValue

from novelty_harness.domain.ids import MCUId
from novelty_harness.ports.models import SearchPage, SearchQuery, SourceRef
from novelty_harness.providers._base import WireModel, validate_wire
from novelty_harness.providers._retrieval import NativeRequests
from novelty_harness.providers.crossref import CrossrefProvider, CrossrefWork, DateParts
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCapabilities,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class RichWork(CrossrefWork):
    issued: DateParts | None = None
    created: DateParts | None = None
    deposited: DateParts | None = None
    indexed: DateParts | None = None


class RichMessage(WireModel):
    items: list[RichWork]
    next_cursor: str | None = Field(default=None, alias="next-cursor")


class RichResponse(WireModel):
    status: str
    message: RichMessage


class CrossrefRetrievalProvider(CrossrefProvider, NativeRequests):
    def min_interval(self) -> float:
        return 1 / 3 if self.mailto and self.mailto.resolve() else 1

    async def retrieval_capabilities(self) -> RetrievalCapabilities:
        strategies = frozenset(
            {
                RetrievalStrategy.LEXICAL,
                RetrievalStrategy.RELATIONAL,
                RetrievalStrategy.HISTORICAL_TERM,
                RetrievalStrategy.ADJACENT_DOMAIN,
            }
        )
        return RetrievalCapabilities(
            strategies=strategies,
            paginated_strategies=strategies,
            limitations=(
                "Bibliographic matching only; changing cursor result sets may omit/repeat records",
            ),
        )

    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]:
        wire = validate_wire(
            RichResponse, data, provider=self.name, query_id=query.query_id, result=result
        )
        page, notes = super().parse(data, result, query, cutoff)
        by_id = {
            w.doi
            or "metadata_"
            + canonical_hash(
                CrossrefWork.model_validate(w.model_dump(by_alias=True)).model_dump(mode="json")
            ): w
            for w in wire.message.items
        }
        for hit in page.results:
            work = by_id.get(hit.source.provider_source_id)
            if work:
                full_dates = [
                    date(*parts)
                    for field in (work.published, work.published_print, work.published_online)
                    if field is not None
                    for parts in field.parts
                    if len(parts) == 3
                ]
                # The legacy screening projection pads partial dates; native chronology must not.
                hit.metadata["publication_date"] = (
                    min(full_dates).isoformat() if full_dates else None
                )
                hit.metadata["date_parts"] = {
                    k: v
                    for k, v in work.model_dump(mode="json", by_alias=True).items()
                    if k
                    in {
                        "published",
                        "published-online",
                        "published-print",
                        "issued",
                        "created",
                        "deposited",
                        "indexed",
                    }
                }
        requested = result.response.request.url.params.get("rows", "25")
        if len(wire.message.items) < int(requested):
            page.next_cursor = None
        return page, notes

    async def retrieve(
        self,
        *,
        intent: SearchIntent,
        strategy: RetrievalStrategy,
        as_of: date,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch:
        return await self.text_retrieve(
            intent=intent, strategy=strategy, as_of=as_of, cursor=cursor, rank_offset=rank_offset
        )

    async def expand(
        self,
        *,
        source: SourceRef,
        strategy: RetrievalStrategy,
        as_of: date,
        mcu_id: MCUId | None = None,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch:
        raise provider_error(
            self.name,
            FailureCategory.CAPABILITY_MISMATCH,
            "Crossref has no native citation/entity expansion",
        )
