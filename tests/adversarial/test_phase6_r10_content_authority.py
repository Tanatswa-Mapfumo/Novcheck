"""R10: persisted source/version content is the authority for Phase 6 passages."""

import pytest
from sqlalchemy import text

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.models import GraphEdgeKind, GraphNode, GraphNodeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.retrieval_mapping import (
    passage_graph_node,
    source_graph_node,
    version_graph_node,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.passages.extraction import (
    extract_paragraph_window,
    extract_resolved_content,
    resolve_version_content,
)
from novelty_harness.evidence.passages.hashing import text_hash
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
from tests.adversarial.test_phase6_sol_review_regressions import _valid_chain
from tests.fixtures.phase5 import phase5_provenance
from tests.unit.evidence.verification.test_eligibility import (
    AS_OF,
    NOW,
    PASSAGE_TEXT,
    build,
)


def _chain_for_content(
    content: str,
    *,
    paragraph: int | None = None,
    versioned: bool = True,
) -> VerifiedEvidenceChain:
    baseline = _valid_chain(build(SupportVerificationState.SUPPORTED))
    source = baseline.source.model_copy(update={"content_hash": text_hash(content)})
    version = (
        baseline.version.model_copy(update={"content_hash": text_hash(content)})
        if versioned and baseline.version is not None
        else None
    )
    mapping = baseline.mapping.model_copy(
        update={"source_version_id": version.version_id if version is not None else None}
    )
    verification = baseline.verification.model_copy(
        update={"source_version_id": version.version_id if version is not None else None}
    )
    claim = baseline.bundle.claim.model_copy(
        update={"source_version_id": version.version_id if version is not None else None}
    )
    resolved = resolve_version_content(source=source, version=version, text=content)
    passage = (
        extract_resolved_content(resolved, observed_at=NOW, provenance=phase5_provenance())
        if paragraph is None
        else extract_paragraph_window(
            resolved,
            start_paragraph=paragraph,
            end_paragraph=paragraph,
            observed_at=NOW,
            provenance=phase5_provenance(),
        )
    ).model_copy(update={"passage_id": baseline.bundle.passages[0].passage_id})
    bundle = baseline.bundle.model_copy(update={"claim": claim, "passages": (passage,)})
    edge = build_verified_evidence_edge(
        mapping=mapping,
        verification=verification,
        proposition=baseline.proposition,
        source=source,
        bundle=bundle,
        version=version,
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id=baseline.assessment_id,
        relation=PrecedentState.DIRECT_PRECEDENT,
    )
    return VerifiedEvidenceChain(
        assessment_id=baseline.assessment_id,
        source=source,
        version=version,
        proposition=baseline.proposition,
        mapping=mapping,
        bundle=bundle,
        verification=verification,
        edge=edge,
    )


def _authority_nodes(chain: VerifiedEvidenceChain) -> tuple[GraphNode, ...]:
    provenance = phase6_graph_provenance()
    nodes = [
        source_graph_node(chain.source, observed_at=NOW, provenance=provenance),
        passage_graph_node(chain.bundle.passages[0], observed_at=NOW, provenance=provenance),
        GraphNode(
            node_id=chain.proposition.mcu_id,
            kind=GraphNodeKind.MCU,
            label="MCU",
            observed_at=NOW,
            provenance=provenance,
        ),
    ]
    if chain.version is not None:
        nodes.insert(1, version_graph_node(chain.version, observed_at=NOW, provenance=provenance))
    return tuple(nodes)


def _persist(
    repository: SqlAlchemyEvidenceGraphRepository,
    chain: VerifiedEvidenceChain,
    *,
    nodes: tuple[GraphNode, ...] = (),
) -> None:
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    graph_nodes, graph_edges = verified_edge_graph_fragment(
        (chain.edge,),
        (classification,),
        observed_at=NOW,
        provenance=phase6_graph_provenance(),
    )
    repository.upsert(
        nodes=(*nodes, *graph_nodes),
        edges=graph_edges,
        verified_edges=(chain.edge,),
        verified_chains=(chain,),
        classified_comparisons=(
            ClassifiedComparison(comparison=comparison, classification=classification),
        ),
    )


def _assert_no_semantic_artifacts(
    repository: SqlAlchemyEvidenceGraphRepository, edge_id: str
) -> None:
    assert not any(edge.kind == GraphEdgeKind.DIRECT_PRECEDENT for edge in repository.edges())
    assert repository.observations(edge_id) == ()
    with repository.engine.connect() as connection:
        for table in ("verified_edges", "verified_chains", "verified_classifications"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_r10_existing_version_content_conflict_rolls_back(tmp_path) -> None:

    original = _chain_for_content(PASSAGE_TEXT)
    foreign = _chain_for_content(
        PASSAGE_TEXT + "\n\nThe operator must switch the load.", paragraph=0
    )
    assert original.version is not None and foreign.version is not None
    assert original.version.version_id == foreign.version.version_id
    assert original.version.content_hash != foreign.version.content_hash
    foreign = foreign.model_copy(update={"source": original.source})
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-existing.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(original))
        with pytest.raises(ValueError, match="content|digest|authority|provenance"):
            _persist(repository, foreign)
        _assert_no_semantic_artifacts(repository, foreign.edge.edge_id)
    finally:
        repository.close()


def test_r10_copied_chain_authority_cannot_replace_stored_version(tmp_path) -> None:
    original = _chain_for_content(PASSAGE_TEXT)
    alternate = _chain_for_content(PASSAGE_TEXT + "\n\nA contrary second paragraph.", paragraph=0)
    assert original.version is not None and alternate.version is not None
    copied = original.model_copy(
        update={
            "source": alternate.source,
            "version": alternate.version,
            "bundle": alternate.bundle,
            "edge": alternate.edge,
        }
    )
    assert copied.bundle.passages[0].attestation is not None
    assert (
        copied.bundle.passages[0].attestation.parent_content_digest == copied.version.content_hash
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-copy.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(original))
        with pytest.raises(ValueError, match="content|digest|authority|provenance"):
            _persist(repository, copied)
        _assert_no_semantic_artifacts(repository, copied.edge.edge_id)
    finally:
        repository.close()


def test_r10_conflicting_version_node_in_same_batch_rolls_back(tmp_path) -> None:
    original = _chain_for_content(PASSAGE_TEXT)
    alternate = _chain_for_content(PASSAGE_TEXT + "\n\nA contrary second paragraph.", paragraph=0)
    assert original.version is not None and alternate.version is not None
    provenance = phase6_graph_provenance()
    nodes = tuple(
        version_graph_node(original.version, observed_at=NOW, provenance=provenance)
        if node.kind == GraphNodeKind.SOURCE_VERSION
        else node
        for node in _authority_nodes(alternate)
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-batch.sqlite")
    try:
        with pytest.raises(ValueError, match="content|digest|authority|provenance"):
            _persist(repository, alternate, nodes=nodes)
        _assert_no_semantic_artifacts(repository, alternate.edge.edge_id)
        assert repository.get_node(alternate.source.source_id) is None
        assert repository.get_node(alternate.version.version_id) is None
    finally:
        repository.close()


def test_r10_unversioned_source_content_conflict_rolls_back(tmp_path) -> None:
    original = _chain_for_content(PASSAGE_TEXT, versioned=False)
    alternate = _chain_for_content(
        PASSAGE_TEXT + "\n\nA contrary second paragraph.", paragraph=0, versioned=False
    )
    assert original.version is None and alternate.version is None
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-unversioned.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(original))
        with pytest.raises(ValueError, match="content|digest|authority|provenance"):
            _persist(repository, alternate)
        _assert_no_semantic_artifacts(repository, alternate.edge.edge_id)
    finally:
        repository.close()


def test_r10_matching_stored_content_persists_direct_comparison(tmp_path) -> None:
    chain = _chain_for_content(PASSAGE_TEXT + "\n\nFurther context.", paragraph=0)
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-match.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(chain))
        _persist(repository, chain)
        assert any(edge.kind == GraphEdgeKind.DIRECT_PRECEDENT for edge in repository.edges())
        assert repository.observations(chain.edge.edge_id) == (NOW,)
        with repository.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM verified_classifications")
                ).scalar_one()
                == 1
            )
    finally:
        repository.close()


def test_r10_matching_new_version_can_establish_authority_in_one_batch(tmp_path) -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-new-version.sqlite")
    try:
        _persist(repository, chain, nodes=_authority_nodes(chain))
        assert any(edge.kind == GraphEdgeKind.DIRECT_PRECEDENT for edge in repository.edges())
        assert repository.observations(chain.edge.edge_id) == (NOW,)
    finally:
        repository.close()


def test_r10_matching_unversioned_source_persists(tmp_path) -> None:
    chain = _chain_for_content(PASSAGE_TEXT, versioned=False)
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-unversioned-match.sqlite")
    try:
        _persist(repository, chain, nodes=_authority_nodes(chain))
        assert any(edge.kind == GraphEdgeKind.DIRECT_PRECEDENT for edge in repository.edges())
    finally:
        repository.close()


def test_r10_genuine_subspan_with_matching_parent_persists(tmp_path) -> None:
    content = "Background only.\n\n" + PASSAGE_TEXT + "\n\nFurther context."
    chain = _chain_for_content(content, paragraph=1)
    proof = chain.bundle.passages[0].attestation
    assert proof is not None
    assert proof.start_offset > 0 and proof.end_offset < len(content)
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-subspan.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(chain))
        _persist(repository, chain)
        assert any(edge.kind == GraphEdgeKind.DIRECT_PRECEDENT for edge in repository.edges())
    finally:
        repository.close()


def test_r10_complete_document_digest_matches_stored_version(tmp_path) -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    proof = chain.bundle.passages[0].attestation
    assert proof is not None and chain.version is not None
    assert proof.passage_digest == proof.parent_content_digest == chain.version.content_hash
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-document.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(chain))
        _persist(repository, chain)
        assert any(edge.kind == GraphEdgeKind.DIRECT_PRECEDENT for edge in repository.edges())
    finally:
        repository.close()


def test_r10_duplicate_same_batch_version_authorities_conflict(tmp_path) -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    assert chain.version is not None
    original_nodes = _authority_nodes(chain)
    foreign_version = chain.version.model_copy(update={"content_hash": text_hash("Different")})
    conflicting_node = version_graph_node(
        foreign_version, observed_at=NOW, provenance=phase6_graph_provenance()
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "r10-duplicate.sqlite")
    try:
        with pytest.raises(ValueError, match="content|authority"):
            _persist(repository, chain, nodes=(*original_nodes, conflicting_node))
        _assert_no_semantic_artifacts(repository, chain.edge.edge_id)
    finally:
        repository.close()


@pytest.mark.parametrize(
    "field,value", [("source_id", "src_foreign"), ("access_state", "ABSTRACT_ONLY")]
)
def test_r10_stored_version_owner_and_access_are_authoritative(tmp_path, field, value) -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    nodes = tuple(
        node.model_copy(update={"attributes": {**node.attributes, field: value}})
        if node.kind == GraphNodeKind.SOURCE_VERSION
        else node
        for node in _authority_nodes(chain)
    )
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"r10-{field}.sqlite")
    try:
        repository.upsert(nodes=nodes)
        with pytest.raises(ValueError, match="content|authority|owner|version"):
            _persist(repository, chain)
        _assert_no_semantic_artifacts(repository, chain.edge.edge_id)
    finally:
        repository.close()


@pytest.mark.parametrize("semantic_input", ["verified", "classification", "graph"])
def test_r10_replayed_semantic_input_rechecks_stored_content(tmp_path, semantic_input) -> None:
    chain = _chain_for_content(PASSAGE_TEXT)
    assert chain.version is not None
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / f"r10-replay-{semantic_input}.sqlite")
    try:
        repository.upsert(nodes=_authority_nodes(chain))
        _persist(repository, chain)
        direct = next(
            edge for edge in repository.edges() if edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
        )
        stored_version = repository.get_node(chain.version.version_id)
        assert stored_version is not None
        changed_version = stored_version.model_copy(
            update={
                "attributes": {
                    **stored_version.attributes,
                    "content_hash": text_hash("Different version content"),
                }
            }
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("UPDATE graph_nodes SET document_json = :document WHERE node_id = :identity"),
                {"document": canonical_json(changed_version), "identity": chain.version.version_id},
            )
        comparison = verified_comparison(chain)
        classification = classify_verified_comparison(comparison, clock=lambda: NOW)
        assert repository.get_edge(direct.edge_id) is None
        with pytest.raises(ValueError, match="content|authority|provenance"):
            if semantic_input == "verified":
                repository.upsert(verified_edges=(chain.edge,))
            elif semantic_input == "classification":
                repository.upsert(
                    classified_comparisons=(
                        ClassifiedComparison(comparison=comparison, classification=classification),
                    )
                )
            else:
                repository.upsert(
                    edges=(direct,),
                    classified_comparisons=(
                        ClassifiedComparison(comparison=comparison, classification=classification),
                    ),
                )
    finally:
        repository.close()
