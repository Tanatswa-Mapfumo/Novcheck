"""Fresh attacks on Phase 6's authoritative semantic contracts."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import text as sql_text

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.domain.evidence import SourceDates
from novelty_harness.evidence.context.expansion import inspect_passage_context
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
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
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.passages.extraction import (
    extract_abstract,
    extract_resolved_content,
    extract_span,
    resolve_version_content,
)
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import PassageLocator, PassageLocatorKind
from novelty_harness.evidence.precedent.gates import (
    ClassificationFacts,
    ClassifiedComparison,
    classify_precedent,
    classify_verified_comparison,
)
from novelty_harness.evidence.verification.gates import (
    build_verified_evidence_edge,
)
from novelty_harness.evidence.verification.integrity import (
    VerifiedEvidenceChain,
    verified_comparison,
)
from novelty_harness.evidence.verification.models import SupportVerification, VerifiedEvidenceEdge
from novelty_harness.evidence.verification.verifier import verify_with_context_retry
from tests.adversarial.test_phase6_sol_review_regressions import (
    _persist_phase6_fragment,
    _valid_chain,
)
from tests.fixtures.phase5 import make_passage, make_version, phase5_provenance
from tests.unit.evidence.verification.test_context_retry import (
    CLAIM_TEXT,
    judgments,
    retry_verifier,
)
from tests.unit.evidence.verification.test_eligibility import (
    AS_OF,
    NOW,
    build,
    bundle,
    mapping,
    proposition,
    source,
    verification,
)
from tests.unit.evidence.verification.test_verifier import bundle as verifier_bundle


def _edge(
    *,
    source_dates: SourceDates,
    version_date: date | None,
    as_of: date = AS_OF,
    assessment_id: str = "asm_contract",
):
    record = source(dates=source_dates)
    version = make_version("src_1", version_id="srcv_1_v1", published_date=version_date)
    return build_verified_evidence_edge(
        mapping=mapping(),
        verification=verification(SupportVerificationState.SUPPORTED),
        proposition=proposition(),
        source=record,
        bundle=bundle(),
        version=version,
        as_of=as_of,
        observed_at=NOW,
        assessment_id=assessment_id,
    )


def test_f02_conflicting_first_public_date_cannot_be_decisive() -> None:
    edge = _edge(
        source_dates=SourceDates(first_public_version=date(2027, 1, 1)),
        version_date=date(2020, 1, 1),
    )
    assert edge.chronology.state == "UNCERTAIN"
    assert not edge.decisive


def test_f02_later_sibling_does_not_disqualify_cited_earlier_preprint() -> None:
    edge = _edge(
        source_dates=SourceDates(publication_date=date(2027, 1, 1)),
        version_date=date(2020, 1, 1),
    )
    assert edge.chronology.state == "PREDATES_CUTOFF"
    assert edge.decisive


def test_f02_old_parent_cannot_make_future_revision_eligible() -> None:
    edge = _edge(
        source_dates=SourceDates(publication_date=date(2020, 1, 1)),
        version_date=date(2027, 1, 1),
    )
    assert edge.chronology.state == "POST_CUTOFF"
    assert not edge.decisive


def test_f02_missing_foreign_and_unknown_cited_version() -> None:
    from novelty_harness.evidence.verification.gates import EdgeEligibilityError

    with pytest.raises(EdgeEligibilityError, match="version"):
        build_verified_evidence_edge(
            mapping=mapping(),
            verification=verification(SupportVerificationState.SUPPORTED),
            proposition=proposition(),
            source=source(),
            bundle=bundle(),
            version=None,
            as_of=AS_OF,
            observed_at=NOW,
            assessment_id="asm_contract",
        )
    with pytest.raises(EdgeEligibilityError, match="owner"):
        build_verified_evidence_edge(
            mapping=mapping(),
            verification=verification(SupportVerificationState.SUPPORTED),
            proposition=proposition(),
            source=source(),
            bundle=bundle(),
            version=make_version(
                "src_other", version_id="srcv_1_v1", published_date=date(2020, 1, 1)
            ),
            as_of=AS_OF,
            observed_at=NOW,
            assessment_id="asm_contract",
        )
    unknown = _edge(source_dates=SourceDates(), version_date=None)
    assert unknown.chronology.state == "UNCERTAIN" and not unknown.decisive


def test_f02_decisive_post_cutoff_is_invalid() -> None:
    future = _edge(source_dates=SourceDates(), version_date=date(2027, 1, 1))
    with pytest.raises(ValidationError, match="decisive|chronology"):
        type(future).model_validate({**future.model_dump(mode="json"), "decisive": True})


def test_f10_aggregate_partial_cannot_disagree_with_all_supported_records() -> None:
    payload = verification(SupportVerificationState.SUPPORTED).model_dump(mode="json")
    payload["state"] = "PARTIALLY_SUPPORTED"
    payload["unsupported_portions"] = ["all patients"]
    with pytest.raises(ValidationError, match="aggregate|commitment"):
        SupportVerification.model_validate(payload)


def test_n02_semantic_edge_collects_distinct_observations_and_exact_replay(tmp_path) -> None:
    edge = _edge(source_dates=SourceDates(), version_date=date(2020, 1, 1))
    replay = edge.model_copy(update={"observed_at": edge.observed_at + timedelta(seconds=1)})
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "observations.sqlite")
    _seed_verification_nodes(repository)
    chain = _chain_for(edge)
    repository.upsert(verified_edges=(edge,), verified_chains=(chain,))
    repository.upsert(verified_edges=(replay,))
    repository.upsert(verified_edges=(replay,))
    assert repository.observations(edge.edge_id) == (edge.observed_at, replay.observed_at)
    repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(tmp_path / "observations.sqlite")
    assert reopened.observations(edge.edge_id) == (edge.observed_at, replay.observed_at)
    reopened.close()


def test_n01_n02_cutoff_and_assessment_have_distinct_semantic_ids(tmp_path) -> None:
    earlier = _edge(
        source_dates=SourceDates(), version_date=date(2020, 1, 1), as_of=date(2019, 1, 1)
    )
    later = _edge(source_dates=SourceDates(), version_date=date(2020, 1, 1))
    other_assessment = _edge(
        source_dates=SourceDates(), version_date=date(2020, 1, 1), assessment_id="asm_other"
    )
    assert len({earlier.edge_id, later.edge_id, other_assessment.edge_id}) == 3
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "identity.sqlite")
    _seed_verification_nodes(repository)
    repository.upsert(
        verified_edges=(earlier, later, other_assessment),
        verified_chains=tuple(_chain_for(edge) for edge in (earlier, later, other_assessment)),
    )
    assert all(
        len(repository.observations(edge.edge_id)) == 1
        for edge in (earlier, later, other_assessment)
    )
    repository.close()


def test_f07_bare_verified_edge_cannot_be_persisted_as_authoritative() -> None:
    edge = _edge(source_dates=SourceDates(), version_date=date(2020, 1, 1))
    repository = SqlAlchemyEvidenceGraphRepository()
    with pytest.raises(ValueError, match="resolved semantic chain"):
        repository.upsert(verified_edges=(edge,))
    assert repository.observations(edge.edge_id) == ()
    repository.close()


def test_f07_classified_edge_requires_classification_identity() -> None:
    repository, edge, chain, _, _, _ = _direct_graph_case()
    with pytest.raises(ValueError, match="authoritative classification"):
        repository.upsert(verified_edges=(edge,), verified_chains=(chain,))
    assert repository.observations(edge.edge_id) == ()
    repository.close()


def _seed_verification_nodes(repository: SqlAlchemyEvidenceGraphRepository) -> None:
    version = make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1))
    provenance = phase6_graph_provenance()
    repository.upsert(
        nodes=(
            source_graph_node(source(dates=SourceDates()), observed_at=NOW, provenance=provenance),
            version_graph_node(version, observed_at=NOW, provenance=provenance),
            passage_graph_node(bundle().passages[0], observed_at=NOW, provenance=provenance),
        )
    )


def _chain_for(edge: VerifiedEvidenceEdge) -> VerifiedEvidenceChain:
    assert edge.assessment_id is not None
    return VerifiedEvidenceChain(
        assessment_id=edge.assessment_id,
        source=source(dates=SourceDates()),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        proposition=proposition(),
        mapping=mapping(),
        bundle=bundle(),
        verification=verification(SupportVerificationState.SUPPORTED),
        edge=edge,
    )


def _located_block(text: str, start: int, passage_id: str):
    return make_passage(
        "src_1",
        text=text,
        passage_id=passage_id,
        source_version_id="srcv_1_v1",
        locator=PassageLocator(
            kind=PassageLocatorKind.BLOCK, char_start=start, char_end=start + len(text)
        ),
    )


@pytest.mark.parametrize("neighbor_before", [True, False])
def test_f03_one_sided_neighbor_never_proves_both_unit_boundaries(neighbor_before: bool) -> None:
    target = _located_block("Relay activates", 100, "pass_target")
    neighbor = (
        _located_block("Earlier detail", 86, "pass_neighbor")
        if neighbor_before
        else _located_block("Later qualifier", 115, "pass_neighbor")
    )
    inspection = inspect_passage_context(
        target,
        available_passages=(target, neighbor),
        attempt=1,
        clock=lambda: NOW,
    )
    assert inspection.completeness != "COMPLETE"
    assert inspection.expansions[0].window_passage == neighbor


def test_f03_complete_abstract_is_complete_only_within_abstract_scope() -> None:
    content = "A complete abstract describes the relay."
    resolved = resolve_version_content(
        source=source(
            access_state=SourceAccessState.ABSTRACT_ONLY, content_hash=text_hash(content)
        ),
        version=make_version(
            "src_1",
            version_id="srcv_1_v1",
            access_state=SourceAccessState.ABSTRACT_ONLY,
            content_hash=text_hash(content),
        ),
        text=content,
    )
    abstract = extract_abstract(
        resolved,
        observed_at=NOW,
        provenance=phase5_provenance("complete-abstract"),
    )
    inspection = inspect_passage_context(
        abstract,
        available_passages=(abstract,),
        attempt=1,
        clock=lambda: NOW,
    )
    assert inspection.completeness == "COMPLETE"
    assert abstract.access_state == "ABSTRACT_ONLY"
    assert any("Abstract-only" in item for item in abstract.limitations)


def test_f03_qualifier_beyond_window_remains_truncated() -> None:
    text = "Relay activates. " + "filler " * 30 + "However, manual intervention is required."
    full = extract_resolved_content(
        "src_1",
        text,
        observed_at=NOW,
        provenance=phase5_provenance("context-unit"),
        source_version_id="srcv_1_v1",
    )
    target = extract_span(
        "src_1",
        text,
        char_start=0,
        char_end=len("Relay activates."),
        observed_at=NOW,
        provenance=phase5_provenance("context-unit"),
        source_version_id="srcv_1_v1",
        kind=PassageLocatorKind.BLOCK,
    )
    inspection = inspect_passage_context(
        target,
        available_passages=(target, full),
        attempt=1,
        window_chars=20,
        clock=lambda: NOW,
    )
    assert inspection.completeness == "TRUNCATED"
    assert inspection.expansions[0].window_passage is not None
    assert "However" not in inspection.expansions[0].window_passage.text


def test_f03_repeated_text_uses_the_exact_located_occurrence() -> None:
    phrase = "Relay activates."
    text = phrase + " First case succeeds. " + phrase + " However, second case fails."
    full = extract_resolved_content(
        "src_1",
        text,
        observed_at=NOW,
        provenance=phase5_provenance("repeat"),
        source_version_id="srcv_1_v1",
    )
    start = text.rfind(phrase)
    target = extract_span(
        "src_1",
        text,
        char_start=start,
        char_end=start + len(phrase),
        observed_at=NOW,
        provenance=phase5_provenance("repeat"),
        source_version_id="srcv_1_v1",
        kind=PassageLocatorKind.BLOCK,
    )
    inspection = inspect_passage_context(
        target,
        available_passages=(target, full),
        attempt=1,
        window_chars=30,
        clock=lambda: NOW,
    )
    assert inspection.expansions[0].window_passage is not None
    assert "second case fails" in inspection.expansions[0].window_passage.text


@pytest.mark.parametrize("budget", [0, 1])
async def test_f03_zero_budget_or_blocked_context_cannot_grant_decisive_support(
    budget: int,
) -> None:
    target = verifier_bundle(CLAIM_TEXT)
    available = (target.passages[0],)
    result = await verify_with_context_retry(
        retry_verifier(lambda _: judgments(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))),
        target,
        available_passages=available,
        max_expansions=budget,
        clock=lambda: NOW,
    )
    assert result.context_completeness != "COMPLETE"
    assert result.verification.state != SupportVerificationState.SUPPORTED


def test_f10_aggregate_supported_cannot_hide_a_partial_commitment() -> None:
    payload = verification(SupportVerificationState.SUPPORTED).model_dump(mode="json")
    payload["commitment_states"][0]["state"] = "PARTIALLY_SUPPORTED"
    payload["commitment_states"][0]["supported_subset"] = "read-only workloads"
    payload["commitment_states"][0]["unsupported_remainder"] = "all workloads"
    with pytest.raises(ValidationError, match="aggregate|commitment"):
        SupportVerification.model_validate(payload)


@pytest.mark.parametrize("with_contradiction", [False, True])
def test_f10_genuine_scoped_partials_preserve_scope_without_direct(
    with_contradiction: bool,
) -> None:
    baseline = verification(
        SupportVerificationState.CONTRADICTED
        if with_contradiction
        else SupportVerificationState.SUPPORTED
    )
    payload = baseline.model_dump(mode="json")
    partial_count = 1 if with_contradiction else 2
    for index in range(partial_count):
        record = payload["commitment_states"][index]
        record["state"] = "PARTIALLY_SUPPORTED"
        record["supported_subset"] = "read-only workloads"
        record["unsupported_remainder"] = "all workloads"
    payload["state"] = "CONTRADICTED" if with_contradiction else "PARTIALLY_SUPPORTED"
    payload["supported_portions"] = ["read-only workloads"]
    payload["unsupported_portions"] = ["all workloads"]
    verified = SupportVerification.model_validate(payload)
    edge = build_verified_evidence_edge(
        mapping=mapping(),
        verification=verified,
        proposition=proposition(),
        source=source(),
        bundle=bundle(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id="asm_partial",
    )
    chain = VerifiedEvidenceChain(
        assessment_id="asm_partial",
        source=source(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        proposition=proposition(),
        mapping=mapping(),
        bundle=bundle(),
        verification=verified,
        edge=edge,
    )
    classification = classify_verified_comparison(verified_comparison(chain), clock=lambda: NOW)
    assert not edge.decisive and not classification.decisive
    assert classification.relation != PrecedentState.DIRECT_PRECEDENT
    assert len(classification.scoped_coverage) == partial_count
    assert all(
        item.supported_subset == "read-only workloads" for item in classification.scoped_coverage
    )


def _direct_graph_case(database=None):
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    chain = _valid_chain(edge)
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    nodes, edges = _persist_phase6_fragment(repository, edge, classification)
    classified = ClassifiedComparison(comparison=comparison, classification=classification)
    return repository, edge, chain, classified, nodes, edges


def test_f06_foreign_classification_mapping_is_rejected_before_projection() -> None:
    repository, edge, _, classified, _, _ = _direct_graph_case()
    foreign = classified.classification.model_copy(update={"mapping_id": "map_foreign"})
    with pytest.raises(ValueError, match="Classification"):
        ClassifiedComparison(comparison=classified.comparison, classification=foreign)
    with pytest.raises(ValueError, match="Classification identity"):
        verified_edge_graph_fragment(
            (edge,),
            (foreign,),
            observed_at=NOW,
            provenance=phase6_graph_provenance(),
        )
    repository.close()


def test_f06_public_classifier_requires_verified_comparison() -> None:
    repository, _, _, classified, _, _ = _direct_graph_case()
    with pytest.raises(ValueError, match="VerifiedComparison"):
        classify_precedent(
            ClassificationFacts(
                proposition=proposition(),
                source_id="src_1",
                source_version_id="srcv_1_v1",
                mapping=mapping(),
                verification=verification(SupportVerificationState.SUPPORTED),
                claim=bundle().claim,
                decisive=True,
                chronology_state="PREDATES_CUTOFF",
            ),
            clock=lambda: NOW,
        )
    assert classify_precedent(classified.comparison, clock=lambda: NOW) == classified.classification
    repository.close()


def test_f06_foreign_classification_basis_is_rejected() -> None:
    repository, _, _, classified, _, _ = _direct_graph_case()
    foreign = classified.classification.model_copy(update={"basis": ("invented basis",)})
    with pytest.raises(ValueError, match="basis"):
        ClassifiedComparison(comparison=classified.comparison, classification=foreign)
    repository.close()


def test_f07_mutated_graph_passage_ids_fail_transactionally() -> None:
    repository, edge, chain, classified, nodes, edges = _direct_graph_case()
    direct = next(item for item in edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    tampered = direct.model_copy(
        update={"attributes": {**direct.attributes, "passage_ids": ["pass_nonexistent"]}}
    )
    with pytest.raises(ValueError, match="repository-derived projection"):
        repository.upsert(
            nodes=nodes,
            edges=(tampered,),
            verified_edges=(edge,),
            verified_chains=(chain,),
            classified_comparisons=(classified,),
        )
    assert repository.get_edge(direct.edge_id) is None
    assert repository.observations(edge.edge_id) == ()
    repository.close()


def test_f07_nonexistent_verified_passage_cannot_become_comparison() -> None:
    repository, edge, chain, _, _, _ = _direct_graph_case()
    forged = chain.model_copy(
        update={"edge": edge.model_copy(update={"passage_ids": ("pass_missing",)})}
    )
    with pytest.raises(ValueError, match="passage_ids|Verified edge"):
        verified_comparison(forged)
    repository.close()


def _persist_complex_valid_case(
    *, combination: bool
) -> tuple[SqlAlchemyEvidenceGraphRepository, str]:
    version = make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1))
    target = "mcu_comb_contract" if combination else "mcu_1"
    prop = proposition().model_copy(update={"mcu_id": target})
    mapped = mapping().model_copy(update={"mcu_id": target})
    original = bundle()
    parent = original.passages[0].attestation
    assert parent is not None
    second_text = "switches a load without an operator."
    start = parent.parent.text.index(second_text)
    second = extract_span(
        parent.parent,
        char_start=start,
        char_end=start + len(second_text),
        observed_at=NOW,
        provenance=phase5_provenance("multi-passage"),
    ).model_copy(update={"passage_id": "pass_2"})
    passages = (original.passages[0],) if combination else (original.passages[0], second)
    ids = tuple(item.passage_id for item in passages)
    claim = original.claim.model_copy(update={"mcu_id": target, "passage_ids": ids})
    evidence_bundle = SupportEvidenceBundle(claim=claim, passages=passages)
    baseline = verification(SupportVerificationState.SUPPORTED)
    records = tuple(
        record.model_copy(update={"passage_ids": ids}) for record in baseline.commitment_states
    )
    verified = baseline.model_copy(
        update={
            "mcu_id": target,
            "commitment_states": records,
            "relied_on_passage_ids": ids,
        }
    )
    edge = build_verified_evidence_edge(
        mapping=mapped,
        verification=verified,
        proposition=prop,
        source=source(),
        bundle=evidence_bundle,
        version=version,
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id="asm_complex",
        relation=PrecedentState.DIRECT_PRECEDENT,
    )
    chain = VerifiedEvidenceChain(
        assessment_id="asm_complex",
        source=source(),
        version=version,
        proposition=prop,
        mapping=mapped,
        bundle=evidence_bundle,
        verification=verified,
        edge=edge,
    )
    comparison = verified_comparison(chain)
    classification = classify_verified_comparison(comparison, clock=lambda: NOW)
    classified = ClassifiedComparison(comparison=comparison, classification=classification)
    repository = SqlAlchemyEvidenceGraphRepository()
    provenance = phase6_graph_provenance()
    base_nodes = (
        source_graph_node(source(), observed_at=NOW, provenance=provenance),
        version_graph_node(version, observed_at=NOW, provenance=provenance),
        GraphNode(
            node_id=target,
            kind=GraphNodeKind.MCU,
            label="Target",
            observed_at=NOW,
            provenance=provenance,
        ),
        *(passage_graph_node(item, observed_at=NOW, provenance=provenance) for item in passages),
    )
    fragment_nodes, fragment_edges = verified_edge_graph_fragment(
        (edge,),
        (classification,),
        observed_at=NOW,
        provenance=provenance,
    )
    repository.upsert(
        nodes=(*base_nodes, *fragment_nodes),
        edges=fragment_edges,
        verified_edges=(edge,),
        verified_chains=(chain,),
        classified_comparisons=(classified,),
    )
    return repository, edge.edge_id


def test_f07_valid_multi_passage_and_combination_graph_projections() -> None:
    for combination in (False, True):
        repository, edge_id = _persist_complex_valid_case(combination=combination)
        direct = repository.edges(kinds=frozenset({GraphEdgeKind.DIRECT_PRECEDENT}))
        assert len(direct) == 1
        assert direct[0].attributes["verified_edge_id"] == edge_id
        assert direct[0].target_node_id == ("mcu_comb_contract" if combination else "mcu_1")
        if not combination:
            assert direct[0].attributes["passage_ids"] == ["pass_1", "pass_2"]
        repository.close()


def test_schema_v3_metadata_graph_migrates_and_unsafe_phase6_is_blocked(tmp_path) -> None:
    from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION, schema_version

    safe_path = tmp_path / "safe-v3.sqlite"
    safe = SqlAlchemyEvidenceGraphRepository(safe_path)
    with safe.engine.begin() as connection:
        connection.execute(sql_text("UPDATE schema_version SET version = 3 WHERE version = 5"))
    safe.close()
    reopened = SqlAlchemyEvidenceGraphRepository(safe_path)
    assert schema_version(reopened.engine) == SCHEMA_VERSION == 5
    reopened.close()

    unsafe_path = tmp_path / "unsafe-v3.sqlite"
    unsafe, edge, chain, classified, nodes, edges = _direct_graph_case(unsafe_path)
    unsafe.upsert(
        nodes=nodes,
        edges=edges,
        verified_edges=(edge,),
        verified_chains=(chain,),
        classified_comparisons=(classified,),
    )
    with unsafe.engine.begin() as connection:
        connection.execute(sql_text("UPDATE schema_version SET version = 3 WHERE version = 5"))
    unsafe.close()
    with pytest.raises(ValueError, match="Legacy Phase 6 graph edges"):
        SqlAlchemyEvidenceGraphRepository(unsafe_path)
