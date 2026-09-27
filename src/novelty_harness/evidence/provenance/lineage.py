"""Construct traceable provenance relations from explicit evidence.

Every edge carries the evidence that established it. Structured metadata
(citation lists, version numbers, patent-family identifiers, retrieval
records) can establish ``CONFIRMED`` lineage. Textual or inferential signals
stay ``POSSIBLE`` until a later phase verifies them; model speculation never
creates ``CONFIRMED`` lineage.
"""

from collections.abc import Sequence

from pydantic import JsonValue

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.normalization.models import SourceRecord
from novelty_harness.evidence.provenance.models import (
    LineageConfidence,
    ProvenanceEdge,
    ProvenanceRelation,
)
from novelty_harness.research.retrieval.models import RetrievalStrategy
from novelty_harness.runtime.tracing.hashing import canonical_hash


def provenance_edge(
    *,
    source_id: SourceId,
    related_source_id: SourceId,
    relation: ProvenanceRelation,
    evidence: Sequence[str],
    confidence: LineageConfidence,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """Build one deterministic provenance edge; identity covers its evidence."""

    evidence_values: list[JsonValue] = [str(item) for item in sorted(set(evidence))]
    payload: JsonValue = {
        "source_id": str(source_id),
        "related_source_id": str(related_source_id),
        "relation": relation.value,
        "evidence": evidence_values,
    }
    return ProvenanceEdge(
        edge_id="prov_" + canonical_hash(payload),
        source_id=source_id,
        related_source_id=related_source_id,
        relation=relation,
        lineage_confidence=confidence,
        evidence=tuple(dict.fromkeys(evidence)),
        observed_at=observed_at,
        provenance=provenance,
        limitations=tuple(limitations),
    )


def citation_edge(
    *,
    citing: SourceId,
    cited: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.CONFIRMED,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``citing CITES cited`` from a structured reference list."""

    return provenance_edge(
        source_id=citing,
        related_source_id=cited,
        relation=ProvenanceRelation.CITES,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def derivation_edge(
    *,
    derivative: SourceId,
    origin: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.POSSIBLE,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``derivative DERIVES_FROM origin``; textual hints stay POSSIBLE."""

    return provenance_edge(
        source_id=derivative,
        related_source_id=origin,
        relation=ProvenanceRelation.DERIVES_FROM,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def repost_edge(
    *,
    repost: SourceId,
    original: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.POSSIBLE,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``repost REPOSTS original`` for mirrors and syndicated copies."""

    return provenance_edge(
        source_id=repost,
        related_source_id=original,
        relation=ProvenanceRelation.REPOSTS,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def version_edge(
    *,
    version: SourceId,
    version_of: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.CONFIRMED,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``version VERSION_OF version_of`` from explicit version metadata."""

    return provenance_edge(
        source_id=version,
        related_source_id=version_of,
        relation=ProvenanceRelation.VERSION_OF,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def patent_family_edge(
    *,
    member: SourceId,
    family_primary: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.CONFIRMED,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``member PATENT_FAMILY_OF family_primary`` from family metadata."""

    return provenance_edge(
        source_id=member,
        related_source_id=family_primary,
        relation=ProvenanceRelation.PATENT_FAMILY_OF,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def implementation_edge(
    *,
    implementation: SourceId,
    specification: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.POSSIBLE,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``implementation IMPLEMENTS specification``."""

    return provenance_edge(
        source_id=implementation,
        related_source_id=specification,
        relation=ProvenanceRelation.IMPLEMENTS,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def documentation_edge(
    *,
    documentation: SourceId,
    artifact: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.POSSIBLE,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``documentation DOCUMENTS artifact``."""

    return provenance_edge(
        source_id=documentation,
        related_source_id=artifact,
        relation=ProvenanceRelation.DOCUMENTS,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def found_by_edge(
    *,
    found: SourceId,
    seed: SourceId,
    evidence: Sequence[str],
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    confidence: LineageConfidence = LineageConfidence.CONFIRMED,
    limitations: Sequence[str] = (),
) -> ProvenanceEdge:
    """``found FOUND_BY seed``: the retrieval record of an expansion path."""

    return provenance_edge(
        source_id=found,
        related_source_id=seed,
        relation=ProvenanceRelation.FOUND_BY,
        evidence=evidence,
        confidence=confidence,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
    )


def _canonical_by_provider_identity(
    sources: Sequence[SourceRecord],
) -> dict[tuple[str, str], str]:
    lookup: dict[tuple[str, str], str] = {}
    for source in sources:
        for path in source.discovery_paths:
            lookup.setdefault((path.provider_name, path.provider_source_id), source.source_id)
    return lookup


def retrieval_provenance_edges(
    sources: Sequence[SourceRecord],
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
) -> tuple[ProvenanceEdge, ...]:
    """Preserve Phase 4 citation/entity expansion origin as graph relations.

    Backward citation discovery means the discovered candidate appears in the
    seed's reference list, so ``found CITES seed``. Forward citation discovery
    means the seed is cited by the discovered candidate, so ``seed CITES
    found``. Related-work and entity-lineage expansion keep ``FOUND_BY`` only,
    because they establish discovery, not a citation.
    """

    lookup = _canonical_by_provider_identity(sources)
    edges: dict[str, ProvenanceEdge] = {}
    for source in sources:
        for path in source.discovery_paths:
            if path.seed_source is None:
                continue
            seed_identity = (
                path.seed_source.provider_name,
                path.seed_source.provider_source_id,
            )
            seed_id = lookup.get(seed_identity)
            if seed_id is None or seed_id == source.source_id:
                continue
            evidence = (
                f"{path.provider_name}:{path.strategy.value}",
                f"seed:{path.seed_source.provider_name}:{path.seed_source.provider_source_id}",
                f"query:{path.query_id}" if path.query_id else "expansion",
            )
            found = found_by_edge(
                found=source.source_id,
                seed=seed_id,
                evidence=evidence,
                observed_at=observed_at,
                provenance=provenance,
            )
            edges[found.edge_id] = found
            if path.strategy == RetrievalStrategy.CITATION_BACKWARD:
                edge = citation_edge(
                    citing=source.source_id,
                    cited=seed_id,
                    evidence=(*evidence, "provider:reference-list"),
                    observed_at=observed_at,
                    provenance=provenance,
                )
                edges[edge.edge_id] = edge
            elif path.strategy == RetrievalStrategy.CITATION_FORWARD:
                edge = citation_edge(
                    citing=seed_id,
                    cited=source.source_id,
                    evidence=(*evidence, "provider:forward-citations"),
                    observed_at=observed_at,
                    provenance=provenance,
                )
                edges[edge.edge_id] = edge
    return tuple(edges[key] for key in sorted(edges))
