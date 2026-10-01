"""Parity between the diagnostic legacy edge adapter and repository authority."""

from dataclasses import replace
from typing import cast

import pytest

from novelty_harness.application.evidence_phase6 import project_verified_edges
from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.assessment_ledger import Phase6CandidateLedgerRecord
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView
from novelty_harness.evidence.graph.repository import Phase6CommitReceipt
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.adversarial.test_phase6_r15_assessment_authority import _load_committed_matrix_case
from tests.fixtures.phase6 import (
    StubLLMProvider,
    context_json,
    map_evidence_response,
    verify_support_response,
)
from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase6_for_ledger


@pytest.mark.asyncio
async def test_repository_view_preserves_legacy_capabilities_and_richer_phase6_facts(
    tmp_path,
) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        legacy = project_verified_edges(result, repository)
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert isinstance(view, Phase6AssessmentView)
        by_edge = {
            item.comparison.comparison.chain.edge.edge_id: item
            for item in view.committed_comparisons
        }
        assert {edge.edge_id for edge in legacy} == set(by_edge)
        for edge in legacy:
            current = by_edge[edge.edge_id]
            chain_edge = current.comparison.comparison.chain.edge
            classification = current.comparison.classification
            assert edge.source_id == chain_edge.source_id
            assert edge.mcu_id == chain_edge.mcu_id
            assert edge.proposition == chain_edge.proposition
            assert edge.passage_ids == chain_edge.passage_ids
            assert edge.comparison.matching_elements == chain_edge.comparison.matching_elements
            assert edge.comparison.matching_relationships == (
                chain_edge.comparison.matching_relationships
            )
            assert edge.comparison.missing_elements == chain_edge.comparison.missing_elements
            assert edge.comparison.conflicting_elements == (
                chain_edge.comparison.conflicting_elements
            )
            assert edge.relation_type == classification.relation
            assert edge.support_verification == chain_edge.support_state
            assert edge.evidence_quality == chain_edge.quality_tier
            assert edge.access_limitations == ()
            assert edge.predates_cutoff is (chain_edge.chronology.state == "PREDATES_CUTOFF") or (
                edge.predates_cutoff is None and chain_edge.chronology.state == "UNCERTAIN"
            )
            assert edge.provenance.kind == "implemented"
            assert chain_edge.provenance != edge.provenance
            assert current.comparison.comparison.source_version_id == chain_edge.source_version_id
            assert current.comparison.comparison.chain.version is not None
            assert current.comparison.comparison.chain.bundle.claim
            assert current.comparison.comparison.chain.verification.commitment_states
            assert current.comparison.comparison.chronology == chain_edge.chronology
            assert current.comparison.comparison.context_completeness == (
                current.comparison.comparison.chain.verification.context_completeness
            )
            assert classification.scoped_coverage or classification.relation.value in {
                "DIRECT_PRECEDENT",
                "UNRESOLVED",
                "CONTRADICTORY_EVIDENCE",
                "NO_DIRECT_PRECEDENT_IDENTIFIED",
            }
            assert current.commit_id in view.commit_ids
            assert classification.basis
            assert current.cited_passages
            assert all(item.passage.attestation for item in current.cited_passages)
            assert all(item.passage.attestation.passage_digest for item in current.cited_passages)
            assert all(item.passage.source_version_id for item in current.cited_passages)

        relation_comparisons = {
            relation.verified_edge_id for relation in view.authorized_graph_relations
        }
        assert relation_comparisons
        for item in view.committed_comparisons:
            edge_id = item.comparison.comparison.chain.edge.edge_id
            if item.projection_status == "GRAPH_AUTHORIZED":
                assert item.graph_edge_ids
                assert edge_id in relation_comparisons
            else:
                assert not item.graph_edge_ids
                assert edge_id not in relation_comparisons

        assert view.coverage.selected_source_ids
        assert view.coverage.excluded_sources or view.coverage.excluded_versions
        assert view.multi_source_context
        assert view.patent_screenings
        assert view.lineage
        assert any(candidate.decision != "ASSESSED" for candidate in view.candidate_outcomes)
        committed_edge_ids = {
            item.comparison.comparison.chain.edge.edge_id for item in view.committed_comparisons
        }
        classification_ids = {
            item.comparison.classification.classification_id for item in view.committed_comparisons
        }
        lineage_root_ids = {
            source_id for cluster in view.lineage for source_id in cluster.root_source_ids
        }
        for derived in (*view.multi_source_context, *view.patent_screenings):
            assert set(derived.input_commit_ids) <= set(view.commit_ids)
            assert set(derived.input_edge_ids) <= committed_edge_ids
            assert set(derived.input_classification_ids) <= classification_ids
            assert set(derived.lineage_root_ids) <= lineage_root_ids
        combination_targets = {
            target.target_id for target in view.targets if target.target_kind == "COMBINATION"
        }
        assert combination_targets
        assert any(
            item.comparison.comparison.chain.edge.mcu_id in combination_targets
            for item in view.committed_comparisons
        )
        assert all(
            candidate.commit_id is None
            and candidate.verified_edge_id is None
            and candidate.classification_id is None
            for candidate in view.candidate_outcomes
            if candidate.decision == "UNASSESSABLE"
        )
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_multi_passage_legacy_parity_retains_every_repository_citation(tmp_path) -> None:
    def map_all_passages(context):
        response = dict(map_evidence_response(context))
        passage_records = cast(list[dict[str, object]], context_json(context, "passages"))
        passage_ids = [str(item["passage_id"]) for item in passage_records]
        dimensions = cast(list[dict[str, object]], response["dimensions"])
        for dimension in dimensions:
            statements = cast(list[dict[str, object]], dimension["matching"])
            for statement in statements:
                statement["passage_ids"] = passage_ids
        return response

    def verify_all_passages(context):
        response = dict(verify_support_response(context))
        payload = cast(dict[str, object], context_json(context, "verification_input"))
        passages = cast(list[dict[str, object]], payload["passages"])
        passage_ids = [str(item["passage_id"]) for item in passages]
        judgments = cast(list[dict[str, object]], response["judgments"])
        for judgment in judgments:
            judgment["passage_ids"] = passage_ids
        return response

    runner = SemanticRunner(
        StubLLMProvider(
            {"map_evidence": map_all_passages, "verify_support": verify_all_passages},
            name="multi-passage-parity",
        )
    )
    result, _, _, _, _ = await run_phase6_for_ledger(
        tmp_path,
        runner=runner,
        evidence_update=lambda evidence: replace(
            evidence,
            passages=(
                *evidence.passages,
                *(
                    passage.model_copy(update={"passage_id": f"{passage.passage_id}_second"})
                    for passage in evidence.passages
                ),
            ),
        ),
    )
    assert result.snapshot_id
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        legacy = project_verified_edges(result, repository)
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        comparisons = {
            item.comparison.comparison.chain.edge.edge_id: item
            for item in view.committed_comparisons
        }
        assert legacy
        for edge in legacy:
            comparison = comparisons[edge.edge_id]
            expected_passage_ids = comparison.comparison.comparison.passage_ids
            assert len(expected_passage_ids) > 1
            assert edge.passage_ids == expected_passage_ids
            assert tuple(item.passage.passage_id for item in comparison.cited_passages) == (
                expected_passage_ids
            )
            assert all(item.commitment_ids for item in comparison.cited_passages)
    finally:
        repository.close()


def test_semantic_matrices_are_explicit_and_unassessable_is_not_a_graph_relation() -> None:
    assert {state.value for state in SupportVerificationState} == {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "INSUFFICIENT_CONTEXT",
        "CONTRADICTED",
    }


@pytest.mark.parametrize(
    ("case", "expected_relation", "expected_support"),
    [
        ("DIRECT_PRECEDENT", PrecedentState.DIRECT_PRECEDENT, "SUPPORTED"),
        (
            "STRONG_PARTIAL_PRECEDENT",
            PrecedentState.STRONG_PARTIAL_PRECEDENT,
            "PARTIALLY_SUPPORTED",
        ),
        ("COMPONENT_PRECEDENT", PrecedentState.COMPONENT_PRECEDENT_ONLY, "PARTIALLY_SUPPORTED"),
        ("ANALOGOUS", PrecedentState.ANALOGOUS_PRECEDENT, "PARTIALLY_SUPPORTED"),
        ("CONTRADICTS", PrecedentState.CONTRADICTORY_EVIDENCE, "CONTRADICTED"),
        ("NO_MATCH", PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED, "NOT_SUPPORTED"),
        ("UNRESOLVED", PrecedentState.UNRESOLVED, "INSUFFICIENT_CONTEXT"),
    ],
)
def test_relation_matrix_legacy_parity_matches_repository_authority(
    tmp_path, case: str, expected_relation: PrecedentState, expected_support: str
) -> None:
    repository, view, classification, _ = _load_committed_matrix_case(tmp_path, case)
    try:
        committed = view.committed_comparisons[0]
        chain = committed.comparison.comparison.chain
        edge = chain.edge
        receipt = Phase6CommitReceipt(
            commit_id=committed.commit_id,
            assessment_id=chain.assessment_id,
            committed_edge_ids=(edge.edge_id,),
            committed_classification_ids=(classification.classification_id,),
        )
        from types import SimpleNamespace

        legacy = project_verified_edges(
            SimpleNamespace(
                edges=(edge,),
                chains=(chain,),
                classifications=(classification,),
                commit_receipts=(receipt,),
            ),
            repository,
        )
        assert classification.relation == expected_relation
        assert len(legacy) == 1
        projected = legacy[0]
        assert projected.edge_id == edge.edge_id
        assert projected.source_id == edge.source_id
        assert projected.mcu_id == edge.mcu_id
        assert projected.proposition == edge.proposition
        assert projected.passage_ids == edge.passage_ids
        assert projected.comparison.matching_elements == edge.comparison.matching_elements
        assert projected.comparison.matching_relationships == (
            edge.comparison.matching_relationships
        )
        assert projected.comparison.missing_elements == edge.comparison.missing_elements
        assert projected.comparison.conflicting_elements == (edge.comparison.conflicting_elements)
        assert projected.relation_type == expected_relation
        assert projected.support_verification == edge.support_state
        assert projected.evidence_quality == edge.quality_tier
        assert projected.predates_cutoff is (edge.chronology.state == "PREDATES_CUTOFF") or (
            projected.predates_cutoff is None and edge.chronology.state == "UNCERTAIN"
        )
        assert committed.commit_id in view.commit_ids
        assert committed.comparison.classification.basis
        assert committed.comparison.comparison.chronology == edge.chronology
        assert committed.comparison.comparison.chain.verification.state.value == expected_support
        assert edge.support_state.value == expected_support
        if committed.projection_status == "GRAPH_AUTHORIZED":
            assert committed.graph_edge_ids
            assert any(
                relation.verified_edge_id == edge.edge_id
                for relation in view.authorized_graph_relations
            )
        else:
            assert not committed.graph_edge_ids
            assert not any(
                relation.verified_edge_id == edge.edge_id
                for relation in view.authorized_graph_relations
            )
    finally:
        repository.close()


def test_unassessable_is_an_unchained_candidate_outcome() -> None:
    candidate = Phase6CandidateLedgerRecord(
        snapshot_id="p6snap_unassessable_case",
        assessment_id="asm_unassessable_case",
        target_id="mcu_unassessable_case",
        source_id="src_unassessable_case",
        decision="UNASSESSABLE",
        reason="The candidate could not be assessed at this scope.",
    )
    assert candidate.decision == "UNASSESSABLE"
    assert candidate.commit_id is None
    assert candidate.verified_edge_id is None
    assert candidate.classification_id is None
    assert candidate.projection_intent is None
    assert {state.value for state in PrecedentState} == {
        "DIRECT_PRECEDENT",
        "STRONG_PARTIAL_PRECEDENT",
        "COMPONENT_PRECEDENT_ONLY",
        "ANALOGOUS_PRECEDENT",
        "SUPERFICIAL_SIMILARITY",
        "NO_DIRECT_PRECEDENT_IDENTIFIED",
        "CONTRADICTORY_EVIDENCE",
        "UNRESOLVED",
        "UNASSESSABLE",
    }
