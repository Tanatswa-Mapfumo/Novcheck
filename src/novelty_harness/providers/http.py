import asyncio
import math
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx
from pydantic import ConfigDict, Field, JsonValue, TypeAdapter

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import TraceStatus
from novelty_harness.ports.models import ProviderCallMetadata
from novelty_harness.ports.retrieval_audit import BudgetExhausted
from novelty_harness.providers.errors import FailureCategory as Failure
from novelty_harness.providers.errors import provider_error
from novelty_harness.runtime.tracing.hashing import canonical_hash

SENSITIVE = {
    "api_key",
    "x-api-key",
    "authorization",
    "token",
    "access_token",
    "mailto",
    "email",
    "password",
}


class RetryPolicy(ContractModel):
    model_config = ConfigDict(frozen=True)
    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: float = Field(default=1, ge=0)
    timeout_seconds: float = Field(default=20, gt=0)


class RateLimitSnapshot(ContractModel):
    model_config = ConfigDict(frozen=True)
    limit: int | None = None
    remaining: int | None = None
    reset_seconds: float | None = None
    interval_seconds: float | None = None
    concurrency: int | None = None
    resource: str | None = None


class HTTPAttempt(ContractModel):
    model_config = ConfigDict(frozen=True)
    provider_name: str
    query_id: str
    request_hash: str
    attempt: int
    at: datetime
    status_code: int | None
    failure: Failure | None
    retry_delay_seconds: float = 0
    pacing_delay_seconds: float = 0
    cooldown_seconds: float = 0
    rate_limit: RateLimitSnapshot


@dataclass(frozen=True)
class HTTPResult:
    response: httpx.Response
    call: ProviderCallMetadata
    attempts: tuple[HTTPAttempt, ...]


def _number(headers: httpx.Headers, *names: str) -> float | None:
    for name in names:
        value = headers.get(name)
        if value is not None:
            try:
                number = float(value.removesuffix("s"))
            except ValueError:
                raise ValueError("Invalid numeric rate metadata") from None
            if not math.isfinite(number) or not 0 <= number <= sys.maxsize:
                raise ValueError("Unrepresentable numeric rate metadata")
            return number
    return None


def rate_snapshot(response: httpx.Response, provider: str, now: datetime) -> RateLimitSnapshot:
    headers = response.headers
    reset = _number(headers, "x-ratelimit-reset")
    if reset is not None and provider == "github":
        reset = max(0, reset - now.timestamp())
    limit = _number(headers, "x-ratelimit-limit", "x-rate-limit-limit")
    remaining = _number(headers, "x-ratelimit-remaining")
    concurrency = _number(headers, "x-concurrency-limit")
    return RateLimitSnapshot(
        limit=int(limit) if limit is not None else None,
        remaining=int(remaining) if remaining is not None else None,
        reset_seconds=reset,
        interval_seconds=_number(headers, "x-rate-limit-interval"),
        concurrency=int(concurrency) if concurrency is not None else None,
        resource=headers.get("x-ratelimit-resource") if provider == "github" else None,
    )


def retry_after_seconds(response: httpx.Response, now: datetime) -> float:
    raw = response.headers.get("retry-after")
    if raw is None:
        return 0
    try:
        seconds = float(raw)
    except ValueError:
        try:
            seconds = max(0, (parsedate_to_datetime(raw) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid retry metadata") from None
    if not math.isfinite(seconds) or not 0 <= seconds <= sys.maxsize:
        raise ValueError("Unrepresentable retry metadata")
    return seconds


def classify(response: httpx.Response, provider: str) -> Failure | None:
    status = response.status_code
    if 200 <= status < 300:
        return None
    if status == 401:
        return Failure.AUTHENTICATION_FAILURE
    if (
        status == 429
        or status == 403
        and provider == "github"
        and (
            response.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in response.headers
            or "secondary rate limit" in response.text.casefold()
        )
    ):
        return Failure.RATE_LIMITED
    if status == 403:
        return Failure.AUTHORIZATION_FAILURE
    if status >= 500:
        return Failure.SERVER_FAILURE
    return Failure.BAD_REQUEST


class HTTPRuntime:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.client, self.clock, self.sleeper = client, clock, sleeper
        self.policy = policy or RetryPolicy()
        self._attempts: list[HTTPAttempt] = []
        self._secrets: set[str] = set()
        self._next_request: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.request_guards: dict[str, Callable[[], None]] = {}
        self.time_limits: dict[str, Callable[[], float | None]] = {}

    @property
    def attempts(self) -> tuple[HTTPAttempt, ...]:
        return tuple(self._attempts)

    def redact(self, data: JsonValue) -> JsonValue:
        if isinstance(data, dict):
            return {
                k: "[REDACTED]" if k.casefold() in SENSITIVE else self.redact(v)
                for k, v in data.items()
                if not any(secret and secret in k for secret in self._secrets)
            }
        if isinstance(data, list):
            return [self.redact(v) for v in data]
        if isinstance(data, str):
            for secret in sorted(self._secrets, key=len, reverse=True):
                data = data.replace(secret, "[REDACTED]")
        return data

    async def request(
        self,
        *,
        provider: str,
        query_id: str,
        method: str,
        endpoint: str,
        params: Mapping[str, str | int | float | bool] | None = None,
        headers: Mapping[str, str] | None = None,
        min_interval: float = 0,
    ) -> HTTPResult:
        params, headers = dict(params or {}), dict(headers or {})
        for k, v in {**params, **headers}.items():
            if k.casefold() in SENSITIVE:
                self._secrets.add(str(v))
                if str(v).startswith("Bearer "):
                    self._secrets.add(str(v)[7:])
        parts = urlsplit(endpoint)
        if parts.query or parts.username or parts.password or parts.fragment:
            raise provider_error(
                provider,
                Failure.BAD_REQUEST,
                "Endpoint must not contain credentials or query",
                query_id,
            )
        safe_endpoint = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        request_hash = canonical_hash(
            {
                "method": method,
                "endpoint": safe_endpoint,
                "params": self.redact(dict(params)),
                "query_id": query_id,
            }
        )
        started = self.clock()
        attempts: list[HTTPAttempt] = []
        async with self._lock:
            for number in range(1, self.policy.max_attempts + 1):
                pace = max(0, self._next_request.get(provider, 0) - self.clock().timestamp())
                deadline = self.time_limits.get(provider)
                remaining = deadline() if deadline else None
                if remaining is not None and remaining <= 0:
                    raise BudgetExhausted("Research deadline exhausted")
                if remaining is not None and pace >= remaining:
                    await self.sleeper(remaining)
                    raise BudgetExhausted("Research deadline prevents provider cooldown wait")
                if pace:
                    await self.sleeper(pace)
                now = self.clock()
                if guard := self.request_guards.get(provider):
                    guard()
                response: httpx.Response | None = None
                failure: Failure | None = None
                deadline_expired = False
                remaining = deadline() if deadline else None
                try:
                    async with asyncio.timeout(remaining):
                        response = await self.client.request(
                            method,
                            endpoint,
                            params=params,
                            headers=headers,
                            timeout=min(self.policy.timeout_seconds, remaining)
                            if remaining is not None
                            else self.policy.timeout_seconds,
                            follow_redirects=False,
                        )
                    failure = classify(response, provider)
                except TimeoutError:
                    failure = Failure.TIMEOUT
                    deadline_expired = True
                except httpx.TimeoutException:
                    failure = Failure.TIMEOUT
                except httpx.RequestError:
                    failure = Failure.TRANSPORT_FAILURE
                try:
                    rate = (
                        rate_snapshot(response, provider, now) if response else RateLimitSnapshot()
                    )
                    cooldown = retry_after_seconds(response, self.clock()) if response else 0
                    if rate.remaining == 0 and rate.reset_seconds is not None:
                        cooldown = max(cooldown, rate.reset_seconds)
                    if (
                        provider == "github"
                        and failure == Failure.RATE_LIMITED
                        and response is not None
                        and "retry-after" not in response.headers
                        and rate.remaining != 0
                        and "secondary rate limit" in response.text.casefold()
                    ):
                        cooldown = max(cooldown, 60)
                except (ValueError, OverflowError):
                    rate = RateLimitSnapshot()
                    cooldown = 0
                    failure = Failure.PARSE_FAILURE
                rate = RateLimitSnapshot.model_validate(self.redact(rate.model_dump(mode="json")))
                interval = min_interval
                if rate.interval_seconds is not None and rate.limit:
                    interval = max(interval, rate.interval_seconds / rate.limit)
                retryable = failure in {
                    Failure.RATE_LIMITED,
                    Failure.TIMEOUT,
                    Failure.TRANSPORT_FAILURE,
                    Failure.SERVER_FAILURE,
                }
                retry = (
                    retryable
                    and method in {"GET", "HEAD", "OPTIONS"}
                    and number < self.policy.max_attempts
                )
                delay = (
                    max(self.policy.backoff_seconds * 2 ** (number - 1), cooldown) if retry else 0
                )
                self._next_request[provider] = self.clock().timestamp() + max(
                    interval, cooldown, delay
                )
                attempt = HTTPAttempt(
                    provider_name=provider,
                    query_id=query_id,
                    request_hash=request_hash,
                    attempt=number,
                    at=now,
                    status_code=response.status_code if response is not None else None,
                    failure=failure,
                    retry_delay_seconds=delay,
                    pacing_delay_seconds=pace,
                    cooldown_seconds=cooldown,
                    rate_limit=rate,
                )
                attempts.append(attempt)
                self._attempts.append(attempt)
                if deadline_expired:
                    raise BudgetExhausted("Research deadline expired during wire request")
                call = ProviderCallMetadata(
                    provider_name=provider,
                    provider_version="http-v1",
                    started_at=started,
                    finished_at=self.clock(),
                    request_hash=request_hash,
                    status=TraceStatus.SUCCESS if failure is None else TraceStatus.FAILURE,
                    failure_code=failure.value if failure else None,
                )
                if failure is None and response is not None:
                    return HTTPResult(response, call, tuple(attempts))
                if not retry:
                    assert failure is not None
                    raise provider_error(
                        provider,
                        failure,
                        "HTTP request failed; see safe attempt trace",
                        query_id,
                        call,
                    )
        raise AssertionError("bounded HTTP attempts must terminate")

    def parse_json(self, result: HTTPResult, *, provider: str, query_id: str) -> JsonValue:
        try:
            data = TypeAdapter[JsonValue](JsonValue).validate_json(
                result.response.content, strict=True
            )
        except ValueError:
            data = None
        if data is None:
            raise provider_error(
                provider, Failure.PARSE_FAILURE, "Invalid JSON response", query_id, result.call
            )
        return self.redact(data)

    def parse_xml(self, result: HTTPResult, *, provider: str, query_id: str) -> ElementTree.Element:
        content = result.response.text
        try:
            if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
                raise ValueError("unsafe XML")
            return ElementTree.fromstring(content)
        except (ElementTree.ParseError, ValueError):
            pass
        raise provider_error(
            provider, Failure.PARSE_FAILURE, "Invalid XML response", query_id, result.call
        )
