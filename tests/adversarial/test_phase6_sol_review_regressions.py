"""Stable reproductions for the GPT-6 Sol High Phase 6 review findings.

One regression per finding F01-F11 plus the minor M01; added after the review
recorded them as open. These do not replace the original tests.
"""

from datetime import date

import pytest
from sqlalchemy import text as sql_text

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.models import EdgeVerificationRef, GraphEdgeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.precedent.gates import (
    ClassificationFacts,
    classify_precedent,
)
from novelty_harness.evidence.precedent.patent import PatentEvidenceEntry
from novelty_harness.evidence.verification.gates import (
    EdgeEligibilityError,
    VerificationValidationError,
    build_verified_evidence_edge,
)
from novelty_harness.evidence.verification.models import (
    CommitmentStateRecord,
    SupportVerification,
)
from tests.fixtures.phase5 import phase5_provenance
from tests.unit.evidence.precedent.test_classification import (
    commitment,
    facts_for,
)
from tests.unit.evidence.precedent.test_classification import (
    proposition as classification_proposition,
)
from tests.unit.evidence.precedent.test_patent import classification as patent_classification
from tests.unit.evidence.verification.test_eligibility import (
    AS_OF,
    NOW,
    build,
    source,
)
from tests.unit.evidence.verification.test_eligibility import (
    mapping as eligibility_mapping,
)
from tests.unit.evidence.verification.test_eligibility import (
    proposition as eligibility_proposition,
)
from tests.unit.evidence.verification.test_eligibility import (
    verification as eligibility_verification,
)
from tests.unit.evidence.verification.test_verifier import (
    bundle,
    proposal_data,
    verifier,
)

ORIGIN = phase5_provenance("sol-review-regressions")


# --- F05 ---


async def test_f05_supported_without_citations_is_rejected() -> None:
    data = proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))
    for judgment in data["judgments"]:  # type: ignore[index]
        judgment["passage_ids"] = []  # type: ignore[index]
    with pytest.raises(VerificationValidationError, match="cite at least one"):
        await verifier(data).verify(bundle(), clock=lambda: NOW)


def test_f05_mapper_passages_cannot_substitute_for_verifier_citations() -> None:
    citation_free = SupportVerification(
        verification_id="ver_empty",
        claim_id="claim_1",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        state=SupportVerificationState.SUPPORTED,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="mech",
                dimension=eligibility_proposition().commitments[0].dimension,
                state="SUPPORTED",
                rationale="supported without citation",
                passage_ids=(),
            ),
            CommitmentStateRecord(
                commitment_id="outcome",
                dimension=eligibility_proposition().commitments[1].dimension,
                state="SUPPORTED",
                rationale="supported without citation",
                passage_ids=(),
            ),
        ),
        supported_portions=("mech", "outcome"),
        verifier_prompt_version="support-verifier-v1",
        verifier_rubric_version="support-rubric-v1",
        observed_at=NOW,
        provenance=ORIGIN,
    )
    with pytest.raises(EdgeEligibilityError, match="verifier-cited passages"):
        build_verified_evidence_edge(
            mapping=eligibility_mapping(),
            verification=citation_free,
            proposition=eligibility_proposition(),
            source=source(),
            as_of=AS_OF,
            observed_at=NOW,
        )


# --- F06 ---


def test_f06_foreign_source_version_proposition_joins_are_rejected() -> None:
    target = eligibility_proposition()
    base = dict(
        proposition=target,
        source_id="src_1",
        source_version_id="srcv_1_v1",
        verification=eligibility_verification(SupportVerificationState.SUPPORTED),
        decisive=True,
        chronology_state="PREDATES_CUTOFF",
    )
    with pytest.raises(ValueError, match="Mapping identity"):
        classify_precedent(
            ClassificationFacts(
                **{**base, "mapping": eligibility_mapping(), "source_id": "src_other"},
            ),
            clock=lambda: NOW,
        )
    foreign_mapping = eligibility_mapping().model_copy(update={"source_version_id": "srcv_other"})
    with pytest.raises(ValueError, match="Mapping identity"):
        classify_precedent(
            ClassificationFacts(**{**base, "mapping": foreign_mapping}), clock=lambda: NOW
        )
    foreign_proposition_mapping = eligibility_mapping().model_copy(
        update={"proposition_id": "prop_other"}
    )
    with pytest.raises(ValueError, match="Mapping identity"):
        classify_precedent(
            ClassificationFacts(**{**base, "mapping": foreign_proposition_mapping}),
            clock=lambda: NOW,
        )
    foreign_verification = eligibility_verification(SupportVerificationState.SUPPORTED).model_copy(
        update={"mapping_id": "map_other"}
    )
    with pytest.raises(ValueError, match="Verification identity"):
        classify_precedent(
            ClassificationFacts(
                **{**base, "mapping": eligibility_mapping(), "verification": foreign_verification}
            ),
            clock=lambda: NOW,
        )
    with pytest.raises(EdgeEligibilityError, match="identities must agree"):
        build_verified_evidence_edge(
            mapping=eligibility_mapping().model_copy(update={"proposition_id": "prop_other"}),
            verification=eligibility_verification(SupportVerificationState.SUPPORTED),
            proposition=target,
            source=source(),
            as_of=AS_OF,
            observed_at=NOW,
        )


def test_f06_patent_entry_mcu_and_version_joins_are_rejected() -> None:
    with pytest.raises(ValueError, match="another MCU"):
        PatentEvidenceEntry(
            source_id="src_patent_a",
            mcu_id="mcu_other",
            is_patent=True,
            classification=patent_classification(
                "src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT
            ),
        )
    with pytest.raises(ValueError, match="another version"):
        PatentEvidenceEntry(
            source_id="src_patent_a",
            source_version_id="srcv_other",
            mcu_id="mcu_1",
            is_patent=True,
            classification=patent_classification(
                "src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT
            ),
        )


# --- F07 ---


def _persist_phase6_fragment(repository, edge, classified):
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind

    existing = (
        GraphNode(
            node_id=edge.source_id,
            kind=GraphNodeKind.SOURCE,
            label="Source",
            observed_at=NOW,
            provenance=ORIGIN,
        ),
        GraphNode(
            node_id="mcu_1",
            kind=GraphNodeKind.MCU,
            label="MCU",
            observed_at=NOW,
            provenance=ORIGIN,
        ),
    )
    repository.upsert(nodes=existing)
    return nodes, graph_edges


def test_f07_graph_persistence_rejects_unresolved_or_mismatched_verification() -> None:
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    from tests.unit.evidence.graph.test_phase6_mapping import (
        classification as graph_classification,
    )

    classified = graph_classification(edge, PrecedentState.DIRECT_PRECEDENT, decisive=True)

    # Legitimate projected edge persists when its verified artifact is present.
    repository = SqlAlchemyEvidenceGraphRepository()
    _, graph_edges = _persist_phase6_fragment(repository, edge, classified)
    direct = next(item for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    repository.upsert(edges=(direct,), verified_edges=(edge,))
    assert repository.get_edge(direct.edge_id) is not None

    fake = direct.model_copy(
        update={
            "verification": EdgeVerificationRef(
                verified_edge_id="edge_does_not_exist",
                support_state=SupportVerificationState.SUPPORTED,
                decisive=True,
                precedent_relation=PrecedentState.DIRECT_PRECEDENT,
            )
        }
    )
    with pytest.raises(ValueError, match="unknown verified edge"):
        repository.upsert(edges=(fake,))
    repository.close()

    # A real verified artifact for another MCU cannot back this edge.
    other_repository = SqlAlchemyEvidenceGraphRepository()
    other_repository.upsert(nodes=_persist_phase6_fragment(other_repository, edge, classified)[0])
    other_mcu_edge = edge.model_copy(update={"mcu_id": "mcu_other"})
    with pytest.raises(ValueError, match="do not match"):
        other_repository.upsert(edges=(direct,), verified_edges=(other_mcu_edge,))
    other_repository.close()


def test_f07_schema_v1_migrates_to_v2(tmp_path) -> None:
    database = tmp_path / "graph.sqlite3"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    # Simulate a v1 database by recording version 1 after the v2 tables exist.
    with repository.engine.begin() as connection:
        connection.execute(sql_text("UPDATE schema_version SET version = 1 WHERE version = 2"))
    repository.close()
    migrated = SqlAlchemyEvidenceGraphRepository(database)
    from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION, schema_version

    assert schema_version(migrated.engine) == SCHEMA_VERSION == 2
    migrated.close()


def test_f06_f05_foundations_hold_on_a_valid_edge() -> None:
    # Sanity: the stricter gates still accept a legitimate cited verification.
    from novelty_harness.evidence.mapping.models import ComparisonDimension

    target = classification_proposition(
        commitment("mech", ComparisonDimension.MECHANISM, text="threshold drives a coil"),
    )
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED"},
            matching=(ComparisonDimension.MECHANISM,),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.DIRECT_PRECEDENT
    assert date(2026, 9, 28) == AS_OF
