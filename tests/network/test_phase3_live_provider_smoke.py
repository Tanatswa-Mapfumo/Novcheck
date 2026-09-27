import os
from datetime import date

import httpx
import pytest

from novelty_harness.ports.models import SearchPage, SearchQuery
from novelty_harness.providers.crossref import CrossrefProvider
from novelty_harness.providers.errors import FailureCategory, ProviderError
from novelty_harness.providers.github import GitHubProvider
from novelty_harness.providers.http import HTTPRuntime, RetryPolicy
from novelty_harness.providers.openalex import OpenAlexProvider
from novelty_harness.providers.registry import CredentialRef

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.environ.get("NOVCHECK_LIVE_SMOKE") != "1", reason="Set NOVCHECK_LIVE_SMOKE=1 explicitly"
    ),
]


@pytest.mark.parametrize("name", ["openalex", "crossref", "github"])
async def test_minimal_live_provider_contract(name):
    async with httpx.AsyncClient() as client:
        runtime = HTTPRuntime(client, policy=RetryPolicy(max_attempts=1, timeout_seconds=5))
        providers = {
            "openalex": OpenAlexProvider(
                runtime, credential=CredentialRef(env_name="OPENALEX_API_KEY")
            ),
            "crossref": CrossrefProvider(runtime, mailto=CredentialRef(env_name="CROSSREF_MAILTO")),
            "github": GitHubProvider(runtime, credential=CredentialRef(env_name="GITHUB_TOKEN")),
        }
        provider = providers[name]
        try:
            page = await provider.search(
                SearchQuery(
                    query_id="qry_live_smoke",
                    text="temperature sensor",
                    purpose="Opt-in contract smoke only",
                    evidence_family="SOFTWARE" if name == "github" else "SCHOLARLY",
                    filters={"as_of": date.today().isoformat()},
                )
            )
        except ProviderError as error:
            if error.failure.category in {
                FailureCategory.TIMEOUT,
                FailureCategory.TRANSPORT_FAILURE,
                FailureCategory.AUTHENTICATION_FAILURE,
                FailureCategory.AUTHORIZATION_FAILURE,
                FailureCategory.RATE_LIMITED,
                FailureCategory.QUOTA_EXHAUSTED,
                FailureCategory.SERVER_FAILURE,
            }:
                pytest.skip(f"Live {name} unavailable: {error.failure.category.value}")
            raise
        assert SearchPage.model_validate_json(page.model_dump_json()) == page
        assert page.call.provider_name == name and page.call.status.value == "SUCCESS"
