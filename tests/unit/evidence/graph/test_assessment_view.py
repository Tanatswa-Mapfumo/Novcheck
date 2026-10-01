from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.assessment_ledger import Phase6CoverageLedger
from novelty_harness.evidence.graph.assessment_view import (
    AuthorizedGraphRelation,
    CitedPassageView,
    CommittedComparisonView,
    Phase6AssessmentView,
)
from novelty_harness.evidence.graph.models import GraphEdgeKind
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.verification.integrity import (
    VerifiedEvidenceChain,
    verified_comparison,
)
from tests.fixtures.phase5 import make_version, phase5_provenance
from tests.unit.evidence.verification.test_eligibility import (
    build,
    bundle,
    mapping,
    proposition,
    source,
    verification,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _classified() -> ClassifiedComparison:
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    chain = VerifiedEvidenceChain(
        assessment_id="asm_test",
        source=source(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        proposition=proposition(),
        mapping=mapping(),
        bundle=bundle(),
        verification=verification(SupportVerificationState.SUPPORTED),
        edge=edge,
    )
    comparison = verified_comparison(chain)
    classified = classify_verified_comparison(comparison, clock=lambda: NOW)
    return ClassifiedComparison(comparison=comparison, classification=classified)


def _cited_passages(classified: ClassifiedComparison) -> tuple[CitedPassageView, ...]:
    chain = classified.comparison.chain
    commitment_ids_by_passage: dict[str, list[str]] = {}
    for state in chain.verification.commitment_states:
        for passage_id in state.passage_ids:
            commitment_ids_by_passage.setdefault(passage_id, []).append(state.commitment_id)
    return tuple(
        CitedPassageView(
            passage=passage,
            commitment_ids=tuple(commitment_ids_by_passage[passage.passage_id]),
        )
        for passage in (*chain.bundle.passages, *chain.context_passages)
        if passage.passage_id in commitment_ids_by_passage
    )


def test_assessment_view_is_frozen_and_versioned() -> None:
    with pytest.raises(ValidationError):
        Phase6AssessmentView.model_validate(
            {
                "assessment_id": "asm_view",
                "snapshot_id": "p6snap_1",
                "as_of": date(2026, 10, 1),
                "view_version": 2,
                "commit_ids": (),
                "committed_comparisons": (),
                "authorized_graph_relations": (),
                "targets": (),
                "candidate_outcomes": (),
                "coverage": {},
                "multi_source_context": (),
                "patent_screenings": (),
                "lineage": (),
                "audit_refs": (),
            }
        )


def test_committed_comparison_retains_exact_classified_chain_and_passages() -> None:
    classified = _classified()
    cited_passages = _cited_passages(classified)
    item = CommittedComparisonView(
        comparison=classified,
        commit_id="p6commit_1",
        projection_status="SEMANTIC_ONLY",
        proposition_node_id=None,
        graph_edge_ids=(),
        cited_passages=cited_passages,
    )
    assert item.comparison is classified
    assert item.cited_passages == cited_passages
    view = Phase6AssessmentView(
        assessment_id="asm_test",
        snapshot_id="p6snap_1",
        as_of=date(2026, 10, 1),
        view_version=1,
        commit_ids=("p6commit_1",),
        committed_comparisons=(item,),
        authorized_graph_relations=(),
        targets=(),
        candidate_outcomes=(),
        coverage=Phase6CoverageLedger(),
        multi_source_context=(),
        patent_screenings=(),
        lineage=(),
        audit_refs=(),
    )
    assert len(view.committed_comparisons) == 1
    assert view.committed_comparisons[0].projection_status == "SEMANTIC_ONLY"
    assert view.authorized_graph_relations == ()
    with pytest.raises((ValidationError, TypeError)):
        item.commit_id = "changed"  # type: ignore[misc]


def test_committed_comparison_rejects_omitted_verifier_cited_passages() -> None:
    classified = _classified()
    with pytest.raises(ValidationError, match="all verifier-cited passages"):
        CommittedComparisonView(
            comparison=classified,
            commit_id="p6commit_1",
            projection_status="SEMANTIC_ONLY",
            proposition_node_id=None,
            graph_edge_ids=(),
            cited_passages=(),
        )


def test_graph_relation_ids_must_match_a_committed_comparison() -> None:
    classified = _classified()
    view_item = CommittedComparisonView(
        comparison=classified,
        commit_id="commit_1",
        projection_status="GRAPH_AUTHORIZED",
        proposition_node_id="prop_expected",
        graph_edge_ids=("gedge_expected",),
        cited_passages=_cited_passages(classified),
    )
    edge, node = _graph_relation_fixture(classified)
    relation = AuthorizedGraphRelation(
        edge=edge,
        proposition_node=node,
        commit_id="commit_1",
        verified_edge_id=classified.comparison.chain.edge.edge_id,
        classification_id=classified.classification.classification_id,
    )
    with pytest.raises(ValidationError, match="edge ID"):
        Phase6AssessmentView(
            assessment_id="asm_view",
            snapshot_id="p6snap_1",
            as_of=date(2026, 10, 1),
            view_version=1,
            commit_ids=("commit_1",),
            committed_comparisons=(view_item,),
            authorized_graph_relations=(relation,),
            targets=(),
            candidate_outcomes=(),
            coverage={},
            multi_source_context=(),
            patent_screenings=(),
            lineage=(),
            audit_refs=(),
        )


def _graph_relation_fixture(classified):
    from novelty_harness.evidence.graph.models import GraphEdge, GraphNode, GraphNodeKind

    provenance = phase5_provenance("assessment-view-test")
    edge = GraphEdge(
        edge_id="gedge_wrong",
        kind=GraphEdgeKind.DIRECT_PRECEDENT,
        source_node_id="src_1",
        target_node_id="mcu_1",
        verification={
            "verified_edge_id": classified.comparison.chain.edge.edge_id,
            "support_state": "SUPPORTED",
            "decisive": True,
            "precedent_relation": "DIRECT_PRECEDENT",
        },
        observed_at=NOW,
        provenance=provenance,
    )
    node = GraphNode(
        node_id="prop_wrong",
        kind=GraphNodeKind.EVIDENCE_PROPOSITION,
        observed_at=NOW,
        provenance=provenance,
    )
    return edge, node
