"""R11: publish assessed Phase 6 semantics only after content-authority commit."""

import json
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import text

from novelty_harness.application.evidence_phase6 import project_verified_edges
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.retrieval_mapping import (
    source_graph_node,
    version_graph_node,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.normalization.models import SourceType
from novelty_harness.evidence.passages.extraction import (
    extract_resolved_content,
    resolve_version_content,
)
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.phase6_pipeline import verify_evidence_against_mcus
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.verification.integrity import verified_comparison
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import JsonlTraceSink, TraceSink
from tests.adversarial.test_phase6_r10_content_authority import _authority_nodes, _chain_for_content
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase4 import assessment, wire
from tests.fixtures.phase6 import (
    StubLLMProvider,
    context_json,
    map_evidence_response,
    scripted_phase6_llm,
    verify_support_response,
)
from tests.integration.test_phase6_evidence_pipeline import NOW, graph_database, run_phase5
from tests.unit.evidence.verification.test_eligibility import PASSAGE_TEXT


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


async def _phase5(tmp_path):
    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    return writer, database, evidence


async def _run(
    writer,
    evidence,
    repository,
    trace_path,
    *,
    sink: TraceSink | None = None,
    runner: SemanticRunner | None = None,
    control_only: bool = False,
):
    return await verify_evidence_against_mcus(
        assessment_id="asm_research",
        evidence=evidence,
        mcus=make_fixture().graph.mcus[:1] if control_only else make_fixture().graph.mcus,
        combinations=() if control_only else make_fixture().graph.combinations,
        as_of=assessment().request.as_of,
        runner=runner or SemanticRunner(scripted_phase6_llm()),
        repository=repository,
        writer=writer,
        trace_sink=sink or JsonlTraceSink(trace_path),
        graph_ref="phase5/evidence_graph.sqlite3",
        clock=lambda: NOW,
    )


def _seed_sources(repository, evidence, *, rejected_source_id, reject_source=False):
    provenance = phase6_graph_provenance()
    nodes = []
    for source in evidence.sources:
        stored = (
            source.model_copy(update={"content_hash": text_hash("Stored content A")})
            if reject_source and source.source_id == rejected_source_id
            else source
        )
        nodes.append(source_graph_node(stored, observed_at=NOW, provenance=provenance))
    for version in evidence.versions:
        stored = (
            version.model_copy(update={"content_hash": text_hash("Stored content A")})
            if version.source_id == rejected_source_id
            else version
        )
        nodes.append(version_graph_node(stored, observed_at=NOW, provenance=provenance))
    repository.upsert(nodes=tuple(nodes))


def _persist_phase5_lineage(repository, evidence, *, phase5_snapshot):
    source_overrides = {source.source_id: source for source in evidence.sources}
    source_nodes = tuple(
        source_graph_node(
            source_overrides.get(source.source_id, source),
            observed_at=NOW,
            provenance=phase6_graph_provenance(),
        )
        for source in phase5_snapshot.sources
    )
    repository.upsert(
        nodes=source_nodes,
        clusters=phase5_snapshot.lineage_clusters,
    )


def _partial_runner(*, direct_marker: str | None = None) -> SemanticRunner:
    def verify(context):
        payload = context_json(context, "verification_input")
        assert isinstance(payload, dict)
        first = payload["passages"][0]
        text = first["text"]
        response = dict(verify_support_response(context))
        if direct_marker is not None and direct_marker in text:
            return response
        judgments = [dict(item) for item in response["judgments"]]
        for judgment in judgments[1:]:
            judgment["state"] = "NOT_SUPPORTED"
            judgment["passage_ids"] = []
        response["judgments"] = judgments
        return response

    return SemanticRunner(
        StubLLMProvider({"map_evidence": map_evidence_response, "verify_support": verify})
    )


def _verifier_state_runner(state: str) -> SemanticRunner:
    def verify(context):
        payload = context_json(context, "verification_input")
        assert isinstance(payload, dict)
        passage_id = payload["passages"][0]["passage_id"]
        judgments = []
        for commitment in payload["commitments"]:
            judgment = {
                "commitment_id": commitment["commitment_id"],
                "state": "INSUFFICIENT" if state == "INSUFFICIENT_CONTEXT" else state,
                "rationale": "scripted semantic judgment",
                "passage_ids": [passage_id],
            }
            if state == "PARTIALLY_SUPPORTED":
                judgment["supported_subset"] = "the narrow case"
                judgment["unsupported_remainder"] = "the broader claim"
            judgments.append(judgment)
        return {
            "prompt_version": "support-verifier-v1",
            "judgments": judgments,
            "context_needed": ["More of the source is needed"]
            if state == "INSUFFICIENT_CONTEXT"
            else [],
        }

    return SemanticRunner(
        StubLLMProvider({"map_evidence": map_evidence_response, "verify_support": verify})
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["CONTRADICTED", "NOT_SUPPORTED"])
async def test_r12_rejected_version_has_no_durable_verifier_conclusion(tmp_path, state) -> None:
    writer, _, evidence = await _phase5(tmp_path)
    version = evidence.versions[0]
    source = next(item for item in evidence.sources if item.source_id == version.source_id)
    evidence = replace(
        evidence,
        sources=(source,),
        versions=(version,),
        passages=tuple(item for item in evidence.passages if item.source_id == source.source_id),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"r12-rejected-{state}.sqlite")
    trace_path = tmp_path / f"r12-rejected-{state}.jsonl"
    try:
        repository.upsert(
            nodes=(
                source_graph_node(source, observed_at=NOW, provenance=phase6_graph_provenance()),
                version_graph_node(
                    version.model_copy(update={"content_hash": text_hash("Stored content A")}),
                    observed_at=NOW,
                    provenance=phase6_graph_provenance(),
                ),
            )
        )
        for _ in range(2):
            result = await _run(
                writer,
                evidence,
                repository,
                trace_path,
                runner=_verifier_state_runner(state),
                control_only=True,
            )
            assert not result.commit_receipts
            assert not result.edges
            rejected = [
                item for item in result.candidate_assessments if item.source_id == source.source_id
            ]
            assert rejected
            assert all(item.status == "AUTHORITY_REJECTED" for item in rejected)
            assert all(item.source_version_id == version.version_id for item in rejected)
            with repository.engine.connect() as connection:
                candidate_documents = [
                    json.loads(row[0])
                    for row in connection.execute(
                        text(
                            "SELECT document_json FROM phase6_assessment_candidates "
                            "WHERE snapshot_id = :snapshot_id AND source_id = :source_id"
                        ),
                        {"snapshot_id": result.snapshot_id, "source_id": source.source_id},
                    )
                ]
            assert candidate_documents
            assert all(item["decision"] == "AUTHORITY_REJECTED" for item in candidate_documents)
            assert all(
                item["source_version_id"] == version.version_id for item in candidate_documents
            )
            assert all(item["commit_id"] is None for item in candidate_documents)
        with repository.engine.connect() as connection:
            for table in (
                "verified_edges",
                "verified_chains",
                "verified_classifications",
                "verification_observations",
            ):
                assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        events = _events(trace_path)
        assert not any(event["reason_code"] == "SUPPORT_VERIFICATION" for event in events)
        assert any(event["reason_code"] == "CONTENT_AUTHORITY_REJECTED" for event in events)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_r12_mapper_failure_remains_an_operational_diagnostic(tmp_path) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace_path = tmp_path / "r12-operational.jsonl"
    invalid_mapper = SemanticRunner(
        StubLLMProvider(
            {
                "map_evidence": {
                    "prompt_version": "evidence-mapper-v1",
                    "dimensions": [],
                    "unresolved": [],
                },
                "verify_support": verify_support_response,
            }
        )
    )
    try:
        result = await _run(
            writer,
            evidence,
            repository,
            trace_path,
            runner=invalid_mapper,
            control_only=True,
        )
        assert not result.commit_receipts
        events = _events(trace_path)
        diagnostics = [
            event for event in events if event["reason_code"] == "EVIDENCE_MAPPING_FAILED"
        ]
        assert diagnostics
        assert all(event["status"] == "FAILURE" for event in diagnostics)
        assert all("state" not in event["data"] for event in diagnostics)
        assert not any(event["reason_code"] == "SUPPORT_VERIFICATION" for event in events)
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "CONTRADICTED",
        "NOT_SUPPORTED",
        "INSUFFICIENT_CONTEXT",
    ],
)
async def test_r12_every_committed_verifier_state_publishes_once_as_success(
    tmp_path, state
) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace_path = tmp_path / f"r12-committed-{state}.jsonl"

    class CommitCheckingSink(JsonlTraceSink):
        def emit(self, event):
            if event.reason_code == "SUPPORT_VERIFICATION":
                with repository.engine.connect() as connection:
                    persisted_edges = {
                        row[0]
                        for row in connection.execute(text("SELECT edge_id FROM verified_chains"))
                    }
                    persisted_classes = {
                        row[0]
                        for row in connection.execute(
                            text("SELECT classification_id FROM verified_classifications")
                        )
                    }
                assert set(event.data["committed_edge_ids"]) <= persisted_edges
                assert set(event.data["committed_classification_ids"]) <= persisted_classes
            super().emit(event)

    try:
        first_events = None
        for attempt in range(2):
            result = await _run(
                writer,
                evidence,
                repository,
                trace_path,
                runner=_verifier_state_runner(state),
                sink=CommitCheckingSink(trace_path),
                control_only=True,
            )
            assert result.commit_receipts
            with repository.engine.connect() as connection:
                candidate_documents = [
                    json.loads(row[0])
                    for row in connection.execute(
                        text(
                            "SELECT document_json FROM phase6_assessment_candidates "
                            "WHERE snapshot_id = :snapshot_id"
                        ),
                        {"snapshot_id": result.snapshot_id},
                    )
                ]
                snapshot_document = json.loads(
                    connection.execute(
                        text(
                            "SELECT document_json FROM phase6_assessment_snapshots "
                            "WHERE snapshot_id = :snapshot_id"
                        ),
                        {"snapshot_id": result.snapshot_id},
                    ).scalar_one()
                )
            assert snapshot_document["audit_refs"]
            assert set(snapshot_document["audit_refs"]) <= {
                event["event_id"]
                for event in _events(trace_path)
                if event["data"].get("publication_kind") == "POST_COMMIT_AUTHORITY"
            }
            if state == "INSUFFICIENT_CONTEXT":
                expansions = [
                    item for record in candidate_documents for item in record["expansions"]
                ]
                if result.expansions:
                    assert expansions
                    assert {item["attempt"] for item in expansions} == {
                        item.attempt for item in result.expansions
                    }
            current_events = [
                event
                for event in _events(trace_path)
                if event["reason_code"] == "SUPPORT_VERIFICATION"
            ]
            if attempt == 0:
                first_events = current_events
            else:
                assert len(current_events) == len(first_events)
        events = [
            event for event in _events(trace_path) if event["reason_code"] == "SUPPORT_VERIFICATION"
        ]
        assert events
        assert len(events) == len({event["event_id"] for event in events})
        assert all(event["status"] == "SUCCESS" for event in events)
        assert all(event["data"]["state"] == state for event in events)
        assert all(event["data"]["committed_edge_ids"] for event in events)
        assert all(event["data"]["committed_classification_ids"] for event in events)
    finally:
        repository.close()


def test_receipt_exists_only_after_authoritative_commit_and_replays_idempotently(tmp_path) -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    classified = ClassifiedComparison(comparison=comparison, classification=classification)
    nodes, edges = verified_edge_graph_fragment(
        (chain.edge,),
        (classification,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "receipt.sqlite")
    try:
        receipt = repository.upsert(
            nodes=(*_authority_nodes(chain), *nodes),
            edges=edges,
            verified_edges=(chain.edge,),
            verified_chains=(chain,),
            classified_comparisons=(classified,),
        )
        assert receipt is not None
        assert receipt.assessment_id == chain.assessment_id
        assert receipt.committed_edge_ids == (chain.edge.edge_id,)
        assert receipt.committed_classification_ids == (classification.classification_id,)
        replay = repository.upsert(
            verified_edges=(chain.edge,),
            verified_chains=(chain,),
            classified_comparisons=(classified,),
        )
        assert replay == receipt
        assert repository.observations(chain.edge.edge_id) == (chain.edge.observed_at,)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_conflicting_version_publishes_no_authoritative_success(tmp_path) -> None:
    writer, _, evidence = await _phase5(tmp_path)
    cited_version = evidence.versions[0]
    source = next(item for item in evidence.sources if item.source_id == cited_version.source_id)
    evidence = replace(
        evidence,
        sources=(source,),
        versions=(cited_version,),
        passages=tuple(
            passage for passage in evidence.passages if passage.source_id == source.source_id
        ),
    )
    stored_version = cited_version.model_copy(
        update={"content_hash": text_hash("Other immutable version content")}
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "conflict.sqlite")
    trace_path = tmp_path / "conflict-trace.jsonl"
    try:
        provenance = phase6_graph_provenance()
        repository.upsert(
            nodes=(
                source_graph_node(source, observed_at=NOW, provenance=provenance),
                version_graph_node(stored_version, observed_at=NOW, provenance=provenance),
            )
        )
        result = await _run(writer, evidence, repository, trace_path)
        assert result.failures
        assert not result.edges
        with repository.engine.connect() as connection:
            for table in (
                "verified_edges",
                "verification_observations",
                "verified_chains",
                "verified_classifications",
            ):
                assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        events = _events(trace_path)
        assert not any(
            event["status"] == "SUCCESS"
            and event["reason_code"] == "PRECEDENT_CLASSIFICATION"
            and event["data"].get("source_id") == source.source_id
            for event in events
        )
        assert not any(
            event["status"] == "SUCCESS"
            and event["reason_code"] in {"MULTI_SOURCE_ASSESSMENT", "PATENT_SCREENING"}
            for event in events
        )
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_exact_match_publishes_success_after_semantic_commit(tmp_path) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace_path = tmp_path / "matching-trace.jsonl"

    class CommitCheckingSink(JsonlTraceSink):
        checked = 0

        def emit(self, event):
            if event.status == "SUCCESS":
                edge_ids = event.data["committed_edge_ids"]
                classification_ids = event.data["committed_classification_ids"]
                with repository.engine.connect() as connection:
                    persisted_edges = {
                        row[0]
                        for row in connection.execute(text("SELECT edge_id FROM verified_edges"))
                    }
                    persisted_classifications = {
                        row[0]
                        for row in connection.execute(
                            text("SELECT classification_id FROM verified_classifications")
                        )
                    }
                assert set(edge_ids) <= persisted_edges
                assert set(classification_ids) <= persisted_classifications
                self.checked += 1
            super().emit(event)

    sink = CommitCheckingSink(trace_path)
    try:
        result = await _run(writer, evidence, repository, trace_path, sink=sink)
        assert result.edges
        assert sink.checked > 0
        events = _events(trace_path)
        classifications = [
            event
            for event in events
            if event["reason_code"] == "PRECEDENT_CLASSIFICATION" and event["status"] == "SUCCESS"
        ]
        assert classifications
        with repository.engine.connect() as connection:
            persisted = {
                row[0]
                for row in connection.execute(
                    text("SELECT classification_id FROM verified_classifications")
                )
            }
        assert {item["data"]["classification_id"] for item in classifications} <= persisted
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_legacy_projection_requires_receipt_for_every_verified_edge(tmp_path) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = await _run(writer, evidence, repository, tmp_path / "projection.jsonl")
        assert result.edges
        assert project_verified_edges(result, repository)
        with pytest.raises(ValueError, match="receipt|committed"):
            project_verified_edges(replace(result, commit_receipts=()), repository)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_exact_replay_does_not_duplicate_authoritative_trace_findings(tmp_path) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace_path = tmp_path / "replayed-trace.jsonl"
    try:
        first = await _run(writer, evidence, repository, trace_path)
        first_events = [
            event
            for event in _events(trace_path)
            if event["reason_code"] == "PRECEDENT_CLASSIFICATION" and event["status"] == "SUCCESS"
        ]
        second = await _run(writer, evidence, repository, trace_path)
        replayed_events = [
            event
            for event in _events(trace_path)
            if event["reason_code"] == "PRECEDENT_CLASSIFICATION" and event["status"] == "SUCCESS"
        ]
        assert [edge.edge_id for edge in first.edges] == [edge.edge_id for edge in second.edges]
        assert len(replayed_events) == len(first_events)
        assert {event["event_id"] for event in replayed_events} == {
            event["event_id"] for event in first_events
        }
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_coordinated_source_and_version_forgery_publishes_no_success(tmp_path) -> None:
    writer, _, evidence = await _phase5(tmp_path)
    version = evidence.versions[0]
    source = next(item for item in evidence.sources if item.source_id == version.source_id)
    evidence = replace(
        evidence,
        sources=(source,),
        versions=(version,),
        passages=tuple(item for item in evidence.passages if item.source_id == source.source_id),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "coordinated.sqlite")
    trace_path = tmp_path / "coordinated.jsonl"
    try:
        _seed_sources(repository, evidence, rejected_source_id=source.source_id, reject_source=True)
        result = await _run(writer, evidence, repository, trace_path, control_only=True)
        assert not result.edges
        assert result.failures
        assert not any(
            item["status"] == "SUCCESS"
            and item["reason_code"]
            in {"PRECEDENT_CLASSIFICATION", "MULTI_SOURCE_ASSESSMENT", "PATENT_SCREENING"}
            for item in _events(trace_path)
        )
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_unversioned_authority_gates_success_publication(tmp_path, conflict: bool) -> None:
    writer, _, evidence = await _phase5(tmp_path)
    source = evidence.sources[0]
    original = next(item for item in evidence.passages if item.source_id == source.source_id)
    assert original.attestation is not None
    parent = original.attestation.parent
    source = source.model_copy(update={"content_hash": text_hash(parent.text)})
    resolved = resolve_version_content(source=source, version=None, text=parent.text)
    passage = extract_resolved_content(
        resolved,
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    evidence = replace(evidence, sources=(source,), versions=(), passages=(passage,))
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"unversioned-{conflict}.sqlite")
    trace_path = tmp_path / f"unversioned-{conflict}.jsonl"
    try:
        _seed_sources(
            repository, evidence, rejected_source_id=source.source_id, reject_source=conflict
        )
        result = await _run(writer, evidence, repository, trace_path, control_only=True)
        success = [
            item
            for item in _events(trace_path)
            if item["reason_code"] == "PRECEDENT_CLASSIFICATION" and item["status"] == "SUCCESS"
        ]
        if conflict:
            assert not result.edges
            assert not success
            assert result.failures
        else:
            assert result.edges
            assert success
            assert repository.observations(result.edges[0].edge_id)
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("rejected_direct", [False, True])
async def test_mixed_patent_and_summary_exclude_rejected_source(
    tmp_path, rejected_direct: bool
) -> None:
    writer, _, evidence = await _phase5(tmp_path)
    phase5_snapshot = evidence
    chosen = tuple(
        source
        for source in evidence.sources
        if any(
            marker in passage.text
            for passage in evidence.passages
            if passage.source_id == source.source_id
            for marker in ("openalex:", "crossref:")
        )
    )
    assert len(chosen) == 2
    rejected = next(
        source
        for source in chosen
        if any(
            "crossref:" in passage.text
            for passage in evidence.passages
            if passage.source_id == source.source_id
        )
    )
    chosen_ids = {source.source_id for source in chosen}
    evidence = replace(
        evidence,
        sources=tuple(
            source.model_copy(update={"source_type": SourceType.PATENT}) for source in chosen
        ),
        versions=tuple(version for version in evidence.versions if version.source_id in chosen_ids),
        passages=tuple(passage for passage in evidence.passages if passage.source_id in chosen_ids),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "mixed-patent.sqlite")
    trace_path = tmp_path / "mixed-patent.jsonl"
    try:
        _seed_sources(repository, evidence, rejected_source_id=rejected.source_id)
        _persist_phase5_lineage(repository, evidence, phase5_snapshot=phase5_snapshot)
        result = await _run(
            writer,
            evidence,
            repository,
            trace_path,
            control_only=True,
            runner=_partial_runner(direct_marker="crossref:" if rejected_direct else None),
        )
        assert len(result.edges) == 1
        assert result.edges[0].source_id != rejected.source_id
        assert result.multi_source
        assert not result.multi_source[0].single_source_direct_eligible
        assert result.multi_source[0].contributing_roots == 1
        assert result.patent_screenings
        assert result.patent_screenings[0].mode not in {
            "SINGLE_REFERENCE_ANTICIPATION_LIKE",
            "MULTI_REFERENCE_COMBINATION_LIKE",
        }
        events = _events(trace_path)
        with repository.engine.connect() as connection:
            derived_documents = [
                json.loads(row[0])
                for row in connection.execute(
                    text(
                        "SELECT document_json FROM phase6_assessment_derived "
                        "WHERE snapshot_id = :snapshot_id"
                    ),
                    {"snapshot_id": result.snapshot_id},
                )
            ]
        committed_source_by_edge = {item.edge_id: item.source_id for item in result.edges}
        assert derived_documents
        for record in derived_documents:
            assert set(record["input_edge_ids"]) <= set(committed_source_by_edge)
            assert all(
                committed_source_by_edge[edge_id] != rejected.source_id
                for edge_id in record["input_edge_ids"]
            )
        assert not any(
            item["reason_code"] == "PRECEDENT_CLASSIFICATION"
            and item["status"] == "SUCCESS"
            and item["data"].get("source_id") == rejected.source_id
            for item in events
        )
        assert all(
            len(item["data"]["committed_edge_ids"]) == 1
            for item in events
            if item["reason_code"] in {"MULTI_SOURCE_ASSESSMENT", "PATENT_SCREENING"}
            and item["status"] == "SUCCESS"
        )
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("persist_lineage", [True, False])
async def test_two_committed_partial_patents_require_persisted_lineage(
    tmp_path, persist_lineage: bool
) -> None:
    writer, _, evidence = await _phase5(tmp_path)
    phase5_snapshot = evidence
    chosen = tuple(
        source
        for source in evidence.sources
        if any(
            marker in passage.text
            for passage in evidence.passages
            if passage.source_id == source.source_id
            for marker in ("openalex:", "crossref:")
        )
    )
    chosen_ids = {source.source_id for source in chosen}
    evidence = replace(
        evidence,
        sources=tuple(
            source.model_copy(update={"source_type": SourceType.PATENT}) for source in chosen
        ),
        versions=tuple(version for version in evidence.versions if version.source_id in chosen_ids),
        passages=tuple(passage for passage in evidence.passages if passage.source_id in chosen_ids),
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "two-patents.sqlite")
    trace_path = tmp_path / "two-patents.jsonl"
    try:
        _seed_sources(repository, evidence, rejected_source_id="src_unused")
        if persist_lineage:
            _persist_phase5_lineage(repository, evidence, phase5_snapshot=phase5_snapshot)
        result = await _run(
            writer,
            evidence,
            repository,
            trace_path,
            control_only=True,
            runner=_partial_runner(),
        )
        assert len(result.edges) == 2
        success = [
            item
            for item in _events(trace_path)
            if item["reason_code"] == "PATENT_SCREENING" and item["status"] == "SUCCESS"
        ]
        if persist_lineage:
            assert result.multi_source[0].combination_context == "MULTI_SOURCE_COMBINATION_ONLY"
            assert result.patent_screenings[0].mode == "MULTI_REFERENCE_COMBINATION_LIKE"
            assert len(success) == 1
            assert len(success[0]["data"]["committed_edge_ids"]) == 2
        else:
            assert not result.multi_source
            assert not result.patent_screenings
            assert not success
            assert any("lineage cluster" in item for item in result.coverage_limitations)
    finally:
        repository.close()


class _FailFirstClassification(JsonlTraceSink):
    def __init__(self, path):
        super().__init__(path)
        self.failed = False

    def emit(self, event):
        if event.reason_code == "PRECEDENT_CLASSIFICATION" and not self.failed:
            self.failed = True
            raise OSError("simulated trace append failure")
        super().emit(event)


@pytest.mark.asyncio
async def test_trace_failure_after_commit_is_replayable_without_duplicate_findings(
    tmp_path,
) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace_path = tmp_path / "flaky-trace.jsonl"
    try:
        with pytest.raises(OSError, match="trace append failure"):
            await _run(
                writer,
                evidence,
                repository,
                trace_path,
                sink=_FailFirstClassification(trace_path),
                control_only=True,
            )
        with repository.engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM verified_edges")).scalar_one() > 0
            first_count = connection.execute(
                text("SELECT count(*) FROM verified_classifications")
            ).scalar_one()
        result = await _run(writer, evidence, repository, trace_path, control_only=True)
        assert result.edges
        with repository.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM verified_classifications")
                ).scalar_one()
                >= first_count
            )
        success = [
            item
            for item in _events(trace_path)
            if item["reason_code"] == "PRECEDENT_CLASSIFICATION" and item["status"] == "SUCCESS"
        ]
        assert len(success) == len({item["event_id"] for item in success})
        assert all(item["data"]["committed_edge_ids"] for item in success)
    finally:
        repository.close()
