"""Parity between the diagnostic legacy edge adapter and repository authority."""

from dataclasses import replace
from typing import cast

import pytest

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_candidate_record_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView
from novelty_harness.evidence.graph.repository import Phase6CommitReceipt
from novelty_harness.evidence.graph.retrieval_mapping import source_graph_node
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.adversarial.test_phase6_r15_assessment_authority import (
    _load_committed_matrix_case,
    _matrix_chain,
)
from tests.diagnostics.legacy_phase6_projection import (
    diagnostic_legacy_projection_ignores_graph_authority,
)
from tests.fixtures.phase5 import make_source, phase5_provenance
from tests.fixtures.phase6 import (
    StubLLMProvider,
    context_json,
    map_evidence_response,
    verify_support_response,
)
from tests.integration.test_phase6_evidence_pipeline import (
    NOW,
    _with_unversioned_and_missing_version_passages,
    graph_database,
    run_phase6_for_ledger,
)


@pytest.mark.asyncio
async def test_repository_view_preserves_legacy_capabilities_and_richer_phase6_facts(
    tmp_path,
) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        legacy = diagnostic_legacy_projection_ignores_graph_authority(result, repository)
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
async def test_loaded_coverage_patent_lineage_and_candidate_facts_match_persisted_inputs(
    tmp_path,
) -> None:
    passage_limitation = (
        "This available passage window omits the supplementary implementation appendix."
    )

    def constrained_and_bounded(evidence):
        limited = replace(
            evidence,
            passages=tuple(
                passage.model_copy(update={"limitations": (passage_limitation,)})
                for passage in evidence.passages
            ),
        )
        return _with_unversioned_and_missing_version_passages(limited)

    result, evidence, snapshot_row, _, candidate_rows = await run_phase6_for_ledger(
        tmp_path,
        max_sources=1,
        evidence_update=constrained_and_bounded,
    )
    assert result.snapshot_id
    expected_snapshot = Phase6AssessmentSnapshotRecord.model_validate_json(
        snapshot_row.document_json
    )
    expected_candidates = {
        row.record_id: Phase6CandidateLedgerRecord.model_validate_json(row.document_json)
        for row in candidate_rows
    }
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert view.coverage == expected_snapshot.coverage
        assert {item.reason for item in view.coverage.excluded_sources} == {"SOURCE_BOUND"}
        assert {item.reason for item in view.coverage.excluded_versions} >= {
            "SOURCE_BOUND",
            "UNVERSIONED",
            "MISSING_VERSION_RECORD",
        }
        actual_candidates = {
            (item.target_id, item.source_id, item.source_version_id): item
            for item in view.candidate_outcomes
        }
        expected_by_identity = {
            (item.target_id, item.source_id, item.source_version_id): item
            for item in expected_candidates.values()
        }
        assert actual_candidates == expected_by_identity
        sources = {item.source_id: item for item in evidence.sources}
        versions = {item.version_id: item for item in evidence.versions}
        for candidate in view.candidate_outcomes:
            source = sources[candidate.source_id]
            assert candidate.source_content_hash == source.content_hash
            assert candidate.source_access_state == source.access_state
            if candidate.source_version_id is not None:
                version = versions.get(candidate.source_version_id)
                if version is not None:
                    assert candidate.version_content_hash == version.content_hash
                    assert candidate.version_access_state == version.access_state

        citations = [
            citation
            for comparison in view.committed_comparisons
            for citation in comparison.cited_passages
        ]
        assert citations
        assert all(citation.passage.limitations == (passage_limitation,) for citation in citations)

        assert view.patent_screenings
        patent_by_target = {item.mcu_id: item for item in result.patent_screenings}
        for record in view.patent_screenings:
            expected = patent_by_target[record.target_id]
            assert record.result == expected
            assert record.result.dates == expected.dates
            assert record.result.locators == expected.locators
            assert record.result.limitations == expected.limitations

        persisted_lineage = {cluster.cluster_id: cluster for cluster in evidence.lineage_clusters}
        assert {item.cluster_id for item in view.lineage} == set(
            expected_snapshot.lineage_cluster_ids
        )
        assert all(persisted_lineage[item.cluster_id] == item for item in view.lineage)
        expected_edges_by_target: dict[str, list[str]] = {}
        expected_commits_by_edge = {
            edge_id: receipt.commit_id
            for receipt in result.commit_receipts
            for edge_id in receipt.committed_edge_ids
        }
        expected_classes_by_edge = {
            edge_id: class_id
            for receipt in result.commit_receipts
            for edge_id, class_id in zip(
                receipt.committed_edge_ids,
                receipt.committed_classification_ids,
                strict=True,
            )
        }
        for edge in result.edges:
            expected_edges_by_target.setdefault(edge.mcu_id, []).append(edge.edge_id)
        roots_by_source = {
            source_id: root_id
            for cluster in evidence.lineage_clusters
            for source_id in cluster.source_ids
            for root_id in cluster.root_source_ids
        }
        for record in (*view.multi_source_context, *view.patent_screenings):
            expected_edge_ids = tuple(expected_edges_by_target.get(record.target_id, ()))
            assert record.input_edge_ids == expected_edge_ids
            assert record.input_commit_ids == tuple(
                expected_commits_by_edge[edge_id] for edge_id in expected_edge_ids
            )
            assert record.input_classification_ids == tuple(
                expected_classes_by_edge[edge_id] for edge_id in expected_edge_ids
            )
            expected_roots = tuple(
                dict.fromkeys(
                    roots_by_source[result_edge.source_id]
                    for result_edge in result.edges
                    if result_edge.edge_id in expected_edge_ids
                    and result_edge.source_id in roots_by_source
                )
            )
            assert record.lineage_root_ids == expected_roots
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
        legacy = diagnostic_legacy_projection_ignores_graph_authority(result, repository)
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

        legacy = diagnostic_legacy_projection_ignores_graph_authority(
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


def test_unassessable_candidate_round_trips_without_graph_authority(tmp_path) -> None:
    assessment_id = "asm_unassessable_view"
    source = make_source("src_unassessable_view")
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "unassessable.sqlite3")
    try:
        repository.upsert(
            nodes=(
                source_graph_node(
                    source,
                    observed_at=NOW,
                    provenance=phase5_provenance("unassessable-candidate-test"),
                ),
            )
        )
        target = Phase6TargetLedgerRecord(
            snapshot_id="pending",
            assessment_id=assessment_id,
            profile=MCUComparisonProfile(
                target_id="mcu_unassessable_view",
                label="Unassessable target",
                statement="The candidate target has insufficient evidence.",
            ),
        )
        candidate = Phase6CandidateLedgerRecord(
            snapshot_id="pending",
            assessment_id=assessment_id,
            target_id=target.profile.target_id,
            source_id=source.source_id,
            source_content_hash=source.content_hash,
            source_access_state=source.access_state,
            decision="UNASSESSABLE",
            reason="No support passage could be selected for this source and target.",
            failure_stage="PASSAGE_SELECTION",
            limitations=("The source has insufficient citable content.",),
        )
        snapshot_template = Phase6AssessmentSnapshotRecord(
            snapshot_id="pending",
            assessment_id=assessment_id,
            as_of=NOW.date(),
            method_version="phase6-unassessable-test-v1",
            max_sources_per_mcu=1,
            max_versions_per_source=1,
            max_expansions=0,
            window_chars=0,
            target_record_ids=(),
            candidate_record_ids=(),
            derived_record_ids=(),
            lineage_cluster_ids=(),
            commit_ids=(),
            coverage=Phase6CoverageLedger(),
            audit_refs=(),
            completed_at=NOW,
        )
        snapshot_id = phase6_assessment_snapshot_id(
            snapshot_template,
            targets=(target,),
            candidates=(candidate,),
            derived=(),
        )
        target = target.model_copy(update={"snapshot_id": snapshot_id})
        candidate = candidate.model_copy(update={"snapshot_id": snapshot_id})
        snapshot = snapshot_template.model_copy(
            update={
                "snapshot_id": snapshot_id,
                "target_record_ids": (phase6_target_record_id(target),),
                "candidate_record_ids": (phase6_candidate_record_id(candidate),),
            }
        )
        repository.record_phase6_assessment(
            snapshot,
            targets=(target,),
            candidates=(candidate,),
            derived=(),
        )
        view = repository.load_phase6_assessment(assessment_id, snapshot_id=snapshot_id)
        assert view.candidate_outcomes == (candidate,)
        loaded = view.candidate_outcomes[0]
        assert loaded.decision == "UNASSESSABLE"
        assert loaded.reason == candidate.reason
        assert loaded.limitations == candidate.limitations
        assert loaded.commit_id is None
        assert loaded.verified_edge_id is None
        assert loaded.classification_id is None
        assert loaded.projection_intent is None
        assert view.committed_comparisons == ()
        assert view.commit_ids == ()
        assert view.authorized_graph_relations == ()
    finally:
        repository.close()


def test_repository_view_preserves_scoped_partial_and_commitment_citations(tmp_path) -> None:
    repository, view, classification, _ = _load_committed_matrix_case(tmp_path, "SCOPED_PARTIAL")
    try:
        expected = _matrix_chain("SCOPED_PARTIAL")
        committed = view.committed_comparisons[0]
        actual = committed.comparison.comparison.chain
        expected_record = next(
            record
            for record in expected.verification.commitment_states
            if record.state == "PARTIALLY_SUPPORTED"
        )
        assert actual.verification.supported_portions == (
            "The controller opens the valve above the threshold.",
        )
        assert actual.verification.unsupported_portions == (
            "The controller also logs that threshold event.",
        )
        assert actual.verification.commitment_states == expected.verification.commitment_states
        actual_record = next(
            record
            for record in actual.verification.commitment_states
            if record.state == "PARTIALLY_SUPPORTED"
        )
        assert actual_record.supported_subset == expected_record.supported_subset
        assert actual_record.unsupported_remainder == expected_record.unsupported_remainder
        assert actual_record.passage_ids == expected_record.passage_ids
        assert classification.scoped_coverage == committed.comparison.classification.scoped_coverage
        assert len(classification.scoped_coverage) == 1
        scoped = classification.scoped_coverage[0]
        assert scoped.supported_subset == expected_record.supported_subset
        assert scoped.unsupported_remainder == expected_record.unsupported_remainder

        citations_by_id = {item.passage.passage_id: item for item in committed.cited_passages}
        cited_ids = {
            passage_id
            for item in actual.verification.commitment_states
            for passage_id in item.passage_ids
        }
        assert set(citations_by_id) == cited_ids
        for passage_id, citation in citations_by_id.items():
            expected_commitments = {
                item.commitment_id
                for item in actual.verification.commitment_states
                if passage_id in item.passage_ids
            }
            assert set(citation.commitment_ids) == expected_commitments
    finally:
        repository.close()
