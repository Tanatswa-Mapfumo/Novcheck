from datetime import date

import httpx
import pytest

from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.openalex import OpenAlexCompiler, OpenAlexProvider
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.retrieval.executor import RetrievalExecutor, strategy_for
from tests.unit.providers.test_openalex import no_sleep, response
from tests.unit.research.test_strategist import build


@pytest.mark.parametrize(
    "family,strategy",
    [
        ("DIRECT_CANONICAL", "LEXICAL"),
        ("FUNCTIONAL", "LEXICAL"),
        ("MECHANISM", "LEXICAL"),
        ("RELATIONSHIP", "RELATIONAL"),
        ("HISTORICAL_TERMINOLOGY", "HISTORICAL_TERM"),
        ("ADJACENT_DOMAIN", "ADJACENT_DOMAIN"),
    ],
)
async def test_real_text_execution_retains_perspective_cursor_and_local_metadata(family, strategy):
    plan, _ = await build()
    intent = next(q for q in plan.intents if q.query_family.value == family)
    requests = []

    def respond(request):
        requests.append(request)
        data = response()
        data["meta"]["next_cursor"] = "next"
        data["results"][0]["relevance_score"] = 12.5
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        batch = await RetrievalExecutor(
            as_of=date(2026, 9, 26), compiler=OpenAlexCompiler()
        ).execute_intent(
            intent=intent,
            provider=OpenAlexProvider(HTTPRuntime(client, sleeper=no_sleep)),
            strategy=strategy_for(intent),
            cursor="previous",
        )
    assert batch.strategy.value == strategy
    assert batch.next_cursor == "next" and not batch.exhausted
    c = batch.candidates[0]
    assert c.strategy == batch.strategy and c.query_id == intent.query_id
    assert c.local_rank == 1 and c.provider_score == 12.5
    assert c.raw_metadata["publication_date"] == "2020-01-02"
    assert c.cursor == "previous"
    assert requests[0].url.params["cursor"] == "previous"
    assert requests[0].url.params["filter"] == "to_publication_date:2026-09-26"


async def test_zero_results_are_exhausted_batch_not_novelty():
    intent = (await build())[0].intents[0]
    data = response()
    data["results"] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    ) as client:
        batch = await RetrievalExecutor(
            as_of=date(2026, 9, 26), compiler=OpenAlexCompiler()
        ).execute_intent(
            intent=intent, provider=OpenAlexProvider(HTTPRuntime(client)), strategy="LEXICAL"
        )
    assert not batch.candidates and batch.exhausted and batch.next_cursor is None
    assert "novelty" not in batch.model_dump()


async def test_provider_failure_not_replaced_with_empty_success():
    intent = (await build())[0].intents[0]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401))
    ) as client:
        with pytest.raises(ProviderError) as raised:
            await RetrievalExecutor(
                as_of=date(2026, 9, 26), compiler=OpenAlexCompiler()
            ).execute_intent(
                intent=intent, provider=OpenAlexProvider(HTTPRuntime(client)), strategy="LEXICAL"
            )
    assert raised.value.failure.category.value == "AUTHENTICATION_FAILURE"


async def test_mislabelling_plain_text_as_native_semantic_is_rejected_before_request():
    intent = SearchIntent.model_validate((await build())[0].intents[0].model_dump())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: pytest.fail("must not request"))
    ) as client:
        with pytest.raises(ProviderError) as raised:
            await RetrievalExecutor(
                as_of=date(2026, 9, 26), compiler=OpenAlexCompiler()
            ).execute_intent(
                intent=intent, provider=OpenAlexProvider(HTTPRuntime(client)), strategy="SEMANTIC"
            )
    assert raised.value.failure.category.value == "CAPABILITY_MISMATCH"
