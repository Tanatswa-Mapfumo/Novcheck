import json

import httpx
import pytest

from novelty_harness.providers.crossref import CrossrefProvider
from novelty_harness.providers.github import GitHubProvider
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.openalex import OpenAlexProvider
from novelty_harness.providers.registry import ProviderRegistry
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.research.screening import ScreeningExecutor, ScreeningHit
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from tests.unit.providers.test_crossref import response as crossref_response
from tests.unit.providers.test_github import response as github_response
from tests.unit.providers.test_openalex import no_sleep
from tests.unit.providers.test_openalex import response as openalex_response
from tests.unit.research.test_coverage_floor import prepared


def registry_for(client):
    registry = ProviderRegistry()
    runtime = HTTPRuntime(client, sleeper=no_sleep)
    for cls in (OpenAlexProvider, CrossrefProvider, GitHubProvider):
        provider = cls(runtime)
        registry.register(provider, provider.descriptor, compiler=provider.compiler)
    return registry


def handler(mode="success"):
    def respond(request):
        host = request.url.host
        if mode == "failure" and host == "api.openalex.org":
            return httpx.Response(429, json={})
        data = {
            "api.openalex.org": openalex_response,
            "api.crossref.org": crossref_response,
            "api.github.com": github_response,
        }[host]()
        if mode == "zero":
            if host == "api.openalex.org":
                data["results"] = []
            elif host == "api.crossref.org":
                data["message"]["items"] = []
            else:
                data["items"] = []
        return httpx.Response(200, json=data)

    return respond


@pytest.mark.parametrize("mode", ["success", "failure", "zero"])
async def test_three_adapters_screen_with_truthful_coverage_and_artifacts(mode, tmp_path):
    plan = await prepared()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler(mode))) as client:
        executor = ScreeningExecutor(registry_for(client), CoveragePolicy.standard())
        result = await executor.execute(plan, writer=RunArtifactWriter(tmp_path))
    scholarly = [c for c in result.coverage if c.evidence_family.value == "SCHOLARLY"]
    assert all(
        c.state.value == ("DEGRADED" if mode == "failure" else "SCREENED") for c in scholarly
    )
    assert all(
        c.state.value == "BLOCKED_NO_PROVIDER"
        for c in result.coverage
        if c.evidence_family.value == "PATENT"
    )
    assert len(result.hits) == (0 if mode == "zero" else 36 if mode == "failure" else 54)
    if mode == "failure":
        assert result.provider_failures
    if mode == "zero":
        assert all(e.state == "ZERO_RESULTS" for e in result.events)
    names = {p.name for p in (tmp_path / plan.assessment_id).iterdir()}
    assert names == {
        "family_applicability.json",
        "search_plan.json",
        "search_plan_review.json",
        "compiled_queries.jsonl",
        "screening_events.jsonl",
        "screening_hits.jsonl",
        "coverage_matrix.json",
        "provider_failures.jsonl",
    }
    assert "SATURATED" not in json.dumps(result.model_dump(mode="json"))
    assert not any("independent_evidence" in h.model_dump() for h in result.hits)


async def test_unreviewed_or_changed_plan_cannot_execute(tmp_path):
    plan = await prepared()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler())) as client:
        executor = ScreeningExecutor(registry_for(client), CoveragePolicy.standard())
        with pytest.raises(ValueError):
            await executor.execute(plan.model_copy(update={"reviewed": False}))
        plan.intents[0].filters["changed"] = True
        with pytest.raises(ValueError):
            await executor.execute(plan)
    assert not list(tmp_path.iterdir())


async def test_malformed_external_headers_do_not_abort_unrelated_provider_branches():
    def respond(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(
                200, json=openalex_response(), headers={"X-RateLimit-Limit": "inf"}
            )
        return handler()(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await ScreeningExecutor(registry_for(client), CoveragePolicy.standard()).execute(
            await prepared()
        )
    assert all(f.category.value == "PARSE_FAILURE" for f in result.provider_failures)
    assert {h.provider_name for h in result.hits} == {"crossref", "github"}
    assert all(
        c.state.value == "DEGRADED"
        for c in result.coverage
        if c.evidence_family.value == "SCHOLARLY"
    )


async def test_provider_metadata_survives_screening_and_artifact_round_trip(tmp_path):
    def respond(request):
        if request.url.host == "api.openalex.org":
            data = openalex_response()
            data["results"][0]["publication_date"] = "2001-02-03"
        elif request.url.host == "api.crossref.org":
            data = crossref_response()
            data["message"]["items"][0]["published"]["date-parts"] = [[2002, 3, 4]]
        else:
            data = github_response()
        return httpx.Response(200, json=data)

    plan = await prepared()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await ScreeningExecutor(registry_for(client), CoveragePolicy.standard()).execute(
            plan, writer=RunArtifactWriter(tmp_path)
        )
    stored = [
        json.loads(line)
        for line in (tmp_path / plan.assessment_id / "screening_hits.jsonl")
        .read_text()
        .splitlines()
    ]
    metadata = {h["provider_name"]: h.get("provider_metadata") for h in stored}
    assert metadata["openalex"]["publication_date"] == "2001-02-03"
    assert metadata["crossref"]["publication_date"] == "2002-03-04"
    assert metadata["github"]["created_at"]
    assert metadata["github"]["updated_at"]
    assert metadata["github"]["topics"]
    assert "license" in metadata["github"]
    assert tuple(ScreeningHit.model_validate(h) for h in stored) == result.hits
