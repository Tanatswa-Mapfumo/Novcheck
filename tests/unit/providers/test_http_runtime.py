from datetime import UTC, datetime

import httpx
import pytest

from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.http import HTTPRuntime, RetryPolicy


@pytest.mark.parametrize(
    "status,category,attempts",
    [
        (400, "BAD_REQUEST", 1),
        (401, "AUTHENTICATION_FAILURE", 1),
        (403, "AUTHORIZATION_FAILURE", 1),
        (429, "RATE_LIMITED", 3),
        (500, "SERVER_FAILURE", 3),
    ],
)
async def test_failures_have_explicit_bounded_attempts_without_secrets(status, category, attempts):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, headers={"Retry-After": "2"}, json={"message": "secret-token"}
            )
        )
    ) as client:
        runtime = HTTPRuntime(client, sleeper=sleep)
        with pytest.raises(ProviderError) as raised:
            await runtime.request(
                provider="stub",
                query_id="qry_1",
                method="GET",
                endpoint="https://stub.test/works",
                params={"api_key": "secret-token"},
                headers={"Authorization": "Bearer secret-token"},
            )
        assert raised.value.failure.category.value == category
        assert len(runtime.attempts) == attempts
        assert "secret-token" not in str(raised.value.failure.model_dump())
        assert len(sleeps) == attempts - 1


async def test_retry_after_http_date_and_github_rate_403_are_honored():
    sleeps, calls = [], []

    async def sleep(seconds):
        sleeps.append(seconds)

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                403,
                headers={
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "Sat, 26 Sep 2026 12:00:05 GMT",
                },
                json={},
            )
        return httpx.Response(200, json={"items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        runtime = HTTPRuntime(
            client, sleeper=sleep, clock=lambda: datetime(2026, 9, 26, 12, tzinfo=UTC)
        )
        result = await runtime.request(
            provider="github",
            query_id="qry_1",
            method="GET",
            endpoint="https://api.github.com/search/repositories",
        )
        assert result.call.status.value == "SUCCESS"
        assert sleeps == [5]
        assert result.attempts[0].failure.value == "RATE_LIMITED"


@pytest.mark.parametrize("kind", ["timeout", "transport", "json", "xml", "nonidempotent"])
async def test_timeout_parse_and_nonidempotent_failures(kind):
    async def sleep(seconds):
        pass

    def respond(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("secret", request=request)
        if kind == "transport":
            raise httpx.ConnectError("secret", request=request)
        return httpx.Response(500 if kind == "nonidempotent" else 200, text="not valid")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        runtime = HTTPRuntime(client, sleeper=sleep, policy=RetryPolicy(max_attempts=2))
        with pytest.raises(ProviderError):
            result = await runtime.request(
                provider="stub",
                query_id="qry_1",
                method="POST" if kind == "nonidempotent" else "GET",
                endpoint="https://stub.test",
            )
            if kind == "json":
                runtime.parse_json(result, provider="stub", query_id="qry_1")
            else:
                runtime.parse_xml(result, provider="stub", query_id="qry_1")
        assert len(runtime.attempts) == (2 if kind in {"timeout", "transport"} else 1)
