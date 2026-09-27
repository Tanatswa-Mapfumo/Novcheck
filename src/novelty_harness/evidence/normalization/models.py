from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.evidence import SourceDates
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import MCUId, QueryId, SearchRunId, SourceId, SourceVersionId
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.retrieval.models import RetrievalMechanism, RetrievalStrategy


class SourceAccessState(StrEnum):
    """What was actually accessible, independent of what the source is."""

    FULL_TEXT = "FULL_TEXT"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    BLOCKED = "BLOCKED"


class SourceType(StrEnum):
    PAPER = "PAPER"
    PREPRINT = "PREPRINT"
    PATENT = "PATENT"
    REPOSITORY = "REPOSITORY"
    PRODUCT = "PRODUCT"
    STANDARD = "STANDARD"
    GOVERNMENT = "GOVERNMENT"
    REPORT = "REPORT"
    WEB = "WEB"
    DATASET = "DATASET"
    OTHER = "OTHER"


class VersionKind(StrEnum):
    PREPRINT = "PREPRINT"
    JOURNAL = "JOURNAL"
    REPOSITORY_RELEASE = "REPOSITORY_RELEASE"
    PATENT_PUBLICATION = "PATENT_PUBLICATION"
    ARCHIVE_SNAPSHOT = "ARCHIVE_SNAPSHOT"
    GENERIC = "GENERIC"


class CanonicalIdentifiers(ContractModel):
    """Canonical global/local identifiers; values are already normalized.

    Normalization itself lives in :mod:`novelty_harness.evidence.normalization.identifiers`.
    Nothing here infers identity from titles.
    """

    model_config = ConfigDict(frozen=True)

    doi: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    arxiv_id: str | None = None
    patent_numbers: tuple[NonBlankText, ...] = ()
    repository: str | None = None
    other: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def nonblank_values(self) -> Self:
        values: list[str | None] = [
            self.doi,
            self.openalex_id,
            self.semantic_scholar_id,
            self.arxiv_id,
            self.repository,
            *self.patent_numbers,
            *self.other.values(),
        ]
        if any(value is not None and not value.strip() for value in values):
            raise ValueError("Identifiers cannot be blank")
        return self

    def is_empty(self) -> bool:
        return not any(
            (
                self.doi,
                self.openalex_id,
                self.semantic_scholar_id,
                self.arxiv_id,
                self.patent_numbers,
                self.repository,
                self.other,
            )
        )


class DiscoveryPath(ContractModel):
    """One retrieval path that discovered a candidate for a canonical source.

    Identity excludes rank/time so identical repeated paths collapse without
    losing the provider/strategy/query/search-run/seed provenance.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["discovery-path-v1"] = "discovery-path-v1"

    provider_name: NonBlankText
    provider_source_id: NonBlankText
    strategy: RetrievalStrategy
    mechanism: RetrievalMechanism
    evidence_family: EvidenceFamily
    query_id: QueryId | None = None
    search_run_id: SearchRunId | None = None
    seed_source: SourceRef | None = None
    mcu_id: MCUId | None = None
    local_rank: int | None = Field(default=None, ge=1)
    discovered_at: UTCDateTime

    def path_key(self) -> tuple[str, ...]:
        """Stable path identity ignoring rank and observation time."""

        seed = (
            (self.seed_source.provider_name, self.seed_source.provider_source_id)
            if self.seed_source
            else ("", "")
        )
        return (
            self.provider_name,
            self.provider_source_id,
            self.strategy.value,
            self.mechanism.value,
            self.evidence_family.value,
            self.query_id or "",
            self.search_run_id or "",
            seed[0],
            seed[1],
            self.mcu_id or "",
        )


class SourceRecord(ContractModel):
    """Canonical, storage-independent source identity.

    Retrieved candidate identity is retained in ``discovery_paths`` and never
    promoted to canonical identity. Stable global identifiers outrank any
    fuzzy or title-based matching.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["canonical-source-v1"] = "canonical-source-v1"

    source_id: SourceId
    canonical_title: NonBlankText
    source_type: SourceType
    canonical_url: str | None = None
    identifiers: CanonicalIdentifiers = Field(default_factory=CanonicalIdentifiers)
    authors_or_owners: tuple[NonBlankText, ...] = ()
    dates: SourceDates = Field(default_factory=SourceDates)
    languages: tuple[NonBlankText, ...] = ()
    access_state: SourceAccessState
    evidence_families: tuple[EvidenceFamily, ...] = ()
    content_hash: NonBlankText | None = None
    discovery_queries: tuple[QueryId, ...] = ()
    discovery_paths: tuple[DiscoveryPath, ...] = ()
    limitations: tuple[NonBlankText, ...] = ()
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def content_state_matches_hash(self) -> Self:
        hashed_states = {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}
        if self.access_state in hashed_states and self.content_hash is None:
            raise ValueError("Resolved content access requires a content hash")
        return self

    def has_stable_identity(self) -> bool:
        return not self.identifiers.is_empty()


class SourceVersionRecord(ContractModel):
    """One observed version of a canonical source.

    A changed content hash creates a new version record; nothing is silently
    overwritten. Hash equality never implies conceptual equivalence.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["source-version-v1"] = "source-version-v1"

    version_id: SourceVersionId
    source_id: SourceId
    version_label: NonBlankText
    version_kind: VersionKind
    content_hash: NonBlankText
    access_state: SourceAccessState
    identifiers: CanonicalIdentifiers = Field(default_factory=CanonicalIdentifiers)
    published_date: date | None = None
    predecessor_version_id: SourceVersionId | None = None
    limitations: tuple[NonBlankText, ...] = ()
    observed_at: UTCDateTime
    provenance: ArtifactProvenance


class ResolvedContent(ContractModel):
    """Honest description of what content resolution actually returned."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["resolved-content-v1"] = "resolved-content-v1"

    access_state: SourceAccessState
    text: str | None = None
    abstract: str | None = None
    content_type: str | None = None
    limitations: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def state_matches_payload(self) -> Self:
        if self.access_state == SourceAccessState.FULL_TEXT:
            if self.text is None or not self.text.strip():
                raise ValueError("FULL_TEXT resolution requires resolved text")
        elif self.access_state == SourceAccessState.ABSTRACT_ONLY:
            payload = self.text if self.text is not None else self.abstract
            if payload is None or not payload.strip():
                raise ValueError("ABSTRACT_ONLY resolution requires an abstract")
        elif self.text is not None or self.abstract is not None:
            raise ValueError("Metadata-only/blocked resolution cannot carry content")
        return self


class SourceNormalizationResult(ContractModel):
    """One canonical source plus its newest version and honest uncertainty."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["source-normalization-v1"] = "source-normalization-v1"

    source: SourceRecord
    version: SourceVersionRecord | None = None
    conflicts: tuple[NonBlankText, ...] = ()
    unresolved_fields: tuple[NonBlankText, ...] = ()
    merged_candidate_keys: tuple[NonBlankText, ...] = ()
