import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from novelty_harness.ports.models import SearchQuery
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.github import GitHubCompiler, GitHubProvider
from novelty_harness.providers.http import HTTPRuntime
from novelty_harness.providers.registry import CredentialRef
from novelty_harness.research.models import SearchIntent
from tests.contract.provider_contracts import assert_search_provider_contract
from tests.unit.providers.test_openalex import no_sleep
from tests.unit.research.test_search_planning import plan_data


def response():
    return json.loads(
        (
            Path(__file__).parents[2] / "fixtures/provider_responses/github/repositories.json"
        ).read_text()
    )


def query():
    return SearchQuery(
        query_id="qry_github",
        text="sensor controls relay",
        purpose="screening",
        evidence_family="SOFTWARE",
        filters={"as_of": "2026-09-26"},
    )


@pytest.mark.parametrize("authenticated", [True, False])
async def test_github_contract_archived_repos_pagination_and_secret_safety(
    authenticated, monkeypatch
):
    monkeypatch.setenv("NOVCHECK_TEST_TOKEN", "token-secret")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=response(),
            headers={
                "X-RateLimit-Resource": "search",
                "Link": '<https://api.github.com/search/repositories?page=2>; rel="next"',
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        runtime = HTTPRuntime(client, sleeper=no_sleep)
        provider = GitHubProvider(
            runtime,
            credential=CredentialRef(env_name="NOVCHECK_TEST_TOKEN") if authenticated else None,
        )
        await assert_search_provider_contract(provider, query())
        page = await provider.search(query())
        assert page.next_cursor == "2"
        assert page.results[0].metadata["archived"] is True
        assert page.results[0].metadata["api_version"] == "2026-03-10"
        assert runtime.attempts[0].rate_limit.resource == "search"
        assert ("Authorization" in requests[0].headers) == authenticated
        assert "token-secret" not in str(runtime.attempts) + page.model_dump_json()
        assert "invention" in " ".join(provider.limitations(query().query_id))


@pytest.mark.parametrize("mode", ["rate", "secondary", "malformed", "incomplete", "empty"])
async def test_github_failures_and_incomplete_results_are_visible(mode):
    def handle(request):
        if mode == "rate":
            return httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={})
        if mode == "secondary":
            return httpx.Response(403, json={"message": "secondary rate limit"})
        data = response()
        if mode == "malformed":
            data["items"][0]["id"] = "wrong"
        if mode == "incomplete":
            data["incomplete_results"] = True
        if mode == "empty":
            data["items"] = []
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = GitHubProvider(HTTPRuntime(client, sleeper=no_sleep))
        if mode in {"rate", "secondary", "malformed"}:
            with pytest.raises(ProviderError):
                await provider.search(query())
        else:
            page = await provider.search(query())
            if mode == "empty":
                assert not page.results
            if mode == "incomplete":
                assert "Incomplete provider result set" in provider.limitations(query().query_id)


def test_github_repository_search_cannot_pretend_to_be_code_search():
    intent = SearchIntent.model_validate(
        {**plan_data()["intents"][0], "evidence_family": "SOFTWARE"}
    )
    compiled = GitHubCompiler().compile(intent, as_of=date(2026, 9, 26))
    assert "created:<=2026-09-26" in compiled.params["q"]
    with pytest.raises(ProviderError) as raised:
        GitHubCompiler().compile(
            intent.model_copy(update={"filters": {"code_search": True}}), as_of=date(2026, 9, 26)
        )
    assert raised.value.failure.category.value == "CAPABILITY_MISMATCH"


async def test_resolved_credential_echo_is_redacted_from_rate_diagnostics(monkeypatch):
    monkeypatch.setenv("NOVCHECK_TEST_TOKEN", "review-fake-secret")

    def handle(request):
        return httpx.Response(
            200, json=response(), headers={"X-RateLimit-Resource": "review-fake-secret"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = GitHubProvider(
            HTTPRuntime(client, sleeper=no_sleep),
            credential=CredentialRef(env_name="NOVCHECK_TEST_TOKEN"),
        )
        await provider.search(query())
        diagnostics = provider.screening_diagnostics(query().query_id)
        assert "review-fake-secret" not in diagnostics.model_dump_json()
        assert diagnostics.attempts[0]["rate_limit"]["resource"] == "[REDACTED]"
