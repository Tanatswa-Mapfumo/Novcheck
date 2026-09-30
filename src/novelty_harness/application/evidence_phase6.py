"""Phase 6 application component and legacy projection for the fixture boundary."""

from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

from pydantic import JsonValue

from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.domain.base import utc_now
from novelty_harness.domain.evidence import EvidenceComparison, EvidenceEdge
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.phase6_pipeline import (
    Phase6EvidenceResult,
    verify_evidence_against_mcus,
)
from novelty_harness.evidence.pipeline import EvidenceNormalizationResult
from novelty_harness.evidence.precedent.gates import ClassifiedComparison
from novelty_harness.evidence.verification.integrity import VerifiedEvidenceChain
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import TraceSink

GRAPH_REF = "phase5/evidence_graph.sqlite3"

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


def project_verified_edges(
    result: Phase6EvidenceResult,
    repository: EvidenceGraphRepository | None = None,
) -> tuple[EvidenceEdge, ...]:
    """Project Phase 6 verified edges onto the legacy evidence-edge boundary.

    This compatibility view exists only so the accepted fixture-backed Phase 7
    adjudicator can consume real Phase 6 output; the canonical records remain
    the Phase 6 artifacts.
    """

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


class Phase6EvidenceComponents:
    """Run real Phase 6 mapping/verification/classification and persist the graph."""

    def __init__(
        self,
        runner: SemanticRunner,
        *,
        max_sources_per_mcu: int = 3,
        max_expansions: int = 2,
        window_chars: int = 600,
        repository_factory: Callable[[Path], EvidenceGraphRepository] = (
            SqlAlchemyEvidenceGraphRepository
        ),
    ) -> None:
        self.runner = runner
        self.max_sources_per_mcu = max_sources_per_mcu
        self.max_expansions = max_expansions
        self.window_chars = window_chars
        self.repository_factory = repository_factory

    async def execute(
        self,
        *,
        assessment: AssessmentRecord,
        evidence: EvidenceNormalizationResult,
        mcus: Sequence[MCU],
        combinations: Sequence[MCUCombination] = (),
        as_of: date,
        writer: RunArtifactWriter,
        trace_sink: TraceSink,
        clock: Callable[[], datetime] = utc_now,
    ) -> Phase6EvidenceResult:
        directory = writer.assessment_dir(assessment.assessment_id)
        repository = self.repository_factory(directory / GRAPH_REF)
        try:
            return await verify_evidence_against_mcus(
                assessment_id=assessment.assessment_id,
                evidence=evidence,
                mcus=mcus,
                combinations=combinations,
                as_of=as_of,
                runner=self.runner,
                repository=repository,
                writer=writer,
                trace_sink=trace_sink,
                graph_ref=GRAPH_REF,
                max_sources_per_mcu=self.max_sources_per_mcu,
                max_expansions=self.max_expansions,
                window_chars=self.window_chars,
                clock=clock,
            )
        finally:
            repository.close()
