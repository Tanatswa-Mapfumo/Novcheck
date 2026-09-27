from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, FiniteFloat, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId, QueryId
from novelty_harness.ports.models import ProviderCallMetadata, SourceRef


class RetrievalStrategy(StrEnum):
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"
    RELATIONAL = "RELATIONAL"
    CITATION_BACKWARD = "CITATION_BACKWARD"
    CITATION_FORWARD = "CITATION_FORWARD"
    RELATED_WORK = "RELATED_WORK"
    ENTITY_LINEAGE = "ENTITY_LINEAGE"
    HISTORICAL_TERM = "HISTORICAL_TERM"
    ADJACENT_DOMAIN = "ADJACENT_DOMAIN"


class RetrievalMechanism(StrEnum):
    TEXT_SEARCH = "TEXT_SEARCH"
    SEMANTIC_SEARCH = "SEMANTIC_SEARCH"
    GRAPH_EXPANSION = "GRAPH_EXPANSION"
    ENTITY_LINEAGE = "ENTITY_LINEAGE"


def mechanism_for(strategy: RetrievalStrategy) -> RetrievalMechanism:
    if strategy == RetrievalStrategy.SEMANTIC:
        return RetrievalMechanism.SEMANTIC_SEARCH
    if strategy == RetrievalStrategy.ENTITY_LINEAGE:
        return RetrievalMechanism.ENTITY_LINEAGE
    if strategy in {
        RetrievalStrategy.CITATION_BACKWARD,
        RetrievalStrategy.CITATION_FORWARD,
        RetrievalStrategy.RELATED_WORK,
    }:
        return RetrievalMechanism.GRAPH_EXPANSION
    return RetrievalMechanism.TEXT_SEARCH


class RetrievalCandidate(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["retrieval-candidate-v1"] = "retrieval-candidate-v1"
    candidate_key: NonBlankText
    source: SourceRef
    mcu_id: MCUId | None
    evidence_family: EvidenceFamily
    provider_name: NonBlankText
    strategy: RetrievalStrategy
    query_id: QueryId | None
    local_rank: int = Field(ge=1)
    provider_score: FiniteFloat | None = None
    discovered_at: UTCDateTime
    raw_metadata: dict[str, JsonValue] = Field(default_factory=lambda: dict[str, JsonValue]())
    seed_source: SourceRef | None = None
    cursor: str | None = None

    @model_validator(mode="after")
    def identity_and_path(self) -> Self:
        if (
            self.source.provider_name != self.provider_name
            or not self.source.provider_source_id.strip()
        ):
            raise ValueError("Candidate must retain its nonblank provider-local source identity")
        if (
            self.strategy
            in {
                RetrievalStrategy.CITATION_BACKWARD,
                RetrievalStrategy.CITATION_FORWARD,
                RetrievalStrategy.RELATED_WORK,
                RetrievalStrategy.ENTITY_LINEAGE,
            }
            and self.seed_source is None
        ):
            raise ValueError("Expansion candidates require their discovery seed")
        if self.query_id is None and self.seed_source is None:
            raise ValueError("Discovery must retain a query or an expansion seed")
        return self


class RetrievalBatch(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["retrieval-batch-v1"] = "retrieval-batch-v1"
    strategy: RetrievalStrategy
    provider_name: NonBlankText
    candidates: tuple[RetrievalCandidate, ...]
    next_cursor: str | None = None
    exhausted: bool = False
    call: ProviderCallMetadata
    limitations: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def consistent_batch(self) -> Self:
        keys = [c.candidate_key for c in self.candidates]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate candidate identities within a retrieval batch")
        if self.call.provider_name != self.provider_name or any(
            c.provider_name != self.provider_name or c.strategy != self.strategy
            for c in self.candidates
        ):
            raise ValueError("Batch provider/strategy must match every candidate and call")
        if self.exhausted and self.next_cursor is not None:
            raise ValueError("Exhausted batch cannot advertise continuation")
        return self
