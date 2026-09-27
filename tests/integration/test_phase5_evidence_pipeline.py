import json

import httpx

from novelty_harness.evidence.graph.models import PHASE5_EDGE_KINDS, GraphNodeKind
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.pipeline import run_evidence_normalization
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase4 import wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.integration.test_phase4_retrieval_pipeline import run as run_phase4


async def test_pipeline_normalizes_real_phase4_output_and_persists_graph(tmp_path) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        research, _, _ = await run_phase4(client)
    writer = RunArtifactWriter(tmp_path)
    sink = InMemoryTraceSink()
    repository = SqlAlchemyEvidenceGraphRepository()
    result = await run_evidence_normalization(
        assessment_id="asm_research",
        research=research,
        resolver=None,
        repository=repository,
        writer=writer,
        trace_sink=sink,
        graph_ref="phase5/evidence_graph.sqlite3",
    )
    assert research.candidate_clusters
    assert result.sources
    # Metadata-only when no resolver is configured; nothing is promoted to content.
    assert all(source.access_state == SourceAccessState.METADATA_ONLY for source in result.sources)
    assert result.passages == ()
    assert result.versions == ()
    # Same DOI across OpenAlex and Crossref becomes one canonical source with both paths.
    control = next(
        (source for source in result.sources if source.identifiers.doi == "10.1234/control"),
        None,
    )
    assert control is not None
    assert {path.provider_name for path in control.discovery_paths} >= {"openalex", "crossref"}
    assert sum(cluster.independent_roots for cluster in result.lineage_clusters) <= len(
        result.sources
    )
    assert result.cycles == ()

    # Persisted graph nodes cover every source; no adjudication edge kinds appear.
    persisted_sources = {
        node.node_id for node in repository.nodes(kinds=frozenset({GraphNodeKind.SOURCE}))
    }
    assert {source.source_id for source in result.sources} <= persisted_sources
    assert all(edge.kind in PHASE5_EDGE_KINDS for edge in repository.edges())
    assert repository.lineage_clusters() == result.lineage_clusters

    names = {path.name for path in (tmp_path / "asm_research" / "phase5").iterdir()}
    assert {
        "sources.jsonl",
        "source_versions.jsonl",
        "passages.jsonl",
        "provenance_edges.jsonl",
        "lineage_clusters.jsonl",
        "source_quality.jsonl",
        "source_relevance.jsonl",
        "provenance_cycles.jsonl",
        "evidence_normalization.json",
    } <= names
    summary = json.loads(
        (tmp_path / "asm_research" / "phase5" / "evidence_normalization.json").read_text()
    )
    assert summary["source_count"] == len(result.sources)
    assert summary["passage_count"] == 0
    assert any(event.reason_code == "EVIDENCE_GRAPH_PERSISTED" for event in sink.events)
    assert all(quality.tier.value == "D" for quality in result.quality_assessments)
    assert all(relevance.relevance.value == "UNKNOWN" for relevance in result.relevance_assessments)
    repository.close()


async def test_pipeline_resolves_content_into_exact_passages_and_versions(tmp_path) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        research, _, _ = await run_phase4(client)
    resolver = SyntheticContentResolver()
    repository = SqlAlchemyEvidenceGraphRepository()
    result = await run_evidence_normalization(
        assessment_id="asm_research",
        research=research,
        resolver=resolver,
        repository=repository,
        writer=RunArtifactWriter(tmp_path),
        trace_sink=InMemoryTraceSink(),
        graph_ref="phase5/evidence_graph.sqlite3",
    )
    resolved = [
        source for source in result.sources if source.access_state == SourceAccessState.FULL_TEXT
    ]
    assert resolved
    assert len(result.versions) == len(resolved)
    assert len(result.passages) == len(resolved)
    for source in resolved:
        matching = [passage for passage in result.passages if passage.source_id == source.source_id]
        assert len(matching) == 1
        passage = matching[0]
        assert passage.text.startswith("Resolved full text for ")
        assert ":" in passage.text.splitlines()[0]
        assert passage.content_hash == text_hash(passage.text)
        version = next(v for v in result.versions if v.source_id == source.source_id)
        assert version.content_hash == source.content_hash
        assert repository.get_node(passage.passage_id) is not None
        assert repository.get_node(version.version_id) is not None
    # Quality of a resolved primary artifact is no longer discovery-only.
    assert any(quality.tier.value in {"A", "B"} for quality in result.quality_assessments)
    repository.close()
