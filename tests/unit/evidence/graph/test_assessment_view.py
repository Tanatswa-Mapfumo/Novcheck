import sqlite3
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CoverageLedger,
    phase6_assessment_snapshot_id,
)
from novelty_harness.evidence.graph.assessment_view import (
    AuthorizedGraphRelation,
    CitedPassageView,
    CommittedComparisonView,
    Phase6AssessmentView,
)
from novelty_harness.evidence.graph.models import GraphEdgeKind
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
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


def test_repository_loads_exact_zero_comparison_snapshot() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="pending",
        assessment_id="asm_empty_view",
        as_of=date(2026, 10, 1),
        method_version="phase6-v1",
        max_sources_per_mcu=0,
        max_versions_per_source=0,
        max_expansions=0,
        window_chars=0,
        target_record_ids=(),
        candidate_record_ids=(),
        derived_record_ids=(),
        lineage_cluster_ids=(),
        commit_ids=(),
        coverage=Phase6CoverageLedger(),
        audit_refs=("trace_empty",),
        completed_at=NOW,
    )
    snapshot = snapshot.model_copy(
        update={
            "snapshot_id": phase6_assessment_snapshot_id(
                snapshot, targets=(), candidates=(), derived=()
            )
        }
    )
    repository.record_phase6_assessment(snapshot, targets=(), candidates=(), derived=())

    view = repository.load_phase6_assessment(
        snapshot.assessment_id, snapshot_id=snapshot.snapshot_id
    )

    assert view.assessment_id == snapshot.assessment_id
    assert view.snapshot_id == snapshot.snapshot_id
    assert view.as_of == snapshot.as_of
    assert view.commit_ids == ()
    assert view.committed_comparisons == ()
    assert view.coverage == snapshot.coverage
    assert view.audit_refs == snapshot.audit_refs
    repository.close()


def test_repository_rejects_missing_or_foreign_snapshot_locator() -> None:
    from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentAuthorityError

    repository = SqlAlchemyEvidenceGraphRepository()
    with pytest.raises(Phase6AssessmentAuthorityError, match="snapshot"):
        repository.load_phase6_assessment("asm_other", snapshot_id="p6snap_missing")
    repository.close()


def test_repository_preserves_snapshot_target_reference_order() -> None:
    from novelty_harness.evidence.graph.assessment_ledger import (
        Phase6AssessmentSnapshotRecord,
        Phase6TargetLedgerRecord,
        phase6_assessment_snapshot_id,
        phase6_target_record_id,
    )
    from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile

    repository = SqlAlchemyEvidenceGraphRepository()
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="pending",
        assessment_id="asm_ordered_view",
        as_of=date(2026, 10, 1),
        method_version="phase6-v1",
        max_sources_per_mcu=1,
        max_versions_per_source=1,
        max_expansions=0,
        window_chars=100,
        target_record_ids=(),
        candidate_record_ids=(),
        derived_record_ids=(),
        lineage_cluster_ids=(),
        commit_ids=(),
        coverage=Phase6CoverageLedger(),
        audit_refs=(),
        completed_at=NOW,
    )
    pending_targets = tuple(
        Phase6TargetLedgerRecord(
            snapshot_id="pending",
            assessment_id=snapshot.assessment_id,
            profile=MCUComparisonProfile(
                target_id=target_id, label=target_id, statement=f"Statement {target_id}"
            ),
        )
        for target_id in ("mcu_z", "mcu_a")
    )
    snapshot_id = phase6_assessment_snapshot_id(
        snapshot, targets=pending_targets, candidates=(), derived=()
    )
    targets = tuple(
        item.model_copy(update={"snapshot_id": snapshot_id}) for item in pending_targets
    )
    snapshot = snapshot.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": tuple(phase6_target_record_id(item) for item in targets),
        }
    )
    repository.record_phase6_assessment(snapshot, targets=targets, candidates=(), derived=())

    view = repository.load_phase6_assessment(snapshot.assessment_id, snapshot_id=snapshot_id)

    assert tuple(str(item.target_id) for item in view.targets) == ("mcu_z", "mcu_a")
    repository.close()


def test_loader_pins_sqlite_read_snapshot_before_ledger_reads(tmp_path) -> None:
    from novelty_harness.evidence.graph.assessment_ledger import (
        Phase6TargetLedgerRecord,
        phase6_target_record_id,
    )
    from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile

    database = tmp_path / "snapshot-consistency.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="pending",
        assessment_id="asm_snapshot_consistency",
        as_of=date(2026, 10, 1),
        method_version="phase6-v1",
        max_sources_per_mcu=0,
        max_versions_per_source=0,
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
    pending_target = Phase6TargetLedgerRecord(
        snapshot_id="pending",
        assessment_id=snapshot.assessment_id,
        profile=MCUComparisonProfile(
            target_id="mcu_consistency",
            label="Consistency target",
            statement="Read from the persisted ledger",
        ),
    )
    snapshot_id = phase6_assessment_snapshot_id(
        snapshot, targets=(pending_target,), candidates=(), derived=()
    )
    target = pending_target.model_copy(update={"snapshot_id": snapshot_id})
    snapshot = snapshot.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": (phase6_target_record_id(target),),
        }
    )
    repository.record_phase6_assessment(snapshot, targets=(target,), candidates=(), derived=())
    concurrent_write_blocked: list[bool] = []

    def attempt_concurrent_write(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        if "FROM phase6_assessment_snapshots" not in statement:
            return
        try:
            with sqlite3.connect(database, timeout=0) as writer:
                writer.execute(
                    "UPDATE phase6_assessment_targets "
                    "SET document_json = document_json || ' ' WHERE record_id = ?",
                    (phase6_target_record_id(target),),
                )
        except sqlite3.OperationalError as exc:
            concurrent_write_blocked.append("locked" in str(exc).casefold())

    event.listen(repository.engine, "after_cursor_execute", attempt_concurrent_write)
    try:
        view = repository.load_phase6_assessment(
            snapshot.assessment_id, snapshot_id=snapshot.snapshot_id
        )
    finally:
        event.remove(repository.engine, "after_cursor_execute", attempt_concurrent_write)
    assert view.snapshot_id == snapshot.snapshot_id
    assert view.targets == (target.profile,)
    assert concurrent_write_blocked == [True]
    repository.close()


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
