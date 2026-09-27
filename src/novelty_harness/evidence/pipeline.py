"""Phase 5 evidence-normalization pipeline.

Consumes Phase 4 candidate clusters, resolves content where possible,
normalizes canonical sources and versions, extracts exact passages, builds
provenance and lineage, assesses quality separately from relevance, and
persists an auditable evidence graph. No Phase 6 equivalence/support
adjudication happens here.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import JsonValue

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import AssessmentStage, TraceStatus
from novelty_harness.domain.evidence import SourceDates
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import AssessmentId, SourceId, new_trace_event_id
from novelty_harness.evidence.graph.models import GraphEdge, GraphNode
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository
from novelty_harness.evidence.graph.retrieval_mapping import (
    discovery_graph,
    passage_graph_node,
    provenance_graph_edges,
    version_graph_node,
)
from novelty_harness.evidence.normalization.identifiers import (
    canonical_source_identity,
    merge_identifiers,
)
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    ResolvedContent,
    SourceAccessState,
    SourceRecord,
    SourceType,
    SourceVersionRecord,
)
from novelty_harness.evidence.normalization.source_normalizer import (
    merge_paths,
    normalize_candidate_cluster,
)
from novelty_harness.evidence.normalization.versions import version_id_for
from novelty_harness.evidence.passages.extraction import extract_abstract, extract_resolved_content
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.provenance.circularity import detect_provenance_cycles
from novelty_harness.evidence.provenance.clustering import build_lineage_clusters
from novelty_harness.evidence.provenance.lineage import retrieval_provenance_edges
from novelty_harness.evidence.provenance.models import (
    EvidenceLineageCluster,
    ProvenanceCycle,
    ProvenanceEdge,
)
from novelty_harness.evidence.quality.assessment import (
    assess_quality,
    signals_from_source_structure,
    unassessed_relevance,
)
from novelty_harness.evidence.quality.models import (
    EvidenceQualityAssessment,
    SourceRelevanceAssessment,
)
from novelty_harness.ports.content import ContentResolver
from novelty_harness.research.adaptive.pipeline import ResearchResult
from novelty_harness.research.retrieval.models import RetrievalCandidate
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink

_ACCESS_PREFERENCE = {
    SourceAccessState.FULL_TEXT: 3,
    SourceAccessState.ABSTRACT_ONLY: 2,
    SourceAccessState.METADATA_ONLY: 1,
    SourceAccessState.BLOCKED: 0,
}

_PROVIDER_PRECEDENCE = ("crossref", "openalex", "semantic_scholar", "arxiv", "github")

_PIPELINE_PROVENANCE = ArtifactProvenance(
    kind="implemented",
    component="evidence_normalization",
    detail="Canonical normalization, provenance and quality; no Phase 6 adjudication.",
)


@dataclass(frozen=True, slots=True)
class EvidenceNormalizationResult:
    sources: tuple[SourceRecord, ...]
    versions: tuple[SourceVersionRecord, ...]
    passages: tuple[PassageRecord, ...]
    provenance_edges: tuple[ProvenanceEdge, ...]
    lineage_clusters: tuple[EvidenceLineageCluster, ...]
    quality_assessments: tuple[EvidenceQualityAssessment, ...]
    relevance_assessments: tuple[SourceRelevanceAssessment, ...]
    cycles: tuple[ProvenanceCycle, ...]
    conflicts: tuple[str, ...]
    unresolved_fields: tuple[str, ...]
    limitations: tuple[str, ...]
    graph_ref: str


def _provider_rank(name: str) -> tuple[int, str]:
    if name in _PROVIDER_PRECEDENCE:
        return (_PROVIDER_PRECEDENCE.index(name), name)
    return (len(_PROVIDER_PRECEDENCE), name)


def _best_candidate(candidates: Sequence[RetrievalCandidate]) -> RetrievalCandidate:
    return min(
        candidates,
        key=lambda candidate: (
            *_provider_rank(candidate.provider_name),
            candidate.source.provider_source_id,
            candidate.strategy.value,
        ),
    )


def _abstract_from_metadata(candidate: RetrievalCandidate) -> str | None:
    abstract = candidate.raw_metadata.get("abstract")
    if isinstance(abstract, str) and abstract.strip():
        return abstract
    return None


async def _resolve_content(
    candidates: Sequence[RetrievalCandidate],
    resolver: ContentResolver | None,
) -> ResolvedContent | None:
    if resolver is None:
        return None
    candidate = _best_candidate(candidates)
    reference = candidate.source
    try:
        content = await resolver.resolve(reference)
    except Exception as error:  # provider/transport failures are explicit access limits
        abstract = _abstract_from_metadata(candidate)
        if abstract is not None:
            return ResolvedContent(
                access_state=SourceAccessState.ABSTRACT_ONLY,
                abstract=abstract,
                limitations=(
                    f"Full text resolution failed ({type(error).__name__}); "
                    "provider-supplied abstract only",
                ),
            )
        return ResolvedContent(
            access_state=SourceAccessState.BLOCKED,
            limitations=(f"Full text resolution failed ({type(error).__name__})",),
        )
    if content.source != reference:
        raise ValueError("Resolved content does not match the requested source")
    if content.text is not None and content.text.strip():
        return ResolvedContent(
            access_state=SourceAccessState.FULL_TEXT,
            text=content.text,
            content_type=content.content_type,
        )
    abstract = _abstract_from_metadata(candidate)
    if abstract is not None:
        return ResolvedContent(
            access_state=SourceAccessState.ABSTRACT_ONLY,
            abstract=abstract,
            limitations=("Resolution returned no full text; provider-supplied abstract only",),
        )
    return ResolvedContent(
        access_state=SourceAccessState.METADATA_ONLY,
        limitations=("Content resolution returned no usable text",),
    )


def _identifier_overlap(left: CanonicalIdentifiers, right: CanonicalIdentifiers) -> bool:
    """Whether two records share identity evidence without conflicting."""

    for field in ("doi", "repository"):
        left_value, right_value = getattr(left, field), getattr(right, field)
        if left_value is not None and right_value is not None and left_value != right_value:
            return False
    if (
        left.patent_numbers
        and right.patent_numbers
        and not set(left.patent_numbers) & set(right.patent_numbers)
    ):
        return False
    shared_other = set(left.other.items()) & set(right.other.items())
    if any(
        key in left.other and key in right.other and left.other[key] != right.other[key]
        for key in set(left.other) & set(right.other)
    ):
        return False
    return any(
        (
            left.doi is not None and left.doi == right.doi,
            left.repository is not None and left.repository == right.repository,
            left.arxiv_id is not None and left.arxiv_id == right.arxiv_id,
            left.openalex_id is not None and left.openalex_id == right.openalex_id,
            left.semantic_scholar_id is not None
            and left.semantic_scholar_id == right.semantic_scholar_id,
            bool(set(left.patent_numbers) & set(right.patent_numbers)),
            bool(shared_other),
        )
    )


def _merge_source_group(
    results: Sequence[tuple[str, SourceRecord, ResolvedContent | None]],
) -> tuple[SourceRecord, tuple[str, ...], tuple[str, ...]]:
    """Merge normalized cluster results that share canonical identity evidence."""

    ordered = sorted(results, key=lambda item: (item[1].source_id, item[0]))
    first = ordered[0][1]
    conflicts: list[str] = []
    unresolved: list[str] = []

    merge = merge_identifiers([record.identifiers for _, record, _ in ordered])
    urls = tuple(sorted({record.canonical_url for _, record, _ in ordered if record.canonical_url}))
    discovery_ids = [
        (path.provider_name, path.provider_source_id)
        for _, record, _ in ordered
        for path in record.discovery_paths
    ]
    identity = canonical_source_identity(merge.identifiers, urls=urls, discovery_ids=discovery_ids)

    titles = {record.canonical_title for _, record, _ in ordered}
    if len(titles) > 1:
        conflicts.append("merged.title: " + " | ".join(sorted(titles)))

    date_fields: dict[str, set[date]] = {}
    for _, record, _ in ordered:
        for field in SourceDates.model_fields:
            value = getattr(record.dates, field)
            if value is not None:
                date_fields.setdefault(field, set()).add(value)
    for field_name, values in sorted(date_fields.items()):
        if len(values) > 1:
            conflicts.append(
                "merged.dates."
                + field_name
                + ": "
                + " | ".join(sorted(value.isoformat() for value in values))
            )

    best_access = max(
        (record.access_state for _, record, _ in ordered),
        key=lambda state: _ACCESS_PREFERENCE[state],
    )
    best_record = next(record for _, record, _ in ordered if record.access_state == best_access)

    paths = merge_paths([path for _, record, _ in ordered for path in record.discovery_paths])

    authors = tuple(
        dict.fromkeys(author for _, record, _ in ordered for author in record.authors_or_owners)
    )
    languages = tuple(
        sorted({language for _, record, _ in ordered for language in record.languages})
    )
    families = tuple(
        dict.fromkeys(family for _, record, _ in ordered for family in record.evidence_families)
    )
    queries = tuple(
        dict.fromkeys(query for _, record, _ in ordered for query in record.discovery_queries)
    )
    limitations = tuple(
        dict.fromkeys(limit for _, record, _ in ordered for limit in record.limitations)
    )
    type_priority = {
        SourceType.PAPER: 6,
        SourceType.PREPRINT: 5,
        SourceType.PATENT: 5,
        SourceType.REPOSITORY: 5,
        SourceType.DATASET: 5,
        SourceType.STANDARD: 5,
        SourceType.GOVERNMENT: 4,
        SourceType.REPORT: 3,
        SourceType.PRODUCT: 2,
        SourceType.WEB: 1,
        SourceType.OTHER: 0,
    }
    most_specific = max(
        (record.source_type for _, record, _ in ordered),
        key=lambda source_type: type_priority[source_type],
    )
    if len({record.source_type for _, record, _ in ordered}) > 1:
        conflicts.append(
            "merged.source_type: "
            + " | ".join(sorted({record.source_type.value for _, record, _ in ordered}))
        )

    merged = first.model_copy(
        update={
            "source_id": identity.source_id,
            "canonical_title": best_record.canonical_title,
            "source_type": most_specific,
            "canonical_url": best_record.canonical_url or next((url for url in urls), None),
            "identifiers": merge.identifiers,
            "authors_or_owners": authors,
            "dates": best_record.dates,
            "languages": languages,
            "access_state": best_access,
            "content_hash": best_record.content_hash,
            "evidence_families": families,
            "discovery_queries": queries,
            "discovery_paths": paths,
            "limitations": limitations,
        }
    )
    if not identity.stable:
        conflicts.append(
            "merged.identity: no stable canonical identifier; identity scoped to merged records"
        )
        unresolved.append("identity")
    unresolved.extend(merge.unresolved)
    return merged, tuple(dict.fromkeys(conflicts)), tuple(dict.fromkeys(unresolved))


def _link_versions(
    versions: Sequence[SourceVersionRecord], *, source_id: SourceId
) -> tuple[SourceVersionRecord, ...]:
    """Rewrite versions onto the merged source and link chronological predecessors."""

    unique: dict[tuple[str, str], SourceVersionRecord] = {}
    for version in versions:
        record = version.model_copy(
            update={
                "source_id": source_id,
                "version_id": version_id_for(
                    source_id, version.version_label, version.content_hash
                ),
            }
        )
        unique.setdefault((record.version_label, record.content_hash), record)
    ordered = sorted(
        unique.values(),
        key=lambda version: (
            version.published_date is None,
            version.published_date or date.min,
            version.observed_at,
            version.version_id,
        ),
    )
    linked: list[SourceVersionRecord] = []
    for index, version in enumerate(ordered):
        if index:
            published = [item for item in linked if item.published_date is not None]
            if published:
                predecessor = max(
                    published,
                    key=lambda item: (item.published_date or date.min, item.observed_at),
                )
            else:
                predecessor = linked[-1]
            version = version.model_copy(update={"predecessor_version_id": predecessor.version_id})
        linked.append(version)
    return tuple(linked)


def _quality_and_relevance(
    sources: Sequence[SourceRecord],
    clusters: Sequence[EvidenceLineageCluster],
    *,
    assessed_at: datetime,
) -> tuple[tuple[EvidenceQualityAssessment, ...], tuple[SourceRelevanceAssessment, ...]]:
    root_ids = {source_id for cluster in clusters for source_id in cluster.root_source_ids}
    quality = tuple(
        assess_quality(
            source,
            assessed_at=assessed_at,
            signals=signals_from_source_structure(source),
            is_lineage_root=source.source_id in root_ids,
        )
        for source in sources
    )
    relevance = tuple(
        unassessed_relevance(source.source_id, assessed_at=assessed_at) for source in sources
    )
    return quality, relevance


def write_evidence_artifacts(
    writer: RunArtifactWriter,
    assessment_id: AssessmentId,
    result: EvidenceNormalizationResult,
) -> None:
    writer.write_jsonl(assessment_id, "phase5/sources.jsonl", result.sources)
    writer.write_jsonl(assessment_id, "phase5/source_versions.jsonl", result.versions)
    writer.write_jsonl(assessment_id, "phase5/passages.jsonl", result.passages)
    writer.write_jsonl(assessment_id, "phase5/provenance_edges.jsonl", result.provenance_edges)
    writer.write_jsonl(assessment_id, "phase5/lineage_clusters.jsonl", result.lineage_clusters)
    writer.write_jsonl(assessment_id, "phase5/source_quality.jsonl", result.quality_assessments)
    writer.write_jsonl(assessment_id, "phase5/source_relevance.jsonl", result.relevance_assessments)
    writer.write_jsonl(assessment_id, "phase5/provenance_cycles.jsonl", result.cycles)
    writer.write_json(
        assessment_id,
        "phase5/evidence_normalization.json",
        {
            "graph_ref": result.graph_ref,
            "source_count": len(result.sources),
            "version_count": len(result.versions),
            "passage_count": len(result.passages),
            "independent_evidence_count": sum(
                cluster.independent_roots for cluster in result.lineage_clusters
            ),
            "cycle_count": len(result.cycles),
            "conflicts": list(result.conflicts),
            "unresolved_fields": list(result.unresolved_fields),
            "limitations": list(result.limitations),
        },
    )


async def run_evidence_normalization(
    *,
    assessment_id: AssessmentId,
    research: ResearchResult,
    resolver: ContentResolver | None,
    repository: EvidenceGraphRepository,
    writer: RunArtifactWriter,
    trace_sink: TraceSink,
    graph_ref: str,
    clock: Callable[[], datetime] = utc_now,
) -> EvidenceNormalizationResult:
    """Run the Phase 5 pipeline end-to-end and persist the evidence graph."""

    def emit(reason: str, data: dict[str, JsonValue], *, failure: bool = False) -> None:
        trace_sink.emit(
            TraceEvent(
                event_id=new_trace_event_id(),
                assessment_id=assessment_id,
                occurred_at=clock(),
                stage=AssessmentStage.EVIDENCE_NORMALIZED,
                component="evidence_normalization",
                status=TraceStatus.FAILURE if failure else TraceStatus.SUCCESS,
                reason_code=reason,
                data={"execution": "implemented", "semantics_implemented": True, **data},
            )
        )

    clusters = tuple(sorted(research.candidate_clusters, key=lambda cluster: cluster.candidate_key))
    normalized: list[
        tuple[str, SourceRecord, ResolvedContent | None, SourceVersionRecord | None]
    ] = []
    conflicts: list[str] = []
    unresolved: list[str] = []
    for cluster in clusters:
        resolved = await _resolve_content(cluster.discoveries, resolver)
        result = await normalize_candidate_cluster(
            cluster,
            observed_at=clock(),
            provenance=_PIPELINE_PROVENANCE,
            resolved=resolved,
        )
        normalized.append((cluster.candidate_key, result.source, resolved, result.version))
        conflicts.extend(result.conflicts)
        unresolved.extend(result.unresolved_fields)
        emit(
            "EVIDENCE_SOURCE_NORMALIZED",
            {
                "source_id": result.source.source_id,
                "candidate_key": cluster.candidate_key,
                "access_state": result.source.access_state.value,
                "has_version": result.version is not None,
            },
        )

    # Union normalized results that share canonical identity evidence.
    parent = list(range(len(normalized)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for index, (_, record, _, _) in enumerate(normalized):
        for other in range(index):
            other_record = normalized[other][1]
            if record.source_id == other_record.source_id or _identifier_overlap(
                record.identifiers, other_record.identifiers
            ):
                parent[max(root(index), root(other))] = min(root(index), root(other))

    groups: dict[int, list[int]] = {}
    for index in range(len(normalized)):
        groups.setdefault(root(index), []).append(index)

    sources: list[SourceRecord] = []
    versions: list[SourceVersionRecord] = []
    passages: list[PassageRecord] = []
    for member_indices in sorted(groups.values()):
        members = [normalized[index] for index in member_indices]
        merged, merge_conflicts, merge_unresolved = _merge_source_group(
            [(key, record, resolved) for key, record, resolved, _ in members]
        )
        conflicts.extend(merge_conflicts)
        unresolved.extend(merge_unresolved)
        linked_versions = _link_versions(
            [version for _, _, _, version in members if version is not None],
            source_id=merged.source_id,
        )
        versions.extend(linked_versions)
        best_resolved: ResolvedContent | None = max(
            (resolved for _, _, resolved, _ in members if resolved is not None),
            key=lambda content: _ACCESS_PREFERENCE[content.access_state],
            default=None,
        )
        if best_resolved is not None and best_resolved.access_state in {
            SourceAccessState.FULL_TEXT,
            SourceAccessState.ABSTRACT_ONLY,
        }:
            payload = (
                best_resolved.text if best_resolved.text is not None else best_resolved.abstract
            )
            assert payload is not None
            matched_version = next(
                (
                    version
                    for version in linked_versions
                    if version.content_hash == text_hash(payload)
                    and version.access_state == best_resolved.access_state
                ),
                None,
            )
            if best_resolved.access_state == SourceAccessState.FULL_TEXT:
                passages.append(
                    extract_resolved_content(
                        merged.source_id,
                        payload,
                        observed_at=clock(),
                        provenance=_PIPELINE_PROVENANCE,
                        source_version_id=matched_version.version_id if matched_version else None,
                    )
                )
            else:
                passages.append(
                    extract_abstract(
                        merged.source_id,
                        payload,
                        observed_at=clock(),
                        provenance=_PIPELINE_PROVENANCE,
                        source_version_id=matched_version.version_id if matched_version else None,
                    )
                )
        sources.append(merged)

    sources.sort(key=lambda source: source.source_id)
    versions.sort(key=lambda version: version.version_id)
    passages.sort(key=lambda passage: passage.passage_id)

    provenance_edges = retrieval_provenance_edges(
        sources, observed_at=clock(), provenance=_PIPELINE_PROVENANCE
    )
    lineage_clusters = build_lineage_clusters(sources, provenance_edges)
    cycles = detect_provenance_cycles([source.source_id for source in sources], provenance_edges)
    quality, relevance = _quality_and_relevance(sources, lineage_clusters, assessed_at=clock())

    limitations: list[str] = [
        "Evidence normalization covers retrieved candidates only; discovery coverage "
        "is established by prior phases, not here",
        "Relevance remains an explicit unassessed placeholder; retrieval rank is not verification",
        "Passage extraction preserves exact content; support/equivalence verification is Phase 6",
    ]
    if resolver is None:
        limitations.append("No content resolver was configured; all sources remain metadata-only")
    for source in sources:
        limitations.extend(source.limitations)
    if cycles:
        limitations.append("Circular provenance detected; independence counts remain conservative")

    nodes: dict[str, GraphNode] = {}
    graph_edges: dict[str, GraphEdge] = {}
    discovery_nodes, discovery_edges = discovery_graph(
        sources, observed_at=clock(), provenance=_PIPELINE_PROVENANCE
    )
    for node in discovery_nodes:
        nodes[node.node_id] = node
    for edge in discovery_edges:
        graph_edges[edge.edge_id] = edge
    for version in versions:
        node = version_graph_node(version, observed_at=clock(), provenance=_PIPELINE_PROVENANCE)
        nodes[node.node_id] = node
    for passage in passages:
        node = passage_graph_node(passage, observed_at=clock(), provenance=_PIPELINE_PROVENANCE)
        nodes[node.node_id] = node
    for edge in provenance_graph_edges(provenance_edges):
        graph_edges[edge.edge_id] = edge

    repository.upsert(
        nodes=tuple(nodes[key] for key in sorted(nodes)),
        edges=tuple(graph_edges[key] for key in sorted(graph_edges)),
        clusters=lineage_clusters,
    )
    emit(
        "EVIDENCE_GRAPH_PERSISTED",
        {
            "graph_ref": graph_ref,
            "node_count": len(nodes),
            "edge_count": len(graph_edges),
            "cluster_count": len(lineage_clusters),
        },
    )
    emit(
        "EVIDENCE_LINEAGE",
        {
            "independent_evidence_count": sum(
                cluster.independent_roots for cluster in lineage_clusters
            ),
            "source_count": len(sources),
            "cycle_count": len(cycles),
        },
    )

    result = EvidenceNormalizationResult(
        sources=tuple(sources),
        versions=tuple(versions),
        passages=tuple(passages),
        provenance_edges=provenance_edges,
        lineage_clusters=lineage_clusters,
        quality_assessments=quality,
        relevance_assessments=relevance,
        cycles=cycles,
        conflicts=tuple(dict.fromkeys(conflicts)),
        unresolved_fields=tuple(dict.fromkeys(unresolved)),
        limitations=tuple(dict.fromkeys(limitations)),
        graph_ref=graph_ref,
    )
    write_evidence_artifacts(writer, assessment_id, result)
    return result


__all__ = [
    "EvidenceNormalizationResult",
    "run_evidence_normalization",
    "write_evidence_artifacts",
]
