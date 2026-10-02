"""Non-authoritative historical Phase 6 projection for diagnostic tests only."""

from pydantic import JsonValue

from novelty_harness.domain.evidence import EvidenceComparison, EvidenceEdge
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository
from novelty_harness.evidence.phase6_pipeline import Phase6EvidenceResult
from novelty_harness.evidence.precedent.gates import ClassifiedComparison
from novelty_harness.evidence.verification.integrity import VerifiedEvidenceChain

PHASE6_PROVENANCE = ArtifactProvenance(
    kind="implemented",
    component="phase6_evidence",
    detail="Mapping, independent verification and local classification; no adjudication.",
)

_CHRONOLOGY_TO_LEGACY: dict[str, bool | None] = {
    "PREDATES_CUTOFF": True,
    "POST_CUTOFF": False,
    "UNCERTAIN": None,
}


def _without_observation_times(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _without_observation_times(part)
            for key, part in value.items()
            if key != "observed_at"
        }
    if isinstance(value, list):
        return [_without_observation_times(part) for part in value]
    return value


def diagnostic_legacy_projection_ignores_graph_authority(
    result: Phase6EvidenceResult,
    repository: EvidenceGraphRepository | None = None,
) -> tuple[EvidenceEdge, ...]:
    """Historical negative-control adapter; never use for downstream authority."""

    if repository is None:
        raise ValueError("Phase 6 projection requires an authoritative repository")

    assessed_classifications = tuple(
        classification
        for classification in result.classifications
        if classification.verification_id is not None
    )
    classifications = {
        classification.verification_id: classification
        for classification in assessed_classifications
    }
    chains: dict[str, VerifiedEvidenceChain] = {
        chain.edge.edge_id: chain for chain in result.chains
    }
    committed: dict[str, ClassifiedComparison] = {}
    for receipt in result.commit_receipts:
        resolved = repository.resolve_phase6_commit(receipt)
        for classified in resolved.comparisons:
            stored_edge = classified.comparison.chain.edge
            if stored_edge.edge_id in committed:
                raise ValueError("Phase 6 result repeats an authoritative committed edge")
            committed[stored_edge.edge_id] = classified
    if (
        len(chains) != len(result.chains)
        or set(chains) != set(committed)
        or len(assessed_classifications) != len(committed)
        or len(classifications) != len(committed)
        or {item.classification_id for item in assessed_classifications}
        != {item.classification.classification_id for item in committed.values()}
    ):
        raise ValueError("Phase 6 result differs from authoritative committed comparisons")
    projected: list[EvidenceEdge] = []
    seen: set[str] = set()
    for edge in result.edges:
        classification = classifications.get(edge.verification_id)
        authoritative = committed.get(edge.edge_id)
        if classification is None or authoritative is None or edge.edge_id in seen:
            raise ValueError("Verified edge has no matching authoritative commit receipt")
        seen.add(edge.edge_id)
        stored_edge = authoritative.comparison.chain.edge
        stored_classification = authoritative.classification
        caller_chain = chains.get(edge.edge_id)
        if (
            caller_chain is None
            or _without_observation_times(caller_chain.model_dump(mode="json"))
            != _without_observation_times(authoritative.comparison.chain.model_dump(mode="json"))
            or _without_observation_times(edge.model_dump(mode="json"))
            != _without_observation_times(stored_edge.model_dump(mode="json"))
            or _without_observation_times(classification.model_dump(mode="json"))
            != _without_observation_times(stored_classification.model_dump(mode="json"))
        ):
            raise ValueError("Caller result differs from authoritative committed comparison")
        projected.append(
            EvidenceEdge(
                edge_id=stored_edge.edge_id,
                source_id=stored_edge.source_id,
                mcu_id=stored_edge.mcu_id,
                proposition=stored_edge.proposition,
                passage_ids=stored_edge.passage_ids,
                comparison=EvidenceComparison(
                    matching_elements=stored_edge.comparison.matching_elements,
                    matching_relationships=stored_edge.comparison.matching_relationships,
                    missing_elements=stored_edge.comparison.missing_elements,
                    conflicting_elements=stored_edge.comparison.conflicting_elements,
                ),
                relation_type=stored_classification.relation,
                predates_cutoff=_CHRONOLOGY_TO_LEGACY[stored_edge.chronology.state],
                evidence_quality=stored_edge.quality_tier,
                access_limitations=(),
                support_verification=stored_edge.support_state,
                provenance=PHASE6_PROVENANCE,
            )
        )
    if len(seen) != len(committed):
        raise ValueError("Phase 6 result omits an authoritative committed edge")
    return tuple(projected)
