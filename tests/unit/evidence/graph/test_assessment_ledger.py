from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
    Phase6DerivedLedgerRecord,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_candidate_record_id,
    phase6_derived_record_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind
from novelty_harness.evidence.graph.sqlalchemy_models import Phase6AssessmentCandidateRow
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.precedent.gates import MultiSourceAssessment
from novelty_harness.evidence.precedent.models import (
    PatentScreeningDateRecord,
    PatentScreeningResult,
)
from novelty_harness.evidence.verification.models import ContextExpansion
from tests.fixtures.phase5 import make_passage, phase5_provenance

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
    expansions: tuple[ContextExpansion, ...] = (),
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
        "expansions": expansions,
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


def _context_expansion(observed_at: datetime) -> ContextExpansion:
    passage = make_passage(
        "src_ledger",
        text="A same-source context passage.",
        source_version_id="srcv_ledger",
        observed_at=observed_at,
    )
    return ContextExpansion(
        origin_passage_id="pass_origin",
        source_id="src_ledger",
        source_version_id="srcv_ledger",
        attempt=1,
        available=True,
        window_passage=passage,
        observed_at=observed_at,
        provenance=phase5_provenance("assessment-ledger-context-expansion-test"),
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


def test_candidate_expansion_replay_ignores_observation_clocks_and_keeps_first_payload() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(
        nodes=(
            _graph_node("src_ledger", GraphNodeKind.SOURCE),
            _graph_node("srcv_ledger", GraphNodeKind.SOURCE_VERSION, source_id="src_ledger"),
        )
    )
    pending_target = Phase6TargetLedgerRecord(
        snapshot_id="pending", assessment_id="asm_ledger", profile=_profile()
    )
    original_expansion = _context_expansion(NOW)
    original_candidate = _candidate(
        snapshot_id="pending",
        source_version_id="srcv_ledger",
        expansions=(original_expansion,),
    )
    original_snapshot, targets, candidates = _ledger(
        targets=(pending_target,), candidates=(original_candidate,)
    )
    later = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)
    replay_expansion = original_expansion.model_copy(
        update={
            "observed_at": later,
            "window_passage": original_expansion.window_passage.model_copy(
                update={"observed_at": later}
            ),
        }
    )
    replay_candidate = _candidate(
        snapshot_id="pending",
        source_version_id="srcv_ledger",
        expansions=(replay_expansion,),
    )
    replay_snapshot, replay_targets, replay_candidates = _ledger(
        targets=(pending_target,), candidates=(replay_candidate,)
    )

    assert replay_snapshot.snapshot_id == original_snapshot.snapshot_id
    assert phase6_candidate_record_id(replay_candidates[0]) == phase6_candidate_record_id(
        candidates[0]
    )
    repository.record_phase6_assessment(
        original_snapshot, targets=targets, candidates=candidates, derived=()
    )
    repository.record_phase6_assessment(
        replay_snapshot, targets=replay_targets, candidates=replay_candidates, derived=()
    )
    record_id = phase6_candidate_record_id(candidates[0])
    with repository.engine.connect() as connection:
        document = connection.execute(
            select(Phase6AssessmentCandidateRow.document_json).where(
                Phase6AssessmentCandidateRow.record_id == record_id
            )
        ).scalar_one()
    stored = Phase6CandidateLedgerRecord.model_validate_json(document)
    assert stored.expansions[0].observed_at == NOW
    assert stored.expansions[0].window_passage is not None
    assert stored.expansions[0].window_passage.observed_at == NOW
    changed_provenance = replay_expansion.model_copy(
        update={"provenance": phase5_provenance("changed-context-provenance")}
    )
    semantic_change = _candidate(
        snapshot_id="pending",
        source_version_id="srcv_ledger",
        expansions=(changed_provenance,),
    )
    changed_snapshot, _, _ = _ledger(targets=(pending_target,), candidates=(semantic_change,))
    assert changed_snapshot.snapshot_id != original_snapshot.snapshot_id
    repository.close()


def test_derived_patent_observation_clock_is_ignored_but_disclosure_date_is_not() -> None:
    result = PatentScreeningResult(
        screening_id="psr_ledger",
        mcu_id="mcu_ledger",
        mode="LIMITED",
        reference_source_ids=("src_ledger",),
        dates=(
            PatentScreeningDateRecord(source_id="src_ledger", publication_date=date(2020, 1, 1)),
        ),
        observed_at=NOW,
        provenance=phase5_provenance("patent-screening-test"),
    )
    derived = Phase6DerivedLedgerRecord(
        snapshot_id="p6snap_derived",
        assessment_id="asm_ledger",
        target_id="mcu_ledger",
        kind="PATENT",
        input_commit_ids=(),
        input_edge_ids=(),
        input_classification_ids=(),
        lineage_root_ids=(),
        as_of=date(2026, 10, 1),
        method_version="patent-v1",
        result=result,
    )
    replay = derived.model_copy(
        update={
            "result": result.model_copy(
                update={"observed_at": datetime(2026, 10, 1, 13, 0, tzinfo=UTC)}
            )
        }
    )
    changed_date = derived.model_copy(
        update={
            "result": result.model_copy(
                update={
                    "dates": (
                        PatentScreeningDateRecord(
                            source_id="src_ledger", publication_date=date(2021, 1, 1)
                        ),
                    )
                }
            )
        }
    )

    assert phase6_derived_record_id(replay) == phase6_derived_record_id(derived)
    assert phase6_derived_record_id(changed_date) != phase6_derived_record_id(derived)


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

    with pytest.raises(ValueError, match="source version does not resolve"):
        repository.record_phase6_assessment(
            snapshot, targets=targets, candidates=candidates, derived=()
        )
    repository.close()


@pytest.mark.parametrize(
    (
        "descriptor_field",
        "descriptor_value",
        "source_attributes",
        "version_attributes",
        "decision",
    ),
    [
        (
            "source_content_hash",
            "hash_invented",
            {"content_hash": "hash_actual", "access_state": "METADATA_ONLY"},
            None,
            "FAILED_MAPPING",
        ),
        (
            "source_access_state",
            SourceAccessState.FULL_TEXT,
            {"content_hash": None, "access_state": SourceAccessState.METADATA_ONLY.value},
            None,
            "EXCLUDED_SOURCE_BOUND",
        ),
        (
            "version_content_hash",
            "hash_invented",
            {"content_hash": "hash_source", "access_state": "METADATA_ONLY"},
            {"content_hash": "hash_actual", "access_state": "FULL_TEXT"},
            "FAILED_VERIFICATION",
        ),
        (
            "version_access_state",
            SourceAccessState.METADATA_ONLY,
            {"content_hash": "hash_source", "access_state": "METADATA_ONLY"},
            {"content_hash": "hash_version", "access_state": "FULL_TEXT"},
            "UNASSESSABLE",
        ),
    ],
)
def test_candidate_descriptors_must_match_persisted_nodes(
    descriptor_field, descriptor_value, source_attributes, version_attributes, decision
) -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    nodes = [_graph_node("src_ledger", GraphNodeKind.SOURCE, **source_attributes)]
    version_id = None
    if version_attributes is not None:
        version_id = "srcv_ledger"
        nodes.append(
            _graph_node(
                version_id,
                GraphNodeKind.SOURCE_VERSION,
                source_id="src_ledger",
                **version_attributes,
            )
        )
    repository.upsert(nodes=tuple(nodes))
    pending_target = Phase6TargetLedgerRecord(
        snapshot_id="pending", assessment_id="asm_ledger", profile=_profile()
    )
    candidate_baseline = {
        "source_content_hash": source_attributes["content_hash"],
        "source_access_state": SourceAccessState(source_attributes["access_state"]),
        "version_content_hash": (
            version_attributes["content_hash"] if version_attributes is not None else None
        ),
        "version_access_state": (
            SourceAccessState(version_attributes["access_state"])
            if version_attributes is not None
            else None
        ),
    }
    candidate = _candidate(
        snapshot_id="pending", source_version_id=version_id, decision=decision
    ).model_copy(update={**candidate_baseline, descriptor_field: descriptor_value})
    snapshot, targets, candidates = _ledger(targets=(pending_target,), candidates=(candidate,))

    with pytest.raises(ValueError, match="(?i)candidate .* descriptor|content descriptor"):
        repository.record_phase6_assessment(
            snapshot, targets=targets, candidates=candidates, derived=()
        )
    repository.close()


@pytest.mark.parametrize(
    ("derived_target", "result_target", "derived_as_of"),
    [
        ("mcu_ledger", "mcu_other", date(2026, 10, 1)),
        ("mcu_ledger", "mcu_ledger", date(2026, 9, 30)),
    ],
)
def test_derived_result_target_and_cutoff_must_match_snapshot(
    derived_target, result_target, derived_as_of
) -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    template = _snapshot()
    target = Phase6TargetLedgerRecord(
        snapshot_id="pending", assessment_id=template.assessment_id, profile=_profile()
    )
    result = MultiSourceAssessment(
        mcu_id=result_target,
        combination_context="NONE",
        single_source_direct_eligible=False,
        independent_roots=0,
        contributing_roots=0,
        summary=("No multi-source result was produced.",),
    )
    derived = Phase6DerivedLedgerRecord(
        snapshot_id="pending",
        assessment_id=template.assessment_id,
        target_id=derived_target,
        kind="MULTI_SOURCE",
        input_commit_ids=(),
        input_edge_ids=(),
        input_classification_ids=(),
        lineage_root_ids=(),
        as_of=derived_as_of,
        method_version="phase6-v1",
        result=result,
    )
    snapshot_id = phase6_assessment_snapshot_id(
        template, targets=(target,), candidates=(), derived=(derived,)
    )
    target = target.model_copy(update={"snapshot_id": snapshot_id})
    derived = derived.model_copy(update={"snapshot_id": snapshot_id})
    snapshot = template.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": (phase6_target_record_id(target),),
            "derived_record_ids": (phase6_derived_record_id(derived),),
        }
    )

    with pytest.raises(ValueError, match="(?i)derived .* target|derived .* cutoff"):
        repository.record_phase6_assessment(
            snapshot, targets=(target,), candidates=(), derived=(derived,)
        )
    repository.close()


def test_derived_input_comparison_mcu_must_match_derived_target() -> None:
    from novelty_harness.evidence.graph.assessment_ledger import (
        phase6_assessment_snapshot_id,
        phase6_candidate_record_id,
        phase6_derived_record_id,
        phase6_target_record_id,
    )
    from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
    from novelty_harness.evidence.precedent.gates import (
        ClassifiedComparison,
        classify_verified_comparison,
    )
    from novelty_harness.evidence.verification.integrity import verified_comparison
    from tests.adversarial.test_phase6_r10_content_authority import (
        _authority_nodes,
        _chain_for_content,
    )
    from tests.unit.evidence.verification.test_eligibility import NOW, PASSAGE_TEXT

    repository = SqlAlchemyEvidenceGraphRepository()
    chain = _chain_for_content(PASSAGE_TEXT)
    classified = ClassifiedComparison(
        comparison=verified_comparison(chain),
        classification=classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW),
    )
    receipt = repository.upsert(
        nodes=_authority_nodes(chain),
        verified_edges=(chain.edge,),
        verified_chains=(chain,),
        classified_comparisons=(classified,),
    )
    assert receipt is not None and receipt.commit_id is not None
    assessed_target = chain.edge.mcu_id
    derived_target = "mcu_other"
    template = Phase6AssessmentSnapshotRecord(
        snapshot_id="pending",
        assessment_id=chain.assessment_id,
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
        commit_ids=(receipt.commit_id,),
        coverage=Phase6CoverageLedger(),
        audit_refs=(),
        completed_at=NOW,
    )
    target_records = tuple(
        Phase6TargetLedgerRecord(
            snapshot_id="pending",
            assessment_id=chain.assessment_id,
            profile=MCUComparisonProfile(target_id=target, label=target, statement=target),
        )
        for target in (assessed_target, derived_target)
    )
    candidate = Phase6CandidateLedgerRecord(
        snapshot_id="pending",
        assessment_id=chain.assessment_id,
        target_id=assessed_target,
        source_id=chain.source.source_id,
        source_version_id=chain.version.version_id if chain.version is not None else None,
        source_content_hash=chain.source.content_hash,
        version_content_hash=chain.version.content_hash if chain.version is not None else None,
        source_access_state=chain.source.access_state,
        version_access_state=chain.version.access_state if chain.version is not None else None,
        decision="ASSESSED",
        projection_intent="GRAPH_BACKED",
        commit_id=receipt.commit_id,
        verified_edge_id=chain.edge.edge_id,
        classification_id=classified.classification.classification_id,
    )
    result = MultiSourceAssessment(
        mcu_id=derived_target,
        combination_context="NONE",
        single_source_direct_eligible=False,
        independent_roots=0,
        contributing_roots=0,
        summary=("No multi-source result was produced.",),
    )
    derived = Phase6DerivedLedgerRecord(
        snapshot_id="pending",
        assessment_id=chain.assessment_id,
        target_id=derived_target,
        kind="MULTI_SOURCE",
        input_commit_ids=(receipt.commit_id,),
        input_edge_ids=(chain.edge.edge_id,),
        input_classification_ids=(classified.classification.classification_id,),
        lineage_root_ids=(),
        lineage_limitations=("Lineage roots are unavailable in this fixture.",),
        as_of=template.as_of,
        method_version="phase6-v1",
        result=result,
    )
    snapshot_id = phase6_assessment_snapshot_id(
        template, targets=target_records, candidates=(candidate,), derived=(derived,)
    )
    targets = tuple(item.model_copy(update={"snapshot_id": snapshot_id}) for item in target_records)
    candidate = candidate.model_copy(update={"snapshot_id": snapshot_id})
    derived = derived.model_copy(update={"snapshot_id": snapshot_id})
    snapshot = template.model_copy(
        update={
            "snapshot_id": snapshot_id,
            "target_record_ids": tuple(phase6_target_record_id(item) for item in targets),
            "candidate_record_ids": (phase6_candidate_record_id(candidate),),
            "derived_record_ids": (phase6_derived_record_id(derived),),
        }
    )

    with pytest.raises(ValueError, match="Derived input comparison MCU differs from its target"):
        repository.record_phase6_assessment(
            snapshot, targets=targets, candidates=(candidate,), derived=(derived,)
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


def test_candidate_retains_source_and_version_routing_descriptors() -> None:
    candidate = Phase6CandidateLedgerRecord(
        snapshot_id="p6snap_1",
        assessment_id="asm_1",
        target_id="mcu_1",
        source_id="src_1",
        source_version_id="srcv_1",
        source_content_hash="sha256:source",
        version_content_hash="sha256:version",
        source_access_state="FULL_TEXT",
        version_access_state="ABSTRACT_ONLY",
        routing_priority=0,
        evidence_families=("PAPER",),
        decision="EXCLUDED_VERSION_BOUND",
        reason="VERSION_BOUND",
    )

    assert candidate.source_access_state.value == "FULL_TEXT"
    assert candidate.version_access_state.value == "ABSTRACT_ONLY"
    assert candidate.routing_priority == 0


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
