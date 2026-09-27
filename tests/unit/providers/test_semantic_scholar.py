import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.registry import CredentialRef
from novelty_harness.providers.semantic_scholar import SemanticScholarProvider
from tests.contract.provider_contracts import assert_search_provider_contract
from tests.unit.providers.test_openalex import no_sleep, query
from tests.unit.research.test_strategist import build

PAPER = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def response():
    return json.loads(
        (
            Path(__file__).parents[2] / "fixtures/provider_responses/semantic_scholar/search.json"
        ).read_text()
    )


async def test_shared_search_contract_offsets_and_optional_key_are_safe(monkeypatch):
    monkeypatch.setenv("NOVCHECK_S2_KEY", "synthetic-s2-secret")
    requests = []

    def respond(request):
        requests.append(request)
        data = response()
        data["offset"] = int(request.url.params["offset"])
        data["next"] = data["offset"] + 25
        data["data"][0]["embedding"]["synthetic-s2-secret"] = "echo"
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = SemanticScholarProvider(
            HTTPRuntime(client, sleeper=no_sleep),
            credential=CredentialRef(env_name="NOVCHECK_S2_KEY"),
        )
        await assert_search_provider_contract(provider, query())
        page = await provider.search(query(), cursor="25")
    assert requests[-1].url.params["offset"] == "25" and page.next_cursor == "50"
    assert requests[-1].headers["x-api-key"] == "synthetic-s2-secret"
    assert "Authorization" not in requests[-1].headers
    assert page.results[0].metadata["externalIds"]["DOI"] == "10.1234/control"
    assert page.results[0].metadata["embedding"]["model"] == "specter_v2"
    assert "synthetic-s2-secret" not in page.model_dump_json()


@pytest.mark.parametrize(
    "strategy,endpoint,edge",
    [
        ("CITATION_BACKWARD", "references", "citedPaper"),
        ("CITATION_FORWARD", "citations", "citingPaper"),
    ],
)
async def test_directional_edges_and_seed_paths(strategy, endpoint, edge):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, json={"offset": 0, "next": 25, "data": [{edge: response()["data"][0]}]}
        )

    seed = SourceRef(provider_name="semantic_scholar", provider_source_id=PAPER)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        batch = await SemanticScholarProvider(HTTPRuntime(client, sleeper=no_sleep)).expand(
            source=seed, strategy=strategy, as_of=date(2026, 9, 26), mcu_id="mcu_control"
        )
    assert requests[0].url.path.endswith("/" + endpoint)
    assert (
        batch.candidates[0].seed_source == seed and batch.candidates[0].strategy.value == strategy
    )
    assert batch.next_cursor == "25"
    assert not any(k in batch.candidates[0].raw_metadata for k in ("novelty", "probability"))


async def test_author_lineage_hydrates_seed_then_expands_public_papers():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, json=response()["data"][0] if request.url.path.endswith(PAPER) else response()
        )

    seed = SourceRef(provider_name="semantic_scholar", provider_source_id=PAPER)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = SemanticScholarProvider(HTTPRuntime(client, sleeper=no_sleep))
        metadata = await provider.paper_metadata(seed)
        batch = await provider.expand(
            source=seed, strategy="ENTITY_LINEAGE", as_of=date(2026, 9, 26)
        )
    assert metadata["paperId"] == PAPER
    assert requests[-1].url.path == "/graph/v1/author/123/papers"
    assert batch.candidates[0].seed_source == seed and len(batch.calls) == 2


@pytest.mark.parametrize("mode", ["malformed", "blocked", "offset_cap", "unsupported", "future"])
async def test_untrusted_graph_failures_limits_and_cutoff(mode):
    def respond(request):
        data = response()
        if mode == "malformed":
            data["data"][0]["paperId"] = 123
        if mode == "future":
            data["data"][0]["publicationDate"] = "2027-01-01"
        return httpx.Response(403 if mode == "blocked" else 200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = SemanticScholarProvider(HTTPRuntime(client, sleeper=no_sleep))
        if mode == "future":
            assert not (await provider.search(query())).results
            batch = await provider.retrieve(
                intent=(await build())[0].intents[0], strategy="LEXICAL", as_of=date(2026, 9, 26)
            )
            assert batch.candidates[0].raw_metadata["publicationDate"] == "2027-01-01"
        else:
            with pytest.raises(ProviderError):
                if mode == "unsupported":
                    await provider.retrieve(
                        intent=(await build())[0].intents[0],
                        strategy="SEMANTIC",
                        as_of=date(2026, 9, 26),
                    )
                else:
                    await provider.search(query(), cursor="1000" if mode == "offset_cap" else None)
