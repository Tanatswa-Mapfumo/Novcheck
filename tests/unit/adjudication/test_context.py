from datetime import UTC, date, datetime

import pytest

from novelty_harness.adjudication.context import Phase7InputManifest, is_true_noop
from novelty_harness.domain.enums import SufficiencyState
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    IdeaContext,
    ProblemDescription,
    SufficiencyAssessment,
)
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CoverageLedger,
    phase6_assessment_snapshot_id,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.research.adaptive.pipeline import ResearchResult
from novelty_harness.runtime.budgets.controller import BudgetUsage

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 10, 3)
PROVENANCE = ArtifactProvenance(kind="implemented", component="test", detail="context")


def make_manifest(**changes: object) -> Phase7InputManifest:
    cir = CanonicalIdeaRepresentation(
        idea_id="idea_context",
        original_input="A proposed mechanism requiring clarification",
        original_input_ref="input_context",
        problem=ProblemDescription(statement="An unresolved problem"),
        context=IdeaContext(temporal_cutoff=AS_OF),
        provenance=PROVENANCE,
    )
    values: dict[str, object] = {
        "assessment_id": "asm_context",
        "phase6_snapshot_id": "p6snap_placeholder",
        "as_of": AS_OF,
        "cir": cir,
        "sufficiency": SufficiencyAssessment(
            idea_id=cir.idea_id,
            state=SufficiencyState.INSUFFICIENT,
            missing_information=("mechanism",),
            provenance=PROVENANCE,
        ),
        "mcu_graph": MCUGraph(idea_id=cir.idea_id, mcus=(), provenance=PROVENANCE),
        "budget_usage": BudgetUsage(provider_calls=0),
        "unknown_upstream_artifacts": ("phase3", "phase4"),
        "method_versions": {"phase7-context": "v1"},
    }
    values.update(changes)
    return Phase7InputManifest.model_validate(values)


def make_snapshot(repository: SqlAlchemyEvidenceGraphRepository) -> str:
    snapshot = Phase6AssessmentSnapshotRecord(
        snapshot_id="pending",
        assessment_id="asm_context",
        as_of=AS_OF,
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
    snapshot_id = phase6_assessment_snapshot_id(snapshot, targets=(), candidates=(), derived=())
    repository.record_phase6_assessment(
        snapshot.model_copy(update={"snapshot_id": snapshot_id}),
        targets=(),
        candidates=(),
        derived=(),
    )
    return snapshot_id


def test_escalation_manifest_keeps_cumulative_budget_above_latest_pass() -> None:
    latest = ResearchResult(
        batches=(),
        fused_candidates=(),
        candidate_clusters=(),
        chronology={},
        temporal_assessments={},
        branch_states=(),
        stop_assessments=(),
        coverage_matrix=(),
        expansion_events=(),
        request_events=(),
        budget_usage=BudgetUsage(provider_calls=1),
        limitations=(),
    )
    manifest = make_manifest(
        research_result=latest,
        budget_usage=BudgetUsage(provider_calls=2),
    )
    assert manifest.budget_usage.provider_calls == 2
    assert manifest.research_result == latest


def test_context_seals_matching_phase6_snapshot(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "phase7.db")
    snapshot_id = make_snapshot(repository)
    manifest = make_manifest(phase6_snapshot_id=snapshot_id)

    sealed = repository.seal_phase7_context(
        "asm_context", snapshot_id=snapshot_id, manifest=manifest
    )
    loaded = repository.load_phase7_context("asm_context", context_id=sealed.context_id)

    assert loaded == sealed
    assert sealed.snapshot_id == snapshot_id
    assert sealed.manifest_digest == manifest.content_digest()
    assert sealed.context_id.startswith("p7ctx_")
    assert (
        repository.seal_phase7_context("asm_context", snapshot_id=snapshot_id, manifest=manifest)
        == sealed
    )
    with pytest.raises(ValueError):
        repository.seal_phase7_context("asm_foreign", snapshot_id=snapshot_id, manifest=manifest)
    repository.close()


def test_context_changes_for_same_snapshot_new_budget_or_coverage(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "phase7.db")
    snapshot_id = make_snapshot(repository)
    first = repository.seal_phase7_context(
        "asm_context",
        snapshot_id=snapshot_id,
        manifest=make_manifest(phase6_snapshot_id=snapshot_id),
    )
    second = repository.seal_phase7_context(
        "asm_context",
        snapshot_id=snapshot_id,
        manifest=make_manifest(
            phase6_snapshot_id=snapshot_id,
            budget_usage=BudgetUsage(provider_calls=1),
            query_history=("qry_zero_yield",),
            stop_reason="NO_NEW_YIELD",
        ),
        parent_context_id=first.context_id,
    )
    assert second.context_id != first.context_id
    assert second.snapshot_id == first.snapshot_id
    assert second.parent_context_id == first.context_id
    assert not is_true_noop(first, second)
    repository.close()


def test_context_true_noop_requires_all_bound_state_equal(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "phase7.db")
    snapshot_id = make_snapshot(repository)
    first = repository.seal_phase7_context(
        "asm_context",
        snapshot_id=snapshot_id,
        manifest=make_manifest(phase6_snapshot_id=snapshot_id),
    )
    replay = repository.load_phase7_context("asm_context", context_id=first.context_id)
    assert is_true_noop(first, replay)
    for changed in ("new query", "new provider", "new access state"):
        successor = repository.seal_phase7_context(
            "asm_context",
            snapshot_id=snapshot_id,
            manifest=make_manifest(
                phase6_snapshot_id=snapshot_id,
                query_history=(changed,),
            ),
            parent_context_id=first.context_id,
        )
        assert not is_true_noop(first, successor)
    repository.close()
