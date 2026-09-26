"""Shared transport checks for fixture-backed provider adapters; never enable sockets."""

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.ports.citations import CitationProvider
from novelty_harness.ports.content import ContentResolver
from novelty_harness.ports.embeddings import EmbeddingProvider
from novelty_harness.ports.llm import LLMProvider
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
from novelty_harness.ports.reranking import Reranker
from novelty_harness.ports.search import SearchProvider


def _assert_model[T: ContractModel](value: object, model_type: type[T]) -> T:
    assert isinstance(value, model_type)
    assert model_type.model_validate_json(value.model_dump_json()) == value
    return value


def _assert_call(name: str, call: ProviderCallMetadata) -> None:
    _assert_model(call, ProviderCallMetadata)
    assert call.provider_name == name
    assert call.provider_name and call.request_hash
    assert call.started_at.utcoffset() is not None
    assert call.finished_at.utcoffset() is not None


async def assert_search_provider_contract(
    provider: SearchProvider,
    query: SearchQuery | None = None,
) -> None:
    assert provider.name
    _assert_model(await provider.capabilities(), ProviderCapabilities)
    _assert_model(await provider.health(), ProviderHealth)
    query = query or SearchQuery(
        query_id="qry_contract",
        text="contract query",
        purpose="transport contract",
        evidence_family=EvidenceFamily.SCHOLARLY,
    )
    page = _assert_model(await provider.search(query), SearchPage)
    _assert_call(provider.name, page.call)
    if page.next_cursor is not None:
        next_page = _assert_model(await provider.search(query, page.next_cursor), SearchPage)
        _assert_call(provider.name, next_page.call)


async def assert_content_resolver_contract(
    provider: ContentResolver,
    source: SourceRef | None = None,
    locator: str = "section-1",
) -> None:
    source = source or SourceRef(provider_name=provider.name, provider_source_id="contract-source")
    content = _assert_model(await provider.resolve(source), SourceContent)
    _assert_call(provider.name, content.call)
    assert content.source == source
    passage = _assert_model(await provider.resolve_passage(source, locator), Passage)
    assert passage.source == source
    assert passage.locator == locator


async def assert_citation_provider_contract(
    provider: CitationProvider,
    source: SourceRef | None = None,
) -> None:
    source = source or SourceRef(provider_name=provider.name, provider_source_id="contract-source")
    for method, relation in (
        (provider.backward_citations, "BACKWARD_CITATION"),
        (provider.forward_citations, "FORWARD_CITATION"),
        (provider.related, "RELATED"),
    ):
        result = _assert_model(await method(source), CitationResult)
        _assert_call(provider.name, result.call)
        assert all(link.source == source and link.relation == relation for link in result.links)


async def assert_llm_provider_contract(provider: LLMProvider) -> None:
    result = _assert_model(
        await provider.generate_structured(
            task="contract",
            schema={"type": "object"},
            context=[ContextBlock(label="evidence", text="Untrusted fixture content")],
            config=LLMCallConfig(),
        ),
        StructuredResult,
    )
    _assert_call(provider.name, result.call)


async def assert_embedding_provider_contract(provider: EmbeddingProvider) -> None:
    result = _assert_model(await provider.embed(["first", "second"]), EmbeddingResult)
    _assert_call(provider.name, result.call)
    assert len(result.vectors) == 2
    assert result.vectors[0]
    assert len(result.vectors[0]) == len(result.vectors[1])


async def assert_reranker_contract(provider: Reranker) -> None:
    candidates = ["first", "second"]
    result = _assert_model(await provider.rank("query", candidates), RerankResult)
    _assert_call(provider.name, result.call)
    candidate_ids = [candidate.candidate_id for candidate in result.candidates]
    ranks = [candidate.rank for candidate in result.candidates]
    assert all(candidate_id in candidates for candidate_id in candidate_ids)
    assert len(candidate_ids) == len(set(candidate_ids))
    assert all(1 <= rank <= len(candidates) for rank in ranks)
    assert len(ranks) == len(set(ranks))
