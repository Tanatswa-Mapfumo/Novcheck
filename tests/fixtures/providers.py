"""Deterministic fixture providers. No retrieval or model computation occurs here."""

from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from novelty_harness.domain.base import ContractModel
from novelty_harness.ports.models import (
    CitationResult,
    ContextBlock,
    EmbeddingResult,
    LLMCallConfig,
    Passage,
    ProviderCallMetadata,
    ProviderCapabilities,
    ProviderHealth,
    RerankResult,
    SearchPage,
    SearchQuery,
    SourceContent,
    SourceRef,
    StructuredResult,
)


class _MockProvider:
    def __init__(self, name: str) -> None:
        self._name = name
        self._calls: list[ProviderCallMetadata] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def calls(self) -> tuple[ProviderCallMetadata, ...]:
        return tuple(call.model_copy(deep=True) for call in self._calls)

    def _respond[T: ContractModel](self, result: T, call: ProviderCallMetadata) -> T:
        self._calls.append(call.model_copy(deep=True))
        return result.model_copy(deep=True)


class MockSearchProvider(_MockProvider):
    def __init__(
        self,
        *,
        name: str,
        query: SearchQuery,
        pages: Mapping[str | None, SearchPage],
        capabilities: ProviderCapabilities,
        health: ProviderHealth,
        capabilities_call: ProviderCallMetadata,
        health_call: ProviderCallMetadata,
    ) -> None:
        super().__init__(name)
        self._query = query.model_copy(deep=True)
        self._pages = {cursor: page.model_copy(deep=True) for cursor, page in pages.items()}
        self._capabilities = capabilities.model_copy(deep=True)
        self._health = health.model_copy(deep=True)
        self._capabilities_call = capabilities_call.model_copy(deep=True)
        self._health_call = health_call.model_copy(deep=True)

    async def search(self, query: SearchQuery, cursor: str | None = None) -> SearchPage:
        if query != self._query:
            raise ValueError("query has no configured fixture")
        page = self._pages[cursor]
        return self._respond(page, page.call)

    async def capabilities(self) -> ProviderCapabilities:
        return self._respond(self._capabilities, self._capabilities_call)

    async def health(self) -> ProviderHealth:
        return self._respond(self._health, self._health_call)


class MockContentResolver(_MockProvider):
    def __init__(
        self,
        *,
        name: str,
        content: SourceContent,
        passage: Passage,
        passage_call: ProviderCallMetadata,
    ) -> None:
        super().__init__(name)
        self._content = content.model_copy(deep=True)
        self._passage = passage.model_copy(deep=True)
        self._passage_call = passage_call.model_copy(deep=True)

    async def resolve(self, source_ref: SourceRef) -> SourceContent:
        if source_ref != self._content.source:
            raise ValueError("source has no configured fixture")
        return self._respond(self._content, self._content.call)

    async def resolve_passage(self, source_ref: SourceRef, locator: str) -> Passage:
        if source_ref != self._passage.source or locator != self._passage.locator:
            raise ValueError("passage has no configured fixture")
        return self._respond(self._passage, self._passage_call)


class MockCitationProvider(_MockProvider):
    def __init__(
        self,
        *,
        name: str,
        source: SourceRef,
        results: Mapping[str, CitationResult],
    ) -> None:
        super().__init__(name)
        self._source = source.model_copy(deep=True)
        self._results = {
            relation: result.model_copy(deep=True) for relation, result in results.items()
        }

    def _result(self, source: SourceRef, relation: str) -> CitationResult:
        if source != self._source:
            raise ValueError("source has no configured fixture")
        result = self._results[relation]
        return self._respond(result, result.call)

    async def backward_citations(self, source_ref: SourceRef) -> CitationResult:
        return self._result(source_ref, "BACKWARD_CITATION")

    async def forward_citations(self, source_ref: SourceRef) -> CitationResult:
        return self._result(source_ref, "FORWARD_CITATION")

    async def related(self, source_ref: SourceRef) -> CitationResult:
        return self._result(source_ref, "RELATED")


class MockLLMProvider(_MockProvider):
    def __init__(self, *, name: str, result: StructuredResult) -> None:
        super().__init__(name)
        self._result = result.model_copy(deep=True)

    async def generate_structured(
        self,
        *,
        task: str,
        schema: dict[str, JsonValue],
        context: Sequence[ContextBlock],
        config: LLMCallConfig,
    ) -> StructuredResult:
        return self._respond(self._result, self._result.call)


class MockEmbeddingProvider(_MockProvider):
    def __init__(self, *, name: str, result: EmbeddingResult) -> None:
        super().__init__(name)
        self._result = result.model_copy(deep=True)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        return self._respond(self._result, self._result.call)


class MockReranker(_MockProvider):
    def __init__(self, *, name: str, result: RerankResult) -> None:
        super().__init__(name)
        self._result = result.model_copy(deep=True)

    async def rank(self, query_representation: str, candidates: Sequence[str]) -> RerankResult:
        return self._respond(self._result, self._result.call)
