import re
from datetime import date
from urllib.parse import quote

from pydantic import Field, FiniteFloat, JsonValue

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.ports.models import SearchPage, SearchQuery, SearchResult, SourceRef
from novelty_harness.providers._base import WireModel, validate_wire
from novelty_harness.providers._retrieval import NativeRequests
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult
from novelty_harness.providers.registry import ProviderDescriptor
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery
from novelty_harness.research.retrieval.executor import strategy_for
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCapabilities,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,title,url,externalIds,abstract,year,publicationDate,authors,embedding.specter_v2"
TEXT_STRATEGIES = frozenset(
    {
        RetrievalStrategy.LEXICAL,
        RetrievalStrategy.RELATIONAL,
        RetrievalStrategy.HISTORICAL_TERM,
        RetrievalStrategy.ADJACENT_DOMAIN,
    }
)


class SemanticScholarCompiler:
    def compile(self, intent: SearchIntent, *, as_of: date) -> CompiledProviderQuery:
        if (
            intent.evidence_family != EvidenceFamily.SCHOLARLY
            or intent.filters
            or re.search(r"\b(?:AND|OR|NOT)\b|\bNEAR/", intent.text)
        ):
            raise provider_error(
                "semantic_scholar",
                FailureCategory.CAPABILITY_MISMATCH,
                "Relevance search does not implement Boolean or extra filters",
                intent.query_id,
            )
        return CompiledProviderQuery(
            query_id=intent.query_id,
            provider_name="semantic_scholar",
            evidence_family=intent.evidence_family,
            endpoint=BASE + "/paper/search",
            method="GET",
            params={"query": intent.text, "offset": 0, "limit": 25, "fields": FIELDS},
            compilation_notes=(
                "Cutoff checked against provisional metadata locally; "
                "unknown dates remain uncertain",
            ),
        )


class Author(WireModel):
    authorId: NonBlankText | None = None
    name: str | None = None


class Paper(WireModel):
    paperId: str = Field(pattern=r"^[a-fA-F0-9]{40}$")
    title: str | None = None
    url: str | None = None
    externalIds: dict[str, JsonValue] = Field(default_factory=lambda: dict[str, JsonValue]())
    publicationDate: str | None = None
    year: int | None = None
    authors: list[Author] = Field(default_factory=list[Author])
    abstract: str | None = None
    embedding: dict[str, JsonValue] | None = None
    score: FiniteFloat | None = None


class PaperPage(WireModel):
    offset: int = Field(default=0, ge=0)
    next: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    data: list[Paper]


class Edge(WireModel):
    citedPaper: Paper | None = None
    citingPaper: Paper | None = None


class EdgePage(WireModel):
    offset: int = Field(default=0, ge=0)
    next: int | None = Field(default=None, ge=0)
    data: list[Edge]


def paper_identity(source: SourceRef) -> str:
    raw = source.provider_source_id
    if source.provider_name != "semantic_scholar" or not (
        re.fullmatch(r"[a-fA-F0-9]{40}|CorpusId:\d+", raw)
        or re.fullmatch(r"DOI:10\.\d{4,9}/[A-Za-z0-9._;()/:-]+", raw)
    ):
        raise provider_error(
            "semantic_scholar", FailureCategory.BAD_REQUEST, "Invalid scholarly paper identity"
        )
    return quote(raw, safe="")


class SemanticScholarProvider(NativeRequests):
    name = "semantic_scholar"
    compiler = SemanticScholarCompiler()
    descriptor = ProviderDescriptor(
        name=name,
        evidence_families=frozenset({EvidenceFamily.SCHOLARLY}),
        search_capabilities=frozenset(
            {"relevance", "metadata", "references", "citations", "author-papers"}
        ),
        auth_mode="optional-x-api-key",
        supports_pagination=True,
        supports_citations=True,
    )

    def headers(self) -> dict[str, str]:
        headers = {"User-Agent": "novcheck/0.1", "Accept": "application/json"}
        key = self.credential.resolve() if self.credential else None
        if key:
            headers["x-api-key"] = key
        return headers

    def min_interval(self) -> float:
        return 1

    def apply_cursor(self, params: dict[str, str | int | float | bool], cursor: str | None) -> None:
        if cursor is not None and (
            not cursor.isdecimal() or len(cursor) > 4 or int(cursor) >= 1000
        ):
            raise provider_error(
                self.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Relevance window is limited to 1000 results",
            )
        params["offset"] = int(cursor or "0")

    async def retrieval_capabilities(self) -> RetrievalCapabilities:
        strategies = TEXT_STRATEGIES | {
            RetrievalStrategy.CITATION_BACKWARD,
            RetrievalStrategy.CITATION_FORWARD,
            RetrievalStrategy.ENTITY_LINEAGE,
        }
        return RetrievalCapabilities(
            strategies=strategies,
            paginated_strategies=strategies,
            max_requests_per_action=2,
            limitations=(
                "Relevance window at most 1000; embeddings are local features, "
                "not semantic-query capability",
            ),
        )

    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]:
        page = validate_wire(
            PaperPage, data, provider=self.name, query_id=query.query_id, result=result
        )
        return self.paper_page(page, result, cutoff, relevance=True)

    def paper_page(
        self,
        page: PaperPage,
        result: HTTPResult,
        cutoff: date,
        *,
        relevance: bool = False,
        wire_ranks: tuple[int, ...] | None = None,
    ) -> tuple[SearchPage, tuple[str, ...]]:
        hits: list[SearchResult] = []
        notes: list[str] = []
        for rank, paper in enumerate(page.data, 1):
            if wire_ranks is not None:
                rank = wire_ranks[rank - 1]
            published = None
            if paper.publicationDate:
                try:
                    published = date.fromisoformat(paper.publicationDate)
                except ValueError:
                    notes.append("Invalid publication date; chronology unresolved")
            if published is not None and published > cutoff:
                notes.append("Post-cutoff record omitted from screening")
                continue
            if published is None:
                notes.append("Publication chronology incomplete or unavailable")
                if paper.year is not None and paper.year > cutoff.year:
                    continue
            hits.append(
                SearchResult(
                    source=SourceRef(
                        provider_name=self.name,
                        provider_source_id=paper.paperId,
                        title=paper.title,
                        canonical_url=paper.url,
                    ),
                    rank=rank,
                    snippet=paper.abstract,
                    metadata={**paper.model_dump(mode="json"), "provider_local_score": paper.score},
                )
            )
        next_offset = page.next
        if relevance and next_offset is not None and next_offset >= 1000:
            next_offset = None
            notes.append("Provider relevance window capped; not exhaustive")
        if next_offset is not None and next_offset <= page.offset:
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Non-advancing provider offset",
                call=result.call,
            )
        return SearchPage(
            results=hits,
            next_cursor=str(next_offset) if next_offset is not None else None,
            call=result.call,
        ), tuple(notes)

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
        if strategy not in TEXT_STRATEGIES or strategy != strategy_for(intent):
            raise provider_error(
                self.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Unsupported native search strategy",
                intent.query_id,
            )
        compiled = self.compiler.compile(intent, as_of=as_of)
        params = dict(compiled.params)
        scalar: dict[str, str | int | float | bool] = {}
        self.apply_cursor(scalar, cursor)
        params.update(scalar)
        compiled = CompiledProviderQuery.model_validate({**compiled.model_dump(), "params": params})
        result = await self.native_request(compiled)
        data = self.runtime.parse_json(result, provider=self.name, query_id=intent.query_id)
        wire = validate_wire(
            PaperPage, data, provider=self.name, query_id=intent.query_id, result=result
        )
        page, notes = self.paper_page(wire, result, date.max, relevance=True)
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
            limitations=notes,
        )

    async def paper_metadata(self, source: SourceRef) -> dict[str, JsonValue]:
        paper, _result, _request = await self._metadata(source)
        return paper.model_dump(mode="json")

    async def _metadata(self, source: SourceRef) -> tuple[Paper, HTTPResult, CompiledProviderQuery]:
        request = CompiledProviderQuery(
            query_id="qry_metadata_" + canonical_hash(source.model_dump(mode="json"))[:20],
            provider_name=self.name,
            evidence_family=EvidenceFamily.SCHOLARLY,
            endpoint=BASE + "/paper/" + paper_identity(source),
            method="GET",
            params={"fields": FIELDS},
        )
        result = await self.native_request(request)
        paper = validate_wire(
            Paper,
            self.runtime.parse_json(result, provider=self.name, query_id=request.query_id),
            provider=self.name,
            query_id=request.query_id,
            result=result,
        )
        if (
            re.fullmatch(r"[a-fA-F0-9]{40}", source.provider_source_id)
            and paper.paperId.casefold() != source.provider_source_id.casefold()
        ):
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Paper metadata identity mismatch",
                request.query_id,
                result.call,
            )
        return paper, result, request

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
        identity = paper_identity(source)
        if strategy not in {
            RetrievalStrategy.CITATION_BACKWARD,
            RetrievalStrategy.CITATION_FORWARD,
            RetrievalStrategy.ENTITY_LINEAGE,
        }:
            raise provider_error(
                self.name, FailureCategory.CAPABILITY_MISMATCH, "Unsupported scholarly expansion"
            )
        qid = (
            "qry_expand_" + canonical_hash([source.model_dump(mode="json"), strategy, mcu_id])[:20]
        )
        compiled: list[CompiledProviderQuery] = []
        calls: list[HTTPResult] = []
        next_author: int | None = None
        if strategy == RetrievalStrategy.ENTITY_LINEAGE:
            paper, metadata_result, metadata_request = await self._metadata(source)
            calls.append(metadata_result)
            compiled.append(metadata_request)
            authors = list(
                dict.fromkeys(a.authorId for a in paper.authors if a.authorId is not None)
            )
            pieces = (cursor or "0:0").split(":")
            if len(pieces) != 2 or not all(p.isdecimal() and len(p) <= 8 for p in pieces):
                raise provider_error(
                    self.name, FailureCategory.BAD_REQUEST, "Invalid author traversal cursor", qid
                )
            index, offset = map(int, pieces)
            if index >= len(authors):
                return self.native_batch(
                    page=SearchPage(results=[], call=metadata_result.call),
                    strategy=strategy,
                    family=EvidenceFamily.SCHOLARLY,
                    mcu_id=mcu_id,
                    query_id=None,
                    seed=source,
                    cursor=cursor,
                    rank_offset=rank_offset,
                    calls=tuple(calls),
                    compiled=tuple(compiled),
                    limitations=("No matched authors available",),
                )
            author = authors[index]
            if not author.isdecimal():
                raise provider_error(
                    self.name,
                    FailureCategory.PARSE_FAILURE,
                    "Invalid author identity",
                    qid,
                    metadata_result.call,
                )
            path = "/author/" + author + "/papers"
            next_author = index + 1 if index + 1 < len(authors) else None
        else:
            if cursor is not None and (not cursor.isdecimal() or len(cursor) > 8):
                raise provider_error(
                    self.name, FailureCategory.BAD_REQUEST, "Invalid citation offset", qid
                )
            offset = int(cursor or "0")
            index = 0
            path = (
                "/paper/"
                + identity
                + (
                    "/references"
                    if strategy == RetrievalStrategy.CITATION_BACKWARD
                    else "/citations"
                )
            )
        request = CompiledProviderQuery(
            query_id=qid,
            provider_name=self.name,
            evidence_family=EvidenceFamily.SCHOLARLY,
            endpoint=BASE + path,
            method="GET",
            params={"offset": offset, "limit": 25, "fields": FIELDS},
        )
        result = await self.native_request(request)
        calls.append(result)
        compiled.append(request)
        data = self.runtime.parse_json(result, provider=self.name, query_id=qid)
        wire_ranks = None
        missing_edges = False
        if strategy == RetrievalStrategy.ENTITY_LINEAGE:
            wire = validate_wire(PaperPage, data, provider=self.name, query_id=qid, result=result)
            rank_span = len(wire.data)
        else:
            edges = validate_wire(EdgePage, data, provider=self.name, query_id=qid, result=result)
            papers = [
                e.citedPaper if strategy == RetrievalStrategy.CITATION_BACKWARD else e.citingPaper
                for e in edges.data
            ]
            rank_span = len(papers)
            wire_ranks = tuple(i for i, paper in enumerate(papers, 1) if paper is not None)
            missing_edges = any(paper is None for paper in papers)
            wire = PaperPage(
                offset=edges.offset, next=edges.next, data=[p for p in papers if p is not None]
            )
        page, notes = self.paper_page(wire, result, date.max, wire_ranks=wire_ranks)
        if missing_edges:
            notes = (*notes, "Incomplete provider result set", "Unavailable citation edges")
        next_cursor = page.next_cursor
        if strategy == RetrievalStrategy.ENTITY_LINEAGE:
            next_cursor = (
                f"{index}:{next_cursor}"
                if next_cursor is not None
                else f"{next_author}:0"
                if next_author is not None
                else None
            )
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
            rank_span=rank_span,
            limitations=(
                *notes,
                "Matched graph only; missing/deleted paper edges remain an access limitation",
            ),
        )
