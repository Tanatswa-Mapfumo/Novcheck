from abc import ABC, abstractmethod
from datetime import date

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from novelty_harness.ports.models import (
    ProviderCapabilities,
    ProviderHealth,
    SearchPage,
    SearchQuery,
)
from novelty_harness.ports.search_audit import ScreeningDiagnostics
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult, HTTPRuntime
from novelty_harness.providers.registry import CredentialRef, ProviderDescriptor
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import ProviderQueryCompiler, compile_intent
from novelty_harness.research.query_taxonomy import QueryFamily


class WireModel(BaseModel):
    # Provider responses evolve independently; validate used fields strictly, ignore other metadata.
    model_config = ConfigDict(extra="ignore", strict=True)


def validate_wire[T: WireModel](
    model: type[T], data: JsonValue, *, provider: str, query_id: str, result: HTTPResult
) -> T:
    try:
        value = model.model_validate(data)
    except ValidationError:
        value = None
    if value is None:
        raise provider_error(
            provider,
            FailureCategory.PARSE_FAILURE,
            "Malformed provider response",
            query_id,
            result.call,
        )
    return value


class HTTPSearchAdapter(ABC):
    name: str
    descriptor: ProviderDescriptor
    compiler: ProviderQueryCompiler

    def __init__(self, runtime: HTTPRuntime, *, credential: CredentialRef | None = None) -> None:
        self.runtime, self.credential = runtime, credential
        self._limitations: dict[str, tuple[str, ...]] = {}
        self._diagnostics: dict[str, ScreeningDiagnostics] = {}

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            evidence_families=set(self.descriptor.evidence_families),
            supports_pagination=self.descriptor.supports_pagination,
            supports_full_text=self.descriptor.supports_full_text,
            supports_backward_citations=self.descriptor.supports_citations,
            supports_forward_citations=self.descriptor.supports_citations,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=True, detail="Locally configured; live availability not probed"
        )

    def limitations(self, query_id: str) -> tuple[str, ...]:
        return self._limitations.get(query_id, ())

    def screening_diagnostics(self, query_id: str) -> ScreeningDiagnostics:
        return self._diagnostics.get(query_id, ScreeningDiagnostics()).model_copy(deep=True)

    def headers(self) -> dict[str, str]:
        headers = {"User-Agent": "novcheck/0.1", "Accept": "application/json"}
        token = self.credential.resolve() if self.credential else None
        if token:
            headers["Authorization"] = "Bearer " + token
        return headers

    def min_interval(self) -> float:
        return 0.1

    def request_params(
        self, params: dict[str, str | int | float | bool]
    ) -> dict[str, str | int | float | bool]:
        return params

    async def search(self, query: SearchQuery, cursor: str | None = None) -> SearchPage:
        raw = query.filters.get("as_of")
        if not isinstance(raw, str):
            raise provider_error(
                self.name, FailureCategory.BAD_REQUEST, "Explicit as_of required", query.query_id
            )
        try:
            cutoff = date.fromisoformat(raw)
        except ValueError:
            cutoff = None
        if cutoff is None:
            raise provider_error(
                self.name, FailureCategory.BAD_REQUEST, "Invalid as_of", query.query_id
            )
        intent = SearchIntent(
            query_id=query.query_id,
            mcu_id="mcu_transport",
            evidence_family=query.evidence_family,
            query_family=QueryFamily.DIRECT_CANONICAL,
            text=query.text,
            rationale=query.purpose,
            concepts=(query.text,),
            filters={k: v for k, v in query.filters.items() if k != "as_of"},
        )
        compiled = compile_intent(self.compiler, intent, as_of=cutoff)
        params: dict[str, str | int | float | bool] = {}
        for key, value in compiled.params.items():
            if not isinstance(value, str | int | float | bool):
                raise provider_error(
                    self.name,
                    FailureCategory.BAD_REQUEST,
                    "Non-scalar compiled parameter",
                    query.query_id,
                )
            params[key] = value
        self.apply_cursor(params, cursor)
        start = len(self.runtime.attempts)
        notes: tuple[str, ...] = ()
        try:
            result = await self.runtime.request(
                provider=self.name,
                query_id=query.query_id,
                method=compiled.method,
                endpoint=compiled.endpoint,
                params=self.request_params(params),
                headers=self.headers(),
                min_interval=self.min_interval(),
            )
            data = self.runtime.parse_json(result, provider=self.name, query_id=query.query_id)
            page, notes = self.parse(data, result, query, cutoff)
            return page
        finally:
            attempts = tuple(
                a
                for a in self.runtime.attempts[start:]
                if a.provider_name == self.name and a.query_id == query.query_id
            )
            self._limitations[query.query_id] = (*compiled.compilation_notes, *notes)
            self._diagnostics[query.query_id] = ScreeningDiagnostics(
                attempts=tuple(a.model_dump(mode="json") for a in attempts),
                had_failed_attempts=any(a.failure is not None for a in attempts),
                limitations=self._limitations[query.query_id],
                complete="Incomplete provider result set" not in notes,
            )

    def apply_cursor(self, params: dict[str, str | int | float | bool], cursor: str | None) -> None:
        params["cursor"] = cursor or "*"

    @abstractmethod
    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]: ...
