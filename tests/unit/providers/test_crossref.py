import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from novelty_harness.providers.crossref import CrossrefCompiler, CrossrefProvider
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.registry import CredentialRef
from novelty_harness.research.models import SearchIntent
from tests.contract.provider_contracts import assert_search_provider_contract
from tests.unit.providers.test_openalex import no_sleep, query
from tests.unit.research.test_search_planning import plan_data


def response():
    return json.loads(
        (Path(__file__).parents[2] / "fixtures/provider_responses/crossref/works.json").read_text()
    )


async def test_crossref_contract_polite_identity_and_rate_headers(monkeypatch):
    monkeypatch.setenv("NOVCHECK_TEST_MAILTO", "private@example.org")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={
                "X-Rate-Limit-Limit": "10",
                "X-Rate-Limit-Interval": "1s",
                "X-Concurrency-Limit": "3",
            },
            json=response(),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        runtime = HTTPRuntime(client, sleeper=no_sleep)
        provider = CrossrefProvider(runtime, mailto=CredentialRef(env_name="NOVCHECK_TEST_MAILTO"))
        await assert_search_provider_contract(provider, query())
        page = await provider.search(query())
        assert page.results[0].source.provider_source_id == "10.1234/control"
        assert requests[0].url.params["mailto"] == "private@example.org"
        assert "query.bibliographic" in requests[0].url.params
        assert runtime.attempts[-1].rate_limit.concurrency == 3
        assert "private@example.org" not in page.model_dump_json() + str(runtime.attempts)


@pytest.mark.parametrize("mode", ["missing", "empty", "malformed", "future", "429", "403"])
async def test_crossref_edge_cases_are_explicit(mode):
    calls = []

    def handle(request):
        calls.append(request)
        if mode in {"429", "403"}:
            return httpx.Response(int(mode), json={})
        data = response()
        if mode == "missing":
            data["message"]["items"][0].pop("DOI")
            data["message"]["items"][0].pop("title")
        if mode == "empty":
            data["message"]["items"] = []
        if mode == "malformed":
            data["message"]["items"][0]["published"] = "nonsense"
        if mode == "future":
            data["message"]["items"][0]["published"]["date-parts"] = [[2027]]
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = CrossrefProvider(HTTPRuntime(client, sleeper=no_sleep))
        if mode in {"429", "403", "malformed"}:
            with pytest.raises(ProviderError):
                await provider.search(query())
        else:
            page = await provider.search(query())
            assert len(page.results) == (1 if mode == "missing" else 0)
            if mode == "missing":
                assert page.results[0].source.title is None
                assert any("DOI" in n for n in provider.limitations(query().query_id))
        assert len(calls) == (3 if mode == "429" else 1)


def test_crossref_rejects_boolean_illusion_and_preserves_neutral_intent():
    intent = SearchIntent.model_validate(plan_data()["intents"][0])
    compiled = CrossrefCompiler().compile(intent, as_of=date(2026, 9, 26))
    assert compiled.params["query.bibliographic"] == intent.text
    assert compiled.compilation_notes
    with pytest.raises(ProviderError) as raised:
        CrossrefCompiler().compile(
            intent.model_copy(update={"text": "sensor AND relay"}), as_of=date(2026, 9, 26)
        )
    assert raised.value.failure.category.value == "CAPABILITY_MISMATCH"
    assert not intent.filters


async def test_unrepresentable_date_parts_are_explicit_chronology_limitations():
    data = response()
    data["message"]["items"][0]["published"]["date-parts"] = [[10**30]]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    ) as client:
        provider = CrossrefProvider(HTTPRuntime(client, sleeper=no_sleep))
        page = await provider.search(query())
        assert page.results[0].metadata["publication_date"] is None
        assert "Invalid publication date; chronology unresolved" in provider.limitations(
            query().query_id
        )
