from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.providers.crossref_pagination import CrossrefRetrievalProvider
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.github_expansion import GitHubRetrievalProvider
from novelty_harness.providers.http import HTTPRuntime, RetryPolicy
from tests.unit.providers.test_crossref import response as crossref_response
from tests.unit.providers.test_github import response as github_response
from tests.unit.providers.test_openalex import no_sleep
from tests.unit.research.test_strategist import build


async def test_crossref_deeper_cursor_preserves_all_parameters_then_short_page_exhausts():
    requests = []

    def respond(request):
        requests.append(request)
        data = crossref_response()
        if len(requests) == 1:
            data["message"]["items"] = [
                {**data["message"]["items"][0], "DOI": f"10.1234/item{i}"} for i in range(25)
            ]
            data["message"]["next-cursor"] = "opaque:+cursor"
        else:
            data["message"]["next-cursor"] = "still-present"
        return httpx.Response(200, json=data)

    intent = (await build())[0].intents[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = CrossrefRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep))
        first = await provider.retrieve(intent=intent, strategy="LEXICAL", as_of=date(2026, 9, 26))
        second = await provider.retrieve(
            intent=intent,
            strategy="LEXICAL",
            as_of=date(2026, 9, 26),
            cursor=first.next_cursor,
            rank_offset=25,
        )
    assert first.next_cursor == "opaque:+cursor" and not first.exhausted
    assert second.next_cursor is None and second.exhausted and second.candidates[0].local_rank == 26
    assert (
        requests[0].url.params["query.bibliographic"]
        == requests[1].url.params["query.bibliographic"]
    )
    assert requests[1].url.params["cursor"] == "opaque:+cursor"
    assert second.compiled_queries[0].params["cursor"] == "opaque:+cursor"
    assert second.candidates[0].raw_metadata["date_parts"]["published"]


async def test_github_deeper_search_retains_owner_and_respects_next_page():
    requests = []

    def respond(request):
        requests.append(request)
        data = github_response()
        data["items"][0]["owner"] = {"id": 99, "login": "example", "type": "Organization"}
        return httpx.Response(
            200,
            json=data,
            headers={"Link": '<https://api.github.com/search/repositories?page=3>; rel="next"'},
        )

    intent = next(q for q in (await build())[0].intents if q.evidence_family.value == "SOFTWARE")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        batch = await GitHubRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)).retrieve(
            intent=intent, strategy="LEXICAL", as_of=date(2026, 9, 26), cursor="2", rank_offset=25
        )
    assert batch.next_cursor == "3" and batch.candidates[0].local_rank == 26
    assert batch.candidates[0].raw_metadata["owner"]["login"] == "example"
    assert requests[0].url.params["page"] == "2"


@pytest.mark.parametrize(
    "owner_type,path", [("User", "/users/example/repos"), ("Organization", "/orgs/example/repos")]
)
async def test_explicit_owner_or_org_lineage_is_not_repository_search(owner_type, path):
    requests = []

    def respond(request):
        requests.append(request)
        repo = github_response()["items"][0]
        repo["owner"] = {"id": 99, "login": "example", "type": owner_type}
        return httpx.Response(200, json=repo if request.url.path == "/repositories/123" else [repo])

    seed = SourceRef(provider_name="github", provider_source_id="123")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        batch = await GitHubRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)).expand(
            source=seed, strategy="ENTITY_LINEAGE", as_of=date(2026, 9, 26)
        )
    assert requests[-1].url.path == path and batch.candidates[0].seed_source == seed
    assert batch.strategy.value == "ENTITY_LINEAGE" and len(batch.calls) == 2
    assert "q" not in requests[-1].url.params


async def test_blocked_github_has_no_silent_general_web_fallback():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ProviderError):
            await GitHubRetrievalProvider(HTTPRuntime(client)).expand(
                source=SourceRef(provider_name="github", provider_source_id="123"),
                strategy="ENTITY_LINEAGE",
                as_of=date(2026, 9, 26),
            )
    assert len(requests) == 1 and requests[0].url.host == "api.github.com"


async def test_secondary_rate_limit_without_headers_retains_documented_minimum_cooldown():
    now = datetime(2026, 9, 27, tzinfo=UTC)
    waits = []
    calls = []

    async def sleep(seconds):
        nonlocal now
        waits.append(seconds)
        now += timedelta(seconds=seconds)

    def respond(request):
        calls.append(request)
        return (
            httpx.Response(403, json={"message": "secondary rate limit"})
            if len(calls) == 1
            else httpx.Response(200, json={})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        runtime = HTTPRuntime(
            client, policy=RetryPolicy(max_attempts=1), clock=lambda: now, sleeper=sleep
        )
        with pytest.raises(ProviderError):
            await runtime.request(
                provider="github",
                query_id="qry_first",
                method="GET",
                endpoint="https://api.github.com/search/repositories",
            )
        await runtime.request(
            provider="github",
            query_id="qry_next",
            method="GET",
            endpoint="https://api.github.com/search/repositories",
        )
    assert waits == [60]


async def test_crossref_missing_doi_records_keep_their_own_date_parts():
    data = crossref_response()
    first = data["message"]["items"][0]
    first.pop("DOI")
    second = {**first, "title": ["Different work"], "published": {"date-parts": [[2010, 4, 5]]}}
    data["message"]["items"] = [first, second]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ) as client:
        batch = await CrossrefRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)).retrieve(
            intent=(await build())[0].intents[0], strategy="LEXICAL", as_of=date(2026, 9, 26)
        )
    assert batch.candidates[1].raw_metadata["date_parts"]["published"]["date-parts"] == [
        [2010, 4, 5]
    ]
