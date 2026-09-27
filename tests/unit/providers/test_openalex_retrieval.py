from datetime import date

import httpx
import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.openalex_semantic import OpenAlexRetrievalProvider
from novelty_harness.research.retrieval.models import RetrievalBatch, RetrievalStrategy
from tests.contract.provider_contracts import assert_search_provider_contract
from tests.unit.providers.test_openalex import no_sleep, query, response
from tests.unit.research.test_strategist import build


async def test_native_semantic_request_is_not_lexical_and_capabilities_are_explicit():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    intent = (await build())[0].intents[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep))
        await assert_search_provider_contract(provider, query())
        batch = await provider.retrieve(intent=intent, strategy="SEMANTIC", as_of=date(2026, 9, 26))
        caps = await provider.retrieval_capabilities()
    params = requests[-1].url.params
    assert params["search.semantic"] == intent.text and "search" not in params
    assert params["per_page"] == "50" and "cursor" not in params
    assert batch.strategy == RetrievalStrategy.SEMANTIC and batch.next_cursor is None
    assert "Semantic result cap 50; neighborhood is not exhaustive" in batch.limitations
    assert caps.semantic_query_chars == 2000 and caps.semantic_max_results == 50
    assert "SEMANTIC" not in caps.paginated_strategies
    assert batch.compiled_queries[-1].params["search.semantic"] == intent.text
    assert RetrievalBatch.model_validate_json(batch.model_dump_json()) == batch


async def test_semantic_uses_supported_year_filter_and_keeps_day_cutoff_provisional():
    from novelty_harness.research.expansion.chronology import assess_temporal, capture_chronology

    def respond(request):
        if request.url.params.get("filter") != "publication_year:<2027":
            return httpx.Response(400, json={"error": "Unsupported semantic date filter"})
        data = response()
        data["results"][0]["publication_date"] = "2026-12-01"
        return httpx.Response(200, json=data)

    intent = (await build())[0].intents[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        batch = await OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)).retrieve(
            intent=intent, strategy="SEMANTIC", as_of=date(2026, 9, 26)
        )
    assert (
        assess_temporal(
            capture_chronology(batch.candidates[0]), as_of=date(2026, 9, 26)
        ).predates_cutoff
        is False
    )
    assert any("exact cutoff" in n for n in batch.limitations)


@pytest.mark.parametrize("length,success", [(2000, True), (2001, False)])
async def test_semantic_length_limit_never_silently_truncates(length, success):
    intent = (await build())[0].intents[0].model_copy(update={"text": "x" * length})
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep))
        if success:
            await provider.retrieve(intent=intent, strategy="SEMANTIC", as_of=date(2026, 9, 26))
            assert len(requests[0].url.params["search.semantic"]) == 2000
        else:
            with pytest.raises(ProviderError) as raised:
                await provider.retrieve(intent=intent, strategy="SEMANTIC", as_of=date(2026, 9, 26))
            assert raised.value.failure.category.value == "CAPABILITY_MISMATCH" and not requests


@pytest.mark.parametrize(
    "strategy,seed_field,filter_prefix",
    [
        ("CITATION_BACKWARD", "referenced_works", "openalex:"),
        ("CITATION_FORWARD", None, "cites:"),
        ("RELATED_WORK", "related_works", "openalex:"),
    ],
)
async def test_citation_directions_and_related_seed_paths(strategy, seed_field, filter_prefix):
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/works/W900":
            data = response()["results"][0]
            data.update(
                id="https://openalex.org/W900",
                referenced_works=["https://openalex.org/W123"],
                related_works=["https://openalex.org/W123"],
            )
            return httpx.Response(200, json=data)
        return httpx.Response(200, json=response())

    seed = SourceRef(provider_name="openalex", provider_source_id="https://openalex.org/W900")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep))
        batch = await provider.expand(
            source=seed, strategy=strategy, as_of=date(2026, 9, 26), mcu_id="mcu_control"
        )
    assert len(requests) == (2 if seed_field else 1)
    assert requests[-1].url.params["filter"].startswith(filter_prefix)
    assert "to_publication_date:2026-09-26" in requests[-1].url.params["filter"]
    assert batch.candidates[0].seed_source == seed
    assert batch.candidates[0].strategy.value == strategy
    assert len(batch.calls) == len(requests) == len(batch.compiled_queries)
    assert batch.candidates[0].raw_metadata["publication_date"] == "2020-01-02"


async def test_forward_citation_cursor_preserves_direction_not_text_search():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    seed = SourceRef(provider_name="openalex", provider_source_id="W900")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        batch = await OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)).expand(
            source=seed,
            strategy="CITATION_FORWARD",
            as_of=date(2026, 9, 26),
            cursor="second",
            rank_offset=25,
        )
    assert requests[0].url.params["cursor"] == "second" and "search" not in requests[0].url.params
    assert batch.candidates[0].local_rank == 26


@pytest.mark.parametrize("bad", ["https://attacker.test/W1", "W1?token=secret", "W1/extra"])
async def test_untrusted_seed_cannot_change_request_endpoint(bad):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: pytest.fail("unsafe request"))
    ) as client:
        with pytest.raises(ProviderError):
            await OpenAlexRetrievalProvider(HTTPRuntime(client)).expand(
                source=SourceRef(provider_name="openalex", provider_source_id=bad),
                strategy="CITATION_BACKWARD",
                as_of=date(2026, 9, 26),
            )
