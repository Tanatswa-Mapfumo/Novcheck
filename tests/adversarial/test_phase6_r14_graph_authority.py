"""R14: Phase 6 graph projections require a committed semantic authority chain."""

import pytest
from sqlalchemy import text

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.models import (
    PHASE6_EDGE_KINDS,
    EdgeVerificationRef,
    GraphEdge,
    GraphEdgeKind,
    GraphNodeKind,
)
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.sqlalchemy_models import GraphEdgeRow
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
from novelty_harness.evidence.verification.integrity import (
    VerifiedEvidenceChain,
    verified_comparison,
)
from novelty_harness.runtime.tracing.hashing import canonical_json
from tests.adversarial.test_phase6_r10_content_authority import (
    _authority_nodes,
    _chain_for_content,
)
from tests.unit.evidence.verification.test_eligibility import AS_OF, NOW, PASSAGE_TEXT, verification


def _replay_direct_graph(repository, chain, classification):
    comparison = verified_comparison(chain)
    graph_nodes, graph_edges = verified_edge_graph_fragment(
        (chain.edge,),
        (classification,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    receipt = repository.upsert(
        nodes=(*_authority_nodes(chain), *graph_nodes),
        edges=graph_edges,
        verified_edges=(chain.edge,),
        verified_chains=(chain,),
        classified_comparisons=(
            ClassifiedComparison(comparison=comparison, classification=classification),
        ),
    )
    assert receipt is not None
    representative = next(
        (edge for edge in graph_edges if edge.kind == GraphEdgeKind.DIRECT_PRECEDENT),
        graph_edges[0],
    )
    return receipt, representative


def _commit_direct_graph(repository: SqlAlchemyEvidenceGraphRepository):
    chain = _chain_for_content(PASSAGE_TEXT)
    classification = classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW)
    receipt, direct = _replay_direct_graph(repository, chain, classification)
    return chain, classification, receipt, direct


def test_r14_migrated_v4_direct_graph_row_is_not_authoritative(tmp_path) -> None:
    database = tmp_path / "legacy-direct.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        _, _, _, direct = _commit_direct_graph(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_graph_edge_memberships"))
            connection.execute(text("DELETE FROM phase6_graph_node_memberships"))
            connection.execute(text("DROP TABLE phase6_graph_edge_memberships"))
            connection.execute(text("DROP TABLE phase6_graph_node_memberships"))
            connection.execute(text("DELETE FROM phase6_commits"))
            connection.execute(text("UPDATE schema_version SET version = 4 WHERE version = 7"))
    finally:
        repository.close()

    migrated = SqlAlchemyEvidenceGraphRepository(database)
    try:
        assert migrated.get_edge(direct.edge_id) is None
        assert migrated.edges(kinds=frozenset({GraphEdgeKind.DIRECT_PRECEDENT})) == ()
    finally:
        migrated.close()


def test_r14_graph_only_write_cannot_project_uncommitted_legacy_semantics(tmp_path) -> None:
    database = tmp_path / "legacy-semantic.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    chain = _chain_for_content(PASSAGE_TEXT)
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    graph_nodes, graph_edges = verified_edge_graph_fragment(
        (chain.edge,),
        (classification,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    try:
        repository.upsert(
            nodes=_authority_nodes(chain),
            verified_edges=(chain.edge,),
            verified_chains=(chain,),
            classified_comparisons=(
                ClassifiedComparison(comparison=comparison, classification=classification),
            ),
        )
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_commits"))
            connection.execute(text("UPDATE schema_version SET version = 4 WHERE version = 7"))
    finally:
        repository.close()

    migrated = SqlAlchemyEvidenceGraphRepository(database)
    try:
        with pytest.raises(ValueError, match="commit|authorit|projection"):
            migrated.upsert(nodes=graph_nodes, edges=graph_edges)
        assert migrated.edges(kinds=frozenset({GraphEdgeKind.DIRECT_PRECEDENT})) == ()
    finally:
        migrated.close()


def test_r14_missing_manifest_invalidates_existing_graph_read(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "removed-manifest.sqlite")
    try:
        _, _, receipt, direct = _commit_direct_graph(repository)
        assert repository.resolve_phase6_commit(receipt)
        assert repository.get_edge(direct.edge_id) is not None
        with repository.engine.begin() as connection:
            connection.execute(text("UPDATE phase6_commits SET document_json = '{}'"))
        with pytest.raises(ValueError, match="commit|persist"):
            repository.resolve_phase6_commit(receipt)
        assert repository.get_edge(direct.edge_id) is None
        assert repository.edges(kinds=frozenset({GraphEdgeKind.DIRECT_PRECEDENT})) == ()
    finally:
        repository.close()


def test_r14_orphan_proposition_node_cannot_advertise_semantics(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "orphan-proposition.sqlite")
    try:
        chain, _, _, _ = _commit_direct_graph(repository)
        proposition_nodes = repository.nodes(kinds=frozenset({GraphNodeKind.EVIDENCE_PROPOSITION}))
        assert len(proposition_nodes) == 1
        proposition_id = proposition_nodes[0].node_id
        assert proposition_nodes[0].attributes["verified_edge_id"] == chain.edge.edge_id
        with repository.engine.begin() as connection:
            connection.execute(text("UPDATE phase6_commits SET document_json = '{}'"))
        assert repository.get_node(proposition_id) is None
        assert repository.nodes(kinds=frozenset({GraphNodeKind.EVIDENCE_PROPOSITION})) == ()
    finally:
        repository.close()


def test_r14_missing_graph_membership_invalidates_authoritative_read(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "missing-membership.sqlite")
    try:
        _, _, receipt, direct = _commit_direct_graph(repository)
        assert repository.resolve_phase6_commit(receipt)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_graph_edge_memberships"))
        assert repository.get_edge(direct.edge_id) is None
    finally:
        repository.close()


def test_r14_caller_copy_cannot_create_an_independent_graph_fact(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "caller-copy.sqlite")
    try:
        _, _, receipt, direct = _commit_direct_graph(repository)
        copied = GraphEdge.model_validate(direct.model_dump(mode="json"))
        with pytest.raises(ValueError, match="semantic commit"):
            repository.upsert(edges=(copied,))
        assert repository.resolve_phase6_commit(receipt)
        assert repository.get_edge(direct.edge_id) == direct
    finally:
        repository.close()


def test_r14_generic_direct_insert_without_semantic_commit_fails(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "no-semantic-commit.sqlite")
    try:
        chain = _chain_for_content(PASSAGE_TEXT)
        classification = classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW)
        _, graph_edges = verified_edge_graph_fragment(
            (chain.edge,),
            (classification,),
            observed_at=NOW,
            provenance=phase6_graph_provenance(),
        )
        direct = next(edge for edge in graph_edges if edge.kind == GraphEdgeKind.DIRECT_PRECEDENT)
        repository.upsert(nodes=_authority_nodes(chain))
        with pytest.raises(ValueError, match="unknown verified edge|semantic commit"):
            repository.upsert(edges=(direct,))
        assert repository.get_edge(direct.edge_id) is None
    finally:
        repository.close()


def test_r14_manually_inserted_direct_row_without_any_commit_is_hidden(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "manual-orphan.sqlite")
    try:
        chain = _chain_for_content(PASSAGE_TEXT)
        classification = classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW)
        _, graph_edges = verified_edge_graph_fragment(
            (chain.edge,),
            (classification,),
            observed_at=NOW,
            provenance=phase6_graph_provenance(),
        )
        direct = next(edge for edge in graph_edges if edge.kind == GraphEdgeKind.DIRECT_PRECEDENT)
        repository.upsert(nodes=_authority_nodes(chain))
        with repository.engine.begin() as connection:
            connection.execute(
                GraphEdgeRow.__table__.insert().values(
                    edge_id=direct.edge_id,
                    kind=direct.kind.value,
                    source_node_id=direct.source_node_id,
                    target_node_id=direct.target_node_id,
                    document_json=canonical_json(direct),
                )
            )
            assert connection.execute(text("SELECT count(*) FROM phase6_commits")).scalar_one() == 0
        assert repository.get_edge(direct.edge_id) is None
        assert repository.edges(kinds=frozenset({GraphEdgeKind.DIRECT_PRECEDENT})) == ()
    finally:
        repository.close()


def test_r14_graph_edge_cannot_borrow_another_commit_membership(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "cross-manifest.sqlite")
    try:
        chain_a, _, receipt_a, direct_a = _commit_direct_graph(repository)
        edge_b = build_verified_evidence_edge(
            mapping=chain_a.mapping,
            verification=chain_a.verification,
            proposition=chain_a.proposition,
            source=chain_a.source,
            bundle=chain_a.bundle,
            version=chain_a.version,
            as_of=AS_OF,
            observed_at=NOW,
            assessment_id="asm_r14_other",
            relation=PrecedentState.DIRECT_PRECEDENT,
        )
        chain_b = VerifiedEvidenceChain.model_validate(
            chain_a.model_copy(
                update={"assessment_id": "asm_r14_other", "edge": edge_b}
            ).model_dump(mode="json")
        )
        classification_b = classify_verified_comparison(
            verified_comparison(chain_b), clock=lambda: NOW
        )
        receipt_b, _ = _replay_direct_graph(repository, chain_b, classification_b)
        assert receipt_a.commit_id != receipt_b.commit_id
        with repository.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE phase6_graph_edge_memberships SET commit_id = :foreign "
                    "WHERE edge_id = :edge"
                ),
                {"foreign": receipt_b.commit_id, "edge": direct_a.edge_id},
            )
        assert repository.get_edge(direct_a.edge_id) is None
    finally:
        repository.close()


def test_r14_corrupted_graph_citation_is_hidden_despite_valid_manifest(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "corrupt-citation.sqlite")
    try:
        _, _, receipt, direct = _commit_direct_graph(repository)
        assert repository.resolve_phase6_commit(receipt)
        changed = direct.model_copy(
            update={"attributes": {**direct.attributes, "passage_ids": ["pass_nonexistent"]}}
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("UPDATE graph_edges SET document_json = :document WHERE edge_id = :edge"),
                {"document": canonical_json(changed), "edge": direct.edge_id},
            )
        assert repository.get_edge(direct.edge_id) is None
    finally:
        repository.close()


def test_r14_exact_semantic_replay_restores_legacy_graph_authority(tmp_path) -> None:
    database = tmp_path / "validated-replay.sqlite"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        chain, classification, receipt, direct = _commit_direct_graph(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_graph_edge_memberships"))
            connection.execute(text("DELETE FROM phase6_graph_node_memberships"))
            connection.execute(text("DROP TABLE phase6_graph_edge_memberships"))
            connection.execute(text("DROP TABLE phase6_graph_node_memberships"))
            connection.execute(text("DELETE FROM phase6_commits"))
            connection.execute(text("UPDATE schema_version SET version = 5 WHERE version = 7"))
    finally:
        repository.close()
    migrated = SqlAlchemyEvidenceGraphRepository(database)
    try:
        assert migrated.get_edge(direct.edge_id) is None
        replay_receipt, replay_direct = _replay_direct_graph(migrated, chain, classification)
        assert replay_receipt == receipt
        assert migrated.resolve_phase6_commit(replay_receipt)
        assert migrated.get_edge(replay_direct.edge_id) == replay_direct
        exact_receipt, _ = _replay_direct_graph(migrated, chain, classification)
        assert exact_receipt == replay_receipt
        with migrated.engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM phase6_commits")).scalar_one() == 1
            assert (
                connection.execute(
                    text("SELECT count(*) FROM phase6_graph_edge_memberships")
                ).scalar_one()
                == 2
            )
    finally:
        migrated.close()


@pytest.mark.parametrize(
    ("state", "expected_kind"),
    [
        (SupportVerificationState.SUPPORTED, GraphEdgeKind.DIRECT_PRECEDENT),
        (SupportVerificationState.PARTIALLY_SUPPORTED, GraphEdgeKind.COMPONENT_PRECEDENT),
        (SupportVerificationState.CONTRADICTED, GraphEdgeKind.CONTRADICTS),
        (SupportVerificationState.NOT_SUPPORTED, GraphEdgeKind.NO_MATCH),
    ],
)
def test_r14_committed_semantic_relation_family_remains_readable(
    tmp_path, state, expected_kind
) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"committed-{state.value}.sqlite")
    try:
        baseline = _chain_for_content(PASSAGE_TEXT)
        judged = verification(state)
        edge = build_verified_evidence_edge(
            mapping=baseline.mapping,
            verification=judged,
            proposition=baseline.proposition,
            source=baseline.source,
            bundle=baseline.bundle,
            version=baseline.version,
            as_of=AS_OF,
            observed_at=NOW,
            assessment_id=baseline.assessment_id,
            relation={
                SupportVerificationState.SUPPORTED: PrecedentState.DIRECT_PRECEDENT,
                SupportVerificationState.PARTIALLY_SUPPORTED: (
                    PrecedentState.COMPONENT_PRECEDENT_ONLY
                ),
                SupportVerificationState.CONTRADICTED: PrecedentState.CONTRADICTORY_EVIDENCE,
                SupportVerificationState.NOT_SUPPORTED: (
                    PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED
                ),
            }[state],
        )
        chain = VerifiedEvidenceChain.model_validate(
            baseline.model_copy(update={"verification": judged, "edge": edge}).model_dump(
                mode="json"
            )
        )
        classification = classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW)
        receipt, _ = _replay_direct_graph(repository, chain, classification)
        assert repository.resolve_phase6_commit(receipt)
        projected = repository.edges(kinds=frozenset({expected_kind}))
        assert projected
        with pytest.raises(ValueError, match="semantic commit"):
            repository.upsert(edges=projected)
    finally:
        repository.close()


def test_r14_ordinary_phase5_graph_relation_still_round_trips(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "ordinary-graph.sqlite")
    try:
        chain = _chain_for_content(PASSAGE_TEXT)
        ordinary = GraphEdge(
            edge_id="gedge_r14_cites",
            kind=GraphEdgeKind.CITES,
            source_node_id=chain.source.source_id,
            target_node_id=chain.bundle.passages[0].passage_id,
            observed_at=NOW,
            provenance=phase6_graph_provenance(),
        )
        assert repository.upsert(nodes=_authority_nodes(chain), edges=(ordinary,)) is None
        assert repository.get_edge(ordinary.edge_id) == ordinary
        assert ordinary in repository.edges(kinds=frozenset({GraphEdgeKind.CITES}))
    finally:
        repository.close()


@pytest.mark.parametrize("kind", sorted(PHASE6_EDGE_KINDS, key=lambda item: item.value))
def test_r14_manual_orphan_relation_family_is_not_authoritative(tmp_path, kind) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"orphan-{kind.value}.sqlite")
    try:
        chain, _, _, direct = _commit_direct_graph(repository)
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM phase6_graph_edge_memberships"))
        reference = EdgeVerificationRef(
            verified_edge_id=chain.edge.edge_id,
            support_state=(
                SupportVerificationState.CONTRADICTED
                if kind == GraphEdgeKind.CONTRADICTS
                else SupportVerificationState.SUPPORTED
            ),
            decisive=kind == GraphEdgeKind.DIRECT_PRECEDENT,
            precedent_relation=(
                PrecedentState.DIRECT_PRECEDENT if kind == GraphEdgeKind.DIRECT_PRECEDENT else None
            ),
        )
        orphan = GraphEdge.model_validate(
            {
                **direct.model_dump(mode="json"),
                "edge_id": f"gedge_orphan_{kind.value.lower()}",
                "kind": kind.value,
                "verification": reference.model_dump(mode="json"),
            }
        )
        with repository.engine.begin() as connection:
            connection.execute(
                GraphEdgeRow.__table__.insert().values(
                    edge_id=orphan.edge_id,
                    kind=orphan.kind.value,
                    source_node_id=orphan.source_node_id,
                    target_node_id=orphan.target_node_id,
                    document_json=canonical_json(orphan),
                )
            )
        assert repository.get_edge(orphan.edge_id) is None
        assert all(edge.edge_id != orphan.edge_id for edge in repository.edges())
    finally:
        repository.close()
