from novelty_harness.evidence.provenance.clustering import (
    build_lineage_clusters,
    cluster_for_source,
    independent_evidence_count,
)
from novelty_harness.evidence.provenance.models import (
    LineageConfidence,
    ProvenanceRelation,
)
from tests.fixtures.phase5 import make_edge, make_source


def test_fifty_derivative_pages_of_one_press_release_count_as_one_root() -> None:
    release = make_source("src_release")
    derivatives = tuple(make_source(f"src_page_{index:02d}") for index in range(50))
    edges = tuple(
        make_edge(
            derivative.source_id,
            release.source_id,
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.CONFIRMED,
        )
        for derivative in derivatives
    )
    clusters = build_lineage_clusters((release, *derivatives), edges)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert len(cluster.source_ids) == 51
    assert cluster.root_source_ids == ("src_release",)
    assert cluster.independent_roots == 1
    assert independent_evidence_count(clusters) == 1


def test_preprint_and_journal_versions_are_one_lineage() -> None:
    preprint = make_source("src_preprint")
    journal = make_source("src_journal")
    edge = make_edge(
        "src_journal",
        "src_preprint",
        relation=ProvenanceRelation.VERSION_OF,
        lineage_confidence=LineageConfidence.CONFIRMED,
    )
    clusters = build_lineage_clusters((preprint, journal), (edge,))
    assert len(clusters) == 1
    assert clusters[0].independent_roots == 1
    assert clusters[0].root_source_ids == ("src_preprint",)


def test_patent_family_is_one_lineage_without_erasing_publications() -> None:
    primary = make_source("src_patent_ep")
    family = (
        make_source("src_patent_us"),
        make_source("src_patent_wo"),
    )
    edges = tuple(
        make_edge(
            member.source_id,
            primary.source_id,
            relation=ProvenanceRelation.PATENT_FAMILY_OF,
            lineage_confidence=LineageConfidence.CONFIRMED,
        )
        for member in family
    )
    clusters = build_lineage_clusters((primary, *family), edges)
    assert len(clusters) == 1
    assert len(clusters[0].source_ids) == 3
    assert clusters[0].root_source_ids == ("src_patent_ep",)
    assert clusters[0].independent_roots == 1


def test_shared_citations_do_not_collapse_independent_works() -> None:
    foundational = make_source("src_foundational")
    replication_a = make_source("src_replication_a")
    replication_b = make_source("src_replication_b")
    edges = (
        make_edge(
            "src_replication_a",
            "src_foundational",
            relation=ProvenanceRelation.CITES,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
        make_edge(
            "src_replication_b",
            "src_foundational",
            relation=ProvenanceRelation.CITES,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
    )
    clusters = build_lineage_clusters((foundational, replication_a, replication_b), edges)
    assert len(clusters) == 3
    assert independent_evidence_count(clusters) == 3
    assert cluster_for_source(clusters, "src_replication_a") != cluster_for_source(
        clusters, "src_replication_b"
    )


def test_independent_replications_of_one_origin_yield_multiple_roots() -> None:
    origin = make_source("src_origin")
    replication_a = make_source("src_replication_a")
    replication_b = make_source("src_replication_b")
    meta = make_source("src_meta_analysis")
    edges = (
        make_edge(
            "src_meta_analysis",
            "src_replication_a",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
        make_edge(
            "src_meta_analysis",
            "src_replication_b",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
        make_edge(
            "src_replication_a",
            "src_origin",
            relation=ProvenanceRelation.CITES,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
    )
    clusters = build_lineage_clusters((origin, replication_a, replication_b, meta), edges)
    multi_root = cluster_for_source(clusters, "src_meta_analysis")
    assert multi_root is not None
    assert multi_root.root_source_ids == ("src_replication_a", "src_replication_b")
    assert multi_root.independent_roots == 2
    assert independent_evidence_count(clusters) == 3


def test_possible_lineage_stays_uncertain_and_is_not_collapsed() -> None:
    release = make_source("src_release")
    blog = make_source("src_blog")
    edge = make_edge(
        "src_blog",
        "src_release",
        relation=ProvenanceRelation.DERIVES_FROM,
        lineage_confidence=LineageConfidence.POSSIBLE,
    )
    clusters = build_lineage_clusters((release, blog), (edge,))
    assert independent_evidence_count(clusters) == 2
    blog_cluster = cluster_for_source(clusters, "src_blog")
    assert blog_cluster is not None
    assert any("Possible DERIVES_FROM" in item for item in blog_cluster.unresolved_ambiguities)


def test_circular_dependency_is_one_ambiguous_lineage() -> None:
    a, b, c = make_source("src_a"), make_source("src_b"), make_source("src_c")
    edges = (
        make_edge(
            "src_a",
            "src_b",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
        make_edge(
            "src_b",
            "src_c",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
        make_edge(
            "src_c",
            "src_a",
            relation=ProvenanceRelation.DERIVES_FROM,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
    )
    clusters = build_lineage_clusters((a, b, c), edges)
    assert len(clusters) == 1
    assert clusters[0].independent_roots == 1
    assert any("Circular dependency" in item for item in clusters[0].unresolved_ambiguities)


def test_unknown_endpoints_stay_visible_and_do_not_crash() -> None:
    known = make_source("src_known")
    edge = make_edge(
        "src_known",
        "src_not_normalized",
        relation=ProvenanceRelation.DERIVES_FROM,
        lineage_confidence=LineageConfidence.CONFIRMED,
    )
    clusters = build_lineage_clusters((known,), (edge,))
    assert len(clusters) == 1
    assert clusters[0].independent_roots == 1
    assert any("outside this normalization" in item for item in clusters[0].unresolved_ambiguities)


def test_lineage_clusters_are_deterministic() -> None:
    sources = (make_source("src_a"), make_source("src_b"))
    edges = (
        make_edge(
            "src_a",
            "src_b",
            relation=ProvenanceRelation.VERSION_OF,
            lineage_confidence=LineageConfidence.CONFIRMED,
        ),
    )
    first = build_lineage_clusters(sources, edges)
    second = build_lineage_clusters(tuple(reversed(sources)), tuple(reversed(edges)))
    assert first == second
