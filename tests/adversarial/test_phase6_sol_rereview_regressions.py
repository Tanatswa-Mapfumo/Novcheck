"""Independent Round-2 reproductions at public Phase 6 semantic boundaries."""

from datetime import date

import pytest

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.models import GraphEdgeKind, GraphNode, GraphNodeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.retrieval_mapping import version_graph_node
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.evidence.mapping.models import ComparisonDimension
from novelty_harness.evidence.phase6_pipeline import select_versions
from novelty_harness.evidence.precedent.gates import (
    ClassificationFacts as RawClassificationFacts,
)
from novelty_harness.evidence.precedent.gates import (
    ClassifiedComparison,
    classify_verified_comparison,
)
from novelty_harness.evidence.precedent.gates import (
    _classify_facts as classify_precedent,
)
from novelty_harness.evidence.verification.gates import (
    EdgeEligibilityError,
    build_verified_evidence_edge,
    validate_verified_chain,
)
from novelty_harness.evidence.verification.integrity import (
    SemanticIntegrityError,
    verified_comparison,
)
from novelty_harness.evidence.verification.models import CommitmentStateRecord, SupportVerification
from tests.fixtures.phase5 import make_passage, make_version
from tests.unit.evidence.precedent.test_classification import (
    classification_facts as ClassificationFacts,
)
from tests.unit.evidence.precedent.test_classification import (
    commitment,
    mapping_for,
    verification_for,
)
from tests.unit.evidence.precedent.test_classification import (
    proposition as classification_proposition,
)
from tests.unit.evidence.verification.test_eligibility import (
    AS_OF,
    NOW,
    bundle,
    mapping,
    proposition,
    source,
    verification,
)


def _edge(**overrides: object):
    arguments = {
        "mapping": mapping(),
        "verification": verification(SupportVerificationState.SUPPORTED),
        "proposition": proposition(),
        "source": source(),
        "bundle": bundle(),
        "as_of": AS_OF,
        "observed_at": NOW,
        "assessment_id": "asm_test",
        "version": make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
    }
    arguments.update(overrides)
    return build_verified_evidence_edge(**arguments)


def test_f02_versioned_evidence_cannot_omit_matching_version() -> None:
    with pytest.raises(EdgeEligibilityError, match="version"):
        _edge(version=None)


def test_f02_cited_preprint_is_not_disqualified_by_later_parent_metadata() -> None:
    edge = _edge(source=source(dates={"publication_date": date(2027, 1, 1)}))
    assert edge.chronology.state == "PREDATES_CUTOFF"
    assert edge.decisive


def test_f02_classifier_rejects_decisive_post_cutoff_facts() -> None:
    with pytest.raises(ValueError, match="chronology"):
        classify_precedent(
            ClassificationFacts(
                proposition=proposition(),
                source_id="src_1",
                source_version_id="srcv_1_v1",
                mapping=mapping(),
                verification=verification(SupportVerificationState.SUPPORTED),
                decisive=True,
                chronology_state="POST_CUTOFF",
            ),
            clock=lambda: NOW,
        )


def test_f03_unknown_or_truncated_context_cannot_be_decisive_at_public_gates() -> None:
    for completeness in ("UNKNOWN", "TRUNCATED", "UNAVAILABLE"):
        uninspected = verification(SupportVerificationState.SUPPORTED).model_copy(
            update={"context_completeness": completeness}
        )
        edge = _edge(verification=uninspected)
        assert not edge.decisive
        with pytest.raises(ValueError, match="context"):
            ClassificationFacts(
                proposition=proposition(),
                source_id="src_1",
                source_version_id="srcv_1_v1",
                mapping=mapping(),
                verification=uninspected,
                decisive=True,
                chronology_state="PREDATES_CUTOFF",
            )


def test_f05_reliance_must_equal_commitment_citation_union() -> None:
    original = verification(SupportVerificationState.SUPPORTED)
    payload = original.model_dump(mode="json")
    payload["relied_on_passage_ids"] = ["pass_unseen"]
    with pytest.raises(ValueError, match="relied_on_passage_ids"):
        SupportVerification.model_validate(payload)
    forged = original.model_copy(update={"relied_on_passage_ids": ("pass_unseen",)})
    with pytest.raises(EdgeEligibilityError, match="relied_on_passage_ids"):
        _edge(verification=forged)


def test_f06_matching_version_id_with_foreign_owner_is_rejected() -> None:
    foreign = make_version("src_other", version_id="srcv_1_v1", published_date=date(2020, 1, 1))
    with pytest.raises(EdgeEligibilityError, match="owner"):
        _edge(version=foreign)


def test_f06_another_claim_or_proposition_cannot_share_a_verified_result() -> None:
    foreign_claim = bundle().claim.model_copy(update={"claim_id": "claim_other"})
    with pytest.raises(EdgeEligibilityError, match="claim"):
        _edge(bundle=bundle().model_copy(update={"claim": foreign_claim}))
    foreign_proposition = bundle().claim.model_copy(update={"proposition_id": "prop_other"})
    with pytest.raises(EdgeEligibilityError, match="proposition"):
        _edge(bundle=bundle().model_copy(update={"claim": foreign_proposition}))

    valid = dict(
        proposition=proposition(),
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mapping=mapping(),
        verification=verification(SupportVerificationState.SUPPORTED),
        decisive=True,
        chronology_state="PREDATES_CUTOFF",
    )
    with pytest.raises(ValueError, match="claim"):
        classify_precedent(RawClassificationFacts(**valid), clock=lambda: NOW)
    with pytest.raises(ValueError, match="proposition"):
        classify_precedent(
            ClassificationFacts(
                **valid,
                claim=bundle().claim.model_copy(update={"proposition_id": "prop_other"}),
            ),
            clock=lambda: NOW,
        )


def test_n01_cutoff_changes_immutable_verified_edge_identity() -> None:
    earlier = _edge(as_of=date(2019, 1, 1))
    later = _edge(as_of=date(2026, 9, 28))
    assert earlier.edge_id != later.edge_id
    assert not earlier.decisive and later.decisive
    assert _edge(as_of=date(2019, 1, 1)).edge_id == earlier.edge_id


def test_f04_mixed_unversioned_passages_are_selected_or_disclosed() -> None:
    version = make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1))
    versioned = make_passage(
        "src_1", passage_id="pass_versioned", source_version_id=version.version_id
    )
    unversioned = make_passage("src_1", passage_id="pass_unversioned")
    slots, excluded = select_versions((version,), (versioned, unversioned), max_versions=2)
    assert slots == (version,)
    assert any("pass_unversioned" in item for item in excluded)
    slots, excluded = select_versions((version,), (versioned, unversioned), max_versions=1)
    assert slots == (version,)
    assert any("pass_unversioned" in item for item in excluded)


def test_f07_direct_graph_edge_cannot_use_a_bare_verified_artifact() -> None:
    from tests.unit.evidence.graph.test_phase6_mapping import classification as graph_classification

    edge = _edge(relation=PrecedentState.DIRECT_PRECEDENT)
    classified = graph_classification(edge, PrecedentState.DIRECT_PRECEDENT, decisive=True)
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    direct = next(item for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(
        nodes=(
            GraphNode(
                node_id="src_1",
                kind=GraphNodeKind.SOURCE,
                label="Source",
                observed_at=NOW,
                provenance=source().provenance,
            ),
            GraphNode(
                node_id="mcu_1",
                kind=GraphNodeKind.MCU,
                label="MCU",
                observed_at=NOW,
                provenance=source().provenance,
            ),
        )
    )
    with pytest.raises(ValueError, match="semantic chain"):
        repository.upsert(nodes=nodes, edges=(direct,), verified_edges=(edge,))
    assert repository.get_edge(direct.edge_id) is None


def test_f07_decisive_chain_requires_the_real_cited_passage_node() -> None:
    from tests.adversarial.test_phase6_sol_review_regressions import _valid_chain

    edge = _edge(relation=PrecedentState.DIRECT_PRECEDENT)
    chain = _valid_chain(edge)
    comparison = verified_comparison(chain)
    classified = classify_verified_comparison(comparison, clock=lambda: NOW)
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    repository = SqlAlchemyEvidenceGraphRepository()
    with pytest.raises(ValueError, match="unresolved passage"):
        repository.upsert(
            nodes=(
                GraphNode(
                    node_id="src_1",
                    kind=GraphNodeKind.SOURCE,
                    label="Source",
                    observed_at=NOW,
                    provenance=source().provenance,
                ),
                version_graph_node(
                    make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
                    observed_at=NOW,
                    provenance=source().provenance,
                ),
                GraphNode(
                    node_id="mcu_1",
                    kind=GraphNodeKind.MCU,
                    label="MCU",
                    observed_at=NOW,
                    provenance=source().provenance,
                ),
                *nodes,
            ),
            edges=graph_edges,
            verified_edges=(edge,),
            verified_chains=(chain,),
            classified_comparisons=(
                ClassifiedComparison(comparison=comparison, classification=classified),
            ),
        )
    assert all(repository.get_edge(item.edge_id) is None for item in graph_edges)


def test_f07_chain_rejects_forged_prompt_version_trace() -> None:
    from tests.adversarial.test_phase6_sol_review_regressions import _valid_chain

    edge = _edge()
    chain = _valid_chain(edge).model_copy(
        update={"edge": edge.model_copy(update={"verifier_prompt_version": "forged-version"})}
    )
    with pytest.raises(SemanticIntegrityError, match="verifier_prompt_version"):
        validate_verified_chain(chain)


def test_n01_two_cutoffs_persist_as_immutable_distinct_graph_artifacts() -> None:
    from tests.adversarial.test_phase6_sol_review_regressions import (
        _persist_phase6_fragment,
        _valid_chain,
    )

    earlier = _edge(as_of=date(2019, 1, 1), relation=PrecedentState.UNRESOLVED)
    later = _edge(as_of=date(2026, 9, 28), relation=PrecedentState.DIRECT_PRECEDENT)
    repository = SqlAlchemyEvidenceGraphRepository()
    for edge in (earlier, later):
        chain = _valid_chain(edge)
        comparison = verified_comparison(chain)
        classified = classify_verified_comparison(comparison, clock=lambda: NOW)
        nodes, graph_edges = _persist_phase6_fragment(repository, edge, classified)
        repository.upsert(
            nodes=nodes,
            edges=graph_edges,
            verified_edges=(edge,),
            verified_chains=(chain,),
            classified_comparisons=(
                ClassifiedComparison(comparison=comparison, classification=classified),
            ),
        )
        repository.upsert(
            nodes=nodes,
            edges=graph_edges,
            verified_edges=(edge,),
            verified_chains=(chain,),
            classified_comparisons=(
                ClassifiedComparison(comparison=comparison, classification=classified),
            ),
        )
    assert earlier.edge_id != later.edge_id
    assert len(repository.nodes(kinds=frozenset({GraphNodeKind.EVIDENCE_PROPOSITION}))) == 2


def test_f09_mapper_only_conflict_cannot_change_fixed_verified_semantics() -> None:
    target = classification_proposition(
        commitment("mech", ComparisonDimension.MECHANISM, text="sensor controls relay")
    )
    verified = verification_for(target, {"mech": "SUPPORTED"})
    relations = []
    for dimension in (
        ComparisonDimension.PURPOSE,
        ComparisonDimension.MECHANISM,
        ComparisonDimension.RELATIONSHIPS,
        ComparisonDimension.CONTROL_FLOW,
        ComparisonDimension.CONTEXT,
        ComparisonDimension.INTENDED_OUTCOME,
    ):
        facts = ClassificationFacts(
            proposition=target,
            source_id="src_1",
            source_version_id="srcv_1_v1",
            mapping=mapping_for(conflicting=(dimension,)),
            verification=verified,
            decisive=True,
            chronology_state="PREDATES_CUTOFF",
        )
        relations.append(classify_precedent(facts, clock=lambda: NOW).relation)
    assert relations == [PrecedentState.DIRECT_PRECEDENT] * 6


def test_f10_scoped_partial_survives_classification_without_direct_inflation() -> None:
    target = classification_proposition(
        commitment("scope", ComparisonDimension.INTENDED_OUTCOME, text="works for all workloads")
    )
    verified = SupportVerification(
        verification_id="ver_scoped",
        claim_id="claim_scoped",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        state=SupportVerificationState.PARTIALLY_SUPPORTED,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="scope",
                dimension=ComparisonDimension.INTENDED_OUTCOME,
                state="PARTIALLY_SUPPORTED",
                rationale="Only the narrower workload is supported",
                passage_ids=("pass_1",),
                supported_subset="read-only workloads",
                unsupported_remainder="all workloads",
            ),
        ),
        supported_portions=("read-only workloads",),
        unsupported_portions=("all workloads",),
        relied_on_passage_ids=("pass_1",),
        verifier_prompt_version="support-verifier-v1",
        verifier_rubric_version="support-rubric-v1",
        observed_at=NOW,
        provenance=source().provenance,
    )
    result = classify_precedent(
        ClassificationFacts(
            proposition=target,
            source_id="src_1",
            source_version_id="srcv_1_v1",
            mapping=mapping_for(matching=(ComparisonDimension.INTENDED_OUTCOME,)),
            verification=verified,
            decisive=False,
            chronology_state="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert result.relation not in {
        PrecedentState.DIRECT_PRECEDENT,
        PrecedentState.SUPERFICIAL_SIMILARITY,
    }
    assert result.scoped_coverage[0].supported_subset == "read-only workloads"
    assert result.scoped_coverage[0].unsupported_remainder == "all workloads"
    assert not result.decisive


def test_f10_partial_subsets_survive_a_separate_contradiction() -> None:
    target = classification_proposition(
        commitment("population", ComparisonDimension.CONTEXT, text="works for all patients"),
        commitment("outcome", ComparisonDimension.INTENDED_OUTCOME, text="reduces errors"),
    )
    verified = SupportVerification(
        verification_id="ver_scoped_contradiction",
        claim_id="claim_scoped_contradiction",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        state=SupportVerificationState.CONTRADICTED,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="population",
                dimension=ComparisonDimension.CONTEXT,
                state="PARTIALLY_SUPPORTED",
                rationale="Only the subgroup is supported",
                passage_ids=("pass_1",),
                supported_subset="adult patients",
                unsupported_remainder="all patients",
            ),
            CommitmentStateRecord(
                commitment_id="outcome",
                dimension=ComparisonDimension.INTENDED_OUTCOME,
                state="CONTRADICTED",
                rationale="Errors increased",
                passage_ids=("pass_1",),
            ),
        ),
        supported_portions=("adult patients",),
        unsupported_portions=("all patients",),
        contradictions=("errors increased",),
        relied_on_passage_ids=("pass_1",),
        context_completeness="COMPLETE",
        verifier_prompt_version="support-verifier-v1",
        verifier_rubric_version="support-rubric-v1",
        observed_at=NOW,
        provenance=source().provenance,
    )
    result = classify_precedent(
        ClassificationFacts(
            proposition=target,
            source_id="src_1",
            source_version_id="srcv_1_v1",
            mapping=mapping_for(),
            verification=verified,
            decisive=False,
            chronology_state="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert result.relation == PrecedentState.CONTRADICTORY_EVIDENCE
    assert result.scoped_coverage[0].supported_subset == "adult patients"
    assert "all patients" in result.missing_elements
    assert not result.decisive


def test_f10_two_scoped_partials_do_not_aggregate_to_full_support() -> None:
    target = classification_proposition(
        commitment("scope", ComparisonDimension.CONTEXT, text="works for all patients"),
        commitment("condition", ComparisonDimension.CONSTRAINTS, text="works in all clinics"),
    )
    verified = SupportVerification(
        verification_id="ver_two_partials",
        claim_id="claim_two_partials",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        state=SupportVerificationState.PARTIALLY_SUPPORTED,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="scope",
                dimension=ComparisonDimension.CONTEXT,
                state="PARTIALLY_SUPPORTED",
                rationale="adult subgroup only",
                passage_ids=("pass_1",),
                supported_subset="adult patients",
                unsupported_remainder="all patients",
            ),
            CommitmentStateRecord(
                commitment_id="condition",
                dimension=ComparisonDimension.CONSTRAINTS,
                state="PARTIALLY_SUPPORTED",
                rationale="research clinics only",
                passage_ids=("pass_1",),
                supported_subset="research clinics",
                unsupported_remainder="all clinics",
            ),
        ),
        supported_portions=("adult patients", "research clinics"),
        unsupported_portions=("all patients", "all clinics"),
        relied_on_passage_ids=("pass_1",),
        context_completeness="COMPLETE",
        verifier_prompt_version="support-verifier-v1",
        verifier_rubric_version="support-rubric-v1",
        observed_at=NOW,
        provenance=source().provenance,
    )
    result = classify_precedent(
        ClassificationFacts(
            proposition=target,
            source_id="src_1",
            source_version_id="srcv_1_v1",
            mapping=mapping_for(),
            verification=verified,
            decisive=False,
            chronology_state="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert result.relation != PrecedentState.DIRECT_PRECEDENT
    assert {item.supported_subset for item in result.scoped_coverage} == {
        "adult patients",
        "research clinics",
    }
    assert {item.unsupported_remainder for item in result.scoped_coverage} == {
        "all patients",
        "all clinics",
    }
