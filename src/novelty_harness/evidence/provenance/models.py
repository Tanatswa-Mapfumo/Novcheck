from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import LineageClusterId, ProvenanceEdgeId, SourceId


class ProvenanceRelation(StrEnum):
    CITES = "CITES"
    DERIVES_FROM = "DERIVES_FROM"
    REPOSTS = "REPOSTS"
    VERSION_OF = "VERSION_OF"
    PATENT_FAMILY_OF = "PATENT_FAMILY_OF"
    IMPLEMENTS = "IMPLEMENTS"
    DOCUMENTS = "DOCUMENTS"
    FOUND_BY = "FOUND_BY"


#: Relations that make the subject dependent on the object for independence
#: accounting. Citation alone is deliberately excluded.
DEPENDENCY_RELATIONS = frozenset(
    {
        ProvenanceRelation.DERIVES_FROM,
        ProvenanceRelation.REPOSTS,
        ProvenanceRelation.VERSION_OF,
        ProvenanceRelation.PATENT_FAMILY_OF,
        ProvenanceRelation.IMPLEMENTS,
        ProvenanceRelation.DOCUMENTS,
    }
)

#: Relations that link sources without collapsing their independence.
ASSOCIATION_RELATIONS = frozenset({ProvenanceRelation.CITES, ProvenanceRelation.FOUND_BY})


class LineageConfidence(StrEnum):
    CONFIRMED = "CONFIRMED"
    POSSIBLE = "POSSIBLE"


class ProvenanceEdge(ContractModel):
    """A directed, evidence-backed provenance relation between two sources."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["provenance-edge-v1"] = "provenance-edge-v1"

    edge_id: ProvenanceEdgeId
    source_id: SourceId
    related_source_id: SourceId
    relation: ProvenanceRelation
    lineage_confidence: LineageConfidence
    evidence: tuple[NonBlankText, ...] = Field(min_length=1)
    observed_at: UTCDateTime
    provenance: ArtifactProvenance
    limitations: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def distinct_endpoints(self) -> Self:
        if self.source_id == self.related_source_id:
            raise ValueError("A provenance relation cannot point at itself")
        return self

    def is_dependency(self) -> bool:
        return self.relation in DEPENDENCY_RELATIONS


class EvidenceLineageCluster(ContractModel):
    """Conservative grouping of sources that share one underlying origin.

    ``source_ids`` is never an evidence count. ``independent_roots`` counts
    distinct underlying evidentiary roots only.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-lineage-cluster-v1"] = "evidence-lineage-cluster-v1"

    cluster_id: LineageClusterId
    source_ids: tuple[SourceId, ...] = Field(min_length=1)
    root_source_ids: tuple[SourceId, ...] = Field(min_length=1)
    independent_roots: int = Field(ge=1)
    rationale: tuple[NonBlankText, ...] = Field(min_length=1)
    unresolved_ambiguities: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Lineage cluster members must be unique")
        if len(set(self.root_source_ids)) != len(self.root_source_ids):
            raise ValueError("Lineage cluster roots must be unique")
        if not set(self.root_source_ids) <= set(self.source_ids):
            raise ValueError("Lineage cluster roots must be members")
        if self.independent_roots != len(self.root_source_ids):
            raise ValueError("Independent root count must equal the root set size")
        return self


class ProvenanceCycle(ContractModel):
    """Suspicious or merely informational circular dependency structure."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["provenance-cycle-v1"] = "provenance-cycle-v1"

    source_ids: tuple[SourceId, ...] = Field(min_length=1)
    relation_types: tuple[ProvenanceRelation, ...] = Field(min_length=1)
    severity: Literal["INFO", "WARNING", "MATERIAL"]
    explanation: NonBlankText
