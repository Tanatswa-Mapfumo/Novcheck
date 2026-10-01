"""R13: a receipt is a reference to persisted authority, not authority itself."""

import json
from dataclasses import replace

import pytest
from sqlalchemy import text

from novelty_harness.application.evidence_phase6 import project_verified_edges
from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION, schema_version
from novelty_harness.evidence.graph.repository import Phase6CommitReceipt
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.mapping.models import ComparisonDimension, PropositionCommitment
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.phase6_pipeline import Phase6EvidenceResult
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.precedent.models import PrecedentClassification
from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
from novelty_harness.evidence.verification.integrity import (
    VerifiedEvidenceChain,
    verified_comparison,
)
from novelty_harness.evidence.verification.models import CommitmentStateRecord, SupportVerification
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
from tests.adversarial.test_phase6_sol_review_regressions import _valid_chain
from tests.unit.evidence.verification.test_eligibility import (
    AS_OF,
    NOW,
    PASSAGE_TEXT,
    build,
    verification,
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
        project_verified_edges(result)


def test_fabricated_matching_receipt_with_empty_repository_cannot_project(tmp_path) -> None:
    result = _unpersisted_result()
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "empty.sqlite")
    try:
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            project_verified_edges(result, repository)
    finally:
        repository.close()


def test_exact_persisted_commit_projects_direct_and_replays(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "committed.sqlite")
    try:
        result = _commit(repository)
        assert (
            project_verified_edges(result, repository)[0].relation_type.value == "DIRECT_PRECEDENT"
        )
        replay = _commit(repository)
        assert replay.commit_receipts == result.commit_receipts
        assert project_verified_edges(replay, repository) == project_verified_edges(
            result, repository
        )
    finally:
        repository.close()


def test_genuine_receipt_does_not_authorize_another_repository(tmp_path) -> None:
    first = SqlAlchemyEvidenceGraphRepository(tmp_path / "first.sqlite")
    second = SqlAlchemyEvidenceGraphRepository(tmp_path / "second.sqlite")
    try:
        result = _commit(first)
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            project_verified_edges(result, second)
    finally:
        first.close()
        second.close()


def test_mutated_caller_edge_does_not_project_under_genuine_receipt(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "mutated-edge.sqlite")
    try:
        result = _commit(repository)
        changed = result.edges[0].model_copy(update={"passage_ids": ("pass_foreign",)})
        with pytest.raises(ValueError, match="commit|authorit|differ"):
            project_verified_edges(replace(result, edges=(changed,)), repository)
    finally:
        repository.close()


def test_mutated_caller_classification_does_not_project_under_genuine_receipt(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "mutated-classification.sqlite")
    try:
        result = _commit(repository)
        changed = result.classifications[0].model_copy(update={"basis": ("invented basis",)})
        with pytest.raises(ValueError, match="commit|authorit|differ"):
            project_verified_edges(replace(result, classifications=(changed,)), repository)
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
                project_verified_edges(replace(result, commit_receipts=(receipt,)), repository)
    finally:
        repository.close()


def test_serialized_genuine_receipt_still_resolves_after_reopen(tmp_path) -> None:
    database = tmp_path / "receipt-roundtrip.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = _commit(repository)
        serialized = result.commit_receipts[0].model_dump_json()
    finally:
        repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(database)
    try:
        restored = Phase6CommitReceipt.model_validate_json(serialized)
        assert (
            project_verified_edges(replace(result, commit_receipts=(restored,)), reopened)[
                0
            ].relation_type.value
            == "DIRECT_PRECEDENT"
        )
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
            project_verified_edges(rejected, repository)
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
                project_verified_edges(variant, repository)
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
            project_verified_edges(
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
                project_verified_edges(replace(result, edges=(altered,)), repository)
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
                project_verified_edges(replace(result, classifications=(altered,)), repository)
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
            project_verified_edges(result, repository)
    finally:
        repository.close()


def test_v4_semantic_rows_need_replay_to_gain_a_v5_commit_manifest(tmp_path) -> None:
    database = tmp_path / "v4-to-v5.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = _commit(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_commits"))
            connection.execute(text("UPDATE schema_version SET version = 4 WHERE version = 6"))
    finally:
        repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(database)
    try:
        assert schema_version(reopened.engine) == SCHEMA_VERSION == 6
        with pytest.raises(ValueError, match="commit|authorit|persist"):
            project_verified_edges(result, reopened)
        replay = _commit(reopened)
        assert project_verified_edges(replay, reopened)
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
            project_verified_edges(result, repository)
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
async def test_repository_backed_projection_preserves_negative_semantic_states(
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
        projected = project_verified_edges(result, repository)
        assert projected
        assert {edge.relation_type for edge in projected} == {expected_relation}
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
def test_commit_manifest_projects_all_basic_semantic_polarities(
    tmp_path, state, expected_relation
) -> None:
    baseline = _valid_chain(build(SupportVerificationState.SUPPORTED))
    chain = VerifiedEvidenceChain.model_validate(
        baseline.model_copy(
            update={"verification": verification(state), "edge": build(state)}
        ).model_dump(mode="json")
    )
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    assert classification.relation == expected_relation
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"{state.value}.sqlite")
    try:
        receipt = repository.upsert(
            nodes=_authority_nodes(chain),
            verified_edges=(chain.edge,),
            verified_chains=(chain,),
            classified_comparisons=(
                ClassifiedComparison(comparison=comparison, classification=classification),
            ),
        )
        assert receipt is not None
        projected = project_verified_edges(_result(chain, classification, receipt), repository)
        assert len(projected) == 1
        assert projected[0].relation_type == expected_relation
    finally:
        repository.close()


def test_commit_manifest_projects_strong_partial_without_upgrading_to_direct(tmp_path) -> None:
    baseline = _valid_chain(build(SupportVerificationState.SUPPORTED))
    extra = PropositionCommitment(
        commitment_id="feature_extra",
        dimension=ComparisonDimension.FEATURES,
        text="the load is remotely logged",
    )
    commitments = (*baseline.proposition.commitments, extra)
    proposition = baseline.proposition.model_copy(update={"commitments": commitments})
    claim = baseline.bundle.claim.model_copy(update={"commitments": commitments})
    bundle = baseline.bundle.model_copy(update={"claim": claim})
    verification_record = baseline.verification.model_copy(
        update={
            "state": SupportVerificationState.PARTIALLY_SUPPORTED,
            "commitment_states": (
                *baseline.verification.commitment_states,
                CommitmentStateRecord(
                    commitment_id=extra.commitment_id,
                    dimension=extra.dimension,
                    state="NOT_SUPPORTED",
                    rationale="No passage supports remote logging",
                ),
            ),
            "material_commitment_ids": tuple(item.commitment_id for item in commitments),
            "unsupported_portions": (extra.text,),
        }
    )
    verified = SupportVerification.model_validate(verification_record.model_dump(mode="json"))
    edge = build_verified_evidence_edge(
        mapping=baseline.mapping,
        verification=verified,
        proposition=proposition,
        source=baseline.source,
        bundle=bundle,
        version=baseline.version,
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id=baseline.assessment_id,
    )
    chain = VerifiedEvidenceChain.model_validate(
        baseline.model_copy(
            update={
                "proposition": proposition,
                "bundle": bundle,
                "verification": verified,
                "edge": edge,
            }
        ).model_dump(mode="json")
    )
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    assert classification.relation == PrecedentState.STRONG_PARTIAL_PRECEDENT
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "strong-partial.sqlite")
    try:
        receipt = repository.upsert(
            nodes=_authority_nodes(chain),
            verified_edges=(edge,),
            verified_chains=(chain,),
            classified_comparisons=(
                ClassifiedComparison(comparison=comparison, classification=classification),
            ),
        )
        assert receipt is not None
        projected = project_verified_edges(_result(chain, classification, receipt), repository)
        assert projected[0].relation_type == PrecedentState.STRONG_PARTIAL_PRECEDENT
    finally:
        repository.close()
