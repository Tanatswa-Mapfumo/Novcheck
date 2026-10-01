import json
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from novelty_harness.evidence.graph.models import GraphNodeKind
from novelty_harness.evidence.graph.sqlalchemy_models import (
    Phase6AssessmentCandidateRow,
    Phase6AssessmentSnapshotRow,
    Phase6AssessmentTargetRow,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.passages.extraction import passage_id_for
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.phase6_pipeline import verify_evidence_against_mcus
from novelty_harness.evidence.pipeline import run_evidence_normalization
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase4 import assessment, wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.fixtures.phase6 import (
    StubLLMProvider,
    map_evidence_response,
    scripted_phase6_llm,
    verify_support_response,
)
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


async def run_phase6_for_ledger(tmp_path, *, max_sources=3, evidence_update=None):
    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    if evidence_update is not None:
        evidence = evidence_update(evidence)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    result = await verify_evidence_against_mcus(
        assessment_id="asm_research",
        evidence=evidence,
        mcus=make_fixture().graph.mcus,
        combinations=make_fixture().graph.combinations,
        as_of=assessment().request.as_of,
        runner=SemanticRunner(scripted_phase6_llm()),
        repository=repository,
        writer=writer,
        trace_sink=InMemoryTraceSink(),
        graph_ref="phase5/evidence_graph.sqlite3",
        max_sources_per_mcu=max_sources,
        clock=lambda: NOW,
    )
    assert result.snapshot_id
    with Session(repository._engine) as session:
        snapshot_row = session.get(Phase6AssessmentSnapshotRow, result.snapshot_id)
        target_rows = tuple(
            session.scalars(
                select(Phase6AssessmentTargetRow).where(
                    Phase6AssessmentTargetRow.snapshot_id == result.snapshot_id
                )
            )
        )
        candidate_rows = tuple(
            session.scalars(
                select(Phase6AssessmentCandidateRow).where(
                    Phase6AssessmentCandidateRow.snapshot_id == result.snapshot_id
                )
            )
        )
    assert snapshot_row is not None
    repository.close()
    return result, evidence, snapshot_row, target_rows, candidate_rows


def _with_unversioned_and_missing_version_passages(evidence):
    additions = []
    for passage in evidence.passages:
        source_id = passage.source_id
        unversioned_data = passage.model_dump(mode="python")
        unversioned_data.update(
            source_version_id=None,
            passage_id=passage_id_for(source_id, None, passage.locator, passage.content_hash),
            attestation=None,
        )
        additions.append(PassageRecord.model_validate(unversioned_data))
        missing_data = passage.model_dump(mode="python")
        missing_data.update(
            source_version_id="srcv_missing_ledger_record",
            passage_id=passage_id_for(
                source_id,
                "srcv_missing_ledger_record",
                passage.locator,
                passage.content_hash,
            ),
            attestation=None,
        )
        additions.append(PassageRecord.model_validate(missing_data))
    return replace(evidence, passages=(*evidence.passages, *additions))


def _without_attested_unit_bounds(evidence):
    passages = []
    for passage in evidence.passages:
        proof = passage.attestation
        if proof is None or proof.unit_start is None:
            passages.append(passage)
            continue
        attestation = proof.model_copy(
            update={"unit_type": None, "unit_start": None, "unit_end": None}
        )
        passages.append(
            passage.model_copy(update={"attestation": attestation, "unit_boundary": None})
        )
    return replace(evidence, passages=tuple(passages))


async def test_ledger_records_combination_profile_and_topology(tmp_path) -> None:
    result, _, _, target_rows, _ = await run_phase6_for_ledger(tmp_path)

    profiles = [json.loads(row.document_json)["profile"] for row in target_rows]
    expected_fixture = make_fixture()
    assert {profile["target_id"] for profile in profiles} == {
        *(mcu.mcu_id for mcu in expected_fixture.graph.mcus),
        *(profile["target_id"] for profile in profiles if profile["target_kind"] == "COMBINATION"),
    }
    combinations = [profile for profile in profiles if profile["target_kind"] == "COMBINATION"]
    assert len(combinations) == 1
    profile = combinations[0]
    expected = expected_fixture.graph.combinations[0]
    assert profile["combination_id"] == expected.combination_id
    assert profile["combination_members"] == list(expected.member_ids)
    assert profile["combination_relationships"] == [
        item.model_dump(mode="json") for item in expected.relationships
    ]
    assert {item["mcu_id"] for item in profile["member_contributions"]} == set(expected.member_ids)
    assert result.snapshot_id


@pytest.mark.asyncio
async def test_assessed_ledger_rows_retain_blocked_context_expansions(tmp_path):
    result, _, _, _, candidate_rows = await run_phase6_for_ledger(
        tmp_path, evidence_update=_without_attested_unit_bounds
    )
    ledger_records = [json.loads(row.document_json) for row in candidate_rows]
    assessed_records = [record for record in ledger_records if record["decision"] == "ASSESSED"]
    expansions = [item for record in assessed_records for item in record["expansions"]]
    assert result.expansions
    assert expansions
    assert {item["attempt"] for item in expansions} == {item.attempt for item in result.expansions}
    assert any(not item["available"] for item in expansions)
    assert any(record["limitations"] for record in assessed_records)


@pytest.mark.asyncio
async def test_ledger_retains_all_failed_mapping_candidates_without_success_trace(tmp_path) -> None:
    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace = InMemoryTraceSink()
    invalid_mapper = SemanticRunner(
        StubLLMProvider(
            {
                "map_evidence": {
                    "prompt_version": "evidence-mapper-v1",
                    "dimensions": [],
                    "unresolved": [],
                },
                "verify_support": lambda _: {},
            }
        )
    )
    try:
        result = await verify_evidence_against_mcus(
            assessment_id="asm_research",
            evidence=evidence,
            mcus=make_fixture().graph.mcus,
            combinations=make_fixture().graph.combinations,
            as_of=assessment().request.as_of,
            runner=invalid_mapper,
            repository=repository,
            writer=writer,
            trace_sink=trace,
            graph_ref="phase5/evidence_graph.sqlite3",
            clock=lambda: NOW,
        )
        with Session(repository._engine) as session:
            rows = tuple(
                session.scalars(
                    select(Phase6AssessmentCandidateRow).where(
                        Phase6AssessmentCandidateRow.snapshot_id == result.snapshot_id
                    )
                )
            )
        outcomes = [json.loads(row.document_json) for row in rows]
        assert outcomes
        failed_outcomes = [item for item in outcomes if item["decision"] == "FAILED_MAPPING"]
        assert failed_outcomes
        assert all(item["failure_stage"] == "MAPPING" for item in failed_outcomes)
        assert all(
            item["source_version_id"]
            == next(
                candidate.source_version_id
                for candidate in result.candidate_assessments
                if candidate.source_id == item["source_id"]
                and candidate.target_mcu_id == item["target_id"]
            )
            for item in failed_outcomes
        )
        assert not result.commit_receipts
        assert all(item.status == "FAILED_MAPPING" for item in result.candidate_assessments)
        assert not any(event.reason_code == "SUPPORT_VERIFICATION" for event in trace.events)
        assert not any(
            event.reason_code == "PRECEDENT_CLASSIFICATION" and event.status.value == "SUCCESS"
            for event in trace.events
        )
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_ledger_keeps_failed_candidate_beside_committed_comparisons(tmp_path) -> None:
    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    trace = InMemoryTraceSink()
    calls = 0

    def fail_first_mapping(context):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"prompt_version": "evidence-mapper-v1", "dimensions": [], "unresolved": []}
        return map_evidence_response(context)

    runner = SemanticRunner(
        StubLLMProvider(
            {"map_evidence": fail_first_mapping, "verify_support": verify_support_response}
        )
    )
    try:
        result = await verify_evidence_against_mcus(
            assessment_id="asm_research",
            evidence=evidence,
            mcus=make_fixture().graph.mcus,
            combinations=make_fixture().graph.combinations,
            as_of=assessment().request.as_of,
            runner=runner,
            repository=repository,
            writer=writer,
            trace_sink=trace,
            graph_ref="phase5/evidence_graph.sqlite3",
            clock=lambda: NOW,
        )
        with Session(repository._engine) as session:
            rows = tuple(
                session.scalars(
                    select(Phase6AssessmentCandidateRow).where(
                        Phase6AssessmentCandidateRow.snapshot_id == result.snapshot_id
                    )
                )
            )
        outcomes = [json.loads(row.document_json) for row in rows]
        failed = [item for item in outcomes if item["decision"] == "FAILED_MAPPING"]
        assessed = [item for item in outcomes if item["decision"] == "ASSESSED"]
        assert failed and assessed
        assert all(item["commit_id"] is None for item in failed)
        assert all(item["commit_id"] is not None for item in assessed)
        failed_source_target = {(item["source_id"], item["target_id"]) for item in failed}
        assert not any(
            event.reason_code == "PRECEDENT_CLASSIFICATION"
            and event.status.value == "SUCCESS"
            and (event.data.get("source_id"), event.data.get("mcu_id")) in failed_source_target
            for event in trace.events
        )
    finally:
        repository.close()


async def test_ledger_keeps_fourth_source_and_mixed_unversioned_passages(tmp_path) -> None:
    result, evidence, snapshot_row, _, candidate_rows = await run_phase6_for_ledger(
        tmp_path, evidence_update=_with_unversioned_and_missing_version_passages
    )

    snapshot = json.loads(snapshot_row.document_json)
    candidate_docs = [json.loads(row.document_json) for row in candidate_rows]
    expected_fourth_source = evidence.sources[3]
    exclusions = snapshot["coverage"]["excluded_sources"]
    fourth_source_exclusion = next(
        item for item in exclusions if item["source_id"] == expected_fourth_source.source_id
    )
    target_profile = next(
        item for item in result.profiles if item.target_id == fourth_source_exclusion["target_id"]
    )
    target_members = (
        set(target_profile.combination_members)
        if target_profile.target_kind == "COMBINATION"
        else {target_profile.target_id}
    )
    expected_routing_priority = int(
        not any(
            path.mcu_id in {target_profile.target_id, *target_members}
            for path in expected_fourth_source.discovery_paths
        )
    )
    assert any(
        item["source_id"] == expected_fourth_source.source_id
        and item["reason"] == "SOURCE_BOUND"
        and item["source_access_state"] == expected_fourth_source.access_state.value
        and item["source_content_hash"] == expected_fourth_source.content_hash
        and item["routing_priority"] == expected_routing_priority
        for item in exclusions
    )
    fourth_version = next(
        version
        for version in evidence.versions
        if version.source_id == expected_fourth_source.source_id
    )
    fourth_version_exclusions = [
        item
        for item in snapshot["coverage"]["excluded_versions"]
        if item["source_id"] == expected_fourth_source.source_id
        and item["source_version_id"] == fourth_version.version_id
    ]
    assert fourth_version_exclusions
    assert all(item["reason"] == "SOURCE_BOUND" for item in fourth_version_exclusions)
    assert all(
        item["version_content_hash"] == fourth_version.content_hash
        for item in fourth_version_exclusions
    )
    assert all(
        item["version_access_state"] == fourth_version.access_state.value
        for item in fourth_version_exclusions
    )
    fourth_candidate_rows = [
        item
        for item in candidate_docs
        if item["source_id"] == expected_fourth_source.source_id
        and item["source_version_id"] == fourth_version.version_id
        and item["decision"] == "EXCLUDED_SOURCE_BOUND"
    ]
    assert fourth_candidate_rows
    assert all(
        item["version_content_hash"] == fourth_version.content_hash
        for item in fourth_candidate_rows
    )
    assert any(
        item["reason"] == "UNVERSIONED" and item["source_version_id"] is None
        for item in snapshot["coverage"]["excluded_versions"]
    )
    assert any(
        item["reason"] == "UNVERSIONED"
        and item["source_version_id"] is None
        and item["decision"] == "EXCLUDED_VERSION_BOUND"
        for item in candidate_docs
    )
    assert any(
        item["reason"] == "MISSING_VERSION_RECORD"
        and item["source_version_id"] == "srcv_missing_ledger_record"
        for item in snapshot["coverage"]["excluded_versions"]
    )
    mixed_source = evidence.sources[0]
    records_for_source = [
        item for item in candidate_docs if item["source_id"] == mixed_source.source_id
    ]
    assert records_for_source
    assert all(
        item["source_content_hash"] == mixed_source.content_hash for item in records_for_source
    )
    assert all(
        item["source_access_state"] == mixed_source.access_state.value
        for item in records_for_source
    )
    assert all(
        item["evidence_families"] == [family.value for family in mixed_source.evidence_families]
        for item in records_for_source
    )
    assert result.snapshot_id


async def test_ledger_records_no_selected_source_as_bounded_local_coverage(tmp_path) -> None:
    def remove_passages(evidence):
        return replace(evidence, passages=())

    result, _, snapshot_row, _, candidate_rows = await run_phase6_for_ledger(
        tmp_path, evidence_update=remove_passages
    )

    snapshot = json.loads(snapshot_row.document_json)
    assert not candidate_rows
    assert snapshot["coverage"]["selected_source_ids"] == []
    assert any(
        "no eligible source" in item.casefold() for item in snapshot["coverage"]["limitations"]
    )
    assert result.snapshot_id


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
