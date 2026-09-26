from typing import Literal

from pydantic import Field, JsonValue

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import EvidenceFamily, TraceStatus
from novelty_harness.domain.ids import PassageId, QueryId


class ProviderCallMetadata(ContractModel):
    provider_name: str
    provider_version: str | None = None
    started_at: UTCDateTime
    finished_at: UTCDateTime
    request_hash: str
    status: TraceStatus
    failure_code: str | None = None


class ProviderCapabilities(ContractModel):
    evidence_families: set[EvidenceFamily] = Field(default_factory=set[EvidenceFamily])
    supports_pagination: bool = False
    supports_full_text: bool = False
    supports_backward_citations: bool = False
    supports_forward_citations: bool = False


class ProviderHealth(ContractModel):
    healthy: bool
    detail: str | None = None


class SearchQuery(ContractModel):
    query_id: QueryId
    text: str
    evidence_family: EvidenceFamily
    purpose: str
    filters: dict[str, JsonValue] = Field(default_factory=dict)


class SourceRef(ContractModel):
    provider_name: str
    provider_source_id: str
    canonical_url: str | None = None
    title: str | None = None


class SearchResult(ContractModel):
    source: SourceRef
    rank: int
    snippet: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SearchPage(ContractModel):
    results: list[SearchResult]
    next_cursor: str | None = None
    call: ProviderCallMetadata


class SourceContent(ContractModel):
    source: SourceRef
    text: str | None
    content_type: str | None = None
    call: ProviderCallMetadata


class Passage(ContractModel):
    passage_id: PassageId
    source: SourceRef
    text: str
    locator: str | None = None


class CitationLink(ContractModel):
    source: SourceRef
    related: SourceRef
    relation: Literal["BACKWARD_CITATION", "FORWARD_CITATION", "RELATED"]


class CitationResult(ContractModel):
    links: list[CitationLink]
    call: ProviderCallMetadata


class EmbeddingResult(ContractModel):
    vectors: list[list[float]]
    call: ProviderCallMetadata


class ContextBlock(ContractModel):
    label: str
    text: str
    trusted_instruction: bool = False


class LLMCallConfig(ContractModel):
    model: str | None = None
    temperature: float | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class StructuredResult(ContractModel):
    data: dict[str, JsonValue]
    raw_text: str | None = None
    call: ProviderCallMetadata


class RankedCandidate(ContractModel):
    candidate_id: str
    score: float
    rank: int


class RerankResult(ContractModel):
    candidates: list[RankedCandidate]
    call: ProviderCallMetadata
