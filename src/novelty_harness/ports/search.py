from typing import Protocol, runtime_checkable

from novelty_harness.ports.models import (
    ProviderCapabilities,
    ProviderHealth,
    SearchPage,
    SearchQuery,
)


@runtime_checkable
class SearchProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def search(self, query: SearchQuery, cursor: str | None = None) -> SearchPage: ...
    async def capabilities(self) -> ProviderCapabilities: ...
    async def health(self) -> ProviderHealth: ...
