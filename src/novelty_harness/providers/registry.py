import os
from dataclasses import dataclass

from pydantic import ConfigDict, Field

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.ports.search import SearchProvider
from novelty_harness.providers.errors import FailureCategory, provider_error


class CredentialRef(ContractModel):
    model_config = ConfigDict(frozen=True)
    env_name: str = Field(pattern=r"^[A-Z_][A-Z0-9_]*$")

    def resolve(self) -> str | None:
        return os.environ.get(self.env_name)


class ProviderDescriptor(ContractModel):
    model_config = ConfigDict(frozen=True)
    name: NonBlankText
    evidence_families: frozenset[EvidenceFamily]
    search_capabilities: frozenset[NonBlankText]
    auth_mode: NonBlankText
    supports_pagination: bool
    supports_citations: bool = False
    supports_full_text: bool = False


class FallbackEvent(ContractModel):
    model_config = ConfigDict(frozen=True)
    primary: NonBlankText
    fallback: NonBlankText
    reason: NonBlankText


@dataclass(frozen=True)
class RegisteredProvider:
    provider: SearchProvider
    descriptor: ProviderDescriptor


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, RegisteredProvider] = {}
        self._fallbacks: list[FallbackEvent] = []

    def register(self, provider: SearchProvider, descriptor: ProviderDescriptor) -> None:
        if provider.name != descriptor.name or descriptor.name in self._providers:
            raise ValueError("descriptor must match a unique provider name")
        self._providers[descriptor.name] = RegisteredProvider(
            provider, descriptor.model_copy(deep=True)
        )

    def providers_for(self, family: EvidenceFamily) -> tuple[RegisteredProvider, ...]:
        return tuple(
            p for p in self._providers.values() if family in p.descriptor.evidence_families
        )

    def get(self, name: str) -> RegisteredProvider:
        if name not in self._providers:
            raise provider_error(
                name, FailureCategory.PROVIDER_UNAVAILABLE, "Provider not registered"
            )
        return self._providers[name]

    @property
    def fallbacks(self) -> tuple[FallbackEvent, ...]:
        return tuple(self._fallbacks)

    def record_fallback(self, primary: str, fallback: str, *, reason: str) -> None:
        self.get(fallback)
        self._fallbacks.append(FallbackEvent(primary=primary, fallback=fallback, reason=reason))
