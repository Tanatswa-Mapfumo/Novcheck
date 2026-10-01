from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from tests.fixtures.phase5 import phase5_provenance

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _snapshot(
    *, audit_refs: tuple[str, ...] = (), completed_at: datetime = NOW
) -> Phase6AssessmentSnapshotRecord:
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="p6snap_pending",
        assessment_id="asm_ledger",
        as_of=date(2026, 10, 1),
        method_version="phase6-v1",
        max_sources_per_mcu=3,
        max_versions_per_source=2,
        max_expansions=2,
        window_chars=1000,
        target_record_ids=(),
        candidate_record_ids=(),
        derived_record_ids=(),
        lineage_cluster_ids=(),
        commit_ids=(),
        coverage=Phase6CoverageLedger(),
        audit_refs=audit_refs,
        completed_at=completed_at,
    )
    computed = phase6_assessment_snapshot_id(snapshot, targets=(), candidates=(), derived=())
    return snapshot.model_copy(update={"snapshot_id": computed})


def _profile(target_id: str = "mcu_ledger") -> MCUComparisonProfile:
    return MCUComparisonProfile(
        target_id=target_id,
        label="Target",
        statement="A target contribution",
    )


def _candidate(
    *,
    snapshot_id: str,
    source_id: str = "src_ledger",
    source_version_id: str | None = None,
    decision: str = "FAILED_MAPPING",
    commit_id: str | None = None,
) -> Phase6CandidateLedgerRecord:
    values: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "assessment_id": "asm_ledger",
        "target_id": "mcu_ledger",
        "source_id": source_id,
        "source_version_id": source_version_id,
        "decision": decision,
        "reason": "candidate retained for ledger validation",
        "failure_stage": "MAPPING" if decision != "ASSESSED" else None,
    }
    if decision == "ASSESSED":
        values.update(
            projection_intent="GRAPH_BACKED",
            commit_id=commit_id,
            verified_edge_id="edge_missing",
            classification_id="cls_missing",
            failure_stage=None,
        )
    return Phase6CandidateLedgerRecord.model_validate(values)


def _ledger(
    *,
    targets: tuple[Phase6TargetLedgerRecord, ...],
    candidates: tuple[Phase6CandidateLedgerRecord, ...],
    commit_ids: tuple[str, ...] = (),
) -> tuple[
    Phase6AssessmentSnapshotRecord,
    tuple[Phase6TargetLedgerRecord, ...],
    tuple[Phase6CandidateLedgerRecord, ...],
]:
    template = _snapshot().model_copy(update={"commit_ids": commit_ids})
    snapshot_id = phase6_assessment_snapshot_id(
        template, targets=targets, candidates=candidates, derived=()
    )
    final_targets = tuple(item.model_copy(update={"snapshot_id": snapshot_id}) for item in targets)
    final_candidates = tuple(
        item.model_copy(update={"snapshot_id": snapshot_id}) for item in candidates
    )
    target_record_ids = tuple(phase6_target_record_id(item) for item in final_targets)
    from novelty_harness.evidence.graph.assessment_ledger import phase6_candidate_record_id

    snapshot = template.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": target_record_ids,
            "candidate_record_ids": tuple(
                phase6_candidate_record_id(item) for item in final_candidates
            ),
            "commit_ids": commit_ids,
        }
    )
    return snapshot, final_targets, final_candidates


def _graph_node(node_id: str, kind: GraphNodeKind, **attributes: object) -> GraphNode:
    return GraphNode(
        node_id=node_id,
        kind=kind,
        observed_at=NOW,
        provenance=phase5_provenance("assessment-ledger-test"),
        attributes=attributes,
    )


def test_zero_comparison_snapshot_is_persisted_and_exact_replay_is_idempotent() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    snapshot = _snapshot()

    assert (
        repository.record_phase6_assessment(snapshot, targets=(), candidates=(), derived=())
        == snapshot.snapshot_id
    )
    assert (
        repository.record_phase6_assessment(snapshot, targets=(), candidates=(), derived=())
        == snapshot.snapshot_id
    )
    repository.close()


def test_same_snapshot_id_cannot_be_reused_for_changed_facts() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    original = _snapshot()
    changed = original.model_copy(update={"method_version": "phase6-v2"})
    repository.record_phase6_assessment(original, targets=(), candidates=(), derived=())

    with pytest.raises(ValueError, match="snapshot ID does not match"):
        repository.record_phase6_assessment(changed, targets=(), candidates=(), derived=())
    repository.close()


def test_snapshot_identity_ignores_audit_references_and_completion_time() -> None:
    original = _snapshot(audit_refs=("trace_first",))
    replay = original.model_copy(
        update={
            "audit_refs": ("trace_retry",),
            "completed_at": datetime(2026, 10, 1, 13, 0, tzinfo=UTC),
        }
    )

    assert (
        phase6_assessment_snapshot_id(replay, targets=(), candidates=(), derived=())
        == original.snapshot_id
    )


def test_snapshot_replay_keeps_first_audit_metadata_and_completion_time() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    original = _snapshot(audit_refs=("trace_first",))
    replay = original.model_copy(
        update={
            "audit_refs": ("trace_retry",),
            "completed_at": datetime(2026, 10, 1, 13, 0, tzinfo=UTC),
        }
    )
    replay = replay.model_copy(
        update={
            "snapshot_id": phase6_assessment_snapshot_id(
                replay, targets=(), candidates=(), derived=()
            )
        }
    )
    repository.record_phase6_assessment(original, targets=(), candidates=(), derived=())

    assert repository.record_phase6_assessment(replay, targets=(), candidates=(), derived=()) == (
        original.snapshot_id
    )
    with repository.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT document_json FROM phase6_assessment_snapshots "
                "WHERE snapshot_id = :snapshot_id"
            ),
            {"snapshot_id": original.snapshot_id},
        ).scalar_one()
    stored = Phase6AssessmentSnapshotRecord.model_validate_json(row)
    assert stored.audit_refs == original.audit_refs
    assert stored.completed_at == original.completed_at
    repository.close()


def test_new_snapshot_can_persist_changed_assessment_facts() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.record_phase6_assessment(_snapshot(), targets=(), candidates=(), derived=())
    changed = _snapshot().model_copy(update={"method_version": "phase6-v2"})
    changed = changed.model_copy(
        update={
            "snapshot_id": phase6_assessment_snapshot_id(
                changed, targets=(), candidates=(), derived=()
            )
        }
    )

    assert (
        repository.record_phase6_assessment(changed, targets=(), candidates=(), derived=())
        == changed.snapshot_id
    )
    repository.close()


def test_target_assessment_and_snapshot_joins_are_validated() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    snapshot = _snapshot()
    profile = _profile()
    target = Phase6TargetLedgerRecord(
        snapshot_id=snapshot.snapshot_id,
        assessment_id="asm_other",
        profile=profile,
    )
    malformed = snapshot.model_copy(
        update={"target_record_ids": ("p6target_placeholder",), "snapshot_id": "p6snap_tmp"}
    )
    malformed = malformed.model_copy(
        update={
            "snapshot_id": phase6_assessment_snapshot_id(
                malformed, targets=(target,), candidates=(), derived=()
            )
        }
    )
    target = target.model_copy(update={"snapshot_id": malformed.snapshot_id})
    record_id = phase6_target_record_id(target)
    malformed = malformed.model_copy(update={"target_record_ids": (record_id,)})

    with pytest.raises(ValueError, match="assessment"):
        repository.record_phase6_assessment(malformed, targets=(target,), candidates=(), derived=())
    repository.close()


def test_candidate_source_must_exist_in_repository() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    pending_target = Phase6TargetLedgerRecord(
        snapshot_id="pending", assessment_id="asm_ledger", profile=_profile()
    )
    pending_candidate = _candidate(snapshot_id="pending", source_id="src_missing")
    snapshot, targets, candidates = _ledger(
        targets=(pending_target,), candidates=(pending_candidate,)
    )

    with pytest.raises(ValueError, match="source does not resolve"):
        repository.record_phase6_assessment(
            snapshot, targets=targets, candidates=candidates, derived=()
        )
    repository.close()


def test_candidate_version_must_belong_to_its_source() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(
        nodes=(
            _graph_node("src_ledger", GraphNodeKind.SOURCE),
            _graph_node("src_other", GraphNodeKind.SOURCE),
            _graph_node("srcv_ledger", GraphNodeKind.SOURCE_VERSION, source_id="src_other"),
        )
    )
    pending_target = Phase6TargetLedgerRecord(
        snapshot_id="pending", assessment_id="asm_ledger", profile=_profile()
    )
    pending_candidate = _candidate(snapshot_id="pending", source_version_id="srcv_ledger")
    snapshot, targets, candidates = _ledger(
        targets=(pending_target,), candidates=(pending_candidate,)
    )

    with pytest.raises(ValueError, match="source version does not belong"):
        repository.record_phase6_assessment(
            snapshot, targets=targets, candidates=candidates, derived=()
        )
    repository.close()


def test_assessed_candidate_must_join_to_existing_commit() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(nodes=(_graph_node("src_ledger", GraphNodeKind.SOURCE),))
    pending_target = Phase6TargetLedgerRecord(
        snapshot_id="pending", assessment_id="asm_ledger", profile=_profile()
    )
    pending_candidate = _candidate(
        snapshot_id="pending",
        decision="ASSESSED",
        commit_id="p6commit_missing",
    )
    snapshot, targets, candidates = _ledger(
        targets=(pending_target,),
        candidates=(pending_candidate,),
        commit_ids=("p6commit_missing",),
    )

    with pytest.raises(ValueError, match="missing commit"):
        repository.record_phase6_assessment(
            snapshot, targets=targets, candidates=candidates, derived=()
        )
    repository.close()


def test_candidate_projection_intent_is_explicit_and_frozen() -> None:
    candidate = Phase6CandidateLedgerRecord(
        snapshot_id="p6snap_1",
        assessment_id="asm_1",
        target_id="mcu_1",
        source_id="src_1",
        source_version_id="srcv_1",
        source_content_hash="sha256:source",
        version_content_hash="sha256:version",
        evidence_families=("PAPER",),
        decision="ASSESSED",
        reason=None,
        failure_stage=None,
        projection_intent="SEMANTIC_ONLY",
        commit_id="p6commit_1",
        verified_edge_id="edge_1",
        classification_id="cls_1",
        expansions=(),
        limitations=(),
    )
    with pytest.raises((ValidationError, TypeError)):
        candidate.decision = "FAILED_MAPPING"  # type: ignore[misc]


def test_snapshot_retains_lineage_cluster_ids() -> None:
    coverage = Phase6CoverageLedger(
        selected_source_ids=(),
        excluded_sources=(),
        selected_version_ids=(),
        excluded_versions=(),
        limitations=(),
    )
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="p6snap_1",
        assessment_id="asm_1",
        as_of=date(2026, 10, 1),
        method_version="phase6-v1",
        max_sources_per_mcu=3,
        max_versions_per_source=2,
        max_expansions=2,
        window_chars=1000,
        target_record_ids=(),
        candidate_record_ids=(),
        derived_record_ids=(),
        lineage_cluster_ids=("lin_1",),
        commit_ids=(),
        coverage=coverage,
        audit_refs=(),
        completed_at=NOW,
    )
    assert snapshot.lineage_cluster_ids == ("lin_1",)
    with pytest.raises((ValidationError, TypeError)):
        snapshot.lineage_cluster_ids = ()  # type: ignore[misc]
