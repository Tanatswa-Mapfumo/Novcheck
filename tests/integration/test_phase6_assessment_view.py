"""Repository loading tests for the Phase 6 assessment snapshot boundary."""

from dataclasses import replace

import pytest

from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentAuthorityError
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
async def test_loader_fails_closed_for_graph_dependent_completed_snapshot(tmp_path) -> None:
    result, _, _, _, candidate_rows = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    assert any('"decision":"ASSESSED"' in row.document_json for row in candidate_rows)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        with pytest.raises(Phase6AssessmentAuthorityError, match="Task 7 graph authority"):
            repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
    finally:
        repository.close()
