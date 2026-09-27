"""Deterministic Phase 5 fixtures. Production code never imports these."""

from datetime import UTC, date, datetime

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.evidence import SourceDates
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    DiscoveryPath,
    SourceAccessState,
    SourceRecord,
    SourceType,
    SourceVersionRecord,
    VersionKind,
)
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import (
    PassageLocator,
    PassageLocatorKind,
    PassageRecord,
)
from novelty_harness.evidence.provenance.models import (
    LineageConfidence,
    ProvenanceEdge,
    ProvenanceRelation,
)
from novelty_harness.research.retrieval.models import RetrievalMechanism, RetrievalStrategy

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def phase5_provenance(component: str = "phase5-fixture") -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="fixture",
        component=component,
        detail="Deterministic Phase 5 fixture; production components are not used here.",
    )


def make_discovery_path(**overrides: object) -> DiscoveryPath:
    values: dict[str, object] = {
        "provider_name": "openalex",
        "provider_source_id": "W1",
        "strategy": RetrievalStrategy.LEXICAL,
        "mechanism": RetrievalMechanism.TEXT_SEARCH,
        "evidence_family": EvidenceFamily.SCHOLARLY,
        "query_id": "qry_1",
        "local_rank": 1,
        "discovered_at": NOW,
    }
    values.update(overrides)
    return DiscoveryPath.model_validate(values)


def make_source(source_id: str = "src_alpha", **overrides: object) -> SourceRecord:
    values: dict[str, object] = {
        "source_id": source_id,
        "canonical_title": f"Source {source_id}",
        "source_type": SourceType.PAPER,
        "canonical_url": f"https://example.org/{source_id}",
        "identifiers": CanonicalIdentifiers(doi=f"10.9999/{source_id}"),
        "authors_or_owners": ("Ada Example",),
        "dates": SourceDates(publication_date=date(2020, 1, 1)),
        "languages": ("en",),
        "access_state": SourceAccessState.FULL_TEXT,
        "evidence_families": (EvidenceFamily.SCHOLARLY,),
        "content_hash": text_hash(f"Content of {source_id}"),
        "discovery_queries": ("qry_1",),
        "discovery_paths": (
            make_discovery_path(
                provider_source_id=f"W-{source_id}",
            ),
        ),
        "provenance": phase5_provenance("make_source"),
    }
    values.update(overrides)
    return SourceRecord.model_validate(values)


def make_passage(
    source_id: str = "src_alpha",
    *,
    text: str = "Exact passage text for the source.",
    **overrides: object,
) -> PassageRecord:
    values: dict[str, object] = {
        "passage_id": "pass_" + text_hash(f"{source_id}:{text}")[:16],
        "source_id": source_id,
        "text": text,
        "content_hash": text_hash(text),
        "access_state": SourceAccessState.FULL_TEXT,
        "locator": PassageLocator(kind=PassageLocatorKind.RESOLVED_CONTENT),
        "observed_at": NOW,
        "provenance": phase5_provenance("make_passage"),
    }
    values.update(overrides)
    return PassageRecord.model_validate(values)


def make_version(source_id: str = "src_alpha", **overrides: object) -> SourceVersionRecord:
    values: dict[str, object] = {
        "version_id": "srcv_" + source_id.removeprefix("src_") + "_v1",
        "source_id": source_id,
        "version_label": "v1",
        "version_kind": VersionKind.PREPRINT,
        "content_hash": text_hash(f"Content of {source_id}"),
        "access_state": SourceAccessState.FULL_TEXT,
        "observed_at": NOW,
        "provenance": phase5_provenance("make_version"),
    }
    values.update(overrides)
    return SourceVersionRecord.model_validate(values)


def make_edge(
    source_id: str,
    related_source_id: str,
    *,
    relation: ProvenanceRelation = ProvenanceRelation.CITES,
    lineage_confidence: LineageConfidence = LineageConfidence.CONFIRMED,
    **overrides: object,
) -> ProvenanceEdge:
    values: dict[str, object] = {
        "edge_id": "prov_" + text_hash(f"{source_id}|{related_source_id}|{relation.value}")[:20],
        "source_id": source_id,
        "related_source_id": related_source_id,
        "relation": relation,
        "lineage_confidence": lineage_confidence,
        "evidence": ("fixture:structured-metadata",),
        "observed_at": NOW,
        "provenance": phase5_provenance("make_edge"),
    }
    values.update(overrides)
    return ProvenanceEdge.model_validate(values)
