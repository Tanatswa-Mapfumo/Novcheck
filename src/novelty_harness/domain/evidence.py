from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import (
    EvidenceFamily,
    EvidenceTier,
    PrecedentState,
    SupportVerificationState,
)
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import EvidenceEdgeId, MCUId, PassageId, QueryId, SourceId


class SourceDates(ContractModel):
    model_config = ConfigDict(frozen=True)
    publication_date: date | None = None
    first_public_version: date | None = None
    repository_created_at: date | None = None
    first_release_date: date | None = None
    patent_priority_date: date | None = None
    patent_publication_date: date | None = None
    product_launch_date: date | None = None
    archive_capture_date: date | None = None


class SourceRecord(ContractModel):
    model_config = ConfigDict(frozen=True)
    source_id: SourceId
    canonical_title: str | None = None
    source_type: NonBlankText
    canonical_url: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    authors_or_owners: tuple[str, ...] = ()
    dates: SourceDates = Field(default_factory=SourceDates)
    languages: tuple[str, ...] = ()
    access_state: Literal["full_text", "abstract_only", "metadata_only", "blocked"]
    content_hash: NonBlankText
    provider_name: NonBlankText
    provider_source_id: NonBlankText
    discovered_by_queries: tuple[QueryId, ...] = ()
    evidence_families: tuple[EvidenceFamily, ...] = ()
    provenance: ArtifactProvenance


class SourcePassage(ContractModel):
    model_config = ConfigDict(frozen=True)
    passage_id: PassageId
    source_id: SourceId
    text: NonBlankText
    locator: str | None = None
    content_hash: NonBlankText
    provenance: ArtifactProvenance


class EvidenceComparison(ContractModel):
    model_config = ConfigDict(frozen=True)
    matching_elements: tuple[str, ...] = ()
    matching_relationships: tuple[str, ...] = ()
    missing_elements: tuple[str, ...] = ()
    conflicting_elements: tuple[str, ...] = ()


class EvidenceEdge(ContractModel):
    model_config = ConfigDict(frozen=True)
    edge_id: EvidenceEdgeId
    source_id: SourceId
    mcu_id: MCUId
    proposition: NonBlankText
    passage_ids: tuple[PassageId, ...] = Field(min_length=1)
    comparison: EvidenceComparison
    relation_type: PrecedentState
    predates_cutoff: bool | None = None
    relevance_strength: str | None = None
    evidence_quality: EvidenceTier | None = None
    access_limitations: tuple[str, ...] = ()
    support_verification: SupportVerificationState
    provenance: ArtifactProvenance
