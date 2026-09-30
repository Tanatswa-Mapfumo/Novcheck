"""Phase 6 application component and legacy projection for the fixture boundary."""

from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

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


def project_verified_edges(result: Phase6EvidenceResult) -> tuple[EvidenceEdge, ...]:
    """Project Phase 6 verified edges onto the legacy evidence-edge boundary.

    This compatibility view exists only so the accepted fixture-backed Phase 7
    adjudicator can consume real Phase 6 output; the canonical records remain
    the Phase 6 artifacts.
    """

    classifications = {
        classification.verification_id: classification
        for classification in result.classifications
        if classification.verification_id is not None
    }
    committed = {
        (edge_id, classification_id, receipt.assessment_id)
        for receipt in result.commit_receipts
        for edge_id, classification_id in zip(
            receipt.committed_edge_ids,
            receipt.committed_classification_ids,
            strict=True,
        )
    }
    projected: list[EvidenceEdge] = []
    for edge in result.edges:
        classification = classifications.get(edge.verification_id)
        if (
            classification is None
            or (
                edge.edge_id,
                classification.classification_id,
                edge.assessment_id,
            )
            not in committed
        ):
            raise ValueError("Verified edge has no matching authoritative commit receipt")
        relation = classification.relation
        projected.append(
            EvidenceEdge(
                edge_id=edge.edge_id,
                source_id=edge.source_id,
                mcu_id=edge.mcu_id,
                proposition=edge.proposition,
                passage_ids=edge.passage_ids,
                comparison=EvidenceComparison(
                    matching_elements=edge.comparison.matching_elements,
                    matching_relationships=edge.comparison.matching_relationships,
                    missing_elements=edge.comparison.missing_elements,
                    conflicting_elements=edge.comparison.conflicting_elements,
                ),
                relation_type=relation,
                predates_cutoff=_CHRONOLOGY_TO_LEGACY[edge.chronology.state],
                evidence_quality=edge.quality_tier,
                access_limitations=(),
                support_verification=edge.support_state,
                provenance=PHASE6_PROVENANCE,
            )
        )
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
