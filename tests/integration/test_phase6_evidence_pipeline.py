import json
from datetime import UTC, datetime

import httpx

from novelty_harness.evidence.graph.models import GraphNodeKind
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.phase6_pipeline import verify_evidence_against_mcus
from novelty_harness.evidence.pipeline import run_evidence_normalization
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase4 import assessment, wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.fixtures.phase6 import scripted_phase6_llm
from tests.integration.test_phase4_retrieval_pipeline import run as run_phase4

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def graph_database(tmp_path):
    database = tmp_path / "asm_research" / "phase5" / "evidence_graph.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    return database


async def run_phase5(writer, client, database):
    research, _, _ = await run_phase4(client)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        return await run_evidence_normalization(
            assessment_id="asm_research",
            research=research,
            resolver=SyntheticContentResolver(),
            repository=repository,
            writer=writer,
            trace_sink=InMemoryTraceSink(),
            graph_ref="phase5/evidence_graph.sqlite3",
        )
    finally:
        repository.close()


async def test_phase6_pipeline_maps_verifies_classifies_and_persists(tmp_path) -> None:
    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    sink = InMemoryTraceSink()
    result = await verify_evidence_against_mcus(
        assessment_id="asm_research",
        evidence=evidence,
        mcus=make_fixture().graph.mcus,
        combinations=make_fixture().graph.combinations,
        as_of=assessment().request.as_of,
        runner=SemanticRunner(scripted_phase6_llm()),
        repository=repository,
        writer=writer,
        trace_sink=sink,
        graph_ref="phase5/evidence_graph.sqlite3",
        clock=lambda: NOW,
    )
    assert evidence.sources and evidence.passages
    assert result.mappings and result.claims and result.verifications
    assert result.edges and result.classifications
    assert all(
        classification.scope == "LOCAL_SOURCE_MCU" for classification in result.classifications
    )
    assert all(
        not classification.global_absence_claim_permitted
        for classification in result.classifications
    )
    for edge in result.edges:
        assert edge.passage_ids
        if edge.decisive:
            assert edge.support_state.value == "SUPPORTED"
            assert edge.chronology.state == "PREDATES_CUTOFF"
    direct = [
        classification
        for classification in result.classifications
        if classification.relation.value == "DIRECT_PRECEDENT"
    ]
    assert direct and all(classification.decisive for classification in direct)

    persisted = {node.kind for node in repository.nodes()}
    assert GraphNodeKind.SOURCE in persisted
    assert GraphNodeKind.MCU in persisted
    assert GraphNodeKind.EVIDENCE_PROPOSITION in persisted
    assert repository.edges(), "verified edges must be persisted"
    assert any(edge.verification is not None for edge in repository.edges())

    names = {path.name for path in (tmp_path / "asm_research" / "phase6").iterdir()}
    assert {
        "profiles.jsonl",
        "propositions.jsonl",
        "mappings.jsonl",
        "support_claims.jsonl",
        "support_verifications.jsonl",
        "context_expansions.jsonl",
        "verified_edges.jsonl",
        "precedent_classifications.jsonl",
        "multi_source_assessments.jsonl",
        "patent_screenings.jsonl",
        "phase6_result.json",
    } <= names
    summary = json.loads((tmp_path / "asm_research" / "phase6" / "phase6_result.json").read_text())
    assert summary["mapping_count"] == len(result.mappings)
    assert summary["verified_edge_count"] == len(result.edges)
    reasons = {event.reason_code for event in sink.events}
    assert {"EVIDENCE_MAPPING", "SUPPORT_VERIFICATION", "PRECEDENT_CLASSIFICATION"} <= reasons
    assert "PHASE6_GRAPH_PERSISTED" in reasons
    repository.close()


async def test_phase6_pipeline_is_deterministic_for_the_same_inputs(tmp_path) -> None:
    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    fixed = make_fixture()

    async def once():
        repository = SqlAlchemyEvidenceGraphRepository(database)
        try:
            return await verify_evidence_against_mcus(
                assessment_id="asm_research",
                evidence=evidence,
                mcus=fixed.graph.mcus,
                combinations=fixed.graph.combinations,
                as_of=assessment().request.as_of,
                runner=SemanticRunner(scripted_phase6_llm()),
                repository=repository,
                writer=writer,
                trace_sink=InMemoryTraceSink(),
                graph_ref="phase5/evidence_graph.sqlite3",
                clock=lambda: NOW,
            )
        finally:
            repository.close()

    first = await once()
    second = await once()
    assert [edge.edge_id for edge in first.edges] == [edge.edge_id for edge in second.edges]
    assert [item.classification_id for item in first.classifications] == [
        item.classification_id for item in second.classifications
    ]
