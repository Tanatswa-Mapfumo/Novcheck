"""Phase 5 application component and its explicit Phase 6 fixture boundary."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.domain.base import utc_now
from novelty_harness.domain.evidence import SourcePassage
from novelty_harness.domain.evidence import SourceRecord as LegacySourceRecord
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    SourceAccessState,
    SourceRecord,
)
from novelty_harness.evidence.passages.models import PassageLocator, PassageRecord
from novelty_harness.evidence.pipeline import (
    EvidenceNormalizationResult,
    run_evidence_normalization,
)
from novelty_harness.ports.content import ContentResolver
from novelty_harness.research.adaptive.pipeline import ResearchResult
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.sinks import TraceSink

GRAPH_REF = "phase5/evidence_graph.sqlite3"

_LEGACY_ACCESS_STATE: dict[
    SourceAccessState, Literal["full_text", "abstract_only", "metadata_only", "blocked"]
] = {
    SourceAccessState.FULL_TEXT: "full_text",
    SourceAccessState.ABSTRACT_ONLY: "abstract_only",
    SourceAccessState.METADATA_ONLY: "metadata_only",
    SourceAccessState.BLOCKED: "blocked",
}


class Phase6FixtureContinuation(Protocol):
    """Phase 6+ evidence mapping remains fixture-backed in Phase 5."""

    async def materialize(
        self, evidence: EvidenceNormalizationResult, graph: MCUGraph
    ) -> tuple[tuple[LegacySourceRecord, ...], tuple[SourcePassage, ...]]: ...


def _identifier_dictionary(identifiers: CanonicalIdentifiers) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for field in (
        "doi",
        "openalex_id",
        "semantic_scholar_id",
        "arxiv_id",
        "repository",
    ):
        value = getattr(identifiers, field)
        if value:
            flattened[field] = value
    if identifiers.patent_numbers:
        flattened["patent_numbers"] = ",".join(identifiers.patent_numbers)
    flattened.update(identifiers.other)
    return flattened


def _locator_text(locator: PassageLocator) -> str:
    if locator.section:
        return f"{locator.kind.value}:{locator.section}"
    if locator.label:
        return f"{locator.kind.value}:{locator.label}"
    if locator.char_start is not None and locator.char_end is not None:
        return f"{locator.kind.value}:{locator.char_start}-{locator.char_end}"
    return locator.kind.value


def project_source(source: SourceRecord, *, provenance: ArtifactProvenance) -> LegacySourceRecord:
    """Project a canonical Phase 5 source onto the accepted legacy boundary type.

    This is a compatibility view for the fixture-backed Phase 6 mapper; the
    canonical record remains the Phase 5 artifact.
    """

    path = source.discovery_paths[0] if source.discovery_paths else None
    return LegacySourceRecord(
        source_id=source.source_id,
        canonical_title=source.canonical_title,
        source_type=source.source_type.value.lower(),
        canonical_url=source.canonical_url,
        identifiers=_identifier_dictionary(source.identifiers),
        authors_or_owners=source.authors_or_owners,
        dates=source.dates,
        languages=source.languages,
        access_state=_LEGACY_ACCESS_STATE[source.access_state],
        content_hash=source.content_hash or canonical_hash(source.source_id),
        provider_name=path.provider_name if path else "phase5",
        provider_source_id=path.provider_source_id if path else source.source_id,
        discovered_by_queries=source.discovery_queries,
        evidence_families=source.evidence_families,
        provenance=provenance,
    )


def project_passage(passage: PassageRecord, *, provenance: ArtifactProvenance) -> SourcePassage:
    return SourcePassage(
        passage_id=passage.passage_id,
        source_id=passage.source_id,
        text=passage.text,
        locator=_locator_text(passage.locator),
        content_hash=passage.content_hash,
        provenance=provenance,
    )


class Phase5EvidenceComponents:
    """Run real Phase 5 normalization and persist the evidence graph."""

    def __init__(
        self,
        repository_factory: Callable[[Path], EvidenceGraphRepository] = (
            SqlAlchemyEvidenceGraphRepository
        ),
    ) -> None:
        self.repository_factory = repository_factory

    async def execute(
        self,
        *,
        assessment: AssessmentRecord,
        research: ResearchResult,
        resolver: ContentResolver | None,
        writer: RunArtifactWriter,
        trace_sink: TraceSink,
        clock: Callable[[], datetime] = utc_now,
    ) -> EvidenceNormalizationResult:
        directory = writer.assessment_dir(assessment.assessment_id)
        database = directory / GRAPH_REF
        database.parent.mkdir(parents=True, exist_ok=True)
        repository = self.repository_factory(database)
        try:
            return await run_evidence_normalization(
                assessment_id=assessment.assessment_id,
                research=research,
                resolver=resolver,
                repository=repository,
                writer=writer,
                trace_sink=trace_sink,
                graph_ref=GRAPH_REF,
                clock=clock,
            )
        finally:
            repository.close()
