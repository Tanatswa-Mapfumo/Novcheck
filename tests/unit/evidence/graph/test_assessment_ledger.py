from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


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
