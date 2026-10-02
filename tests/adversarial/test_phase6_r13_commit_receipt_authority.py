"""R13: a receipt is a reference to persisted authority, not authority itself."""

import json
from dataclasses import replace

import pytest
from sqlalchemy import text

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION, schema_version
from novelty_harness.evidence.graph.repository import Phase6CommitReceipt
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.phase6_pipeline import Phase6EvidenceResult
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.precedent.models import PrecedentClassification
from novelty_harness.evidence.verification.integrity import (
    VerifiedEvidenceChain,
    verified_comparison,
)
from novelty_harness.runtime.tracing.hashing import canonical_json
from tests.adversarial.test_phase6_r10_content_authority import (
    _authority_nodes,
    _chain_for_content,
)
from tests.adversarial.test_phase6_r11_authoritative_publication import (
    _phase5,
    _run,
    _verifier_state_runner,
)
from tests.adversarial.test_phase6_r15_assessment_authority import _load_committed_matrix_case
from tests.adversarial.test_phase6_sol_review_regressions import _valid_chain
from tests.diagnostics.legacy_phase6_projection import (
    diagnostic_legacy_projection_ignores_graph_authority,
)
from tests.unit.evidence.verification.test_eligibility import (
    NOW,
    PASSAGE_TEXT,
    build,
)


def _result(
    chain: VerifiedEvidenceChain,
    classification: PrecedentClassification,
    receipt: Phase6CommitReceipt,
) -> Phase6EvidenceResult:
    return Phase6EvidenceResult(
        profiles=(),
        propositions=(),
        mappings=(),
        claims=(),
        verifications=(),
        expansions=(),
        edges=(chain.edge,),
        chains=(chain,),
        classifications=(classification,),
        commit_receipts=(receipt,),
        candidate_assessments=(),
        multi_source=(),
        patent_screenings=(),
        unassessed_sources=(),
        unassessed_versions=(),
        coverage_limitations=(),
        failures=(),
        limitations=(),
        graph_ref="nonexistent.sqlite",
        snapshot_id="p6snap_fixture",
    )


def _unpersisted_result() -> Phase6EvidenceResult:
    chain = _valid_chain(build(SupportVerificationState.SUPPORTED))
    classification = classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW)
    receipt = Phase6CommitReceipt(
        assessment_id=chain.assessment_id,
        committed_edge_ids=(chain.edge.edge_id,),
        committed_classification_ids=(classification.classification_id,),
    )
    return _result(chain, classification, receipt)


def _commit(repository: SqlAlchemyEvidenceGraphRepository) -> Phase6EvidenceResult:
    chain = _chain_for_content(PASSAGE_TEXT)
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    receipt = repository.upsert(
        nodes=_authority_nodes(chain),
        verified_edges=(chain.edge,),
        verified_chains=(chain,),
        classified_comparisons=(
            ClassifiedComparison(comparison=comparison, classification=classification),
        ),
    )
    assert receipt is not None
    return _result(chain, classification, receipt)


def test_fabricated_matching_receipt_without_repository_cannot_project() -> None:
    result = _unpersisted_result()

    with pytest.raises(ValueError, match="repository|commit|authorit"):
        diagnostic_legacy_projection_ignores_graph_authority(result)


def test_fabricated_matching_receipt_with_empty_repository_cannot_project(tmp_path) -> None:
    result = _unpersisted_result()
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "empty.sqlite")
    try:
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            diagnostic_legacy_projection_ignores_graph_authority(result, repository)
    finally:
        repository.close()


def test_exact_persisted_commit_loads_direct_and_replays(tmp_path) -> None:
    repository, loaded, classification, graph_edges = _load_committed_matrix_case(
        tmp_path, "DIRECT_PRECEDENT"
    )
    try:
        assert classification.relation == PrecedentState.DIRECT_PRECEDENT
        assert loaded.committed_comparisons[0].projection_status == "GRAPH_AUTHORIZED"
        assert {relation.edge.edge_id for relation in loaded.authorized_graph_relations} == {
            edge.edge_id for edge in graph_edges
        }
        comparison = loaded.committed_comparisons[0]
        receipt = Phase6CommitReceipt(
            commit_id=comparison.commit_id,
            assessment_id=loaded.assessment_id,
            committed_edge_ids=(comparison.comparison.comparison.chain.edge.edge_id,),
            committed_classification_ids=(classification.classification_id,),
        )
        assert repository.resolve_phase6_commit(receipt).comparisons
        replay_repository, replay, replay_classification, replay_edges = (
            _load_committed_matrix_case(tmp_path, "DIRECT_PRECEDENT")
        )
        try:
            assert replay == loaded
            assert replay_classification == classification
            assert replay_edges == graph_edges
            assert (
                replay_repository.load_phase6_assessment(
                    loaded.assessment_id, snapshot_id=loaded.snapshot_id
                )
                == loaded
            )
        finally:
            replay_repository.close()
    finally:
        repository.close()


def test_genuine_receipt_does_not_authorize_another_repository(tmp_path) -> None:
    first = SqlAlchemyEvidenceGraphRepository(tmp_path / "first.sqlite")
    second = SqlAlchemyEvidenceGraphRepository(tmp_path / "second.sqlite")
    try:
        result = _commit(first)
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            diagnostic_legacy_projection_ignores_graph_authority(result, second)
    finally:
        first.close()
        second.close()


def test_mutated_caller_edge_does_not_project_under_genuine_receipt(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "mutated-edge.sqlite")
    try:
        result = _commit(repository)
        changed = result.edges[0].model_copy(update={"passage_ids": ("pass_foreign",)})
        with pytest.raises(ValueError, match="commit|authorit|differ"):
            diagnostic_legacy_projection_ignores_graph_authority(
                replace(result, edges=(changed,)), repository
            )
    finally:
        repository.close()


def test_mutated_caller_classification_does_not_project_under_genuine_receipt(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "mutated-classification.sqlite")
    try:
        result = _commit(repository)
        changed = result.classifications[0].model_copy(update={"basis": ("invented basis",)})
        with pytest.raises(ValueError, match="commit|authorit|differ"):
            diagnostic_legacy_projection_ignores_graph_authority(
                replace(result, classifications=(changed,)), repository
            )
    finally:
        repository.close()


def test_mutated_and_deserialized_receipts_cannot_invent_authority(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "mutated-receipt.sqlite")
    try:
        result = _commit(repository)
        genuine = result.commit_receipts[0]
        variants = (
            genuine.model_copy(update={"committed_edge_ids": ("edge_foreign",)}),
            genuine.model_copy(update={"commit_id": "p6commit_foreign"}),
            Phase6CommitReceipt.model_construct(
                commit_id=genuine.commit_id,
                assessment_id=genuine.assessment_id,
                committed_edge_ids=genuine.committed_edge_ids,
                committed_classification_ids=("cls_foreign",),
            ),
            Phase6CommitReceipt.model_validate_json(
                json.dumps(
                    {
                        **genuine.model_dump(mode="json"),
                        "commit_id": "p6commit_fabricated",
                    }
                )
            ),
        )
        for receipt in variants:
            with pytest.raises(ValueError, match="commit|authorit|differ"):
                diagnostic_legacy_projection_ignores_graph_authority(
                    replace(result, commit_receipts=(receipt,)), repository
                )
    finally:
        repository.close()


def test_serialized_genuine_receipt_still_resolves_after_reopen(tmp_path) -> None:
    repository, view, classification, _ = _load_committed_matrix_case(tmp_path, "DIRECT_PRECEDENT")
    database = tmp_path / "DIRECT_PRECEDENT.sqlite"
    try:
        comparison = view.committed_comparisons[0]
        receipt = Phase6CommitReceipt(
            commit_id=comparison.commit_id,
            assessment_id=view.assessment_id,
            committed_edge_ids=(comparison.comparison.comparison.chain.edge.edge_id,),
            committed_classification_ids=(classification.classification_id,),
        )
        serialized = receipt.model_dump_json()
    finally:
        repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(database)
    try:
        restored = Phase6CommitReceipt.model_validate_json(serialized)
        assert reopened.resolve_phase6_commit(restored).comparisons
        loaded = reopened.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
        assert loaded == view
    finally:
        reopened.close()


def test_old_receipt_cannot_project_later_authority_rejected_comparison(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "rejected-later.sqlite")
    try:
        original = _commit(repository)
        altered = _chain_for_content(PASSAGE_TEXT + "\n\nA later contrary statement.", paragraph=0)
        altered_comparison = verified_comparison(altered)
        altered_classification = classify_verified_comparison(altered_comparison, clock=lambda: NOW)
        with pytest.raises(ValueError, match="content|authority|digest|provenance"):
            repository.upsert(
                nodes=_authority_nodes(altered),
                verified_edges=(altered.edge,),
                verified_chains=(altered,),
                classified_comparisons=(
                    ClassifiedComparison(
                        comparison=altered_comparison,
                        classification=altered_classification,
                    ),
                ),
            )
        rejected = _result(altered, altered_classification, original.commit_receipts[0])
        with pytest.raises(ValueError, match="commit|authorit|differ"):
            diagnostic_legacy_projection_ignores_graph_authority(rejected, repository)
        with repository.engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM phase6_commits")).scalar_one() == 1
    finally:
        repository.close()


def test_rejected_first_comparison_rolls_back_without_commit_manifest(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "rejected-first.sqlite")
    try:
        original = _chain_for_content(PASSAGE_TEXT)
        altered = _chain_for_content(PASSAGE_TEXT + "\n\nA contrary statement.", paragraph=0)
        repository.upsert(nodes=_authority_nodes(original))
        comparison = verified_comparison(altered)
        classification = classify_verified_comparison(comparison, clock=lambda: NOW)
        with pytest.raises(ValueError, match="content|authority|digest|provenance"):
            repository.upsert(
                nodes=_authority_nodes(altered),
                verified_edges=(altered.edge,),
                verified_chains=(altered,),
                classified_comparisons=(
                    ClassifiedComparison(comparison=comparison, classification=classification),
                ),
            )
        with repository.engine.connect() as connection:
            for table in (
                "phase6_commits",
                "verified_edges",
                "verified_chains",
                "verified_classifications",
                "verification_observations",
            ):
                assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
    finally:
        repository.close()


def test_genuine_receipt_cannot_cross_wire_assessment_or_target(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "cross-wire.sqlite")
    try:
        result = _commit(repository)
        receipt = result.commit_receipts[0]
        foreign_receipt = receipt.model_copy(update={"assessment_id": "asm_foreign"})
        foreign_edge = result.edges[0].model_copy(update={"mcu_id": "mcu_comb_foreign"})
        foreign_classification = result.classifications[0].model_copy(
            update={"classification_id": "cls_foreign"}
        )
        variants = (
            replace(result, commit_receipts=(foreign_receipt,)),
            replace(result, edges=(foreign_edge,)),
            replace(result, classifications=(foreign_classification,)),
        )
        for variant in variants:
            with pytest.raises(ValueError, match="commit|authorit|differ"):
                diagnostic_legacy_projection_ignores_graph_authority(variant, repository)
    finally:
        repository.close()


def test_extra_foreign_assessed_classification_is_not_hidden_by_valid_receipt(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "extra-classification.sqlite")
    try:
        result = _commit(repository)
        foreign = result.classifications[0].model_copy(
            update={"classification_id": "cls_foreign", "verification_id": "ver_foreign"}
        )
        with pytest.raises(ValueError, match="commit|authorit|differ"):
            diagnostic_legacy_projection_ignores_graph_authority(
                replace(result, classifications=(*result.classifications, foreign)), repository
            )
    finally:
        repository.close()


def test_genuine_receipt_rejects_changed_semantic_identity_and_provenance(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "identity.sqlite")
    try:
        result = _commit(repository)
        edge = result.edges[0]
        classification = result.classifications[0]
        edge_variants = (
            edge.model_copy(update={"source_id": "src_foreign"}),
            edge.model_copy(update={"source_version_id": "srcv_foreign"}),
            edge.model_copy(update={"mapping_id": "map_foreign"}),
            edge.model_copy(update={"verification_id": "ver_foreign"}),
            edge.model_copy(
                update={"chronology": edge.chronology.model_copy(update={"state": "POST_CUTOFF"})}
            ),
            edge.model_copy(
                update={"provenance": edge.provenance.model_copy(update={"detail": "forged"})}
            ),
        )
        for altered in edge_variants:
            with pytest.raises(ValueError, match="commit|authorit|differ"):
                diagnostic_legacy_projection_ignores_graph_authority(
                    replace(result, edges=(altered,)), repository
                )
        for altered in (
            classification.model_copy(update={"mapping_id": "map_foreign"}),
            classification.model_copy(update={"relation": PrecedentState.COMPONENT_PRECEDENT_ONLY}),
            classification.model_copy(
                update={
                    "provenance": classification.provenance.model_copy(update={"detail": "forged"})
                }
            ),
        ):
            with pytest.raises(ValueError, match="commit|authorit|differ"):
                diagnostic_legacy_projection_ignores_graph_authority(
                    replace(result, classifications=(altered,)), repository
                )
    finally:
        repository.close()


def test_matching_semantic_rows_without_commit_manifest_do_not_authorize_projection(
    tmp_path,
) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "missing-manifest.sqlite")
    try:
        result = _commit(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_commits"))
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            diagnostic_legacy_projection_ignores_graph_authority(result, repository)
    finally:
        repository.close()


def test_v4_semantic_rows_need_replay_to_gain_a_v7_commit_manifest(tmp_path) -> None:
    database = tmp_path / "v4-to-v7.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = _commit(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_commits"))
            connection.execute(
                text("UPDATE schema_version SET version = 4 WHERE version = :current"),
                {"current": SCHEMA_VERSION},
            )
    finally:
        repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(database)
    try:
        assert schema_version(reopened.engine) == SCHEMA_VERSION == 7
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            diagnostic_legacy_projection_ignores_graph_authority(result, reopened)
        replay = _commit(reopened)
        assert reopened.resolve_phase6_commit(replay.commit_receipts[0]).comparisons
    finally:
        reopened.close()


def test_receipt_resolution_rechecks_persisted_content_authority(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "tampered-authority.sqlite")
    try:
        result = _commit(repository)
        version = result.chains[0].version
        assert version is not None
        version_node = repository.get_node(version.version_id)
        assert version_node is not None
        altered = version_node.model_copy(
            update={
                "attributes": {
                    **version_node.attributes,
                    "content_hash": text_hash("Another immutable version"),
                }
            }
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("UPDATE graph_nodes SET document_json = :document WHERE node_id = :identity"),
                {"document": canonical_json(altered), "identity": version.version_id},
            )
        with pytest.raises(ValueError, match="content|authority|provenance"):
            diagnostic_legacy_projection_ignores_graph_authority(result, repository)
    finally:
        repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_relation"),
    [
        ("PARTIALLY_SUPPORTED", PrecedentState.UNRESOLVED),
        ("CONTRADICTED", PrecedentState.CONTRADICTORY_EVIDENCE),
        ("NOT_SUPPORTED", PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED),
        ("INSUFFICIENT_CONTEXT", PrecedentState.UNRESOLVED),
    ],
)
async def test_repository_loaded_assessment_preserves_negative_semantic_states(
    tmp_path, state, expected_relation
) -> None:
    writer, database, evidence = await _phase5(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = await _run(
            writer,
            evidence,
            repository,
            tmp_path / f"{state}.jsonl",
            runner=_verifier_state_runner(state),
            control_only=True,
        )
        assert result.snapshot_id is not None
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        assert view.committed_comparisons
        assert {item.comparison.classification.relation for item in view.committed_comparisons} == {
            expected_relation
        }
    finally:
        repository.close()


@pytest.mark.parametrize(
    ("state", "expected_relation"),
    [
        (SupportVerificationState.SUPPORTED, PrecedentState.DIRECT_PRECEDENT),
        (
            SupportVerificationState.PARTIALLY_SUPPORTED,
            PrecedentState.COMPONENT_PRECEDENT_ONLY,
        ),
        (SupportVerificationState.CONTRADICTED, PrecedentState.CONTRADICTORY_EVIDENCE),
        (
            SupportVerificationState.NOT_SUPPORTED,
            PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
        ),
        (SupportVerificationState.INSUFFICIENT_CONTEXT, PrecedentState.UNRESOLVED),
    ],
)
def test_assessment_loader_preserves_all_basic_semantic_polarities(
    tmp_path, state, expected_relation
) -> None:
    case = {
        SupportVerificationState.SUPPORTED: "DIRECT_PRECEDENT",
        SupportVerificationState.PARTIALLY_SUPPORTED: "COMPONENT_PRECEDENT",
        SupportVerificationState.CONTRADICTED: "CONTRADICTS",
        SupportVerificationState.NOT_SUPPORTED: "NO_MATCH",
        SupportVerificationState.INSUFFICIENT_CONTEXT: "UNRESOLVED",
    }[state]
    repository, view, classification, graph_edges = _load_committed_matrix_case(tmp_path, case)
    try:
        loaded = repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
        assert loaded == view
        assert len(loaded.committed_comparisons) == 1
        assert classification.relation == expected_relation
        assert loaded.committed_comparisons[0].comparison.classification.relation == (
            expected_relation
        )
        assert {relation.edge.edge_id for relation in loaded.authorized_graph_relations} == {
            edge.edge_id for edge in graph_edges
        }
    finally:
        repository.close()


def test_assessment_loader_preserves_strong_partial_without_upgrading_to_direct(tmp_path) -> None:
    repository, view, classification, graph_edges = _load_committed_matrix_case(
        tmp_path, "STRONG_PARTIAL_PRECEDENT"
    )
    try:
        loaded = repository.load_phase6_assessment(view.assessment_id, snapshot_id=view.snapshot_id)
        assert loaded == view
        assert classification.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT
        assert loaded.committed_comparisons[0].comparison.classification.relation == (
            PrecedentState.STRONG_PARTIAL_PRECEDENT
        )
        assert {relation.edge.edge_id for relation in loaded.authorized_graph_relations} == {
            edge.edge_id for edge in graph_edges
        }
    finally:
        repository.close()
