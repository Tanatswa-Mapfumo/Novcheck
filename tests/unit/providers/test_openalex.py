import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from novelty_harness.ports.models import SearchQuery
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.openalex import OpenAlexCompiler, OpenAlexProvider
from novelty_harness.providers.registry import CredentialRef
from novelty_harness.research.models import SearchIntent
from tests.contract.provider_contracts import assert_search_provider_contract
from tests.unit.research.test_search_planning import plan_data


def response():
    return json.loads(
        (Path(__file__).parents[2] / "fixtures/provider_responses/openalex/works.json").read_text()
    )


def query():
    return SearchQuery(
        query_id="qry_api",
        text="sensor controls relay",
        purpose="screening",
        evidence_family="SCHOLARLY",
        filters={"as_of": "2026-09-26"},
    )


async def no_sleep(seconds):
    pass


async def test_openalex_success_pagination_and_shared_contract(monkeypatch):
    monkeypatch.setenv("NOVCHECK_TEST_KEY", "top-secret")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        runtime = HTTPRuntime(client, sleeper=no_sleep)
        provider = OpenAlexProvider(runtime, credential=CredentialRef(env_name="NOVCHECK_TEST_KEY"))
        await assert_search_provider_contract(provider, query())
        page = await provider.search(query())
        assert page.results[0].metadata["doi"] == "https://doi.org/10.1234/control"
        assert page.results[0].metadata["abstract_available"] is True
        assert page.next_cursor == "next-page"
        assert requests[0].headers["Authorization"] == "Bearer top-secret"
        assert "to_publication_date:2026-09-26" in requests[0].url.params["filter"]
        assert "top-secret" not in str(runtime.attempts) + page.model_dump_json()


@pytest.mark.parametrize("mode", ["empty", "malformed", "future", "429", "500", "400"])
async def test_openalex_explicit_failures_empty_and_cutoff(mode):
    calls = []

    def handle(request):
        calls.append(request)
        if mode in {"429", "500", "400"} and (mode != "500" or len(calls) == 1):
            return httpx.Response(int(mode), headers={"Retry-After": "0"}, json={})
        data = response()
        if mode == "empty":
            data["results"] = []
        if mode == "malformed":
            data = {"results": "wrong"}
        if mode == "future":
            data["results"][0]["publication_date"] = "2027-01-01"
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAlexProvider(HTTPRuntime(client, sleeper=no_sleep))
        if mode in {"429", "400", "malformed"}:
            with pytest.raises(ProviderError) as raised:
                await provider.search(query())
            assert (
                raised.value.failure.category.value
                == {"429": "RATE_LIMITED", "400": "BAD_REQUEST", "malformed": "PARSE_FAILURE"}[mode]
            )
        else:
            page = await provider.search(query())
            assert len(page.results) == (1 if mode == "500" else 0)
        if mode == "500":
            assert len(calls) == 2


def test_openalex_compiler_rejects_unsupported_filters_and_preserves_intent():
    intent = SearchIntent.model_validate(plan_data()["intents"][0])
    assert (
        OpenAlexCompiler().compile(intent, as_of=date(2026, 9, 26)).params["search"] == intent.text
    )
    with pytest.raises(ProviderError):
        OpenAlexCompiler().compile(
            intent.model_copy(update={"filters": {"proximity": 3}}), as_of=date(2026, 9, 26)
        )
