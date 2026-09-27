import re
from datetime import date
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, JsonValue

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.ports.models import SearchPage, SearchQuery, SearchResult, SourceRef
from novelty_harness.providers._base import WireModel, validate_wire
from novelty_harness.providers._retrieval import NativeRequests
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.github import GitHubProvider, Repository
from novelty_harness.providers.http import HTTPResult
from novelty_harness.providers.registry import ProviderDescriptor
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCapabilities,
    RetrievalStrategy,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class Owner(WireModel):
    id: int = Field(gt=0)
    login: NonBlankText
    type: str


class RichRepository(Repository):
    owner: Owner | None = None
    pushed_at: str | None = None


class RichRepositories(WireModel):
    total_count: int = Field(ge=0)
    incomplete_results: bool
    items: list[RichRepository]


class RepoList(WireModel):
    items: list[RichRepository]


def next_page(result: HTTPResult, path: str) -> str | None:
    link = result.response.links.get("next", {}).get("url")
    if not link:
        return None
    parts = urlsplit(link)
    page = parse_qs(parts.query).get("page", [""])[0]
    current = int(result.response.request.url.params.get("page", "1"))
    if (
        parts.scheme != "https"
        or parts.netloc != "api.github.com"
        or parts.path != path
        or not page.isdecimal()
        or len(page) > 8
        or int(page) <= current
    ):
        raise provider_error(
            "github",
            FailureCategory.PARSE_FAILURE,
            "Unsafe or non-advancing pagination link",
            call=result.call,
        )
    return page


class GitHubRetrievalProvider(GitHubProvider, NativeRequests):
    descriptor = ProviderDescriptor.model_validate(
        {
            **GitHubProvider.descriptor.model_dump(),
            "search_capabilities": GitHubProvider.descriptor.search_capabilities
            | {"owner-org-lineage"},
        }
    )

    async def retrieval_capabilities(self) -> RetrievalCapabilities:
        strategies = frozenset(
            {
                RetrievalStrategy.LEXICAL,
                RetrievalStrategy.RELATIONAL,
                RetrievalStrategy.HISTORICAL_TERM,
                RetrievalStrategy.ADJACENT_DOMAIN,
                RetrievalStrategy.ENTITY_LINEAGE,
            }
        )
        return RetrievalCapabilities(
            strategies=strategies,
            paginated_strategies=strategies,
            max_requests_per_action=2,
            limitations=(
                "Repository search window <=1000; owner/org public metadata only, not code/history",
            ),
        )

    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]:
        wire = validate_wire(
            RichRepositories, data, provider=self.name, query_id=query.query_id, result=result
        )
        page, notes = super().parse(data, result, query, cutoff)
        by_id = {str(r.id): r for r in wire.items}
        for hit in page.results:
            repo = by_id[hit.source.provider_source_id]
            hit.metadata.update(
                {
                    "owner": repo.owner.model_dump(mode="json") if repo.owner else None,
                    "full_name": repo.full_name,
                    "pushed_at": repo.pushed_at,
                }
            )
        page.next_cursor = next_page(result, "/search/repositories")
        if page.next_cursor is not None and int(page.next_cursor) > 40:
            page.next_cursor = None
            notes = (*notes, "Provider search window capped; not exhaustive")
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
        strategy = RetrievalStrategy(strategy)
        if strategy != RetrievalStrategy.ENTITY_LINEAGE:
            raise provider_error(
                self.name,
                FailureCategory.CAPABILITY_MISMATCH,
                "Only explicit repository owner/org expansion supported",
            )
        if (
            source.provider_name != self.name
            or not source.provider_source_id.isdecimal()
            or len(source.provider_source_id) > 20
        ):
            raise provider_error(
                self.name, FailureCategory.BAD_REQUEST, "Invalid repository identity"
            )
        if cursor is not None and (not cursor.isdecimal() or len(cursor) > 8 or int(cursor) < 1):
            raise provider_error(
                self.name, FailureCategory.BAD_REQUEST, "Invalid owner repository page"
            )
        qid = "qry_entity_" + canonical_hash([source.model_dump(mode="json"), mcu_id])[:20]
        metadata = CompiledProviderQuery(
            query_id=qid,
            provider_name=self.name,
            evidence_family=EvidenceFamily.SOFTWARE,
            endpoint="https://api.github.com/repositories/" + source.provider_source_id,
            method="GET",
        )
        result = await self.native_request(metadata)
        seed = validate_wire(
            RichRepository,
            self.runtime.parse_json(result, provider=self.name, query_id=qid),
            provider=self.name,
            query_id=qid,
            result=result,
        )
        if str(seed.id) != source.provider_source_id:
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Seed repository identity mismatch",
                qid,
                result.call,
            )
        owner = seed.owner
        if (
            owner is None
            or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner.login) is None
            or owner.type not in {"User", "Organization"}
        ):
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Owner identity unavailable or unsafe",
                qid,
                result.call,
            )
        path = ("/orgs/" if owner.type == "Organization" else "/users/") + owner.login + "/repos"
        request = CompiledProviderQuery(
            query_id=qid,
            provider_name=self.name,
            evidence_family=EvidenceFamily.SOFTWARE,
            endpoint="https://api.github.com" + path,
            method="GET",
            params={
                "page": int(cursor or "1"),
                "per_page": 25,
                "type": "public" if owner.type == "Organization" else "owner",
            },
        )
        listing = await self.native_request(request, interval=1)
        repos = validate_wire(
            RepoList,
            {"items": self.runtime.parse_json(listing, provider=self.name, query_id=qid)},
            provider=self.name,
            query_id=qid,
            result=listing,
        )
        page = SearchPage(
            results=[
                SearchResult(
                    source=SourceRef(
                        provider_name=self.name,
                        provider_source_id=str(r.id),
                        title=r.full_name,
                        canonical_url=r.html_url,
                    ),
                    rank=i,
                    snippet=r.description,
                    metadata={**r.model_dump(mode="json"), "provider_local_score": r.score},
                )
                for i, r in enumerate(repos.items, 1)
            ],
            call=listing.call,
        )
        return self.native_batch(
            page=page,
            strategy=strategy,
            family=EvidenceFamily.SOFTWARE,
            mcu_id=mcu_id,
            query_id=None,
            seed=source,
            cursor=cursor,
            rank_offset=rank_offset,
            calls=(result, listing),
            compiled=(metadata, request),
            next_cursor=next_page(listing, path),
            limitations=("Current repository/owner metadata is not verified historical content",),
        )
