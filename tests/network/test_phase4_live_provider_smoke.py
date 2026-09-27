import os
from datetime import date

import httpx
import pytest

from novelty_harness.providers.errors import FailureCategory, ProviderError
from novelty_harness.providers.http import HTTPRuntime, RetryPolicy
from novelty_harness.providers.openalex_semantic import OpenAlexRetrievalProvider
from novelty_harness.providers.registry import CredentialRef
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.retrieval.models import RetrievalBatch

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.environ.get("NOVCHECK_LIVE_SMOKE") != "1", reason="Set NOVCHECK_LIVE_SMOKE=1 explicitly"
    ),
]


async def test_live_openalex_native_semantic_contract():
    intent = SearchIntent(
        query_id="qry_live_semantic",
        mcu_id="mcu_live",
        evidence_family="SCHOLARLY",
        query_family="MECHANISM",
        text="temperature measurement controls switching",
        rationale="Opt-in native retrieval contract only",
        concepts=("temperature", "switching"),
    )
    async with httpx.AsyncClient() as client:
        provider = OpenAlexRetrievalProvider(
            HTTPRuntime(client, policy=RetryPolicy(max_attempts=1, timeout_seconds=5)),
            credential=CredentialRef(env_name="OPENALEX_API_KEY"),
        )
        try:
            batch = await provider.retrieve(intent=intent, strategy="SEMANTIC", as_of=date.today())
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
                pytest.skip("Live OpenAlex semantic unavailable: " + error.failure.category.value)
            raise
    assert RetrievalBatch.model_validate_json(batch.model_dump_json()) == batch
    assert batch.strategy.value == "SEMANTIC" and len(batch.candidates) <= 50
