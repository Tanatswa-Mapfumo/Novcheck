from datetime import date

import httpx
import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.openalex_semantic import OpenAlexRetrievalProvider
from novelty_harness.research.expansion.citations import ExpansionRequest, expand_candidates
from tests.unit.providers.test_openalex import no_sleep, response


def wire(request):
    if request.url.path == "/works/W900":
        data = response()["results"][0]
        data.update(
            id="https://openalex.org/W900",
            referenced_works=["https://openalex.org/W123"],
            related_works=[],
        )
        return httpx.Response(200, json=data)
    return httpx.Response(200, json=response())


def request(**updates):
    return ExpansionRequest.model_validate(
        {
            "source": SourceRef(provider_name="openalex", provider_source_id="W900"),
            "mcu_id": "mcu_control",
            "kinds": {"CITATION_BACKWARD", "CITATION_FORWARD"},
            **updates,
        }
    )


async def test_directions_preserve_same_candidate_multiple_seed_paths():
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        result = await expand_candidates(
            request(),
            provider=OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)),
            as_of=date(2026, 9, 26),
            max_actions=2,
        )
    assert result.attempted_kinds == {"CITATION_BACKWARD", "CITATION_FORWARD"}
    assert len(result.candidates) == 2 and len(result.batches) == 2
    assert {c.strategy.value for c in result.candidates} == {
        "CITATION_BACKWARD",
        "CITATION_FORWARD",
    }
    assert all(c.seed_source.provider_source_id == "W900" for c in result.candidates)


async def test_missing_provider_explicit_unavailable_no_recursive_expansion():
    result = await expand_candidates(
        request(), provider=None, as_of=date(2026, 9, 26), max_actions=2
    )
    assert result.unavailable_kinds == request().kinds and not result.candidates
    assert not result.attempted_kinds
    with pytest.raises(ValueError, match="approval"):
        await expand_candidates(
            request(depth=2), provider=None, as_of=date(2026, 9, 26), max_actions=2
        )


async def test_entity_unsupported_and_budget_are_visible_not_silent():
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        provider = OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep))
        entity = request(kinds={"ENTITY_LINEAGE"})
        result = await expand_candidates(
            entity, provider=provider, as_of=date(2026, 9, 26), max_actions=1
        )
        blocked = await expand_candidates(
            request(), provider=provider, as_of=date(2026, 9, 26), max_actions=0
        )
    assert result.unavailable_kinds == {"ENTITY_LINEAGE"}
    assert not blocked.attempted_kinds and blocked.deferred_kinds == request().kinds


async def test_provider_failure_remains_structured_without_response_secrets():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"secret": "TOKEN"}))
    ) as client:
        result = await expand_candidates(
            request(kinds={"CITATION_FORWARD"}),
            provider=OpenAlexRetrievalProvider(HTTPRuntime(client, sleeper=no_sleep)),
            as_of=date(2026, 9, 26),
            max_actions=1,
        )
    assert len(result.failures) == 1 and "AUTHORIZATION_FAILURE" in result.failures[0]
    assert "TOKEN" not in result.model_dump_json()
