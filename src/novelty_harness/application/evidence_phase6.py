"""Phase 6 application component for evidence verification."""

from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.domain.base import utc_now
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
