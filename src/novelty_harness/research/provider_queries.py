from datetime import date
from typing import Literal, Protocol, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import QueryId
from novelty_harness.research.models import SearchIntent


class CompiledProviderQuery(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["compiled-query-v1"] = "compiled-query-v1"
    query_id: QueryId
    provider_name: NonBlankText
    evidence_family: EvidenceFamily
    endpoint: NonBlankText
    method: Literal["GET", "POST"]
    params: dict[str, JsonValue] = Field(default_factory=dict)
    body: dict[str, JsonValue] | None = None
    headers_profile: NonBlankText | None = None
    compilation_notes: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def safe_request(self) -> Self:
        url = urlsplit(self.endpoint)
        if url.scheme != "https" or not url.netloc or url.query or url.username or url.fragment:
            raise ValueError("compiled endpoint must be a credential-free HTTPS endpoint")

        def inspect(value: JsonValue) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.casefold() in {
                        "api_key",
                        "token",
                        "access_token",
                        "authorization",
                        "mailto",
                        "email",
                        "password",
                    }:
                        raise ValueError(
                            "credentials and personal identification stay outside artifacts"
                        )
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        inspect(self.params)
        inspect(self.body)
        return self


class ProviderQueryCompiler(Protocol):
    def compile(self, intent: SearchIntent, *, as_of: date) -> CompiledProviderQuery: ...


def compile_intent(
    compiler: ProviderQueryCompiler, intent: SearchIntent, *, as_of: date
) -> CompiledProviderQuery:
    compiled = CompiledProviderQuery.model_validate(
        compiler.compile(intent.model_copy(deep=True), as_of=as_of).model_dump()
    )
    if compiled.query_id != intent.query_id or compiled.evidence_family != intent.evidence_family:
        raise ValueError("compiled query must preserve intent identity and family")
    return compiled
