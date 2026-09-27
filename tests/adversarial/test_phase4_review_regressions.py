import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.ports.retrieval_audit import BudgetExhausted
from novelty_harness.providers.errors import ProviderError
from novelty_harness.research.fusion.clustering import cluster_candidates
from novelty_harness.runtime.config.models import BudgetLimits
from tests.fixtures.phase4 import assessment, registry, wire
from tests.integration.test_phase4_retrieval_pipeline import run
from tests.unit.research.fusion.test_clustering import record
from tests.unit.research.test_strategist import build


async def test_depth_deferred_top_neighborhood_is_not_completed_exploration():
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        result, _, _ = await run(client)
    scholarly = [
        c for c in result.coverage_matrix if c.screening.evidence_family.value == "SCHOLARLY"
    ]
    assert all(c.stop.reason.value != "SATURATED" for c in scholarly)
    assert any(s.deferred_neighborhoods for s in result.branch_states)


async def test_last_reserved_deep_round_can_execute_its_wire_requests():
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        result, _, _ = await run(client, limits=BudgetLimits(max_deep_search_rounds=1))
    assert result.budget_usage.deep_search_rounds == 1
    assert any(c.seed_source is not None for b in result.batches for c in b.candidates)
    assert result.budget_usage.provider_calls > 72
    assert any(s.reason.value == "BUDGET_STOPPED" for s in result.stop_assessments)


async def test_elapsed_deadline_caps_huge_cooldown_sleep_before_retry():
    now = datetime(2026, 9, 27, tzinfo=UTC)
    sleeps = []

    async def sleep(seconds):
        nonlocal now
        sleeps.append(seconds)
        now += timedelta(seconds=seconds)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(503, json={}, headers={"Retry-After": "86400"})
        )
    ) as client:
        result, runtime, _ = await run(
            client,
            limits=BudgetLimits(max_elapsed_seconds=2),
            retries=3,
            clock=lambda: now,
            sleeper=sleep,
        )
    assert sleeps == [2] and len(runtime.attempts) == 1
    assert any(s.reason.value == "BUDGET_STOPPED" for s in result.stop_assessments)


async def test_elapsed_deadline_cancels_inflight_request_and_keeps_safe_attempt():
    cancelled = False

    async def never_returns(request):
        nonlocal cancelled
        try:
            await asyncio.Future()
        finally:
            cancelled = True

    async with httpx.AsyncClient(transport=httpx.MockTransport(never_returns)) as client:
        providers, runtime = registry(client)
        provider = providers.get("semantic_scholar").provider
        provider.set_time_limit(lambda: 0.01)
        async with asyncio.timeout(0.5):
            with pytest.raises(BudgetExhausted):
                await provider.expand(
                    source=SourceRef(provider_name="semantic_scholar", provider_source_id="a" * 40),
                    strategy="CITATION_FORWARD",
                    as_of=assessment().request.as_of,
                )
    assert cancelled and len(runtime.attempts) == 1
    assert runtime.attempts[0].failure.value == "TIMEOUT"
    assert provider.retrieval_request_events()[0].failure_code == "BUDGET_STOPPED"


async def test_hostile_crossref_date_is_unknown_without_crashing_other_branches():
    def respond(request):
        data = wire(request).json()
        if request.url.host == "api.crossref.org":
            data["message"]["items"][0]["published"]["date-parts"] = [[2**100, 1, 1]]
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result, _, _ = await run(client)
    assert any(b.provider_name == "openalex" and b.candidates for b in result.batches)
    crossref = [c for b in result.batches if b.provider_name == "crossref" for c in b.candidates]
    assert crossref and all(c.raw_metadata["publication_date"] is None for c in crossref)


def test_opaque_local_identifier_cannot_masquerade_as_global_doi():
    opaque = record("opaque_provider", "10.1234/shared")
    explicit = record("crossref", "10.1234/shared", raw_metadata={"doi": "10.1234/shared"})
    assert len(cluster_candidates([opaque, explicit])) == 2


@pytest.mark.parametrize("name", ["openalex", "semantic_scholar"])
async def test_native_response_rejects_malformed_work_identity(name):
    def respond(request):
        data = wire(request).json()
        if name == "openalex":
            data["results"][0]["id"] = "https://attacker.test/W100"
        else:
            data["data"][0]["paperId"] = "10.1234/opaque"
        return httpx.Response(200, json=data)

    intent = (await build())[0].intents[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        providers, _ = registry(client)
        provider = providers.get(name).provider
        with pytest.raises(ProviderError) as raised:
            await provider.retrieve(
                intent=intent,
                strategy="LEXICAL",
                as_of=assessment().request.as_of,
            )
    assert raised.value.failure.category.value == "PARSE_FAILURE"


@pytest.mark.parametrize("kind", ["CITATION_BACKWARD", "RELATED_WORK"])
async def test_openalex_hydration_rejects_work_outside_requested_reference_set(kind):
    def respond(request):
        data = wire(request).json()
        if request.url.path.startswith("/works/W"):
            data["related_works"] = ["https://openalex.org/W100"]
        else:
            data["results"][0]["id"] = "https://openalex.org/W999"
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        providers, _ = registry(client)
        p = providers.get("openalex").provider
        with pytest.raises(ProviderError) as raised:
            await p.expand(
                source=SourceRef(provider_name="openalex", provider_source_id="W900"),
                strategy=kind,
                as_of=assessment().request.as_of,
            )
    assert raised.value.failure.category.value == "PARSE_FAILURE"


async def test_missing_s2_edge_retains_wire_rank_span_and_incomplete_access():
    paper = {"paperId": "b" * 40, "title": "Work", "publicationDate": "2001-01-01"}

    def respond(request):
        offset = int(request.url.params.get("offset", "0"))
        return httpx.Response(
            200,
            json={"data": [{"citedPaper": None}, {"citedPaper": paper}], "offset": 0, "next": 2}
            if offset == 0
            else {"data": [{"citedPaper": paper}], "offset": 2},
        )

    seed = SourceRef(provider_name="semantic_scholar", provider_source_id="a" * 40)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        providers, _ = registry(client)
        p = providers.get("semantic_scholar").provider
        first = await p.expand(
            source=seed, strategy="CITATION_BACKWARD", as_of=assessment().request.as_of
        )
        assert first.candidates[0].local_rank == 2 and not first.complete
        assert first.rank_span == 2
        second = await p.expand(
            source=seed,
            strategy="CITATION_BACKWARD",
            as_of=assessment().request.as_of,
            cursor=first.next_cursor,
            rank_offset=first.rank_span,
        )
        assert second.candidates[0].local_rank == 3
