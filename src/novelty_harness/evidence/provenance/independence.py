"""Conservative source-to-independent-root mapping for lineage clusters."""

from collections.abc import Mapping, Sequence

from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster


def independent_root_map(
    clusters: Sequence[EvidenceLineageCluster],
) -> Mapping[SourceId, SourceId | None]:
    """Map cluster members only when their persisted root is unambiguous."""
    root_by_source: dict[SourceId, SourceId | None] = {}
    for cluster in clusters:
        roots = set(cluster.root_source_ids)
        for source_id in cluster.source_ids:
            root = (
                next(iter(roots)) if len(roots) == 1 else source_id if source_id in roots else None
            )
            if source_id in root_by_source and root_by_source[source_id] != root:
                root_by_source[source_id] = None
            else:
                root_by_source[source_id] = root
    return root_by_source


def independent_roots_for_sources(
    source_ids: Sequence[SourceId], clusters: Sequence[EvidenceLineageCluster]
) -> tuple[tuple[SourceId, ...], tuple[str, ...]]:
    """Resolve only roots made unambiguous by the persisted cluster structure."""
    root_by_source = independent_root_map(clusters)

    requested_sources = set(source_ids)
    roots = tuple(
        sorted(
            {
                root
                for source_id in requested_sources
                if (root := root_by_source.get(source_id)) is not None
            }
        )
    )
    unresolved_count = sum(root_by_source.get(source_id) is None for source_id in requested_sources)
    limitations = (
        (
            "No unambiguous persisted Phase 5 lineage root was available for "
            f"{unresolved_count} derived input source(s); independent-root coverage is incomplete",
        )
        if unresolved_count
        else ()
    )
    return roots, limitations
