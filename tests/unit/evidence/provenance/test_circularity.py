from novelty_harness.evidence.provenance.circularity import detect_provenance_cycles
from novelty_harness.evidence.provenance.models import (
    LineageConfidence,
    ProvenanceRelation,
)
from tests.fixtures.phase5 import make_edge


def test_derivation_cycle_is_material() -> None:
    edges = (
        make_edge("src_a", "src_b", relation=ProvenanceRelation.DERIVES_FROM),
        make_edge("src_b", "src_c", relation=ProvenanceRelation.DERIVES_FROM),
        make_edge("src_c", "src_a", relation=ProvenanceRelation.DERIVES_FROM),
    )
    cycles = detect_provenance_cycles(("src_a", "src_b", "src_c"), edges)
    assert len(cycles) == 1
    assert cycles[0].severity == "MATERIAL"
    assert cycles[0].source_ids == ("src_a", "src_b", "src_c")
    assert cycles[0].relation_types == (ProvenanceRelation.DERIVES_FROM,)


def test_circular_reposts_are_material() -> None:
    edges = (
        make_edge("src_a", "src_b", relation=ProvenanceRelation.REPOSTS),
        make_edge("src_b", "src_a", relation=ProvenanceRelation.REPOSTS),
    )
    cycles = detect_provenance_cycles(("src_a", "src_b"), edges)
    assert len(cycles) == 1
    assert cycles[0].severity == "MATERIAL"


def test_mutual_paper_citation_is_informational_not_dependency() -> None:
    edges = (
        make_edge("src_a", "src_b", relation=ProvenanceRelation.CITES),
        make_edge("src_b", "src_a", relation=ProvenanceRelation.CITES),
    )
    cycles = detect_provenance_cycles(("src_a", "src_b"), edges)
    assert len(cycles) == 1
    assert cycles[0].severity == "INFO"
    assert cycles[0].relation_types == (ProvenanceRelation.CITES,)
    assert "does not establish dependency" in cycles[0].explanation


def test_possible_dependency_cycle_is_only_a_warning() -> None:
    edges = (
        make_edge(
            "src_a",
            "src_b",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.POSSIBLE,
        ),
        make_edge(
            "src_b",
            "src_a",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.POSSIBLE,
        ),
    )
    cycles = detect_provenance_cycles(("src_a", "src_b"), edges)
    assert len(cycles) == 1
    assert cycles[0].severity == "WARNING"
    assert "uncertain" in cycles[0].explanation


def test_mixed_citation_and_derivation_cycle_is_material() -> None:
    edges = (
        make_edge("src_a", "src_b", relation=ProvenanceRelation.CITES),
        make_edge("src_b", "src_a", relation=ProvenanceRelation.DERIVES_FROM),
    )
    cycles = detect_provenance_cycles(("src_a", "src_b"), edges)
    assert len(cycles) == 1
    assert cycles[0].severity == "MATERIAL"
    assert set(cycles[0].relation_types) == {
        ProvenanceRelation.CITES,
        ProvenanceRelation.DERIVES_FROM,
    }


def test_acyclic_lineage_has_no_cycles() -> None:
    edges = (
        make_edge("src_a", "src_b", relation=ProvenanceRelation.DERIVES_FROM),
        make_edge("src_c", "src_b", relation=ProvenanceRelation.CITES),
        make_edge("src_d", "src_a", relation=ProvenanceRelation.FOUND_BY),
    )
    assert detect_provenance_cycles(("src_a", "src_b", "src_c", "src_d"), edges) == ()


def test_cycle_detection_is_deterministic_and_ignores_unknown_sources() -> None:
    edges = (
        make_edge("src_a", "src_b", relation=ProvenanceRelation.DERIVES_FROM),
        make_edge("src_b", "src_a", relation=ProvenanceRelation.DERIVES_FROM),
        make_edge("src_a", "src_unknown", relation=ProvenanceRelation.DERIVES_FROM),
    )
    first = detect_provenance_cycles(("src_a", "src_b"), edges)
    second = detect_provenance_cycles(("src_b", "src_a"), tuple(reversed(edges)))
    assert first == second == detect_provenance_cycles(("src_a", "src_b"), tuple(reversed(edges)))
