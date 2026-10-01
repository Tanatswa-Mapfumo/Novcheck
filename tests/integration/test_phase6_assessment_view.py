"""Repository loading tests for the Phase 6 assessment snapshot boundary."""

from dataclasses import replace

import pytest

from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from tests.fixtures.phase4 import assessment
from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase6_for_ledger


@pytest.mark.asyncio
async def test_loader_reads_complete_bounded_snapshot_with_unassessed_candidates(tmp_path) -> None:
    result, _, _, target_rows, candidate_rows = await run_phase6_for_ledger(
        tmp_path,
        evidence_update=lambda evidence: replace(
            evidence, sources=(), versions=(), passages=(), lineage_clusters=()
        ),
    )
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert view.snapshot_id == result.snapshot_id
        assert len(view.targets) == len(target_rows)
        assert len(view.candidate_outcomes) == len(candidate_rows)
        assert view.committed_comparisons == ()
        assert view.authorized_graph_relations == ()
        assert all(item.decision != "ASSESSED" for item in view.candidate_outcomes)
        assert view.as_of == assessment().request.as_of
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_loader_authorizes_graph_dependent_completed_snapshot(tmp_path) -> None:
    result, _, _, _, candidate_rows = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    assert any('"decision":"ASSESSED"' in row.document_json for row in candidate_rows)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert view.authorized_graph_relations
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_loader_exposes_only_currently_authorized_graph_projection(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        graph_backed = [
            item
            for item in view.committed_comparisons
            if item.projection_status == "GRAPH_AUTHORIZED"
        ]
        assert graph_backed
        assert view.authorized_graph_relations
        assert all(item.graph_edge_ids and item.proposition_node_id for item in graph_backed)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_repository_view_retains_complete_chronology_context_and_version_attestation(
    tmp_path,
) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert view.committed_comparisons
        for item in view.committed_comparisons:
            comparison = item.comparison.comparison
            chain = comparison.chain
            assert comparison.chronology.as_of == view.as_of
            assert comparison.chronology.state == chain.edge.chronology.state
            assert comparison.context_completeness == chain.verification.context_completeness
            assert comparison.source_version_id == (
                chain.version.version_id if chain.version else None
            )
            assert comparison.claim_id == chain.bundle.claim.claim_id
            assert comparison.verified_semantic_facts == chain.verification.commitment_states
            assert item.comparison.classification.basis
            assert item.cited_passages
            for citation in item.cited_passages:
                assert citation.passage.source_id == chain.source.source_id
                assert citation.passage.source_version_id == comparison.source_version_id
                assert citation.passage.attestation is not None
                assert citation.passage.attestation.parent.source_version_id == (
                    citation.passage.source_version_id
                )
                assert citation.commitment_ids
    finally:
        repository.close()
