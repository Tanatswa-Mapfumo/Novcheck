import re
from datetime import date

from pydantic import Field, JsonValue

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.ids import MCUId
from novelty_harness.ports.models import SearchPage, SearchQuery, SourceRef
from novelty_harness.providers._base import validate_wire
from novelty_harness.providers._retrieval import NativeRequests
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult
from novelty_harness.providers.openalex import OpenAlexProvider, Work
from novelty_harness.providers.registry import ProviderDescriptor
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery
from novelty_harness.research.retrieval.executor import RetrievalExecutor
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCapabilities,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class ExpansionWork(Work):
    referenced_works: list[str] = Field(default_factory=list[str])
    related_works: list[str] = Field(default_factory=list[str])


def work_id(source: SourceRef) -> str:
    raw = source.provider_source_id.removeprefix("https://openalex.org/")
    if source.provider_name != "openalex" or re.fullmatch(r"W\d+", raw) is None:
        raise provider_error(
            "openalex", FailureCategory.BAD_REQUEST, "Invalid OpenAlex work identity"
        )
    return raw


class OpenAlexRetrievalProvider(OpenAlexProvider, NativeRequests):
    descriptor = ProviderDescriptor.model_validate(
        {
            **OpenAlexProvider.descriptor.model_dump(),
            "supports_citations": True,
            "search_capabilities": frozenset(
                {
                    "works-text",
                    "publication-cutoff",
                    "semantic",
                    "references",
                    "citations",
                    "related-works",
                }
            ),
        }
    )

    async def retrieval_capabilities(self) -> RetrievalCapabilities:
        return RetrievalCapabilities(
            strategies=frozenset(
                s for s in RetrievalStrategy if s != RetrievalStrategy.ENTITY_LINEAGE
            ),
            paginated_strategies=frozenset(
                s
                for s in RetrievalStrategy
                if s not in {RetrievalStrategy.SEMANTIC, RetrievalStrategy.ENTITY_LINEAGE}
            ),
            semantic_query_chars=2000,
            semantic_max_results=50,
            max_requests_per_action=2,
            limitations=(
                "Semantic mode: 1 request/second, 50 results maximum; no cursor continuation",
            ),
        )

    async def retrieve(
        self,
        *,
        intent: SearchIntent,
        strategy: RetrievalStrategy,
        as_of: date,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch:
        strategy = RetrievalStrategy(strategy)
        if strategy != RetrievalStrategy.SEMANTIC:
            return await RetrievalExecutor(
                as_of=as_of, compiler=self.compiler, clock=self.runtime.clock
            ).execute_intent(
                intent=intent,
                provider=self,
                strategy=strategy,
                cursor=cursor,
                rank_offset=rank_offset,
            )
        if (
            len(intent.text) > 2000
            or cursor is not None
            or intent.filters
            or intent.evidence_family != EvidenceFamily.SCHOLARLY
        ):
            raise provider_error(
                self.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Semantic mode requires <=2000 characters and no cursor/extra filters",
                intent.query_id,
            )
        compiled = CompiledProviderQuery(
            query_id=intent.query_id,
            provider_name=self.name,
            evidence_family=intent.evidence_family,
            endpoint="https://api.openalex.org/works",
            method="GET",
            params={
                "search.semantic": intent.text,
                "per_page": 50,
                "filter": "to_publication_date:" + as_of.isoformat(),
            },
            compilation_notes=("Native semantic search, distinct from lexical search",),
        )
        result = await self.native_request(compiled, interval=1)
        data = self.runtime.parse_json(result, provider=self.name, query_id=intent.query_id)
        query = SearchQuery(
            query_id=intent.query_id,
            text=intent.text,
            purpose=intent.rationale,
            evidence_family=intent.evidence_family,
        )
        page, notes = self.parse(data, result, query, date.max)
        if len(page.results) > 50:
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Semantic result cap violated",
                intent.query_id,
                result.call,
            )
        return self.native_batch(
            page=page,
            strategy=strategy,
            family=intent.evidence_family,
            mcu_id=intent.mcu_id,
            query_id=intent.query_id,
            seed=None,
            cursor=None,
            rank_offset=rank_offset,
            calls=(result,),
            compiled=(compiled,),
            limitations=(*notes, "Semantic result cap 50; neighborhood is not exhaustive"),
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
        strategy = RetrievalStrategy(strategy)
        if strategy not in {
            RetrievalStrategy.CITATION_BACKWARD,
            RetrievalStrategy.CITATION_FORWARD,
            RetrievalStrategy.RELATED_WORK,
        }:
            raise provider_error(
                self.name, FailureCategory.CAPABILITY_MISMATCH, "Unsupported OpenAlex expansion"
            )
        identity = work_id(source)
        qid = "qry_expand_" + canonical_hash([identity, strategy, mcu_id])[:20]
        compiled: list[CompiledProviderQuery] = []
        calls: list[HTTPResult] = []
        next_cursor = None
        if strategy == RetrievalStrategy.CITATION_FORWARD:
            params: dict[str, JsonValue] = {
                "filter": "cites:" + identity + ",to_publication_date:" + as_of.isoformat(),
                "per_page": 25,
                "cursor": cursor or "*",
            }
        else:
            if cursor is not None and not cursor.isdecimal():
                raise provider_error(
                    self.name, FailureCategory.BAD_REQUEST, "Invalid expansion offset", qid
                )
            metadata = CompiledProviderQuery(
                query_id=qid,
                provider_name=self.name,
                evidence_family=EvidenceFamily.SCHOLARLY,
                endpoint="https://api.openalex.org/works/" + identity,
                method="GET",
            )
            result = await self.native_request(metadata)
            compiled.append(metadata)
            calls.append(result)
            data = self.runtime.parse_json(result, provider=self.name, query_id=qid)
            work = validate_wire(
                ExpansionWork, data, provider=self.name, query_id=qid, result=result
            )
            if work_id(SourceRef(provider_name=self.name, provider_source_id=work.id)) != identity:
                raise provider_error(
                    self.name,
                    FailureCategory.PARSE_FAILURE,
                    "Seed metadata identity mismatch",
                    qid,
                    result.call,
                )
            ids = (
                work.referenced_works
                if strategy == RetrievalStrategy.CITATION_BACKWARD
                else work.related_works
            )
            ids = list(
                dict.fromkeys(
                    work_id(SourceRef(provider_name=self.name, provider_source_id=i)) for i in ids
                )
            )
            offset = int(cursor or "0")
            selected = ids[offset : offset + 100]
            if not selected:
                return self.native_batch(
                    page=SearchPage(results=[], call=result.call),
                    strategy=strategy,
                    family=EvidenceFamily.SCHOLARLY,
                    mcu_id=mcu_id,
                    query_id=None,
                    seed=source,
                    cursor=cursor,
                    rank_offset=rank_offset,
                    calls=tuple(calls),
                    compiled=tuple(compiled),
                    limitations=(
                        "Provider-matched graph only; missing references remain outside access",
                    ),
                )
            next_cursor = str(offset + 100) if offset + 100 < len(ids) else None
            params = {
                "filter": "openalex:"
                + "|".join(selected)
                + ",to_publication_date:"
                + as_of.isoformat(),
                "per_page": 100,
            }
        request = CompiledProviderQuery(
            query_id=qid,
            provider_name=self.name,
            evidence_family=EvidenceFamily.SCHOLARLY,
            endpoint="https://api.openalex.org/works",
            method="GET",
            params=params,
        )
        result = await self.native_request(request)
        calls.append(result)
        compiled.append(request)
        data = self.runtime.parse_json(result, provider=self.name, query_id=qid)
        page, notes = self.parse(
            data,
            result,
            SearchQuery(
                query_id=qid, text="", purpose=strategy, evidence_family=EvidenceFamily.SCHOLARLY
            ),
            date.max,
        )
        if strategy == RetrievalStrategy.CITATION_FORWARD:
            next_cursor = page.next_cursor if page.results else None
        return self.native_batch(
            page=page,
            strategy=strategy,
            family=EvidenceFamily.SCHOLARLY,
            mcu_id=mcu_id,
            query_id=None,
            seed=source,
            cursor=cursor,
            rank_offset=rank_offset,
            calls=tuple(calls),
            compiled=tuple(compiled),
            next_cursor=next_cursor,
            limitations=(
                *notes,
                "Provider-matched graph only; missing references remain outside access",
            ),
        )
